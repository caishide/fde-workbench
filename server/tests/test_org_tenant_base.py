"""多客户工作平台 M1：组织底座（orgs 表 + 三列归属 + 回填 + 审计维度）。

任务书 §7 M1 验收钉：
1. **迁移链干净**：additive 单迁移 up/down 对称；``orgs`` 表 + ``users.org_id``
   / ``projects.org_id`` / ``operation_events.org_id`` 三列（均 RESTRICT）；
   internal org 迁移播种；**存量项目回填 internal org**（幂等，重放安全）；
   **存量用户不回填**（org_id=NULL 平台身份拍板 §11-8）。
2. **归属戳单一入口**（orgs/org_scope.py，before_flush 会话级事件覆盖一切
   ORM 写路径）：leader 的 org → 项目归属；平台身份 leader → internal org；
   **显式 org_id 不被覆盖**；事件维度从项目归属推导，无 project 事件＝平台级
   （NULL）。
3. **「企业 A 建项目 → 企业 B 不可见」集成测试**（真实 API：POST /projects
   经服务层与归属戳，GET 列表/详情经既有 project_access 单一权威）。
4. 可辨变异：归属戳缺省（internal 兜底）/事件维度/回填 WHERE/显式 org 覆盖
   ——逐一摘除必转红（本地变异验证留痕，不入库）。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import INITIAL_PASSWORD
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.orgs.models import (
    INTERNAL_ORG_ID,
    INTERNAL_ORG_NAME,
    ORG_TYPE_ENTERPRISE,
    ORG_TYPE_INTERNAL,
    Org,
)
from fde_api.orgs.org_scope import (
    ensure_internal_org,
    org_of_project,
    orgs_of_user,
)
from fde_api.workbench.models import (
    ModuleCatalog,
    OperationEvent,
    Project,
    ProjectMember,
)
from test_migrations import (  # noqa: F401  (迁移种子助手单一权威)
    cleanup_seeded_rows,
    scalar,
    seed_project,
    seed_reference_data,
    seed_user_and_template,
    table_names,
)

SERVER_ROOT = Path(__file__).resolve().parents[1]
M1_MIGRATION = (
    SERVER_ROOT
    / "migrations"
    / "versions"
    / "a5e9c3f1b7d4_m1_org_tenant_base.py"
)
PROJECTS_URL = "/api/v1/projects"


def _make_org(session: Session, *, name: str, org_type: str = ORG_TYPE_ENTERPRISE) -> Org:
    org = Org(org_type=org_type, name=name)
    session.add(org)
    session.flush()
    return org


def _make_user(
    session: Session,
    *,
    username: str,
    role: str = "project_lead",
    org_id: str | None = None,
) -> User:
    user = User(
        username=username,
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    user.org_id = org_id
    session.add(user)
    session.flush()
    return user


def _headers(user: User, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _first_active_module_key(session: Session) -> str:
    module = session.scalar(
        select(ModuleCatalog).where(ModuleCatalog.is_active.is_(True))
    )
    assert module is not None
    return module.module_key


# ---------------------------------------------------------------------------
# 1. 结构与迁移链
# ---------------------------------------------------------------------------


def test_migration_seed_matches_model_constants():
    """迁移种子常量与 models 单一权威逐位一致（防两处漂移的文本钉）。"""
    body = M1_MIGRATION.read_text(encoding="utf-8")
    seeded_id = re.search(r'INTERNAL_ORG_ID = "([0-9a-f-]+)"', body)
    seeded_name = re.search(r'INTERNAL_ORG_NAME = "([^"]+)"', body)
    assert seeded_id is not None and seeded_id.group(1) == INTERNAL_ORG_ID
    assert seeded_name is not None and seeded_name.group(1) == INTERNAL_ORG_NAME


def test_internal_org_present_at_head(db_session: Session) -> None:
    org = db_session.get(Org, INTERNAL_ORG_ID)
    assert org is not None
    assert org.org_type == ORG_TYPE_INTERNAL
    assert org.name == INTERNAL_ORG_NAME
    assert org.created_by_user_id is None


def test_migration_roundtrip_backfills_projects_to_internal_org(
    alembic_config, engine
):
    """up/down 对称 + 存量项目回填 internal org + 存量用户不回填（重放幂等）。"""
    from alembic import command

    command.downgrade(alembic_config, "b7e4d1c9a3f2")
    assert "orgs" not in table_names(engine)
    ids = seed_user_and_template(engine, username="migration.fde-org-keep")
    project_id, sop_node_id = seed_project(
        engine, ids, project_code="FDE-ORG-KEEP"
    )

    command.upgrade(alembic_config, "head")

    assert {"orgs"} <= table_names(engine)
    assert (
        scalar(
            engine,
            "SELECT org_type FROM orgs WHERE id = :id",
            {"id": INTERNAL_ORG_ID},
        )
        == "internal"
    )
    # 存量项目 → internal org；存量用户 → 保持 NULL（平台身份不回填）
    assert (
        scalar(
            engine,
            "SELECT org_id FROM projects WHERE project_code='FDE-ORG-KEEP'",
        )
        == INTERNAL_ORG_ID
    )
    assert (
        scalar(
            engine,
            "SELECT org_id FROM users WHERE id = :id",
            {"id": ids["user_id"]},
        )
        is None
    )

    command.downgrade(alembic_config, "b7e4d1c9a3f2")

    assert "orgs" not in table_names(engine)
    assert "org_id" not in {
        column["name"] for column in inspect(engine).get_columns("projects")
    }
    assert (
        scalar(
            engine,
            "SELECT project_code FROM projects WHERE project_code='FDE-ORG-KEEP'",
        )
        == "FDE-ORG-KEEP"
    )

    command.upgrade(alembic_config, "head")

    # 重放幂等：回填再走一遍，结果一致
    assert (
        scalar(
            engine,
            "SELECT org_id FROM projects WHERE project_code='FDE-ORG-KEEP'",
        )
        == INTERNAL_ORG_ID
    )
    cleanup_seeded_rows(
        engine, ids, project_id=project_id, sop_node_id=sop_node_id
    )
    seed_reference_data(engine.url.render_as_string(hide_password=False))


# ---------------------------------------------------------------------------
# 2. orgs 表结构约束
# ---------------------------------------------------------------------------


def test_org_type_domain_is_closed(db_session: Session) -> None:
    db_session.add(Org(org_type="partner", name="越界类型"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_org_name_is_unique(db_session: Session) -> None:
    name = "重名企业测试"
    db_session.add(Org(org_type=ORG_TYPE_ENTERPRISE, name=name))
    db_session.add(Org(org_type=ORG_TYPE_ENTERPRISE, name=name))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_org_subject_key_unique_but_nullable_multi(db_session: Session) -> None:
    subject_key = "91350100M000100Y43"
    db_session.add(
        Org(org_type=ORG_TYPE_ENTERPRISE, name="主体键A", subject_key=subject_key)
    )
    db_session.flush()
    db_session.add(
        Org(org_type=ORG_TYPE_ENTERPRISE, name="主体键B", subject_key=subject_key)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    # 多行 NULL 共存（PG 可空唯一语义）
    db_session.add(Org(org_type=ORG_TYPE_INTERNAL, name="无主体键A"))
    db_session.add(Org(org_type=ORG_TYPE_INTERNAL, name="无主体键B"))
    db_session.flush()
    assert (
        db_session.scalar(
            select(func.count()).select_from(Org).where(Org.name.like("无主体键%"))
        )
        == 2
    )


# ---------------------------------------------------------------------------
# 3. 归属戳（orgs/org_scope.py 单一入口）
# ---------------------------------------------------------------------------


def test_platform_actor_project_stamps_internal_org(db_session: Session) -> None:
    """平台身份（org NULL）建项目 → 归 internal org（平台侧项目，ADR-M1 §3）。"""
    leader = _make_user(db_session, username="org.m1.platform-lead")
    project = Project(
        project_code="M1-PLAT-001",
        name="平台侧项目",
        enterprise_code="平台演示",
        planned_start_date=date(2026, 12, 1),
        leader_user_id=leader.id,
        template_snapshot={"modules": []},
    )
    db_session.add(project)
    db_session.flush()
    assert project.org_id == INTERNAL_ORG_ID
    assert org_of_project(project) == INTERNAL_ORG_ID


def test_enterprise_leader_project_stamps_own_org(db_session: Session) -> None:
    org_a = _make_org(db_session, name="归属企业A")
    leader_a = _make_user(
        db_session, username="org.m1.enterprise-lead", org_id=org_a.id
    )
    project = Project(
        project_code="M1-ORG-A-001",
        name="企业A项目",
        enterprise_code="客户A·制造·苏州",
        planned_start_date=date(2026, 12, 1),
        leader_user_id=leader_a.id,
        template_snapshot={"modules": []},
    )
    db_session.add(project)
    db_session.flush()
    assert project.org_id == org_a.id


def test_explicit_org_id_is_not_overridden(db_session: Session) -> None:
    """显式 org_id 不被归属戳覆盖（M2/M5 显式指定归属的前置语义）。"""
    org_platform = _make_org(
        db_session, name="显式指定平台", org_type=ORG_TYPE_INTERNAL
    )
    org_a = _make_org(db_session, name="显式指定企业A")
    leader = _make_user(
        db_session, username="org.m1.explicit-lead", org_id=org_a.id
    )
    project = Project(
        project_code="M1-EXPLICIT-001",
        name="显式归属项目",
        enterprise_code="客户B·行业·城市",
        planned_start_date=date(2026, 12, 1),
        leader_user_id=leader.id,
        org_id=org_platform.id,
        template_snapshot={"modules": []},
    )
    db_session.add(project)
    db_session.flush()
    assert project.org_id == org_platform.id


def test_operation_event_stamps_org_from_project(db_session: Session) -> None:
    """审计维度＝数据归属口径：有 project 的事件从项目归属推导。"""
    from fde_api.projects.events import record_event

    org_a = _make_org(db_session, name="事件归属企业A")
    leader_a = _make_user(
        db_session, username="org.m1.event-lead", org_id=org_a.id
    )
    project = Project(
        project_code="M1-EVENT-001",
        name="事件项目",
        enterprise_code="客户C·行业·城市",
        planned_start_date=date(2026, 12, 1),
        leader_user_id=leader_a.id,
        template_snapshot={"modules": []},
    )
    db_session.add(project)
    db_session.flush()
    event = record_event(db_session, leader_a, "project_created", project, {})
    db_session.flush()
    assert event.org_id == org_a.id


def test_platform_level_event_keeps_null_org(db_session: Session) -> None:
    """无 project 的事件＝平台级（org NULL，目标归属可从对象推导——ADR-M1 §4）。"""
    from fde_api.projects.events import record_event

    actor = _make_user(db_session, username="org.m1.platform-admin", role="admin")
    target = _make_user(db_session, username="org.m1.event-target")
    event = record_event(db_session, actor, "user_created", target, {})
    db_session.flush()
    assert event.project_id is None
    assert event.org_id is None


def test_orgs_of_user_direct_and_membership(db_session: Session) -> None:
    """``orgs_of(user) = [users.org_id] + 成员项目传递的 org``（去重保序）。"""
    org_a = _make_org(db_session, name="成员传递企业A")
    org_b = _make_org(db_session, name="直接归属企业B")
    # 平台身份用户：直接 org 为空，经成员项目传递拿到 org_a
    member = _make_user(db_session, username="org.m1.member-user", org_id=None)
    leader_a = _make_user(
        db_session, username="org.m1.member-lead", org_id=org_a.id
    )
    project = Project(
        project_code="M1-MEMBER-001",
        name="成员项目",
        enterprise_code="客户D·行业·城市",
        planned_start_date=date(2026, 12, 1),
        leader_user_id=leader_a.id,
        template_snapshot={"modules": []},
    )
    db_session.add(project)
    db_session.flush()
    db_session.add(
        ProjectMember(project_id=project.id, user_id=member.id, role="viewer")
    )
    db_session.flush()
    assert orgs_of_user(db_session, member.id) == [org_a.id]
    # 直接归属在前，成员传递在后（去重）
    dual = _make_user(db_session, username="org.m1.dual-user", org_id=org_b.id)
    db_session.add(
        ProjectMember(project_id=project.id, user_id=dual.id, role="viewer")
    )
    db_session.flush()
    assert orgs_of_user(db_session, dual.id) == [org_b.id, org_a.id]


def test_ensure_internal_org_is_idempotent(db_session: Session) -> None:
    first = ensure_internal_org(db_session)
    second = ensure_internal_org(db_session)
    assert first.id == second.id == INTERNAL_ORG_ID
    assert (
        db_session.scalar(
            select(func.count()).select_from(Org).where(Org.id == INTERNAL_ORG_ID)
        )
        == 1
    )
    # 创建分支（夹具里内部组织总在场，get 命中会掩盖 NameError 类缺陷——
    # 本分支由 mypy name-defined 钉补测）：先删行再 ensure，须以单一权威
    # 常量重建。
    from sqlalchemy import delete

    db_session.execute(delete(Org).where(Org.id == INTERNAL_ORG_ID))
    db_session.flush()
    rebuilt = ensure_internal_org(db_session)
    assert rebuilt.id == INTERNAL_ORG_ID
    assert rebuilt.org_type == ORG_TYPE_INTERNAL
    assert rebuilt.name == INTERNAL_ORG_NAME


# ---------------------------------------------------------------------------
# 4. 集成验收：企业 A 建项目 → 企业 B 不可见（真实 API + 真实归属戳）
# ---------------------------------------------------------------------------


def test_enterprise_a_project_invisible_to_enterprise_b(
    db_session: Session, client, settings
) -> None:
    # db_session 清理会带走模块目录（reference 种子逐测重灌的既有房法）
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    org_a = _make_org(db_session, name="集成企业A")
    org_b = _make_org(db_session, name="集成企业B")
    user_a = _make_user(db_session, username="org.m1.int-a", org_id=org_a.id)
    user_b = _make_user(db_session, username="org.m1.int-b", org_id=org_b.id)
    # API 请求走应用自己的会话——夹具侧数据先提交（既有房法：factory 即 commit）
    db_session.commit()
    module_key = _first_active_module_key(db_session)
    payload = {
        "name": "企业A交付项目",
        "enterprise_code": "客户A·制造·苏州",
        "planned_start_date": "2026-12-01",
        "leader_user_id": user_a.id,
        "module_keys": [module_key],
        "creation_source": "manual",
        "project_snapshot": {"modules": [{"module_key": module_key}]},
    }

    created = client.post(
        PROJECTS_URL, json=payload, headers=_headers(user_a, settings)
    )
    assert created.status_code == 201, created.get_json()
    project_id = created.get_json()["data"]["id"]
    project = db_session.get(Project, project_id)
    assert project is not None
    # 归属戳经真实服务路径落位：项目归属企业 A 的 org
    assert project.org_id == org_a.id

    # 企业 A 可见（leader 自动成员）；企业 B 全链路不可见（既有 project_access
    # 单一权威 + 非 200 拒绝——M1 只验证底座归位，不新增隔离逻辑）
    listed_a = client.get(PROJECTS_URL, headers=_headers(user_a, settings))
    assert listed_a.status_code == 200
    ids_a = [item["id"] for item in listed_a.get_json()["data"]["items"]]
    assert project_id in ids_a

    listed_b = client.get(PROJECTS_URL, headers=_headers(user_b, settings))
    assert listed_b.status_code == 200
    ids_b = [item["id"] for item in listed_b.get_json()["data"]["items"]]
    assert project_id not in ids_b

    detail_b = client.get(
        f"{PROJECTS_URL}/{project_id}", headers=_headers(user_b, settings)
    )
    assert detail_b.status_code in (403, 404)
    detail_a = client.get(
        f"{PROJECTS_URL}/{project_id}", headers=_headers(user_a, settings)
    )
    assert detail_a.status_code == 200

    # 审计维度：立项事件挂企业 A 的 org（数据归属口径）
    event = db_session.scalar(
        select(OperationEvent).where(
            OperationEvent.target_id == project_id,
            OperationEvent.event_type == "project_created",
        )
    )
    assert event is not None
    assert event.org_id == org_a.id
