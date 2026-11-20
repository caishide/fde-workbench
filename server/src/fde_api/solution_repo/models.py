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
        }
