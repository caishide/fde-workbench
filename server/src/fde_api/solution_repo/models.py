"""solution_repo 域模型（AF3-WP1）：``repo_bindings`` 仓库绑定行。

绑定语义（04 §3.3）：每次工作区绑定 repo、基线 commit、分支、路径白名单与
执行 grant——一行 = (org, repo_root, branch) 三元组唯一（``uq_repo_bindings``
）；``allow_roots`` 快照落行（绑定时刻冻结——修改 allow_roots = 重新绑定，
旧批准随源内容失效语义由 WP2/WP4 提案面承接）。

status 闭集：``active|revoked`` CHECK 机械约束；revoke 即时生效（撤权面，
AF1② 撤权语义域内同构）。append-only 倾向：无 UPDATE 内容面（仅 status 翻
revoked 一次），无 DELETE 面（绑定历史留痕）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.workbench.models import Base, TimestampMixin, new_uuid

REPO_BINDING_STATUSES = ("active", "revoked")


class RepoBinding(Base, TimestampMixin):
    __tablename__ = "repo_bindings"
    __table_args__ = (
        CheckConstraint(
            f"status IN {REPO_BINDING_STATUSES!r}",
            name="ck_repo_bindings_status",
        ),
        UniqueConstraint("org_id", "repo_root", "branch", name="uq_repo_bindings_org_repo_branch"),
        Index("ix_repo_bindings_org_status", "org_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # 租户面按值存（复用 orgs 模型标识体系，禁自造 tenant_id——任务书 §15）
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 绑定四元组（仓库根/工作区根为服务端受控本机路径；不是客户敏感数据、
    # 不是凭据——repo_root 是绑定配置面。allow_roots 为绑定时刻冻结快照）
    repo_root: Mapped[str] = mapped_column(String(500), nullable=False)
    workspace_root: Mapped[str] = mapped_column(String(500), nullable=False)
    allow_roots_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # 执行 grant（04 §3.3 五要素；评审 D3 清偿）：agent_allowed 子集白名单
    # （null＝全量 agent_allowed；闭集外 op 绑定时 422、服务面越权 403）
    grant_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # 审计快照（bind/revoke 事件与操作计数；结构化审计台账归 WP5 证据绑定面）
    audit_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "binding_id": self.id,
            "org_id": self.org_id,
            "requester_id": self.requester_id,
            "repo_root": self.repo_root,
            "workspace_root": self.workspace_root,
            "allow_roots": list(self.allow_roots_json or []),
            "base_commit": self.base_commit,
            "branch": self.branch,
            "status": self.status,
            "grant_json": self.grant_json,
        }


REPO_PATCH_STATUSES = ("applied", "failed")


class RepoPatch(Base, TimestampMixin):
    """类型化 Patch 应用行（AF3-WP2）。

    **零明文**（AE1 params_sha256 同构纪律）：PatchPlan 只存 ``plan_sha256``
    指纹，条目内容（产物文件明文）不落库——产物真身在绑定仓的 git 历史
    （applied_commit 可追溯），落库面只有指纹与结果元数据。

    幂等（AE1 同构）：``UNIQUE(org_id, binding_id, patch_id)``——同键重放＝
    复放首次结果（service 层查行返回，零重复副作用）。status 闭集
    ``applied|failed``：闸前拒绝（白名单/形状/base mismatch/dirty）不落行
    （拒绝路径不落库——AE1 口径）；应用执行失败落 ``failed`` 行＋错误快照。
    """

    __tablename__ = "repo_patches"
    __table_args__ = (
        CheckConstraint(
            f"status IN {REPO_PATCH_STATUSES!r}",
            name="ck_repo_patches_status",
        ),
        UniqueConstraint("org_id", "binding_id", "patch_id", name="uq_repo_patches_org_binding_patch"),
        Index("ix_repo_patches_org_status", "org_id", "status"),
        Index("ix_repo_patches_binding", "binding_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False)
    patch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    applied_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    audit_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "binding_id": self.binding_id,
            "plan_sha256": self.plan_sha256,
            "entry_count": self.entry_count,
            "base_commit": self.base_commit,
            "applied_commit": self.applied_commit,
            "status": self.status,
            "error_code": self.error_code,
        }
