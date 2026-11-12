"""项目本体绑定与升级留痕（V3.3 任务书 §5.2；规格 = Fde-Ontology docs/v3.3/m1/ontology-data-model.md §3）。

**两段交付（D7 决策单，m2/00-m2-work-order.md）**：org_id 列预留（可空+索引），
orgs 多租户轨道合流后回填 NOT NULL；ontology-service 侧已按 org 强制隔离
（跨租户一律 404），本表 org_id 段 1 阶段不作鉴权谓词。

硬规则（§5.2 + I5）：
- 绑定必须指向已发布版本（draft 拒绝——由 ontology-service 校验，本侧 pin 的
  version_id 必须来自 publish 响应）；
- 一个项目可绑定多个本体（uq: project+ontology 单活跃绑定）；
- 版本升级必须差异审查+批准（ontology_binding_upgrades 留痕，retire 不删行）；
- 保留历史绑定与执行时版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.auth.models import (
    Base,
)
from fde_api.workbench.models import TimestampMixin, VersionedMixin, new_uuid


class ProjectOntologyBinding(Base, TimestampMixin, VersionedMixin):
    __tablename__ = "project_ontology_bindings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'retired')", name="ck_project_ontology_bindings_status"
        ),
        # 单活跃绑定：同项目同本体至多一行 active（status='active' 唯一性由服务层保证，
        # 部分唯一索引段 2 org 合流后补；先以 (project_id, ontology_id) 唯一约束收口）
        UniqueConstraint(
            "project_id", "ontology_id", name="uq_project_ontology_bindings_project_ontology"
        ),
        Index("ix_project_ontology_bindings_project", "project_id"),
        Index("ix_project_ontology_bindings_org", "org_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # D7 段 1：预留列；orgs 轨道合流后回填 NOT NULL（append-only 演进）
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ontology_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # opaque 指针（→ ontology-service ontology_versions.id，无 FK 跨库）
    pinned_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pinned_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    binding_role: Mapped[str] = mapped_column(String(40), nullable=False, default="primary")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    bound_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "ontology_id": self.ontology_id,
            "pinned_version_id": self.pinned_version_id,
            "pinned_version": self.pinned_version,
            "binding_role": self.binding_role,
            "status": self.status,
        }


class OntologyBindingUpgrade(Base, TimestampMixin):
    """升级留痕（§5.2："版本升级必须有差异审查和批准"+"保留历史绑定和执行时使用的版本"）。"""

    __tablename__ = "ontology_binding_upgrades"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')", name="ck_ontology_binding_upgrades_status"
        ),
        Index("ix_ontology_binding_upgrades_binding", "binding_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False)
    from_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    to_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # opaque → ontology-service GET /change-sets/{id}（差异审查证据，I7 指针化）
    diff_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_change_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    proposed_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
