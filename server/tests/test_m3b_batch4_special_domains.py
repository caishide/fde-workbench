"""M3b 批次 ④（特殊域与平台事实 57 端点）留痕与隔离核验套件。

依据：《M3a-隔离入口与装饰器扩展规格-v1》§3（跨 org 留痕 §3.4／失败码闭集
§3.5／逐批验证方法 §3.6）＋《ADR-M3》§5（dispatch 撮合域只做一件事：
**package_access 授予/撤销补主体归属校验与留痕**——「谁授权给谁」）＋ 2026-11-11
拍板（留痕触发面＝**企业 org 之间才算**）。

覆盖面＝《全局面盘点表》④ 特殊域与平台事实（dispatch 撮合域 18＋simulation 演练
域 14＋agents／ai／bridge／internal／users／auth 等 25）：

- **实改面＝dispatch package_access 授予留痕**：每次授予落一条事件（授权人 →
  被授权人 → 包 → 角色）；被授权人属**别家企业** ⇒ ``cross_org_`` 前缀且 org
  维度取被授权账号归属（跨企业授权在审计面可分辨）。
- **dispatch 访问面核验**：无 ``package_access`` 授权行 ⇒ 404（``require_package_access``
  不泄露包存在性）；admin 平台全局语义放行；授予后可读（阳性对照）。
- **users 域核验**：批次②的共享记录器接线顺带覆盖 ``PATCH /users/<id>``——
  admin 改**别家企业**账号 ⇒ ``cross_org_user_updated``（平台身份目标逐字节不变）。
- **auth 域核验**：改密只认本人（主体归属）。
- 域级代表用例进 CI（拍板 2026-11-11 交互四项之②）；agents／ai／bridge／
  internal／simulation 各域的隔离面由既有套件覆盖（测试指针见盘点表），本批
  **核验销号不重复造例**。
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from fde_api.auth.tokens import issue_access_token
from fde_api.dispatch.access import grant_package_access
from fde_api.dispatch.models import DeliveryPackage
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import OperationEvent

from multi_tenant_harness import make_enterprise_org, make_project, make_user


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _package(db_session, project, owner):
    """造一个交付包（dispatch 撮合域的最小可投递实体）。"""
    solution = ProjectSolution(
        project_id=project.id,
        name="隔离用例方案",
        owner_user_id=owner.id,
    )
    db_session.add(solution)
    db_session.flush()
    package = DeliveryPackage(
        id=solution.id,
        solution_id=solution.id,
        project_id=project.id,
        package_code=f"PKG-{uuid4().hex[:10].upper()}",
        dispatch_status="published",
    )
    db_session.add(package)
    db_session.commit()
    return package


def _grant_events(db_session, actor, subject_id: str) -> list[OperationEvent]:
    return list(
        db_session.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.actor_user_id == actor.id,
                OperationEvent.target_type == "user",
                OperationEvent.target_id == subject_id,
            )
            .order_by(OperationEvent.created_at, OperationEvent.id)
        ).all()
    )


# ---------------------------------------------------------------------------
# dispatch 撮合域：package_access 授予留痕（ADR-M3 §5）
# ---------------------------------------------------------------------------


def test_cross_enterprise_package_access_grant_leaves_cross_org_event(
    db_session
):
    """跨企业授予只读授权 ⇒ ``cross_org_`` 前缀＋org 维度取被授权账号归属。"""
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    org_c = make_enterprise_org(db_session)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B4{uuid4().hex[:6]}", org_id=org_b.id
    )
    package = _package(db_session, project_b, leader_b)
    delivery_c = make_user(db_session, "fde_engineer", org_id=org_c.id)

    grant_package_access(
        db_session,
        package_id=package.id,
        user_id=delivery_c.id,
        role="delivery",
        granted_by_user_id=admin.id,
    )
    db_session.commit()

    events = _grant_events(db_session, admin, delivery_c.id)
    assert any(
        event.event_type == "cross_org_package_access_granted" for event in events
    ), "跨企业 package_access 授予未留痕（缺 cross_org_ 前缀事件）"
    event = next(
        e for e in events if e.event_type == "cross_org_package_access_granted"
    )
    assert event.org_id == org_c.id, "跨 org 事件的 org 维度须取被授权账号归属"
    assert event.changes["package_id"] == package.id
    assert event.changes["role"] == "delivery"


def test_same_enterprise_package_access_grant_has_no_cross_org_prefix(db_session):
    """同企业内授予 ⇒ 不算跨 org（事件名逐字节不变）。"""
    org_b = make_enterprise_org(db_session)
    admin_b = make_user(db_session, "admin", org_id=org_b.id)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B4{uuid4().hex[:6]}", org_id=org_b.id
    )
    package = _package(db_session, project_b, leader_b)
    delivery_b = make_user(db_session, "fde_engineer", org_id=org_b.id)

    grant_package_access(
        db_session,
        package_id=package.id,
        user_id=delivery_b.id,
        role="delivery",
        granted_by_user_id=admin_b.id,
    )
    db_session.commit()

    events = _grant_events(db_session, admin_b, delivery_b.id)
    assert [event.event_type for event in events] == ["package_access_granted"]
    assert all(event.org_id is None for event in events)


def test_platform_identity_package_access_grant_has_no_cross_org_prefix(db_session):
    """平台身份账号被授予 ⇒ 不算跨 org（存量零回归钉）。"""
    admin = make_user(db_session, "admin")
    leader_p = make_user(db_session, "project_lead")
    project_p = make_project(db_session, leader_p, code=f"M3B4{uuid4().hex[:6]}")
    package = _package(db_session, project_p, leader_p)
    delivery_p = make_user(db_session, "fde_engineer")

    grant_package_access(
        db_session,
        package_id=package.id,
        user_id=delivery_p.id,
        role="delivery",
        granted_by_user_id=admin.id,
    )
    db_session.commit()

    events = _grant_events(db_session, admin, delivery_p.id)
    assert [event.event_type for event in events] == ["package_access_granted"]
    assert all(event.org_id is None for event in events)


# ---------------------------------------------------------------------------
# dispatch 访问面：package_access 是第三语义（无授权 ⇒ 404，不泄露存在性）
# ---------------------------------------------------------------------------


def test_dispatch_package_read_requires_package_access(client, db_session, settings):
    """无 package_access 授权行 ⇒ 交付包 404（不泄露包存在性）。"""
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B4{uuid4().hex[:6]}", org_id=org_b.id
    )
    package = _package(db_session, project_b, leader_b)
    outsider = make_user(db_session, "fde_engineer")

    blocked = client.get(
        f"/api/v1/dispatch/packages/{package.id}", headers=_auth(outsider, settings)
    )
    assert blocked.status_code == 404, blocked.get_data(as_text=True)

    # 授予只读授权后同一账号可读（阳性对照）
    grant_package_access(
        db_session,
        package_id=package.id,
        user_id=outsider.id,
        role="delivery",
        granted_by_user_id=admin.id,
    )
    db_session.commit()
    allowed = client.get(
        f"/api/v1/dispatch/packages/{package.id}", headers=_auth(outsider, settings)
    )
    assert allowed.status_code == 200, allowed.get_data(as_text=True)


def test_dispatch_package_read_admin_platform_semantics(client, db_session, settings):
    """admin 平台全局语义：未授权也可读交付包（§9.2③既有语义不变）。"""
    admin = make_user(db_session, "admin")
    leader_b = make_user(db_session, "project_lead")
    project_b = make_project(db_session, leader_b, code=f"M3B4{uuid4().hex[:6]}")
    package = _package(db_session, project_b, leader_b)

    response = client.get(
        f"/api/v1/dispatch/packages/{package.id}", headers=_auth(admin, settings)
    )
    assert response.status_code == 200, response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# users 域：批次②共享记录器接线顺带覆盖（admin 改别家企业账号）
# ---------------------------------------------------------------------------


def test_admin_cross_enterprise_user_update_leaves_cross_org_event(
    client, db_session, settings
):
    """admin 改**别家企业**账号 ⇒ ``cross_org_user_updated``（批次②接线覆盖）。"""
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)

    response = client.patch(
        f"/api/v1/users/{user_b.id}",
        json={"display_name": "隔离用例改名"},
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _grant_events(db_session, admin, user_b.id)
    assert [event.event_type for event in events] == ["cross_org_user_updated"]
    assert events[0].org_id == org_b.id


# ---------------------------------------------------------------------------
# auth 域：改密只认本人（主体归属）——隔离面由既有 ``test_auth_api.py`` 覆盖，
# 本批**核验销号不重复造例**（盘点表测试指针已指该套件）。
# ---------------------------------------------------------------------------
