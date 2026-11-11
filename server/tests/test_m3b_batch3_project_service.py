"""M3b 批次 ③（项目服务域 97 端点）越权、留痕与「单一可见性权威」机械闸。

依据：《M3a-隔离入口与装饰器扩展规格-v1》§3（服务层校验／跨 org 留痕 §3.4／
失败码闭集 §3.5／逐批验证方法 §3.6）＋ 2026-11-11 拍板（留痕触发面＝**企业 org
之间才算**；read-only 核验＝域级代表性用例进 CI）。

本批三件事：

1. **实改面＝成员面跨 org 留痕接线**（规格 §3.4 明列「成员跨企业授予」）：
   ``projects/events.py::record_event`` 的单点接线把**项目成员行**目标解析为其
   **账号**——平台/他企业 admin 把**别家企业**账号授予项目成员 ⇒ 事件名带
   ``cross_org_`` 前缀且 ``operation_events.org_id`` 取被作用账号归属。
   同企业内授予、平台身份账号授予 ⇒ 事件名逐字节不变（存量零回归）。
2. **机械闸＝「自建可见性谓词」全仓扫描**（把①-b 的教训固化为闸）：除统一入口
   ``projects/permissions.py`` 外，任何函数都不得拿 ``ProjectMember`` 的字段
   构造**可见性谓词**（比较形态）——eager load（取数）与归属戳计算不算。
3. **域级代表性越权用例**：跨企业**成员关系**场景（企业甲账号被平台授予企业乙
   项目的成员身份）——成员关系本身挡不住 org 维度，这才构成判别力。

**诚实边界**：项目域既有行为按规格 §3.5「既有项目域行为本轮不变」保持原样
（同项目无权＝403 ``forbidden``；跨 org 命中项目域沿用既有码），本批**不改写**
既有项目域错误码。
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.tokens import issue_access_token
from fde_api.orgs.models import INTERNAL_ORG_ID
from fde_api.workbench.models import OperationEvent

from multi_tenant_harness import (
    add_member,
    make_enterprise_org,
    make_project,
    make_user,
)

SERVER_SRC = Path(__file__).resolve().parents[1] / "src" / "fde_api"

# 「自建可见性谓词」扫描的**白名单**——逐条人工复核过（不是放行未查）：
#   1) documents/snapshots.py::_serialize_members —— 序列化既有成员行（非谓词）
#   2) orgs/org_scope.py::orgs_of_user —— 归属戳计算（成员项目传递 org，非可见性）
#   3) projects/gate_service.py::submit_gate_evidence —— 交付方身份标记
#      （项目访问判定已由 _load_project_for_gates 走统一入口完成）
#   4) users/service.py::update_user —— admin 改角色前的**成员关系冲突**检查
#      （写前约束，不是可见性规则）
_VISIBILITY_PREDICATE_EXCEPTIONS = {
    ("documents/snapshots.py", "_serialize_members"),
    ("orgs/org_scope.py", "orgs_of_user"),
    ("projects/gate_service.py", "submit_gate_evidence"),
    ("users/service.py", "update_user"),
}

_AUTHORITY_NAMES = {"project_access", "visible_project_filter", "visible_project_ids"}


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _mentions_project_member(node: ast.AST) -> bool:
    """谓词形态判据：``ProjectMember.<字段>`` 出现在比较式里。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in {
            "user_id",
            "project_id",
            "role",
        }:
            base = sub.value
            if isinstance(base, ast.Name) and base.id == "ProjectMember":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "ProjectMember":
                return True
    return False


def _self_built_visibility_predicates() -> list[tuple[str, str, int]]:
    """全仓扫描自建可见性谓词（返回 ``(相对路径, 函数名, 行号)``）。"""
    hits: list[tuple[str, str, int]] = []
    for path in sorted(SERVER_SRC.rglob("*.py")):
        if path.name == "permissions.py" and path.parent.name == "projects":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            used |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if used & _AUTHORITY_NAMES:
                continue
            if not any(
                isinstance(sub, ast.Compare) and _mentions_project_member(sub)
                for sub in ast.walk(node)
            ):
                continue
            rel = path.relative_to(SERVER_SRC).as_posix()
            hits.append((rel, node.name, node.lineno))
    return hits


@pytest.fixture
def cross_org_project(db_session):
    """企业甲账号（**跨企业成员**）＋ 企业乙项目（leader 为企业乙账号）。

    跨企业成员关系＝判别力关键场景（成员关系本身挡不住 org 维度）。
    """
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "fde_engineer", org_id=org_a.id)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B3{uuid4().hex[:6]}", org_id=org_b.id
    )
    add_member(db_session, project_b, user_a)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "leader_b": leader_b,
        "project_b": project_b,
    }


# ---------------------------------------------------------------------------
# 1. 机械闸：可见性规则单一权威
# ---------------------------------------------------------------------------


def test_no_self_built_visibility_predicate_outside_unified_entry():
    """除统一入口外，全仓不得自建 ``ProjectMember`` 可见性谓词。"""
    hits = _self_built_visibility_predicates()
    found = {(rel, name) for rel, name, _line in hits}
    unexpected = sorted(found - _VISIBILITY_PREDICATE_EXCEPTIONS)
    assert not unexpected, (
        "发现自建可见性谓词（须走 projects/permissions.py 统一入口）："
        f"{unexpected}"
    )
    stale = sorted(_VISIBILITY_PREDICATE_EXCEPTIONS - found)
    assert not stale, f"白名单条目已失效（须清理）：{stale}"


