"""M3a：org 维度隔离入口的机械钉（统一入口 SQL 下推 + 令牌口径）。

对应《M3a-隔离入口与装饰器扩展规格-v1》：

- §2 可见性的两个入口（列表级 SQL 下推 ``visible_project_ids`` ／ 对象级
  ``project_access``）**必须同语义**——否则出现「列表可见、详情 403」的
  幽灵行（``test_visibility_parity.py`` 老坑复发）；
- §1 org 三态语义（平台身份 ／ 企业身份 ／ 平台内部 org 桶）；
- §4 令牌 8 claim fail-closed，且**授权判定以读库值为准**（claim 只是
  15 分钟快照）。

越权套件本体见 ``test_cross_tenant_isolation.py``（M3c 骨架）。
"""
from __future__ import annotations

from uuid import uuid4

import jwt
from sqlalchemy import event, select

from fde_api.auth.decorators import require_auth
from fde_api.auth.tokens import issue_access_token
from fde_api.orgs.isolation import is_platform_identity, org_scope_allows
from fde_api.orgs.models import INTERNAL_ORG_ID
from fde_api.projects.permissions import project_access, visible_project_ids
from fde_api.workbench.models import Project

from multi_tenant_harness import (
    add_member,
    make_enterprise_org,
    make_project,
    make_user,
)


def _code() -> str:
    return f"M3{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# §2 可见性两入口同语义
# ---------------------------------------------------------------------------


def test_visible_project_ids_matches_project_access_parity(db_session) -> None:
    """列表级（SQL 下推）与对象级（project_access）可见集**逐位一致**。

    角色矩阵覆盖：admin／平台身份／企业身份 leader／企业身份成员／非成员／
    停用账号——任何一格两入口不一致即红（幽灵行防线）。
    """
    org = make_enterprise_org(db_session)
    leader = make_user(db_session, "project_lead", org_id=org.id)
    member = make_user(db_session, "fde_engineer", org_id=org.id)
    stranger = make_user(db_session, "fde_engineer", org_id=org.id)
    platform = make_user(db_session, "project_lead")
    admin = make_user(db_session, "admin")
    inactive = make_user(db_session, "fde_engineer", org_id=org.id)
    inactive.is_active = False
    db_session.commit()

    project = make_project(db_session, leader, code=_code(), org_id=org.id)
    add_member(db_session, project, member)

    all_projects = db_session.scalars(select(Project)).all()
    for actor in (leader, member, stranger, platform, admin, inactive):
        expected = {
            row.id
            for row in all_projects
            if project_access(actor, row).can_view
        }
        assert set(visible_project_ids(db_session, actor)) == expected, (
            f"{actor.role}/org={actor.org_id} 两入口可见集不一致："
            f"SQL 差集={set(visible_project_ids(db_session, actor)) - expected}"
        )


def test_cross_enterprise_member_cannot_see_other_org_project(db_session) -> None:
    """**核心隔离钉**：跨企业成员关系不构成跨企业可见性。

    企业甲的账号被（平台身份）加进企业乙的项目——按 org 归属维度收敛后
    不可见。摘除 org 谓词此钉即红（M3a 的判别力来源）。
    """
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "fde_engineer", org_id=org_a.id)
    leader_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(db_session, leader_b, code=_code(), org_id=org_b.id)
    add_member(db_session, project_b, user_a)

    assert project_b.id not in visible_project_ids(db_session, user_a)
    assert not project_access(user_a, project_b).can_view


def test_same_org_member_can_see_project(db_session) -> None:
    """同企业成员可见本企业项目（隔离不得误伤）。"""
    org = make_enterprise_org(db_session)
    user = make_user(db_session, "fde_engineer", org_id=org.id)
    leader = make_user(db_session, "project_lead", org_id=org.id)
    project = make_project(db_session, leader, code=_code(), org_id=org.id)
    add_member(db_session, project, user)

    assert project.id in visible_project_ids(db_session, user)
    assert project_access(user, project).can_view


def test_platform_identity_member_sees_project_across_org(db_session) -> None:
    """平台身份（org_id IS NULL）成员关系照旧可见——交付者跨企业服务不受限。"""
    org = make_enterprise_org(db_session)
    deliverer = make_user(db_session, "fde_engineer")
    leader = make_user(db_session, "project_lead", org_id=org.id)
    project = make_project(db_session, leader, code=_code(), org_id=org.id)
    add_member(db_session, project, deliverer)

    assert project.id in visible_project_ids(db_session, deliverer)
    assert project_access(deliverer, project).can_view


def test_enterprise_member_sees_internal_org_project(db_session) -> None:
    """平台立项桶（G6 通路：平台立项 → 企业账号作 viewer 成员）不得被隔离打断。"""
    enterprise = make_user(db_session, "viewer", org_id=make_enterprise_org(db_session).id)
    staff = make_user(db_session, "project_lead")
    project = make_project(db_session, staff, code=_code(), org_id=INTERNAL_ORG_ID)
    add_member(db_session, project, enterprise, role="viewer")

    assert project.id in visible_project_ids(db_session, enterprise)
    assert project_access(enterprise, project).can_view


def test_admin_sees_all_projects(db_session) -> None:
    """admin 是平台能力——可见性不受 org 约束（既有语义不变）。"""
    org = make_enterprise_org(db_session)
    admin = make_user(db_session, "admin")
    leader = make_user(db_session, "project_lead", org_id=org.id)
    project = make_project(db_session, leader, code=_code(), org_id=org.id)

    assert project.id in visible_project_ids(db_session, admin)
    assert project_access(admin, project).can_view


