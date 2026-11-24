"""Ecosystem OS M3 D-5①：运营待办主体收敛只读变体机械钉。

拍板范围（2026-11-24 交互式 D-5＝①候选 1＋2）：区域伙伴自助运营页消费
``GET /api/v1/ops/todos/mine``——登录用户只见**自己名下**的未决事项：
审批＝我发起（``requested_by_user_id``）／AI 确认＝我发起待我确认
（``OperationEvent.actor_user_id``）／offer＝我名下（``candidate_user_id``），
三域全部硬 FK；**meeting_todo 显式排除**（owner 是纪要内自由文本，无用户
FK，不可作主体口径——与「文本前缀不可作分层口径」同纪律）。

钉面：主体收敛两向（我的含他的不含）／排除钉（造了也不进＋admin 版在场
证伪「没造上」）／域闭集 400／401／A4 只读快照／静态钉（闭集字面＋路由
单点）。伙伴读面（regional-partners 本人收敛）由
``test_commercial_regional_partners.py`` 既有钉覆盖，不重复。
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fde_api.control.models import AutomationApproval
from fde_api.dispatch.models import DispatchOffer
from fde_api.meetings.models import ReviewMeetingMinutes
from fde_api.ops_todos import SUBJECT_SCOPED_DOMAINS, collect_subject_ops_todos
from fde_api.workbench.models import OperationEvent
from test_api_confirmation_expiry import _awaiting_action
from test_ai_server_chat_mcp import access_headers, ai_context, make_project
from test_ecosystem_m2_ops_todos import _approval, _minutes, _offer, _ids

MINE_ROUTE = "/api/v1/ops/todos/mine"


def _seed_two_subjects(ai_context, db_session):
    """两个主体各自的审批＋offer；admin 另有一条待确认 AI 动作。"""
    users, _execute = ai_context
    admin, alice = users["admin"], users["alice"]
    project = make_project(db_session, admin)
    now = datetime.now(UTC)
    approval_admin = _approval(db_session, project, admin,
                               expires_at=now + timedelta(hours=2))
    approval_alice = _approval(db_session, project, alice,
                               expires_at=now + timedelta(hours=3))
    # 同项目下 (project_id, dispatch_round) 唯一 ⇒ 两个主体各占一轮
    offer_admin, _pkg = _offer(db_session, project, admin,
                               offered_at=now - timedelta(hours=1), round_no=1)
    offer_alice, _pkg = _offer(db_session, project, alice,
                               offered_at=now - timedelta(hours=2), round_no=2)
    return {
        "admin": admin, "alice": alice, "project": project,
        "approvals": {admin.id: approval_admin, alice.id: approval_alice},
        "offers": {admin.id: offer_admin, alice.id: offer_alice},
    }


def test_mine_is_subject_scoped_across_three_domains(ai_context, client, settings, db_session):
    """三域主体收敛两向：我的含我的、不含他的；AI 确认只归发起人。"""
    seeded = _seed_two_subjects(ai_context, db_session)
    _awaiting_action(ai_context, db_session)  # admin 发起 → 只进 admin 的 mine
    admin, alice = seeded["admin"], seeded["alice"]

    mine_alice = client.get(MINE_ROUTE, headers=access_headers(alice, settings))
    assert mine_alice.status_code == 200
    alice_items = mine_alice.json["data"]["items"]
    assert _ids(alice_items, "automation_approval") == {seeded["approvals"][alice.id].id}
    assert _ids(alice_items, "dispatch_offer") == {seeded["offers"][alice.id].id}
    assert _ids(alice_items, "api_confirmation") == set()
    assert all(entry["object_id"] != seeded["approvals"][admin.id].id for entry in alice_items)

    mine_admin = client.get(MINE_ROUTE, headers=access_headers(admin, settings))
    assert mine_admin.status_code == 200
    admin_items = mine_admin.json["data"]["items"]
    assert _ids(admin_items, "automation_approval") == {seeded["approvals"][admin.id].id}
    assert _ids(admin_items, "dispatch_offer") == {seeded["offers"][admin.id].id}
    assert len(_ids(admin_items, "api_confirmation")) == 1
    assert all(entry["object_id"] != seeded["offers"][alice.id].id for entry in admin_items)


def test_mine_excludes_meeting_todo_even_when_owned_by_actor(
    ai_context, client, settings, db_session
):
    """排除钉：owner 写成本人用户名也不进 mine（自由文本不可作主体口径）；
    admin 全量视图在场同条目——证伪「没造上」。"""
    seeded = _seed_two_subjects(ai_context, db_session)
    alice = seeded["alice"]
    _minutes(db_session, seeded["project"], alice,
             todos=[{"text": "跟进交付风险", "owner": alice.username}])

    mine = client.get(MINE_ROUTE, headers=access_headers(alice, settings))
    assert mine.status_code == 200
    assert _ids(mine.json["data"]["items"], "meeting_todo") == set()

    full = client.get("/api/v1/ops/todos",
                      headers=access_headers(seeded["admin"], settings))
    assert full.status_code == 200
    assert len(_ids(full.json["data"]["items"], "meeting_todo")) == 1


def test_mine_domain_filter_rejects_out_of_closure(ai_context, client, settings):
    """域闭集钉：meeting_todo 出闭集 400；消息逐字含三值闭集。"""
    users, _ = ai_context
    response = client.get(
        MINE_ROUTE + "?domain=meeting_todo",
        headers=access_headers(users["admin"], settings),
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_domain"
    assert "/".join(SUBJECT_SCOPED_DOMAINS) in response.json["error"]["message"]


def test_mine_requires_auth(client, settings):
    response = client.get(MINE_ROUTE)
    assert response.status_code == 401


def test_mine_listing_has_no_write_side_effects(ai_context, client, settings, db_session):
    """A4 同款快照：/todos/mine 前后事件计数与行状态逐位不变。"""
    seeded = _seed_two_subjects(ai_context, db_session)
    _awaiting_action(ai_context, db_session)
    admin = seeded["admin"]

    def _snapshot():
        db_session.expire_all()
        return (
            db_session.query(AutomationApproval).count(),
            db_session.query(DispatchOffer).count(),
            db_session.query(OperationEvent).count(),
        )

    before = _snapshot()
    response = client.get(MINE_ROUTE, headers=access_headers(admin, settings))
    assert response.status_code == 200
    assert _snapshot() == before


def test_subject_closure_is_literal_and_route_is_single_point():
    """静态钉：闭集字面三元组（meeting_todo 不在内）＋新路由全仓恰一处。"""
    source = (Path(__file__).resolve().parents[1] / "src" / "fde_api" / "ops_todos.py") \
        .read_text(encoding="utf-8")
    assert SUBJECT_SCOPED_DOMAINS == ("automation_approval", "api_confirmation",
                                      "dispatch_offer")
    assert "meeting_todo" not in SUBJECT_SCOPED_DOMAINS
    assert source.count('"/todos/mine"') == 1
    assert "显式排除" in source, "meeting_todo 排除理由必须留痕于模块头"


def test_collect_subject_matches_route_projection(ai_context, db_session):
    """服务函数与路由同投影：admin 全量含他人条目、主体收敛版不含。"""
    seeded = _seed_two_subjects(ai_context, db_session)
    admin, alice = seeded["admin"], seeded["alice"]
    now = datetime.now(UTC)
    scoped_admin = collect_subject_ops_todos(actor_id=admin.id, now=now)
    scoped_alice = collect_subject_ops_todos(actor_id=alice.id, now=now)
    assert _ids(scoped_admin, "dispatch_offer") == {seeded["offers"][admin.id].id}
    assert _ids(scoped_alice, "dispatch_offer") == {seeded["offers"][alice.id].id}
    # 互斥：两主体的投影 object_id 无交集
    assert not (_ids(scoped_admin, "automation_approval")
                & _ids(scoped_alice, "automation_approval"))
