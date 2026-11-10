"""M1 归属语义单一入口（ADR-M1 §3/§7）：归属戳 + 推导助手。

- **归属戳**（``before_flush`` 会话级事件，覆盖一切 ORM 写路径——路由/服务/
  种子/脚本无一漏网）：``Project`` 未显式携带 ``org_id`` 时按 leader 的归属
  落 org；leader 为平台身份（``org_id=NULL``）时落 **internal org**（ADR-M1
  §3「internal = 承载存量回填与平台侧项目」）。**显式传入的 org_id 不覆盖**
  ——M2 注册面 / M5 企业空间将来显式指定归属时不被隐式改写。
- **审计维度**：``OperationEvent.org_id`` 从其 project 的归属推导（数据归属
  口径：「这条事件关于哪个 org 的数据」）；无 project 的事件＝平台级（NULL，
  目标归属可从 target 对象推导——ADR-M1 §4）。
- **零第二权限体系**（红线 8）：本模块不产生任何授权判定，只维护归属维度；
  成员可见性仍由 ``projects/permissions.py`` 单一权威决定。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.orgs.models import (
    INTERNAL_ORG_ID,
    INTERNAL_ORG_NAME,
    ORG_TYPE_INTERNAL,
    Org,
)

if TYPE_CHECKING:  # 顶层零导入：orgs⇄workbench 包环由 architecture_purity 闸冻结
    from fde_api.workbench.models import Project


def install_org_attribution() -> None:
    """注册归属戳监听（模块底部调用一次——Python 模块缓存保证同进程只注册
    一次；监听体内按 ``org_id is None`` 幂等，重复触发也无副作用）。"""
    event.listen(Session, "before_flush", _stamp_org_attribution)


def _stamp_org_attribution(
    session: Session, flush_context: Any, instances: Any
) -> None:
    # 懒导入解包环（workbench.models 尾部导入本模块注册监听——顶层互导会被
    # test_architecture_purity 的冻结闸转红）
    from fde_api.workbench.models import OperationEvent, Project

    pending = list(session.new)
    # 先戳项目（同事务里「建项目 + 事件留痕」时事件推导依赖项目已带归属）
    for obj in pending:
        if isinstance(obj, Project) and obj.org_id is None:
            leader = session.get(User, obj.leader_user_id)
            obj.org_id = (
                leader.org_id if leader is not None else None
            ) or INTERNAL_ORG_ID
    for obj in pending:
        if (
            isinstance(obj, OperationEvent)
            and obj.org_id is None
            and obj.project_id is not None
        ):
            project = session.get(Project, obj.project_id)
            if project is not None:
                obj.org_id = project.org_id


def org_of_project(project: Project) -> str | None:
    """``org_of(project) = projects.org_id``（ADR-M1 §3 推导语义）。"""
    return project.org_id


def orgs_of_user(session: Session, user_id: str) -> list[str]:
    """``orgs_of(user) = [users.org_id] + 经成员项目传递的 org``（去重保序）。

    直接归属在前（平台身份则无）；成员项目传递的 org 依附其后——成员可见性
    仍由 ``project_members`` 决定（G6 红线），本函数只回答「用户与哪些 org
    有关」，不回答「能看什么」。
    """
    orgs: list[str] = []
    from fde_api.workbench.models import Project, ProjectMember  # 懒导入解包环

    direct = session.scalar(select(User.org_id).where(User.id == user_id))
    if direct is not None:
        orgs.append(direct)
    member_orgs = session.scalars(
        select(Project.org_id)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user_id)
        .where(Project.org_id.is_not(None))
        .distinct()
        .order_by(Project.org_id)
    ).all()
    for org_id in member_orgs:
        if org_id is not None and org_id not in orgs:
            orgs.append(org_id)
    return orgs


def ensure_internal_org(session: Session) -> Org:
    """幂等 get-or-create 平台内部组织（迁移种子 / cli bootstrap / 测试夹具同源）。"""
    existing = session.get(Org, INTERNAL_ORG_ID)
    if existing is not None:
        return existing
    org = Org(
        id=INTERNAL_ORG_ID,
        org_type=ORG_TYPE_INTERNAL,
        name=INTERNAL_ORG_NAME,
    )
    session.add(org)
    session.flush()
    return org


install_org_attribution()