def test_inactive_actor_has_empty_visible_set(db_session) -> None:
    """停用账号可见集为空（既有语义不变）。"""
    org = make_enterprise_org(db_session)
    user = make_user(db_session, "fde_engineer", org_id=org.id)
    leader = make_user(db_session, "project_lead", org_id=org.id)
    project = make_project(db_session, leader, code=_code(), org_id=org.id)
    add_member(db_session, project, user)
    user.is_active = False
    db_session.commit()

    assert visible_project_ids(db_session, user) == []


# ---------------------------------------------------------------------------
# §2 SQL 下推（禁止「SQL 后再加一层 Python 过滤」，红线 10）
# ---------------------------------------------------------------------------


def test_visible_project_ids_pushes_predicate_into_sql(db_session) -> None:
    """可见性判定必须落在 SQL（成员 EXISTS 谓词 ＋ org 谓词都在查询里）。"""
    org = make_enterprise_org(db_session)
    user = make_user(db_session, "fde_engineer", org_id=org.id)
    leader = make_user(db_session, "project_lead", org_id=org.id)
    project = make_project(db_session, leader, code=_code(), org_id=org.id)
    add_member(db_session, project, user)

    statements: list[str] = []
    engine = db_session.get_bind()

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        visible_project_ids(db_session, user)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    sql = " ".join(statements).lower()
    assert statements, "未捕获到 SQL——可见集不得靠 Python 过滤拼装"
    assert "where" in sql, "可见性查询缺少 WHERE——退化成全表扫描"
    assert "project_members" in sql, "成员谓词未下推到 SQL"
    assert "org_id" in sql, "org 谓词未下推到 SQL"


# ---------------------------------------------------------------------------
# §1 org 三态语义（纯函数层）
# ---------------------------------------------------------------------------


def test_org_scope_three_states(db_session) -> None:
    """平台身份／企业身份／平台内部 org 桶的三态判定逐条钉死。"""
    org = make_enterprise_org(db_session)
    platform = make_user(db_session, "fde_engineer")
    enterprise = make_user(db_session, "fde_engineer", org_id=org.id)
    admin = make_user(db_session, "admin")

    assert is_platform_identity(platform) is True
    assert is_platform_identity(enterprise) is False
    assert is_platform_identity(admin) is True

    # 平台身份不受 org 限制
    assert org_scope_allows(platform, org.id) is True
    assert org_scope_allows(platform, INTERNAL_ORG_ID) is True
    # 企业身份：本企业 ＋ 平台内部桶 ＋ 平台级行可见，别家企业不可见
    assert org_scope_allows(enterprise, org.id) is True
    assert org_scope_allows(enterprise, INTERNAL_ORG_ID) is True
    assert org_scope_allows(enterprise, None) is True
    assert org_scope_allows(enterprise, "other-org-id") is False
    # admin 是平台能力
    assert org_scope_allows(admin, "other-org-id") is True


# ---------------------------------------------------------------------------
# §4 令牌口径：8 claim fail-closed ＋ 授权以读库值为准
# ---------------------------------------------------------------------------


def test_access_token_carries_org_id_claim(db_session, settings) -> None:
    """令牌携带 org_id claim（可空＝平台身份）。"""
    org = make_enterprise_org(db_session)
    enterprise = make_user(db_session, "viewer", org_id=org.id)
    platform = make_user(db_session, "viewer")

    enterprise_claims = jwt.decode(
        issue_access_token(enterprise, settings),
        settings.jwt_secret,
        algorithms=["HS256"],
        issuer="fde-workbench",
    )
    platform_claims = jwt.decode(
        issue_access_token(platform, settings),
        settings.jwt_secret,
        algorithms=["HS256"],
        issuer="fde-workbench",
    )

    assert enterprise_claims["org_id"] == org.id
    assert platform_claims["org_id"] is None


def test_token_without_org_id_claim_is_rejected(client, db_session, settings) -> None:
    """缺 org_id 的旧令牌一律 401（fail-closed：缺 claim 不得按平台身份放行）。"""
    user = make_user(db_session, "viewer")
    legacy_claims = {
        "sub": user.id,
        "role": user.role,
        "pwd": True,
        "ver": user.auth_version,
        "iat": 1_700_000_000,
        "exp": 4_100_000_000,
        "iss": "fde-workbench",
    }
    token = jwt.encode(legacy_claims, settings.jwt_secret, algorithm="HS256")

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "access_token_invalid"


def test_org_authority_reads_database_not_token_claim(app, db_session, settings) -> None:
    """**授权判定以读库值为准**——令牌 claim 只是快照，不作授权依据。

    场景：令牌签发后账号归属变更（企业甲 → 企业乙）⇒ 请求上下文里的 org
    必须是**库里的新值**，否则陈旧令牌即越权通行证。
    """
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user = make_user(db_session, "viewer", org_id=org_a.id)
    token = issue_access_token(user, settings)

    user.org_id = org_b.id
    db_session.commit()

    claims = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], issuer="fde-workbench"
    )
    assert claims["org_id"] == org_a.id  # 快照仍是旧 org

    with app.test_request_context(
        "/api/v1/projects", headers={"Authorization": f"Bearer {token}"}
    ):
        from flask import g

        @require_auth
        def _probe():
            return g.current_user_org_id

        assert _probe() == org_b.id
