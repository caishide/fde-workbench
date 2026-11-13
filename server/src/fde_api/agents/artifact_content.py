"""产物内容读取面（T-A10 桌面产物预览/下载；N3c 轮与 G-15 合批交付）。

「看到什么就复核什么」的桌面内闭环：AgentsConsole 产物行此前只有指针＋指纹
（复核人被迫离开应用到宿主工作区看原件，N1 人工链辅助轮实弹暴露）——本模块
把原件内容就地带回桌面，**逐字节 sha256 对库行指纹自证**（不符 ⇒ 503
fail-closed：复核人看到的内容与被复核的行保证同源）。

进程空间裁决（backlog T-A10 登记项，2026-11-12 蔡工 N3c 轮按推荐项拍板）：
原件存宿主工作区（``settings.agent_workspace_root``，storage_ref 形状
``{run_id}/output/{path}``）——宿主裸跑态全量可用；容器部署态读不到宿主
路径 ⇒ **显式 404 artifact_content_unavailable（不静默、不伪造空内容）**，
与 T-Z1 ``adapter_missing`` 同族降级语义。

边界（红线）：只读面（零写路径零事件——预览不新增外发通道）；原件永不进
仓库/数据库（响应体是临时读取，不留存）；权限与复核动作同尺（can_manage
——能预览的人才能复核）；路径防穿越（storage_ref 拒绝绝对路径，resolve 后
必须落在该 run 工作区 ``output/`` 内——含 ``..`` 与符号链接逃逸）；超限
413（不静默截断——截断的「预览」会诱导误复核）。
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path, PurePosixPath

from flask import current_app
from sqlalchemy.orm import Session

from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.auth.models import User
from fde_api.projects.permissions import project_access
from fde_api.storage.layout import org_object_prefix
from fde_api.workbench.models import Project

# 预览/下载体量上限（manifest 契约产物是文本件族：doc/diff/config/code/
# test_results——5MB 覆盖全部现实形态；超限显式拒绝不截断）。
MAX_ARTIFACT_CONTENT_BYTES = 5 * 1024 * 1024

_KIND_MIME = {
    "doc": "text/markdown",
    "config": "application/json",
    "test_results": "application/json",
    "code": "text/plain",
    "diff": "text/plain",
}


class ArtifactContentError(Exception):
    """产物内容读取失败（稳定错误码；路由面映射 HTTP）。"""

    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _guess_mime(kind: str, filename: str) -> str:
    import mimetypes

    guessed, _encoding = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    return _KIND_MIME.get(kind, "application/octet-stream")


def read_artifact_content(
    session: Session, *, actor: User, run_id: str, artifact_id: str
) -> dict:
    """读取 run 产物原件内容（can_manage；只读零写）。

    失败语义（fail-closed 家族一致，零静默降级）：
    - run 不存在 / artifact 不属于该 run / 项目不可见 ⇒ 404（不泄露存在性）；
    - 非 can_manage ⇒ 403（与产物复核动作同尺）；
    - 工作区原件不在场（容器部署态常态）⇒ 404 artifact_content_unavailable；
    - storage_ref 绝对路径或逃逸 output/ ⇒ 404 artifact_content_path_unsafe；
    - 原件超 MAX_ARTIFACT_CONTENT_BYTES ⇒ 413 artifact_content_too_large；
    - 逐字节 sha256 ≠ 库行指纹 ⇒ 503 artifact_content_fingerprint_mismatch
      （fail-closed：内容与被复核行不同源，绝不能给复核人看）。
    """
    run = session.get(AgentRun, run_id)
    if run is None:
        raise ArtifactContentError("run_not_found", "智能体 run 不存在。", 404)
    project = session.get(Project, run.project_id)
    access = project_access(actor, project) if project else None
    if project is None or access is None:
        raise ArtifactContentError("project_not_found", "项目不存在或无权访问。", 404)
    if not access.can_manage:
        raise ArtifactContentError("project_forbidden", "产物内容预览需要项目管理权限。", 403)
    artifact = session.get(AgentArtifact, artifact_id)
    if artifact is None or artifact.run_id != run.id:
        raise ArtifactContentError("artifact_not_found", "产物不存在或不属于该 run。", 404)

    initiator = session.get(User, run.initiated_by_user_id)
    org_segment = org_object_prefix(getattr(initiator, "org_id", None))
    settings = current_app.config["SETTINGS"]
    workspace_root = Path(settings.agent_workspace_root)
    raw_ref = artifact.storage_ref
    # host_poll 回执落账的指针带 host: 前缀（host_receipt 约定：原件在宿主
    # 磁盘，回执只登记宿主侧指纹）。裸跑态服务端与宿主同机 ⇒ 剥前缀后与
    # 容器形状 {run_id}/output/{path} 同构可读（N3c 拍板：宿主裸跑态全量
    # 可用）；容器态原件不在场 ⇒ 自然落到下方 artifact_content_unavailable
    # 显式降级。剥前缀后防穿越校验与容器指针完全同套（安全语义不变）。
    ref_text = raw_ref.removeprefix("host:")
    ref = PurePosixPath(ref_text)
    if ref.is_absolute() or ".." in ref.parts:
        raise ArtifactContentError(
            "artifact_content_path_unsafe", "产物指针非法（拒绝绝对路径与上跳）。", 404
        )
    output_root = (workspace_root / org_segment / run_id / "output").resolve()
    candidate = (workspace_root / org_segment / ref_text).resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as error:
        raise ArtifactContentError(
            "artifact_content_path_unsafe", "产物指针逃逸该 run 工作区 output/。", 404
        ) from error
    if not candidate.is_file():
        # 容器部署态常态：原件在宿主工作区，服务端容器读不到——显式降级，
        # 不伪造空内容（与 T-Z1 adapter_missing 同族语义）。
        raise ArtifactContentError(
            "artifact_content_unavailable",
            "产物原件不在服务端可见的工作区（宿主裸跑态在部署机本地可用；容器部署态读不到宿主路径）。",
            404,
        )
    # 体量闸在载荷之前：stat() 预检（read_bytes 整读前拒绝，避免超大原件
    # 全量进内存后才 413——413 语义不变，只是不再先付内存代价）。
    if candidate.stat().st_size > MAX_ARTIFACT_CONTENT_BYTES:
        raise ArtifactContentError(
            "artifact_content_too_large",
            f"产物超过预览上限（{MAX_ARTIFACT_CONTENT_BYTES} 字节），请到宿主工作区取原件。",
            413,
        )
    data = candidate.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != artifact.sha256:
        # 指纹不符＝原件已被改动/损坏——fail-closed，绝不能给复核人看。
        raise ArtifactContentError(
            "artifact_content_fingerprint_mismatch",
            "产物原件指纹与库行不一致（原件可能已被改动），已拒绝返回。",
            503,
        )
    return {
        "run_id": run.id,
        "artifact_id": artifact.id,
        "kind": artifact.kind,
        "storage_ref": artifact.storage_ref,
        "sha256": artifact.sha256,
        "size": len(data),
        "mime": _guess_mime(artifact.kind, candidate.name),
        "reviewed": artifact.reviewed,
        "content_base64": base64.b64encode(data).decode("ascii"),
    }
