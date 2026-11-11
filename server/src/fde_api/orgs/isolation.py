"""M3a：org 维度隔离语义的**单一入口**（M3a 规格 v1 §1–§2）。

本模块只回答两个问题，不产生任何授权体系（红线 8：org 是**归属维度**，
授权仍归 ``project_members`` ＋ 既有角色尺）：

1. **某 actor 能否作用在某资源所属 org 上**（``org_scope_allows``）；
2. **可见项目集合的 SQL 谓词**（``project_org_scope_filter``——下推到 SQL，
   禁止「SQL 后再加一层 Python 过滤」，红线 10）。

三态语义（拍板 §11-8 / M3a 规格 §1）：

- **平台身份**（``users.org_id IS NULL``）：不受 org 限制，跨 org 可见——
  存量用户全部落在这一态（M1 拍板「存量用户不回填」⇒ 存量回归面零变化）；
  平台身份的跨 org **写动作必须留痕**（``operation_events``，规格 §3.4）。
- **企业身份**（``users.org_id = X``）：可见范围收敛为「本企业 org ＋ 平台
  内部 org 桶 ＋ 项目级平台行（``projects.org_id IS NULL``）」。
- **平台内部 org**（``INTERNAL_ORG_ID``）：平台自有项目归属桶——平台身份
  立项的项目落此处，是「平台立项 → 企业账号作 viewer 成员」既有通路
  （G6 ADR-010）的落点，**不在企业间隔离边界内**（其混装缺口登记在
  《全局面盘点表》「待 M0 补充」节，消解路径归 M5）。

**零 flask / 零环境读取**：本模块是纯领域判定（与 ``orgs/org_scope.py``
的归属戳职责分离——那管「归属怎么落」，这管「可见性怎么判」）。
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from fde_api.auth.models import User
from fde_api.orgs.models import INTERNAL_ORG_ID


def is_platform_identity(user: User) -> bool:
    """平台身份判定——``org_id IS NULL``（含 admin：平台能力恒真）。"""
    return user.role == "admin" or user.org_id is None


def org_scope_org_ids(user: User) -> list[str] | None:
    """actor 可见的 org 集合；``None`` = **不限**（平台身份 / admin）。

    ``None`` 的含义是「不设 org 限制」，**不是**「额外授权」——成员关系
    仍是可见性的必要条件（规格 §2 的判定式）。
    """
    if is_platform_identity(user):
        return None
    org_id = user.org_id
    if org_id is None:  # 平台身份已在上一行判过；此分支只为类型收窄
        return None
    return [org_id, INTERNAL_ORG_ID]


def org_scope_allows(user: User, resource_org_id: str | None) -> bool:
    """actor 能否作用在 ``resource_org_id`` 归属的资源上。

    - admin（平台能力）恒真；平台身份恒真（不受 org 限制，§11-8）；
    - 企业身份：平台级行（``resource_org_id IS NULL``）／本企业 org／
      平台内部 org 桶 三者之一方可；
    - 其余一律拒绝（**fail-closed**，规格 §3.2）。
    """
    if is_platform_identity(user):
        return True
    if resource_org_id is None:
        # 项目级平台行：归属戳落地前的瞬间与回填前存量行——不作企业间边界。
        return True
    return resource_org_id in (user.org_id, INTERNAL_ORG_ID)


def project_org_scope_filter(user: User) -> ColumnElement[bool] | None:
    """可见项目集合的 **org 谓词**（SQL 下推形态）。

    平台身份返回 ``None``＝不加 org 约束（可见性仍受成员关系约束）。
    企业身份返回可下推的布尔谓词：``projects.org_id IS NULL OR projects.org_id IN (…)``。
    """
    org_ids = org_scope_org_ids(user)
    if org_ids is None:
        return None
    from fde_api.workbench.models import Project  # 懒导入解包环

    return or_(
        Project.org_id.is_(None),
        Project.org_id.in_(org_ids),
    )
