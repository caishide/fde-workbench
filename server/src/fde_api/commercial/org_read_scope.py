"""M6：商业域读面的 **org 归属隔离** 接线（多客户 M6-1 轮）。

**本模块不是权限体系**——判定权威始终在既有单一入口
``fde_api.orgs.isolation``（M3a 规格 §1／红线 8「org 是归属维度不是授权
维度」）。本模块只做两件事：

1. **归属推导**（裁决 1：**零迁移、零新表、零新列、零新路由**）：科目/权益/
   认证/商机等行**不含 org_id**，经其关联账号（``subject_user_id``／
   ``payee_user_id``／``user_id``／``reported_by_user_id`` 等用户 FK）→
   ``users.org_id`` 推导该行的归属 org；
2. **可见性判定**（列表级 SQL 下推 ＋ 对象级同语义——M3a 规格 §2 硬要求：
   「对象级入口与列表级入口必须同语义，否则详情 403 / 列表可见的幽灵行」）。

**三态语义承袭 M3a**（``orgs/isolation.py``）＋ 商业域既有「本人／admin」两档：

| actor 态 | 判定 | 商业域读面可见范围 |
|---|---|---|
| **admin** | ``role == 'admin'`` | 全量（平台能力，逐位不变） |
| **平台身份** | ``org_id IS NULL`（非 admin） | **只见本人**（存量口径**逐位不变**——M1 拍板「存量用户不回填」⇒ 存量回归面零变化） |
| **企业身份** | ``org_id = X`（非 admin） | **本 org（＋平台内部桶）**（M5 已落模式「本 org 成员或 admin」） |

**对象级四态判定**（:func:`resource_visibility`）——各读面据此选失败码：

| 判定 | 含义 | 读面典型失败码 |
|---|---|---|
| ``self`` | actor 本人 | —（放行） |
| ``same_org`` | 企业身份 ＋ 目标属本 org（M5 模式：同企业成员互相可见） | —（放行）／按读面既有码 |
| ``cross_enterprise`` | 企业身份 ＋ 目标属**别家**企业 org | **404**（M3a §3.5 默认口径：不确认资源存在） |
| ``other`` | 平台身份 ＋ 目标非本人（**存量口径**） | 沿用该读面**既有码**（403 等）——零回归 |

**G2 两面（额度账／企业空间）的现状说明（逐个核实后不改）**：这两面既有判定
是「**绑定账号本人或 admin**，他人一律 404」（CR-062 拍板）——**绑定账号是账号
维度的强判定**，天然比 org 维度更严（别家企业账号必非绑定账号 ⇒ 必 404），
故 M6 **不改动这两面的行为**（改之即推翻 CR-062：既有
``test_commercial_enterprise_space.py::test_space_view_scopes`` 钉住
「同主体第二经办人也 404」）。M6 对这两面只做**现状核实**（见 M6 验收对照表）。
"""
from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from fde_api.auth.models import ROLE_ADMIN, User
from fde_api.orgs.isolation import is_platform_identity, org_scope_org_ids

__all__ = [
    "VIS_CROSS_ENTERPRISE",
    "VIS_OTHER",
    "VIS_SAME_ORG",
    "VIS_SELF",
    "actor_org_scope",
    "resource_visibility",
    "user_org_id",
    "visible_user_ids_query",
]

# ── 对象级可见性四态 ──
VIS_SELF = "self"  # actor 本人
VIS_SAME_ORG = "same_org"  # 企业身份 ＋ 目标属本 org
VIS_CROSS_ENTERPRISE = "cross_enterprise"  # 企业身份 ＋ 目标属别家企业
VIS_OTHER = "other"  # 平台身份 ＋ 目标非本人（存量口径）


def actor_org_scope(actor: User) -> list[str] | None:
    """**企业身份** actor 的可见 org 集合（``[本 org, 平台内部桶]``）。

    平台身份（``org_id IS NULL``，含 admin）返回 ``None``＝**不限**（调用方
    按各读面既有语义处理：admin 全量／平台身份只见本人）。
    """
    if is_platform_identity(actor):
        return None
    scope = org_scope_org_ids(actor)
    return list(scope) if scope is not None else None


def visible_user_ids_query(actor: User) -> Select[tuple[str]] | None:
    """**可见范围内账号 id 的子查询**（SQL 下推形态）。

    - 平台身份／admin ⇒ ``None``＝不加 org 约束（调用方按既有语义处理）；
    - 企业身份 ⇒ ``users.org_id IN (可见 org 集合)``。
    """
    scope = actor_org_scope(actor)
    if scope is None:
        return None
    return select(User.id).where(User.org_id.in_(scope))


def user_org_id(session: Session, user_id: object) -> str | None:
    """取账号归属 org；账号不存在／无归属 ⇒ ``None``（平台身份语义）。"""
    if not isinstance(user_id, str) or not user_id:
        return None
    row = session.get(User, user_id)
    return row.org_id if row is not None else None


def resource_visibility(
    session: Session, actor: User, *user_ids: object
) -> str:
    """行级**可见性四态**判定（对象级读面的单一入口）。

    - admin ⇒ ``VIS_SELF``（平台能力恒放行，由调用方 admin 分支处理）；
    - actor 本人是关联账号之一 ⇒ ``VIS_SELF``；
    - **平台身份**（``org_id IS NULL`，非 admin）＋ 目标非本人 ⇒ ``VIS_OTHER``
      （**存量口径逐位不变**——各读面沿用既有 403 码）；
    - **企业身份** ＋ 目标账号归属 org ∈ 可见 org 集合 ⇒ ``VIS_SAME_ORG``
      （M5 已落模式「本 org 成员或 admin」⇒ 同企业成员互相可见）；
    - **企业身份** ＋ 目标账号归属**别家**企业 org ⇒ ``VIS_CROSS_ENTERPRISE`
      （⇒ 404：不确认资源存在）。

    目标账号**无 org 归属**（平台侧账号／未知账号）⇒ 按 ``VIS_OTHER`` 处理
    （**不按企业边界拦截**——平台级行不属任何企业，交由调用方既有判定处理）。
    """
    if actor.role == ROLE_ADMIN:
        return VIS_SELF
    if actor.id in user_ids:
        return VIS_SELF
    scope = actor_org_scope(actor)
    if scope is None:
        # 平台身份（存量口径）：目标非本人 ⇒ 既有 403 语义。
        return VIS_OTHER
    for user_id in user_ids:
        org_id = user_org_id(session, user_id)
        if org_id is None:
            continue
        if org_id in scope:
            return VIS_SAME_ORG
        return VIS_CROSS_ENTERPRISE
    return VIS_OTHER