# ---------------------------------------------------------------------------
# 2. 跨 org 留痕：成员面（规格 §3.4「成员跨企业授予」）
# ---------------------------------------------------------------------------


def _member_events(db_session, actor, project_id: str) -> list[OperationEvent]:
    return list(
        db_session.scalars(
            select(OperationEvent)
            .where(
                OperationEvent.actor_user_id == actor.id,
                OperationEvent.target_type == "project_member",
                OperationEvent.project_id == project_id,
            )
            .order_by(OperationEvent.created_at, OperationEvent.id)
        ).all()
    )


def test_admin_cross_org_member_grant_leaves_cross_org_event(
    client, db_session, settings
):
    """平台 admin 把**别家企业**账号授予成员 ⇒ ``cross_org_`` 前缀＋org 维度。

    org 维度取**被作用账号归属**（企业丙），不是项目归属（企业乙）——口径与
    批次②的账号类代操作一致。
    """
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    org_c = make_enterprise_org(db_session)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B3{uuid4().hex[:6]}", org_id=org_b.id
    )
    newcomer_c = make_user(db_session, "fde_engineer", org_id=org_c.id)

    response = client.post(
        f"/api/v1/projects/{project_b.id}/members",
        json={
            "user_id": newcomer_c.id,
            "role": "member",
            "version": project_b.version,
        },
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _member_events(db_session, admin, project_b.id)
    assert [event.event_type for event in events] == [
        "cross_org_project_member_added"
    ], "跨企业成员授予未留痕（缺 cross_org_ 前缀事件）"
    assert events[0].org_id == org_c.id, "跨 org 事件的 org 维度须取被作用账号归属"
    assert events[0].changes["user_id"] == newcomer_c.id


def test_same_enterprise_member_grant_has_no_cross_org_prefix(
    client, db_session, settings
):
    """同企业内 admin 授予成员 ⇒ 不算跨 org（事件名逐字节不变）。"""
    org_b = make_enterprise_org(db_session)
    admin_b = make_user(db_session, "admin", org_id=org_b.id)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, leader_b, code=f"M3B3{uuid4().hex[:6]}", org_id=org_b.id
    )
    newcomer = make_user(db_session, "fde_engineer", org_id=org_b.id)

    response = client.post(
        f"/api/v1/projects/{project_b.id}/members",
        json={
            "user_id": newcomer.id,
            "role": "member",
            "version": project_b.version,
        },
        headers=_auth(admin_b, settings),
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _member_events(db_session, admin_b, project_b.id)
    assert [event.event_type for event in events] == ["project_member_added"]
    assert all(event.org_id == org_b.id for event in events)


def test_platform_identity_member_grant_has_no_cross_org_prefix(
    client, db_session, settings
):
    """平台身份账号被授予成员 ⇒ 不算跨 org（存量零回归钉）。"""
    admin = make_user(db_session, "admin")
    leader_p = make_user(db_session, "project_lead")
    project_p = make_project(db_session, leader_p, code=f"M3B3{uuid4().hex[:6]}")
    newcomer_p = make_user(db_session, "fde_engineer")

    response = client.post(
        f"/api/v1/projects/{project_p.id}/members",
        json={
            "user_id": newcomer_p.id,
            "role": "member",
            "version": project_p.version,
        },
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    events = _member_events(db_session, admin, project_p.id)
    assert [event.event_type for event in events] == ["project_member_added"]
    assert all(event.org_id == INTERNAL_ORG_ID for event in events)


# ---------------------------------------------------------------------------
# 3. 域级代表性越权用例（跨企业成员关系 ⇒ 项目域各读面一律收敛）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path_suffix",
    [
        "",
        "/gates",
        "/quotes",
        "/payments",
        "/contracts",
        "/members",
        "/tasks",
        "/gantt",
    ],
)
def test_cross_enterprise_member_blocked_from_project_reads(
    client, db_session, settings, cross_org_project, path_suffix
):
    """跨企业成员 ⇒ 项目域读面全部收敛（成员关系挡不住 org 维度）。"""
    project_b = cross_org_project["project_b"]
    user_a = cross_org_project["user_a"]
    leader_b = cross_org_project["leader_b"]

    path = f"/api/v1/projects/{project_b.id}{path_suffix}"
    blocked = client.get(path, headers=_auth(user_a, settings))
    assert blocked.status_code in (403, 404), (path, blocked.status_code)

    allowed = client.get(path, headers=_auth(leader_b, settings))
    assert allowed.status_code == 200, (path, allowed.get_data(as_text=True))


def test_cross_enterprise_member_cannot_grant_membership(
    client, db_session, settings, cross_org_project
):
    """跨企业成员 ⇒ 成员授予写面 403（成员关系不蕴含管理权）。"""
    project_b = cross_org_project["project_b"]
    user_a = cross_org_project["user_a"]
    newcomer = make_user(
        db_session, "fde_engineer", org_id=cross_org_project["org_b"].id
    )

    response = client.post(
        f"/api/v1/projects/{project_b.id}/members",
        json={"user_id": newcomer.id, "role": "member", "version": project_b.version},
        headers=_auth(user_a, settings),
    )
    assert response.status_code == 403, response.get_data(as_text=True)
