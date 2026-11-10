"""CR-063：list_projects 的 SQL 可见性预过滤 ⊆ visible_project_ids 单一权威。

projects/permissions.py 的权威注释（「不在 SQL 里重写第二套可见性规则」）
与 list_projects/control._project_scope 的 SQL 预过滤并存——现状语义重合
靠三条写路径不变量维持（leader 必须 admin/project_lead、降级受阻、成员行
禁降）。本对账钉把「重合」变成测试事实：任一写路径将来放宽导致幽灵行
（列表可见/详情 403），此钉先红。
"""
from __future__ import annotations

from uuid import uuid4

from test_agents_d4_harness import make_user  # noqa: F401  (pytest fixtures below)
from test_agents_d4_harness import d4_app, d4_client, d4_settings  # noqa: F401
from test_document_drafts_api import _persist_project

from fde_api.extensions import db
from fde_api.projects.permissions import visible_project_ids
from fde_api.projects.service import list_projects
from fde_api.workbench.models import ProjectMember


def _leader_client(db_session, d4_client, d4_settings):
    return make_user(db_session, "project_lead")


def test_list_projects_subset_of_visible_ids(db_session, d4_client, d4_settings) -> None:
    leader = _leader_client(db_session, d4_client, d4_settings)
    member = make_user(db_session, "fde_engineer")
    stranger = make_user(db_session, "fde_engineer")
    admin = make_user(db_session, "admin")

    p1 = _persist_project(db_session, leader, code=f"VP{uuid4().hex[:4]}·制造业·苏州")
    p2 = _persist_project(db_session, admin, code=f"VP{uuid4().hex[:4]}·制造业·苏州")
    db_session.add(ProjectMember(project_id=p2.id, user_id=member.id, role="member"))
    db_session.commit()

    for actor in (leader, member, stranger, admin):
        rows, _total = list_projects(actor=actor, query={"page": 1, "page_size": 50})
        listed = {row["id"] for row in rows}
        visible = set(visible_project_ids(db_session, actor))
        assert listed <= visible, (
            f"{actor.role} 列表出现 visible_project_ids 之外的幽灵行："
            f"{listed - visible}"
        )

    # 语义抽查（非空集才有对账意义）：
    # leader 只见自己挂帅的；member 只见自己是成员的；stranger 零可见。
    leader_rows, _ = list_projects(actor=leader, query={"page": 1, "page_size": 50})
    assert {r["id"] for r in leader_rows} == {p1.id}
    member_rows, _ = list_projects(actor=member, query={"page": 1, "page_size": 50})
    assert {r["id"] for r in member_rows} == {p2.id}
    stranger_rows, _ = list_projects(actor=stranger, query={"page": 1, "page_size": 50})
    assert stranger_rows == []
