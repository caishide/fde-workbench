"""项目本体绑定服务（V3.3 WP4 段 1）。

职责：绑定 CRUD + 升级留痕状态机 + 与 ontology-service 的一致性校验
（pinned_version_id 必须是 runtime 上真实存在的已发布版本，I5——draft 不可
被生产 Agent/Workflow 使用）。runtime 不可达 → 拒绝写（契约 §3：降级不降
红线，绑定是交付控制面写操作）。

评审加固（Fde-Ontology docs/v3.3/m2/02-code-review-workbench-2026-11-13.md）：
- W-C：全部端点项目访问控制（project_access.can_view；不存在/无权 → 404，
  S-01 不泄露存在性）；
- W-B/D10：I5 调用发 FDE_ONTOLOGY_ORG_ID（配置）+ 真实 project_id；
  approve 时对目标版本**再次** I5 复核（propose→approve 间版本可能下架；
  兼修"审批不触 runtime"的写不降级违约）；
- W-D：错误分型契约——runtime 404 → 409 version_not_published（spec：draft
  409）、401/403 → 502 runtime_auth（配置错误不伪装领域错误）；
- W-A/E：单活跃绑定（active_marker uq）+ upgrade_pending 生命周期 + retire 后
  可重绑 + 并发行锁 + 不泄内部异常文本。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.integrations.models import (
    ACTIVE_MARKER,
    OntologyBindingUpgrade,
    ProjectOntologyBinding,
)
from fde_api.integrations.ontology_client import (
    OntologyAuthError,
    OntologyClient,
    OntologyClientError,
    OntologyConflict,
    OntologyUnavailable,
)
from fde_api.projects.permissions import project_access
from fde_api.workbench.models import Project

BINDING_ROLES = ("primary",)


class BindingError(ValueError):
    """带 HTTP 状态的绑定业务错误。"""

    def __init__(self, message: str, status: int = 400, code: str = "binding_error") -> None:
        self.message = message
        self.status = status
        self.code = code
        super().__init__(message)


def client_from_settings() -> OntologyClient:
    settings = current_app.config["SETTINGS"]
    assert settings.ontology_api_key is not None
    assert settings.ontology_signing_key is not None
    return OntologyClient(
        settings.ontology_base_url,
        settings.ontology_api_key.get_secret_value(),
        settings.ontology_signing_key.get_secret_value(),
        timeout=settings.ontology_timeout_seconds,
    )


def _runtime_org() -> str:
    """D10：段 1 I5 调用的 org 上下文（validator 已保证 enabled 时非空）。"""
    settings = current_app.config["SETTINGS"]
    return settings.ontology_org_id


def _verified_snapshot(
    client: OntologyClient, *, actor: User, ontology_id: str, version_id: str, project_id: str
) -> dict[str, Any]:
    """I5：绑定仅指发布版本（draft 409；评审 W-D/W-B/D10）。"""
    try:
        body = client.get_version_snapshot(
            actor_id=str(actor.id),
            org_id=_runtime_org(),
            project_id=project_id,
            ontology_id=ontology_id,
            version_id=version_id,
        )
    except OntologyUnavailable as exc:
        raise BindingError(
            f"ontology runtime unreachable: {exc}", status=503, code="ontology_unavailable"
        ) from exc
    except OntologyAuthError as exc:
        # 配置错误（key 失效//org 错）必须显性暴露，不得伪装成领域错误
        raise BindingError(
            "ontology runtime rejected credentials (check FDE_ONTOLOGY_* config)",
            status=502,
            code="runtime_auth",
        ) from exc
    except OntologyConflict as exc:
        raise BindingError(
            "ontology runtime conflict during I5 verification",
            status=502,
            code="runtime_conflict",
        ) from exc
    except OntologyClientError as exc:
        raise BindingError(
            f"ontology runtime failure: {exc}", status=502, code="runtime_error"
        ) from exc
    status = body.pop("_status", 500)
    if status != 200:
        raise BindingError(
            "pinned_version_id is not a published version on the runtime (I5)",
            status=409,
            code="version_not_published",
        )
    return body


def _load_accessible_project(session: Any, actor: User, project_id: str) -> Project:
    """W-C/S-01：项目不存在或无 view 权 → 统一 404（不泄露存在性）。"""
    project = session.get(Project, project_id)
    if project is None or not project_access(actor, project).can_view:
        raise BindingError("project not found", status=404, code="not_found")
    return project


def _pending_upgrades(session: Any, binding_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(OntologyBindingUpgrade)
        .where(OntologyBindingUpgrade.binding_id == binding_id)
        .order_by(OntologyBindingUpgrade.created_at)
    ).all()
    return [u.snapshot() for u in rows]


def list_bindings(*, actor: User, project_id: str) -> list[dict[str, Any]]:
    session = db.session()
    _load_accessible_project(session, actor, project_id)
    bindings = session.scalars(
        select(ProjectOntologyBinding)
        .where(ProjectOntologyBinding.project_id == project_id)
        .order_by(ProjectOntologyBinding.created_at)
    ).all()
    out = []
    for b in bindings:
        item = b.snapshot()
        item["pending_upgrades"] = _pending_upgrades(session, b.id)  # 审批人发现入口（评审）
        out.append(item)
    return out


def create_binding(*, actor: User, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ontology_id = str(payload.get("ontology_id", "")).strip()
    version_id = str(payload.get("pinned_version_id", "")).strip()
    if not ontology_id or not version_id:
        raise BindingError("ontology_id and pinned_version_id are required", code="invalid_request")
    binding_role = str(payload.get("binding_role", "primary"))
    if binding_role not in BINDING_ROLES:
        raise BindingError(
            f"binding_role must be one of {BINDING_ROLES}", code="invalid_request"
        )
    session = db.session()
    try:
        with session.begin():
            _load_accessible_project(session, actor, project_id)
            client = client_from_settings()
            verified = _verified_snapshot(
                client, actor=actor, ontology_id=ontology_id, version_id=version_id,
                project_id=project_id,
            )
            # 重绑允许：仅 active/upgrade_pending 占位（retired 可重绑，评审 W-A）
            dup = session.scalars(
                select(ProjectOntologyBinding).where(
                    ProjectOntologyBinding.project_id == project_id,
                    ProjectOntologyBinding.ontology_id == ontology_id,
                    ProjectOntologyBinding.active_marker.is_not(None),
                )
            ).first()
            if dup is not None:
                raise BindingError(
                    "project already bound to this ontology", status=409, code="binding_exists"
                )
            binding = ProjectOntologyBinding(
                project_id=project_id,
                ontology_id=ontology_id,
                pinned_version_id=version_id,
                # 以 runtime 核实响应回填版本标签（不信任客户端自报，评审 W-D）
                pinned_version=str(verified.get("version", ""))[:32],
                binding_role=binding_role,
                status="active",
                active_marker=ACTIVE_MARKER,
                bound_by_user_id=str(actor.id),
            )
            session.add(binding)
            session.flush()
            return binding.snapshot()
    except BindingError:
        raise
    except IntegrityError as exc:
        raise BindingError(
            "project already bound to this ontology", status=409, code="binding_exists"
        ) from exc
    except Exception as exc:
        current_app.logger.exception("create_binding failed")
        raise BindingError("binding failed", status=500, code="binding_failed") from exc


def propose_upgrade(
    *, actor: User, project_id: str, binding_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    to_version_id = str(payload.get("to_version_id", "")).strip()
    if not to_version_id:
        raise BindingError("to_version_id is required", code="invalid_request")
    # §5.2："版本升级必须有差异审查"——差异材料与变更集指针缺一不可（评审 W-D）
    diff_summary = str(payload.get("diff_summary", "")).strip()
    source_change_set_id = str(payload.get("source_change_set_id", "")).strip()
    if not diff_summary or not source_change_set_id:
        raise BindingError(
            "diff_summary and source_change_set_id are required for upgrade review (§5.2)",
            code="invalid_request",
        )
    session = db.session()
    try:
        with session.begin():
            _load_accessible_project(session, actor, project_id)
            binding = session.get(ProjectOntologyBinding, binding_id)
            if (
                binding is None
                or binding.project_id != project_id
                or binding.status not in ("active",)
            ):
                raise BindingError("binding not found", status=404, code="not_found")
            # 行锁串行化并发提案（评审 W-A：双提案竞态）
            binding = session.scalars(
                select(ProjectOntologyBinding)
                .where(ProjectOntologyBinding.id == binding_id)
                .with_for_update()
            ).first()
            assert binding is not None  # 上一步已验存在
            if to_version_id == binding.pinned_version_id:
                raise BindingError("upgrade target equals current pin", code="invalid_request")
            client = client_from_settings()
            verified = _verified_snapshot(
                client, actor=actor, ontology_id=binding.ontology_id,
                version_id=to_version_id, project_id=project_id,
            )
            pending = session.scalars(
                select(OntologyBindingUpgrade).where(
                    OntologyBindingUpgrade.binding_id == binding_id,
                    OntologyBindingUpgrade.status == "proposed",
                )
            ).first()
            if pending is not None:
                raise BindingError(
                    "an upgrade proposal is already pending", status=409, code="upgrade_pending"
                )
            upgrade = OntologyBindingUpgrade(
                binding_id=binding_id,
                from_version_id=binding.pinned_version_id,
                to_version_id=to_version_id,
                to_version=str(verified.get("version", ""))[:32],
                diff_summary=diff_summary,
                source_change_set_id=source_change_set_id,
                status="proposed",
                proposed_by_user_id=str(actor.id),
            )
            session.add(upgrade)
            binding.status = "upgrade_pending"  # data-model §3 状态位
            binding.version += 1
            session.flush()
            return upgrade.snapshot()
    except BindingError:
        raise
    except IntegrityError as exc:
        raise BindingError(
            "an upgrade proposal is already pending", status=409, code="upgrade_pending"
        ) from exc
    except Exception as exc:
        current_app.logger.exception("propose_upgrade failed")
        raise BindingError("upgrade proposal failed", status=500, code="upgrade_proposal_failed") from exc


def approve_upgrade(
    *, actor: User, project_id: str, binding_id: str, upgrade_id: str, decision: str
) -> dict[str, Any]:
    if decision not in ("approved", "rejected"):
        raise BindingError("decision must be approved|rejected", code="invalid_request")
    session = db.session()
    try:
        with session.begin():
            _load_accessible_project(session, actor, project_id)
            # 行锁串行化：propose/approve/approve 竞态统一收敛（评审 W-A/E）
            binding = session.scalars(
                select(ProjectOntologyBinding)
                .where(ProjectOntologyBinding.id == binding_id)
                .with_for_update()
            ).first()
            if (
                binding is None
                or binding.project_id != project_id
                or binding.status != "upgrade_pending"
            ):
                raise BindingError("binding not found", status=404, code="not_found")
            upgrade = session.scalars(
                select(OntologyBindingUpgrade)
                .where(OntologyBindingUpgrade.id == upgrade_id)
                .with_for_update()
            ).first()
            if upgrade is None or upgrade.binding_id != binding_id:
                raise BindingError("upgrade proposal not found", status=404, code="not_found")
            if upgrade.status != "proposed":
                raise BindingError(
                    "upgrade proposal already acted", status=409, code="upgrade_already_acted"
                )
            if upgrade.proposed_by_user_id == str(actor.id):
                raise BindingError(
                    "proposer cannot approve own upgrade (I4)", status=403, code="self_approval"
                )
            if decision == "approved":
                # approve 时点二次 I5（写不降级 + propose→approve 间版本可能下架）
                client = client_from_settings()
                verified = _verified_snapshot(
                    client, actor=actor, ontology_id=binding.ontology_id,
                    version_id=upgrade.to_version_id, project_id=project_id,
                )
                # retire 旧行不删行（§5.2 保留历史绑定），新 pin 落 active 行
                binding.status = "retired"
                binding.active_marker = None
                binding.version += 1
                successor = ProjectOntologyBinding(
                    project_id=project_id,
                    ontology_id=binding.ontology_id,
                    pinned_version_id=upgrade.to_version_id,
                    pinned_version=str(verified.get("version", ""))[:32],
                    binding_role=binding.binding_role,
                    status="active",
                    active_marker=ACTIVE_MARKER,
                    bound_by_user_id=str(actor.id),
                    approved_by_user_id=str(actor.id),
                )
                session.add(successor)
            else:
                # rejected → 绑定恢复 active（upgrade_pending 是暂挂态，评审 W-A）
                binding.status = "active"
                binding.active_marker = ACTIVE_MARKER
                binding.version += 1
            upgrade.status = decision
            upgrade.approved_by_user_id = str(actor.id)
            upgrade.acted_at = datetime.now(UTC)
            session.flush()
            return successor.snapshot() if decision == "approved" else upgrade.snapshot()
    except BindingError:
        raise
    except IntegrityError as exc:
        current_app.logger.exception("approve_upgrade integrity failure")
        raise BindingError(
            "upgrade approval conflict", status=409, code="upgrade_conflict"
        ) from exc
    except Exception as exc:
        current_app.logger.exception("approve_upgrade failed")
        raise BindingError("upgrade approval failed", status=500, code="upgrade_approval_failed") from exc
