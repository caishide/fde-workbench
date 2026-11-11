from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from fde_api.auth.models import User
from fde_api.auth.permissions import role_at_least
from fde_api.orgs.isolation import org_scope_allows, project_org_scope_filter
from fde_api.workbench.models import Project, ProjectMember


@dataclass(frozen=True, slots=True)
class ProjectAccess:
    can_view: bool
    can_manage: bool
    can_update_assigned_tasks: bool


NO_PROJECT_ACCESS = ProjectAccess(False, False, False)


def project_access(user: User, project: Project) -> ProjectAccess:
    """Combine inherited system capability with explicit project scope."""
    if not user.is_active:
        return NO_PROJECT_ACCESS
    if user.role == "admin":
        return ProjectAccess(True, True, True)
    # M3a（M3a 规格 v1 §2）：企业身份的可见范围收敛到「本企业 org ＋ 平台
    # 内部 org 桶 ＋ 平台级行」；平台身份（org_id IS NULL）不受 org 限制。
    # org 只是归属维度，成员关系仍是可见性的必要条件（红线 8：不建第二套
    # 权限体系）。
    if not org_scope_allows(user, project.org_id):
        return NO_PROJECT_ACCESS
    if (
        user.id == project.leader_user_id
        and role_at_least(user.role, "project_lead")
    ):
        return ProjectAccess(True, True, role_at_least(user.role, "fde_engineer"))

    member = next((item for item in project.members if item.user_id == user.id), None)
    if member is None:
        return NO_PROJECT_ACCESS
    if member.role == "viewer":
        return ProjectAccess(True, False, False)
    return ProjectAccess(
        True,
        False,
        role_at_least(user.role, "fde_engineer"),
    )


def visible_project_filter(user: User) -> ColumnElement[bool]:
    """可见性谓词（**SQL 形态**）——列表级与对象级同源的单一权威。

    - admin（平台能力）：全部项目；
    - 其余：``(leader 且角色 ≥ project_lead) OR EXISTS(成员行)``，
      再叠加 org 谓词（企业身份收敛到「本企业 org ＋ 平台内部 org 桶 ＋
      平台级行」；平台身份不受 org 约束但**成员关系约束照旧**）。

    消费方：``visible_project_ids``（列表级取 id）与项目列表 SQL 预过滤
    （``projects/service.py::list_projects``）——**两处必须共用本谓词**，
    否则出现「列表可见、详情无权」的幽灵行（``test_visibility_parity.py``）。
    """
    if user.role == "admin":
        return Project.id.is_not(None)

    member_or_leader = exists(
        select(ProjectMember.id).where(
            ProjectMember.project_id == Project.id,
            ProjectMember.user_id == user.id,
        )
    )
    visibility = []
    if role_at_least(user.role, "project_lead"):
        visibility.append(Project.leader_user_id == user.id)
    visibility.append(member_or_leader)

    predicate = or_(*visibility)
    org_filter = project_org_scope_filter(user)
    if org_filter is not None:
        predicate = and_(predicate, org_filter)
    return predicate


def visible_project_ids(session: Any, user: User) -> list[str]:
    """actor 可见项目 id 集——跨域列表面的可见性单一权威。

    **M3a：判定下推到 SQL**（原实现是「全表取回 + Python 逐项目判定」，
    成本随项目量线性）。可见性语义仍只有这一处，列表级与对象级
    （``project_access``）**必须同语义**；org 谓词同样下推（``ix_projects_org_id``
    索引在位）——不在 SQL 之后再加一层 Python 过滤（红线 10）。
    """
    if not user.is_active:
        return []
    return list(
        session.scalars(select(Project.id).where(visible_project_filter(user))).all()
    )
