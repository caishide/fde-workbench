"""项目本体绑定服务（V3.3 WP4 段 1）。

职责：绑定 CRUD + 升级留痕状态机 + 与 ontology-service 的一致性校验
（pinned_version_id 必须是 runtime 上真实存在的已发布版本，I5——draft 不可
被生产 Agent/Workflow 使用）。runtime 不可达 → 拒绝写（契约 §3：降级不降
红线，绑定是交付控制面写操作）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask import current_app
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.integrations.models import OntologyBindingUpgrade, ProjectOntologyBinding
from fde_api.integrations.ontology_client import (
    OntologyClient,
    OntologyClientError,
    OntologyUnavailable,
)
from fde_api.workbench.models import Project


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


def _verify_version_published(
    client: OntologyClient, *, actor: User, ontology_id: str, version_id: str
) -> dict[str, Any]:
    """I5：绑定仅指发布版本。404=版本不存在或不可见 → 拒绝绑定。"""
    body = client.get_version_snapshot(
        actor_id=str(actor.id), org_id="", project_id="", ontology_id=ontology_id, version_id=version_id
    )
    status = body.pop("_status", 500)
    if status != 200:
        raise BindingError(
            "pinned_version_id is not a published version on the runtime (I5)",
            status=400,
            code="version_not_published",
        )
    return body


def list_bindings(*, actor: User, project_id: str) -> list[dict[str, Any]]:
    session = db.session()
    bindings = session.scalars(
        select(ProjectOntologyBinding)
        .where(ProjectOntologyBinding.project_id == project_id)
        .order_by(ProjectOntologyBinding.created_at)
    ).all()
    return [b.snapshot() for b in bindings]


def create_binding(*, actor: User, project_id: str, input: dict[str, Any]) -> dict[str, Any]:
    ontology_id = str(input.get("ontology_id", "")).strip()
    version_id = str(input.get("pinned_version_id", "")).strip()
    if not ontology_id or not version_id:
        raise BindingError("ontology_id and pinned_version_id are required", code="invalid_request")
    session = db.session()
    try:
        with session.begin():
            project = session.get(Project, project_id)
            if project is None:
                raise BindingError("project not found", status=404, code="not_found")
            client = client_from_settings()
            try:
                _verify_version_published(client, actor=actor, ontology_id=ontology_id, version_id=version_id)
            except (OntologyUnavailable, OntologyClientError) as exc:
                # 契约 §3：写操作降级=拒绝（不降红线——绑定必须可验证）
                raise BindingError(
                    f"ontology runtime unavailable: {exc}", status=503, code="ontology_unavailable"
                ) from exc
            dup = session.scalars(
                select(ProjectOntologyBinding).where(
                    ProjectOntologyBinding.project_id == project_id,
                    ProjectOntologyBinding.ontology_id == ontology_id,
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
                pinned_version=str(input.get("pinned_version", "")),
                binding_role=str(input.get("binding_role", "primary")),
                status="active",
                bound_by_user_id=str(actor.id),
            )
            session.add(binding)
            session.flush()
            return binding.snapshot()
    except BindingError:
        raise
    except Exception as exc:
        raise BindingError(f"binding failed: {exc}") from exc


def propose_upgrade(*, actor: User, project_id: str, binding_id: str, input: dict[str, Any]) -> dict[str, Any]:
    to_version_id = str(input.get("to_version_id", "")).strip()
    if not to_version_id:
        raise BindingError("to_version_id is required", code="invalid_request")
    session = db.session()
    try:
        with session.begin():
            binding = session.get(ProjectOntologyBinding, binding_id)
            if binding is None or binding.project_id != project_id or binding.status != "active":
                raise BindingError("binding not found", status=404, code="not_found")
            if to_version_id == binding.pinned_version_id:
                raise BindingError("upgrade target equals current pin", code="invalid_request")
            client = client_from_settings()
            try:
                _verify_version_published(
                    client, actor=actor, ontology_id=binding.ontology_id, version_id=to_version_id
                )
            except (OntologyUnavailable, OntologyClientError) as exc:
                raise BindingError(
                    f"ontology runtime unavailable: {exc}", status=503, code="ontology_unavailable"
                ) from exc
            pending = session.scalars(
                select(OntologyBindingUpgrade).where(
                    OntologyBindingUpgrade.binding_id == binding_id,
                    OntologyBindingUpgrade.status == "proposed",
                )
            ).first()
            if pending is not None:
                raise BindingError("an upgrade proposal is already pending", status=409, code="upgrade_pending")
            upgrade = OntologyBindingUpgrade(
                binding_id=binding_id,
                from_version_id=binding.pinned_version_id,
                to_version_id=to_version_id,
                to_version=str(input.get("to_version", "")),
                diff_summary=str(input.get("diff_summary", "")),
                source_change_set_id=input.get("source_change_set_id"),
                status="proposed",
                proposed_by_user_id=str(actor.id),
            )
            session.add(upgrade)
            session.flush()
            return {
                "id": upgrade.id,
                "binding_id": upgrade.binding_id,
                "from_version_id": upgrade.from_version_id,
                "to_version_id": upgrade.to_version_id,
                "status": upgrade.status,
            }
    except BindingError:
        raise
    except Exception as exc:
        raise BindingError(f"upgrade proposal failed: {exc}") from exc


def approve_upgrade(*, actor: User, project_id: str, binding_id: str, upgrade_id: str, decision: str) -> dict[str, Any]:
    if decision not in ("approved", "rejected"):
        raise BindingError("decision must be approved|rejected", code="invalid_request")
    session = db.session()
    try:
        with session.begin():
            binding = session.get(ProjectOntologyBinding, binding_id)
            if binding is None or binding.project_id != project_id or binding.status != "active":
                raise BindingError("binding not found", status=404, code="not_found")
            upgrade = session.get(OntologyBindingUpgrade, upgrade_id)
            if upgrade is None or upgrade.binding_id != binding_id or upgrade.status != "proposed":
                raise BindingError("upgrade proposal not found", status=404, code="not_found")
            if upgrade.proposed_by_user_id == str(actor.id):
                raise BindingError(
                    "proposer cannot approve own upgrade (I4)", status=403, code="self_approval"
                )
            upgrade.status = decision  # type: ignore[assignment]
            upgrade.approved_by_user_id = str(actor.id)
            upgrade.acted_at = datetime.now(UTC)
            if decision == "approved":
                # retire 旧行不删行（§5.2 保留历史绑定），新 pin 落 active 行
                binding.status = "retired"
                binding.version += 1
                successor = ProjectOntologyBinding(
                    project_id=project_id,
                    ontology_id=binding.ontology_id,
                    pinned_version_id=upgrade.to_version_id,
                    pinned_version=upgrade.to_version,
                    binding_role=binding.binding_role,
                    status="active",
                    bound_by_user_id=str(actor.id),
                    approved_by_user_id=str(actor.id),
                )
                session.add(successor)
                session.flush()
                result: dict[str, Any] = successor.snapshot()
            else:
                result = {"id": upgrade.id, "status": "rejected"}
            return result
    except BindingError:
        raise
    except Exception as exc:
        raise BindingError(f"upgrade approval failed: {exc}") from exc
