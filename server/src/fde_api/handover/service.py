"""handover 服务：结项交付包生命周期（goal-tb tb4）。

权限（D11 草案 §二原文）：seal/unseal/编辑=项目负责人+admin（can_manage）；
**deliver（登记对外交付）=admin**；查看=项目成员（can_view）。
审计：handover_package_sealed / _unsealed / _delivered OperationEvent
（target=项目，changes 只带 id 与元数据，不复制产物内容）。
明确不做（草案原文）：自动打包 zip、对外下载链接签名、与合同条款联动。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.extensions import db
from fde_api.projects.events import record_event
from fde_api.projects.permissions import project_access, visible_project_ids
from fde_api.handover.models import ITEM_TYPES, HandoverPackage, HandoverPackageItem
from fde_api.ux_write_gate import PAUSED_CODE, PAUSED_MESSAGE, writes_paused
from fde_api.workbench.models import Gate, Project, User

MAX_LABEL_CHARS = 200
MAX_ITEMS = 200
MAX_DISPLAY_NAME = 255
_LIST_LIMIT_DEFAULT = 50
_LIST_LIMIT_MAX = 200

# B1 结项资产闸（FDU 对照拍板 E-1，2026-11-28）：登记 payload 携带「可复用
# 资产包」三件指针（件 1 复盘／件 2 交接／件 3 可复用方法——S13 既产物
# retrospective/handoff/patterns 取指针，键集即 sop_nodes.json S13 artifact
# 字面闭集；件 4 工位清单件走交付包发布快照新字段，不在本闸）。四件套字段
# 定义为我方独立设计，与外部材料零对照关系。红线：三件全是指针，原件留
# 项目工作目录；空包不放行（缺任一件即 422，宁可拒登不制造形式合规）。
ASSET_BUNDLE_KEYS = ("retrospective", "handoff", "patterns")
MAX_ASSET_URI_CHARS = 500  # 对齐 ProjectEvidence.source_uri 同款约定
# B9-a 结果合同回指：G4（试点签约门）证据清单项字面（seed 数据引用，
# server/seeds/gates.json G4 evidence_checklist）。
RESULT_CONTRACT_LABEL = "结果合同页"


class HandoverServiceError(Exception):
    def __init__(self, code: str, message: str, status: int, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.detail = detail or {}


def _error(code: str, message: str, status: int = 400, detail: dict[str, Any] | None = None) -> HandoverServiceError:
    return HandoverServiceError(code, message, status, detail)


def _session() -> Any:
    return db.session()


def _load_project_for(session: Any, actor: User, project_id: str, *, manage: bool) -> Project:
    project = session.get(Project, project_id)
    access = project_access(actor, project) if project else None
    if project is None or access is None:
        raise _error("project_not_found", "项目不存在或无权访问。", 404)
    if manage and not access.can_manage:
        raise _error("project_forbidden", "需要项目管理权限。", 403)
    if not manage and not access.can_view:
        raise _error("project_forbidden", "无权访问该项目。", 403)
    return project


def _load_package_for(session: Any, actor: User, package_id: str, *, manage: bool) -> tuple[HandoverPackage, Project]:
    package = session.get(HandoverPackage, package_id)
    if package is None:
        raise _error("package_not_found", "交付包不存在。", 404)
    project = _load_project_for(session, actor, package.project_id, manage=manage)
    return package, project


def _lock_package(session: Any, package_id: str, *, read: bool = False) -> HandoverPackage:
    # 先授权再锁；等待另一事务后必须覆盖 identity map 里的旧状态。
    package = session.scalar(
        select(HandoverPackage).where(HandoverPackage.id == package_id)
        .with_for_update(read=read).execution_options(populate_existing=True)
    )
    if package is None:
        raise _error("package_not_found", "交付包不存在。", 404)
    return package


def _require_admin(actor: User) -> None:
    if actor.role != "admin":
        raise _error("admin_required", "交付登记（delivered）仅管理员可执行（D11 草案权限）。", 403)


# ---------------------------------------------------------------------------
# 快照与清单


def _snapshot_item(artifact: AgentArtifact, display_name: str) -> dict[str, Any]:
    return {
        "item_type": "artifact",
        "artifact_id": artifact.id,
        "run_id": artifact.run_id,
        "kind": artifact.kind,
        "display_name": display_name[:MAX_DISPLAY_NAME],
        "storage_ref": artifact.storage_ref,
        "sha256": artifact.sha256,
    }


def _snapshot_document_version(version: Any, display_name: str) -> dict[str, Any]:
    return {
        "item_type": "document",
        "document_version_id": version.id,
        "run_id": None,
        "kind": "document",
        "display_name": display_name[:MAX_DISPLAY_NAME],
        "storage_ref": f"document-version:{version.id}",
        "sha256": version.sha256,
    }


def _snapshot_file_version(version: Any, display_name: str) -> dict[str, Any]:
    return {
        "item_type": "file",
        "file_version_id": version.id,
        "run_id": None,
        "kind": "file",
        "display_name": display_name[:MAX_DISPLAY_NAME],
        "storage_ref": version.storage_key,
        "sha256": version.sha256,
    }


def _require_display_name(raw: dict[str, Any], default: str) -> str:
    display_name = raw.get("display_name")
    if display_name is None:
        display_name = default
    if not isinstance(display_name, str) or not display_name.strip():
        raise _error("invalid_items", "display_name 必须是非空字符串。", 422)
    return display_name.strip()


def _validate_item_payloads(session: Any, project_id: str, raw_items: Any) -> list[dict[str, Any]]:
    """draft 清单编辑的形状与归属校验：快照取 live 产物行的当前指纹。

    item_type 三态（缺省 artifact 向后兼容）：artifact→AgentArtifact（须已人工
    复核）；document→ProjectDocumentVersion（须 confirmed 且带 sha256）；
    file→ProjectFileVersion（须 available 且带 sha256）。document/file 懒导入
    documents/files 模型（跨域边界，架构纯净度钉）。
    """
    if not isinstance(raw_items, list) or not raw_items:
        raise _error("invalid_items", "items 必须是非空数组。", 422)
    if len(raw_items) > MAX_ITEMS:
        raise _error("invalid_items", f"items 上限 {MAX_ITEMS} 行。", 422, {"limit": MAX_ITEMS})
    seen: set[tuple[str, str]] = set()
    snapshots: list[dict[str, Any]] = []
    pointer_key_by_type = {
        "artifact": "artifact_id",
        "document": "document_version_id",
        "file": "file_version_id",
    }
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise _error("invalid_items", "items 元素必须是对象。", 422)
        present = {
            key: raw.get(key)
            for key in pointer_key_by_type.values()
            if isinstance(raw.get(key), str) and raw.get(key)
        }
        given_type = raw.get("item_type")
        if given_type is None:
            # 指针键自反推：恰带一个指针键即按键定型（向后兼容裸 artifact_id 形态）
            if len(present) != 1:
                raise _error(
                    "invalid_items",
                    "items[] 须恰带一个指针键（artifact_id/document_version_id/file_version_id）。",
                    422,
                )
            item_type = next(key for key in ITEM_TYPES if pointer_key_by_type[key] in present)
        else:
            if given_type not in ITEM_TYPES:
                raise _error(
                    "invalid_items",
                    f"items[].item_type 须为 {'/'.join(ITEM_TYPES)}。",
                    422,
                )
            item_type = given_type
            if pointer_key_by_type[item_type] not in present:
                raise _error(
                    "invalid_items",
                    f"items[].{pointer_key_by_type[item_type]} 必填。",
                    422,
                )
        if item_type == "artifact":
            artifact_id = raw.get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id:
                raise _error("invalid_items", "items[].artifact_id 必填。", 422)
            if (item_type, artifact_id) in seen:
                raise _error("invalid_items", "同一产物在清单内重复。", 422)
            seen.add((item_type, artifact_id))
            artifact = session.get(AgentArtifact, artifact_id)
            if artifact is None:
                raise _error("artifact_not_found", f"产物不存在：{artifact_id}", 404)
            run = session.get(AgentRun, artifact.run_id)
            if run is None or run.project_id != project_id:
                raise _error("artifact_foreign_project", "产物不属于该项目（跨项目封包拒绝）。", 409)
            display_name = _require_display_name(
                raw, artifact.storage_ref.rsplit("/", 1)[-1]
            )
            snapshots.append(_snapshot_item(artifact, display_name))
        elif item_type == "document":
            document_version_id = raw.get("document_version_id")
            if not isinstance(document_version_id, str) or not document_version_id:
                raise _error("invalid_items", "items[].document_version_id 必填。", 422)
            if (item_type, document_version_id) in seen:
                raise _error("invalid_items", "同一文档版本在清单内重复。", 422)
            seen.add((item_type, document_version_id))
            version, document = _load_packable_document_version(session, project_id, document_version_id)
            display_name = _require_display_name(
                raw, f"{document.business_code} v{version.version_number}"
            )
            snapshots.append(_snapshot_document_version(version, display_name))
        else:
            file_version_id = raw.get("file_version_id")
            if not isinstance(file_version_id, str) or not file_version_id:
                raise _error("invalid_items", "items[].file_version_id 必填。", 422)
            if (item_type, file_version_id) in seen:
                raise _error("invalid_items", "同一文件版本在清单内重复。", 422)
            seen.add((item_type, file_version_id))
            version = _load_packable_file_version(session, project_id, file_version_id)
            display_name = _require_display_name(raw, version.original_filename)
            snapshots.append(_snapshot_file_version(version, display_name))
    return snapshots


def _load_packable_document_version(session: Any, project_id: str, version_id: str) -> tuple[Any, Any]:
    """document 入包前置：存在 / 本项目 / confirmed / 带 sha256（返回版本与文档行）。

    display_name 默认值（business_code + 版本号，代号化安全）由调用方按本函数
    返回值计算——先过状态闸再算展示名，错误码优先。
    """
    from fde_api.documents.models import ProjectDocument, ProjectDocumentVersion

    version = session.get(ProjectDocumentVersion, version_id)
    if version is None:
        raise _error("document_not_found", f"文档版本不存在：{version_id}", 404)
    document = session.get(ProjectDocument, version.document_id)
    if document is None or document.project_id != project_id:
        raise _error("document_foreign_project", "文档不属于该项目（跨项目封包拒绝）。", 409)
    if version.status != "confirmed":
        raise _error(
            "document_not_confirmed",
            "封包仅接受已确认（confirmed）的文档版本（与产物 reviewed 闸同构）。",
            409,
            {"document_version_id": version.id, "status": version.status},
        )
    if not version.sha256:
        raise _error(
            "document_fingerprint_missing",
            "该文档版本缺少 sha256 指纹（DOCX 未生成或未落指纹），不可封包。",
            422,
            {"document_version_id": version.id},
        )
    return version, document


def _load_packable_file_version(session: Any, project_id: str, version_id: str) -> Any:
    """file 入包前置：存在 / 本项目 / available / 带 sha256。"""
    from fde_api.files.models import ProjectFile, ProjectFileVersion

    version = session.get(ProjectFileVersion, version_id)
    if version is None:
        raise _error("file_not_found", f"文件版本不存在：{version_id}", 404)
    project_file = session.get(ProjectFile, version.file_id)
    if project_file is None or project_file.project_id != project_id:
        raise _error("file_foreign_project", "文件不属于该项目（跨项目封包拒绝）。", 409)
    if version.status != "available":
        raise _error(
            "file_not_available",
            "封包仅接受可用（available）状态的文件版本（与产物 reviewed 闸同构）。",
            409,
            {"file_version_id": version.id, "status": version.status},
        )
    if not version.sha256:
        raise _error(
            "file_fingerprint_missing",
            "该文件版本缺少 sha256 指纹（扫描处理未完成），不可封包。",
            422,
            {"file_version_id": version.id},
        )
    return version


def _item_pointer(row: dict[str, Any]) -> str:
    """manifest 行指针稳定串（排序键；三类型统一，入参为投影 dict）。"""
    if row["item_type"] == "document":
        return row["document_version_id"] or ""
    if row["item_type"] == "file":
        return row["file_version_id"] or ""
    return row["artifact_id"] or ""


def _canonical_manifest(package: HandoverPackage, items: list[HandoverPackageItem]) -> dict[str, Any]:
    return {
        "package_id": package.id,
        "label": package.label,
        "sealed_at": package.sealed_at.isoformat() if package.sealed_at else None,
        "items": sorted(
            (
                {
                    "item_type": item.item_type,
                    "artifact_id": item.artifact_id,
                    "document_version_id": item.document_version_id,
                    "file_version_id": item.file_version_id,
                    "run_id": item.run_id,
                    "kind": item.kind,
                    "display_name": item.display_name,
                    "storage_ref": item.storage_ref,
                    "sha256": item.sha256,
                }
                for item in items
            ),
            key=_item_pointer,
        ),
    }


def _manifest_digest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replace_items(session: Any, package: HandoverPackage, snapshots: list[dict[str, Any]]) -> None:
    session.query(HandoverPackageItem).filter(HandoverPackageItem.package_id == package.id).delete()
    for snapshot in snapshots:
        session.add(HandoverPackageItem(package_id=package.id, **snapshot))
    session.flush()  # 序列化前落库（session autoflush 可能被配置关闭）


# ---------------------------------------------------------------------------
# 序列化


def _serialize_package(row: HandoverPackage, *, detail: bool, session: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "label": row.label,
        "status": row.status,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat(),
        "sealed_by_user_id": row.sealed_by_user_id,
        "sealed_at": row.sealed_at.isoformat() if row.sealed_at else None,
        "unsealed_count": row.unsealed_count,
        "delivered_by_user_id": row.delivered_by_user_id,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
    }
    if row.status != "draft":
        data["manifest_sha256"] = row.manifest_sha256
    if detail:
        data["write_preconditions"] = "v1"
        items = list(session_items(session, row.id))
        data["items"] = [
            {
                "id": item.id,
                "item_type": item.item_type,
                "artifact_id": item.artifact_id,
                "document_version_id": item.document_version_id,
                "file_version_id": item.file_version_id,
                "run_id": item.run_id,
                "kind": item.kind,
                "display_name": item.display_name,
                "storage_ref": item.storage_ref,
                "sha256": item.sha256,
            }
            for item in items
        ]
        if row.status != "draft":
            data["manifest"] = _canonical_manifest(row, items)
    return data


def session_items(session: Any, package_id: str) -> Any:
    """清单行查询（**必须传当前事务 session**——db.session() 每次新建会话，
    新会话看不到事务内未提交行）。"""
    return session.scalars(
        select(HandoverPackageItem)
        .where(HandoverPackageItem.package_id == package_id)
        .order_by(HandoverPackageItem.display_name, HandoverPackageItem.id)
    )


# ---------------------------------------------------------------------------
# 生命周期


def create_package(*, actor: User, payload: dict[str, Any]) -> dict[str, Any]:
    session = _session()
    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise _error("invalid_request", "project_id 必填。", 400)
    label = payload.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > MAX_LABEL_CHARS):
        raise _error("invalid_request", f"label 须为 ≤{MAX_LABEL_CHARS} 字符的字符串。", 422)
    with session.begin():
        project = _load_project_for(session, actor, project_id, manage=True)
        snapshots = _validate_item_payloads(session, project.id, payload.get("items"))
        package = HandoverPackage(
            project_id=project.id,
            created_by_user_id=actor.id,
            label=label.strip() if isinstance(label, str) and label.strip() else None,
            status="draft",
        )
        session.add(package)
        session.flush()
        _replace_items(session, package, snapshots)
        record_event(session, actor, "handover_package_created", project, {
            "package_id": package.id,
            "item_count": len(snapshots),
        })
        return _serialize_package(package, detail=True, session=session)


def list_packages(*, actor: User, project_id: str | None, limit: int, offset: int) -> dict[str, Any]:
    session = _session()
    rows_query = select(HandoverPackage).order_by(HandoverPackage.created_at.desc(), HandoverPackage.id)
    if project_id is not None:
        project = _load_project_for(session, actor, project_id, manage=False)
        rows_query = rows_query.where(HandoverPackage.project_id == project.id)
    else:
        visible = visible_project_ids(session, actor)
        if not visible:
            return {"items": [], "total": None, "limit": limit, "offset": offset, "truncated": False}
        rows_query = rows_query.where(HandoverPackage.project_id.in_(visible))
    rows = list(session.scalars(rows_query.offset(offset).limit(limit + 1)))
    truncated = len(rows) > limit
    return {
        "items": [_serialize_package(row, detail=False, session=session) for row in rows[:limit]],
        "total": None,
        "limit": limit,
        "offset": offset,
        "truncated": truncated,
    }


def get_package(*, actor: User, package_id: str) -> dict[str, Any]:
    session = _session()
    with session.begin():
        _load_package_for(session, actor, package_id, manage=False)
        # 包头与清单分两条 SELECT；共享锁确保详情不会混合两个批次。
        package = _lock_package(session, package_id, read=True)
        return _serialize_package(package, detail=True, session=session)


def update_package(*, actor: User, package_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _session()
    with session.begin():
        _load_package_for(session, actor, package_id, manage=True)
        package = _lock_package(session, package_id)
        if package.status != "draft":
            raise _error("package_not_draft", "只有草稿包可编辑（封存后清单冻结；解封后回草稿再编辑）。", 409)
        if "label" in payload:
            label = payload.get("label")
            if label is None:
                package.label = None
            elif isinstance(label, str) and label.strip() and len(label) <= MAX_LABEL_CHARS:
                package.label = label.strip()
            else:
                raise _error("invalid_request", f"label 须为 ≤{MAX_LABEL_CHARS} 字符的字符串。", 422)
        if "items" in payload:
            snapshots = _validate_item_payloads(session, package.project_id, payload.get("items"))
            _replace_items(session, package, snapshots)
        return _serialize_package(package, detail=True, session=session)


def _seal_check_artifact(session: Any, package: HandoverPackage, item: HandoverPackageItem) -> None:
    artifact = session.get(AgentArtifact, item.artifact_id) if item.artifact_id else None
    if artifact is None:
        raise _error("artifact_missing", f"清单产物已不存在：{item.artifact_id}", 409)
    run = session.get(AgentRun, artifact.run_id)
    if run is None or run.project_id != package.project_id:
        raise _error("artifact_foreign_project", "产物不属于该项目（跨项目封包拒绝）。", 409)
    if not artifact.reviewed:
        raise _error(
            "artifact_not_reviewed",
            "清单含未人工复核的产物——封包仅接受已复核产物（与 D11 草案 status 闸同构）。",
            409,
            {"artifact_id": artifact.id},
        )
    if artifact.sha256 != item.sha256:
        raise _error(
            "fingerprint_drift",
            "清单快照指纹与产物现行指纹不一致。",
            409,
            {"artifact_id": artifact.id},
        )


def _seal_check_document_version(session: Any, package: HandoverPackage, item: HandoverPackageItem) -> None:
    from fde_api.documents.models import ProjectDocument, ProjectDocumentVersion

    version = session.get(ProjectDocumentVersion, item.document_version_id) if item.document_version_id else None
    if version is None:
        raise _error("document_missing", f"清单文档版本已不存在：{item.document_version_id}", 409)
    document = session.get(ProjectDocument, version.document_id)
    if document is None or document.project_id != package.project_id:
        raise _error("document_foreign_project", "文档不属于该项目（跨项目封包拒绝）。", 409)
    if version.status != "confirmed":
        raise _error(
            "document_not_confirmed",
            "清单含未确认的文档版本——封包仅接受 confirmed 文档（与产物 reviewed 闸同构）。",
            409,
            {"document_version_id": version.id, "status": version.status},
        )
    if version.sha256 != item.sha256:
        raise _error(
            "fingerprint_drift",
            "清单快照指纹与文档版本现行指纹不一致。",
            409,
            {"document_version_id": version.id},
        )


def _seal_check_file_version(session: Any, package: HandoverPackage, item: HandoverPackageItem) -> None:
    from fde_api.files.models import ProjectFile, ProjectFileVersion

    version = session.get(ProjectFileVersion, item.file_version_id) if item.file_version_id else None
    if version is None:
        raise _error("file_missing", f"清单文件版本已不存在：{item.file_version_id}", 409)
    project_file = session.get(ProjectFile, version.file_id)
    if project_file is None or project_file.project_id != package.project_id:
        raise _error("file_foreign_project", "文件不属于该项目（跨项目封包拒绝）。", 409)
    if version.status != "available":
        raise _error(
            "file_not_available",
            "清单含不可用的文件版本——封包仅接受 available 文件（与产物 reviewed 闸同构）。",
            409,
            {"file_version_id": version.id, "status": version.status},
        )
    if version.sha256 != item.sha256:
        raise _error(
            "fingerprint_drift",
            "清单快照指纹与文件版本现行指纹不一致。",
            409,
            {"file_version_id": version.id},
        )


def seal_package(*, actor: User, package_id: str) -> dict[str, Any]:
    """封存：冻结清单 + 逐项校验（存在/本项目/状态闸/指纹一致）+ manifest 规范化哈希。"""
    session = _session()
    with session.begin():
        _, project = _load_package_for(session, actor, package_id, manage=True)
        package = _lock_package(session, package_id)
        now = datetime.now(UTC)
        if package.status != "draft":
            raise _error("package_not_draft", "只有草稿包可封存。", 409)
        items = list(session_items(session, package.id))
        if not items:
            raise _error("empty_package", "空清单不可封存。", 422)
        for item in items:
            if item.item_type == "document":
                _seal_check_document_version(session, package, item)
            elif item.item_type == "file":
                _seal_check_file_version(session, package, item)
            else:
                _seal_check_artifact(session, package, item)
        # 先落封存态再算 manifest（sealed_at 必须在清单里，否则摘要与呈现不一致）
        package.status = "sealed"
        package.sealed_by_user_id = actor.id
        package.sealed_at = now
        manifest = _canonical_manifest(package, items)
        package.manifest_sha256 = _manifest_digest(manifest)
        record_event(session, actor, "handover_package_sealed", project, {
            "package_id": package.id,
            "item_count": len(items),
            "manifest_sha256": package.manifest_sha256,
        })
        return _serialize_package(package, detail=True, session=session)


def unseal_package(*, actor: User, package_id: str) -> dict[str, Any]:
    session = _session()
    with session.begin():
        _, project = _load_package_for(session, actor, package_id, manage=True)
        package = _lock_package(session, package_id)
        now = datetime.now(UTC)
        if package.status != "sealed":
            raise _error("package_not_sealed", "只有已封存包可解封（draft 无需解封；delivered 不可逆）。", 409)
        package.status = "draft"
        package.sealed_by_user_id = None
        package.sealed_at = None
        package.manifest_sha256 = None
        package.unsealed_count += 1
        package.unsealed_by_user_id = actor.id
        package.unsealed_at = now
        record_event(session, actor, "handover_package_unsealed", project, {
            "package_id": package.id,
            "unsealed_count": package.unsealed_count,
        })
        return _serialize_package(package, detail=True, session=session)


def deliver_package(
    *,
    actor: User,
    package_id: str,
    payload: Any,
    preconditions_required: bool = True,
    asset_bundle_gate_required: bool = True,
) -> dict[str, Any]:
    """交付登记（admin 专属）：只有用户确认的封存批次可以进入终态。

    B1 结项资产闸＋B9-a 结果合同回指（2026-11-28）：payload 须携带
    `asset_bundle` 三件指针与 `result_contract` 回指；兼容语义沿 ux-p0
    先例——只对完全省略键的旧请求按部署开关放行，携带即严格校验。
    """
    session = _session()
    with session.begin():
        _, project = _load_package_for(session, actor, package_id, manage=True)
        _require_admin(actor)
        package = _lock_package(session, package_id)
        if writes_paused():
            # 授权已通过才判暂停：未授权请求仍是原 403/404，不因暂停改变口径。
            raise _error(PAUSED_CODE, PAUSED_MESSAGE, 503)
        if package.status == "delivered":
            raise _error("already_delivered", "该包已登记交付（终态不可逆）。", 409)
        if package.status != "sealed":
            raise _error("package_not_sealed", "只有已封存包可登记交付。请重新读取交付包。", 409)
        skipped = _require_delivery_snapshot(package, payload, required=preconditions_required)
        asset_bundle, result_contract, skipped_bundle = _require_asset_bundle_and_result_contract(
            session, project, payload, required=asset_bundle_gate_required
        )
        package.status = "delivered"
        package.delivered_by_user_id = actor.id
        package.delivered_at = datetime.now(UTC)
        if skipped:
            # 兼容期放行省略条件的登记必须留痕，否则该终态与「确认过」不可区分。
            record_event(session, actor, "handover_precondition_skipped", project, {
                "package_id": package.id,
                "manifest_sha256": package.manifest_sha256,
                "unsealed_count": package.unsealed_count,
            })
        if skipped_bundle:
            # 兼容期放行省略资产闸的登记同样留痕（missing 列出放行了哪些键）。
            record_event(session, actor, "handover_asset_bundle_skipped", project, {
                "package_id": package.id,
                "missing": skipped_bundle,
            })
        record_event(session, actor, "handover_package_delivered", project, {
            "package_id": package.id,
            "manifest_sha256": package.manifest_sha256,
            "unsealed_count": package.unsealed_count,
            # B1/B9-a：结项出口留痕（指针，原件留项目工作目录）。兼容期省略
            # 时为 None——复盘读数据此区分「带了资产包」与「兼容期放行」。
            "asset_bundle": asset_bundle,
            "result_contract": result_contract,
        })
        return _serialize_package(package, detail=True, session=session)


def _require_delivery_snapshot(package: HandoverPackage, payload: Any, *, required: bool) -> bool:
    """True 表示兼容期放行了省略条件的登记（调用方须留痕）。"""
    if not isinstance(payload, dict):
        raise _error("invalid_request", "请求内容必须为 JSON 对象。", 400)
    digest_key = "expected_manifest_sha256"
    count_key = "expected_unsealed_count"
    if digest_key not in payload and count_key not in payload:
        if required:
            raise _error("write_preconditions_required", "交付登记需要封存批次确认。请升级客户端并重新读取交付包。", 428)
        return True
    digest = payload.get(digest_key)
    count = payload.get(count_key)
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or type(count) is not int or count < 0:
        raise _error("invalid_write_preconditions", "交付登记需要完整的封存摘要和有效的解封次数。", 422)
    if digest != package.manifest_sha256 or count != package.unsealed_count:
        raise _error("handover_snapshot_conflict", "封存批次已变化，本次未登记。请重新读取并确认交付包。", 409)
    return False


def _validated_asset_pointer(value: Any) -> dict[str, str]:
    """单件指针形状：{source_uri, sha256}（键集闭合）；返回归一化两键。"""
    if not isinstance(value, dict) or set(value.keys()) != {"source_uri", "sha256"}:
        raise _error(
            "invalid_asset_bundle",
            "资产指针必须恰含 source_uri 与 sha256 两键。",
            422,
        )
    source_uri = value["source_uri"]
    if not isinstance(source_uri, str) or not source_uri.strip() or len(source_uri) > MAX_ASSET_URI_CHARS:
        raise _error(
            "invalid_asset_bundle",
            f"source_uri 必须是 1–{MAX_ASSET_URI_CHARS} 字符的字符串。",
            422,
        )
    sha256 = value["sha256"]
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise _error("invalid_asset_bundle", "sha256 必须是 64 位十六进制指纹。", 422)
    return {"source_uri": source_uri, "sha256": sha256.lower()}


def _result_contract_evidence_hashes(session: Any, project_id: str) -> list[str]:
    """项目 G4 门禁清单项「结果合同页」中已确认（accepted）证据的指纹集。

    无 G4 行 / 无该清单项 / 项未 accepted → 空集（调用方放行——结果合同
    未走试点门禁线的项目不因缺 G4 证据被拦，回指留痕可推翻）。
    """
    gate = session.scalar(select(Gate).where(Gate.project_id == project_id, Gate.gate_key == "G4"))
    if gate is None:
        return []
    hashes: list[str] = []
    for item in gate.evidence_checklist or []:
        if (
            item.get("label") == RESULT_CONTRACT_LABEL
            and item.get("claim_status") == "accepted"
            and isinstance(item.get("content_hash"), str)
        ):
            hashes.append(item["content_hash"].lower())
    return hashes


def _require_asset_bundle_and_result_contract(
    session: Any, project: Project, payload: Any, *, required: bool
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """B1 结项资产闸＋B9-a 结果合同回指（同端点一次过闸，E-1/Yui 定案）。

    返回 (asset_bundle, result_contract, skipped_missing)。skipped_missing
    非空表示兼容期放行了省略键的旧请求（调用方须留痕）；键在场则一律
    严格校验，与部署开关无关。
    """
    if not isinstance(payload, dict):
        raise _error("invalid_request", "请求内容必须为 JSON 对象。", 400)
    skipped_missing: list[str] = []

    if "asset_bundle" in payload:
        raw_bundle = payload["asset_bundle"]
        if not isinstance(raw_bundle, dict) or set(raw_bundle.keys()) != set(ASSET_BUNDLE_KEYS):
            raise _error(
                "invalid_asset_bundle",
                f"asset_bundle 必须恰含 {'、'.join(ASSET_BUNDLE_KEYS)} 三件（空包不放行）。",
                422,
            )
        asset_bundle = {key: _validated_asset_pointer(raw_bundle[key]) for key in ASSET_BUNDLE_KEYS}
    else:
        if required:
            raise _error(
                "asset_bundle_required",
                "交付登记需要结项资产包（复盘/交接/可复用方法三件指针）。请升级客户端后重新登记。",
                428,
            )
        skipped_missing.append("asset_bundle")
        asset_bundle = None

    evidence_hashes = _result_contract_evidence_hashes(session, project.id)
    if "result_contract" in payload:
        result_contract = _validated_asset_pointer(payload["result_contract"])
        if evidence_hashes and result_contract["sha256"] not in evidence_hashes:
            raise _error(
                "result_contract_mismatch",
                "result_contract 指纹与 G4 门禁在案的「结果合同页」证据不一致。",
                409,
            )
    else:
        # 有源必回指：G4 已 accepted「结果合同页」在案 ⇒ 键不得省略；
        # 无源可指（项目未走试点门禁线）⇒ 省略放行（delivered 事件
        # result_contract=null 如实留痕，复盘读数可区分）。
        if evidence_hashes:
            if required:
                raise _error(
                    "result_contract_required",
                    "项目 G4 门禁在案「结果合同页」证据，交付登记必须回指它。请升级客户端后重新登记。",
                    428,
                )
            skipped_missing.append("result_contract")
        result_contract = None

    return asset_bundle, result_contract, skipped_missing


def available_artifacts(*, actor: User, project_id: str, item_type: str = "artifact") -> dict[str, Any]:
    """封包挑选面：本项目**过闸**候选投影（指针+指纹，不进 api_catalog）。

    item_type 三态：artifact=已人工复核产物（既有行为零变化）；document=已确认
    文档版本；file=可用文件版本。非 artifact 形状按类型投影（键闭集随类型）。
    """
    session = _session()
    if item_type not in ITEM_TYPES:
        raise _error("invalid_request", f"type 须为 {'/'.join(ITEM_TYPES)}。", 400)
    with session.begin():
        project = _load_project_for(session, actor, project_id, manage=False)
        if item_type == "document":
            from fde_api.documents.models import ProjectDocument, ProjectDocumentVersion

            rows = list(session.scalars(
                select(ProjectDocumentVersion)
                .join(ProjectDocument, ProjectDocumentVersion.document_id == ProjectDocument.id)
                .where(ProjectDocument.project_id == project.id, ProjectDocumentVersion.status == "confirmed")
                .order_by(ProjectDocumentVersion.created_at.desc())
                .limit(_LIST_LIMIT_MAX)
            ))
            return {
                "items": [
                    {
                        "document_version_id": row.id,
                        "document_id": row.document_id,
                        "version_number": row.version_number,
                        "kind": "document",
                        "storage_ref": f"document-version:{row.id}",
                        "sha256": row.sha256,
                    }
                    for row in rows
                ],
                "truncated": len(rows) >= _LIST_LIMIT_MAX,
            }
        if item_type == "file":
            from fde_api.files.models import ProjectFile, ProjectFileVersion

            rows = list(session.scalars(
                select(ProjectFileVersion)
                .join(ProjectFile, ProjectFileVersion.file_id == ProjectFile.id)
                .where(ProjectFile.project_id == project.id, ProjectFileVersion.status == "available")
                .order_by(ProjectFileVersion.created_at.desc())
                .limit(_LIST_LIMIT_MAX)
            ))
            return {
                "items": [
                    {
                        "file_version_id": row.id,
                        "file_id": row.file_id,
                        "kind": "file",
                        "storage_ref": row.storage_key,
                        "sha256": row.sha256,
                    }
                    for row in rows
                ],
                "truncated": len(rows) >= _LIST_LIMIT_MAX,
            }
        rows = list(session.scalars(
            select(AgentArtifact)
            .join(AgentRun, AgentArtifact.run_id == AgentRun.id)
            .where(AgentRun.project_id == project.id, AgentArtifact.reviewed.is_(True))
            .order_by(AgentArtifact.created_at.desc())
            .limit(_LIST_LIMIT_MAX)
        ))
        return {
            "items": [
                {
                    "artifact_id": row.id,
                    "run_id": row.run_id,
                    "kind": row.kind,
                    "storage_ref": row.storage_ref,
                    "sha256": row.sha256,
                    "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                }
                for row in rows
            ],
            "truncated": len(rows) >= _LIST_LIMIT_MAX,
        }
