"""Ecosystem OS M2 WP-2：运营待办只读聚合视图机械钉（立项书 §四 A4/A6）。

验收落点：A4＝视图只读（路由零写副作用、无人工确认不得产生执行结果、
不进 AI 目录）；A6＝零真相层引用、零事件追加。另钉跨视图一致性（与
expirations 三域谓词同源：审批/确认等集、offer 超集）与 queue 归类闭集
（V1.0 §4.3 六类，权威＝岗位卡装载器常量）。
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from fde_api.agents.hq_cards import HUMAN_APPROVAL_QUEUE
from fde_api.control.api_catalog import CATALOG
from fde_api.control.models import AutomationApproval
from fde_api.dispatch.models import DeliveryPackage, DispatchOffer
from fde_api.expirations import CONFIRMATION_SCAN_LIMIT, collect_expiration_entries
from fde_api.meetings.models import ReviewMeeting, ReviewMeetingMinutes
from fde_api.ops_todos import (
    DEFAULT_LIMIT,
    DOMAIN_QUEUES,
    MEETING_TODO_LOOKBACK_DAYS,
    MEETING_TODO_STATE,
    TITLE_MAX_CHARS,
    collect_ops_todos,
    validate_queue_mapping,
)
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import OperationEvent
from test_api_confirmation_expiry import _awaiting_action
from test_ai_server_chat_mcp import access_headers, ai_context, make_project

OPS_ROUTE = "/api/v1/ops/todos"
REQUIRED_KEYS = {"domain", "object_id", "title", "deadline_at", "state", "queue"}


def _approval(db_session, project, user, *, expires_at, status="pending"):
    row = AutomationApproval(project_id=project.id, requested_by_user_id=user.id,
        request_key=f"req-{uuid4().hex[:12]}", capability="solutions.export_sow",
        tool_name="export_sow", arguments_json={}, arguments_sha256="a" * 64,
        risk_level=3, status=status, expires_at=expires_at)
    db_session.add(row)
    db_session.commit()  # 投影走独立会话（读已提交），必须先提交
    return row


def _offer(db_session, project, candidate, *, mode="assign", offered_at,
           response_window_hours=24, status="offered", round_no=1):
    solution = ProjectSolution(project_id=project.id, name="待办测试方案",
        owner_user_id=project.leader_user_id)
    db_session.add(solution)
    db_session.flush()
    package = DeliveryPackage(id=uuid4().hex, solution_id=solution.id,
        project_id=project.id, package_code="PKJ-" + uuid4().hex[:8].upper(),
        dispatch_status="offered", dispatch_round=round_no,
        response_window_hours=response_window_hours)
    db_session.add(package)
    db_session.flush()
    offer = DispatchOffer(package_id=package.id, dispatch_round=round_no,
        candidate_user_id=candidate.id, status=status, offered_at=offered_at,
        match_breakdown={"mode": mode})
    db_session.add(offer)
    db_session.commit()
    return offer, package


def _minutes(db_session, project, user, *, todos, created_at=None):
    meeting = ReviewMeeting(project_id=project.id, template_id="T2-lite",
        hosted_by_user_id=user.id, topic_refs={}, turn_budget=2)
    db_session.add(meeting)
    db_session.flush()
    row = ReviewMeetingMinutes(meeting_id=meeting.id, consensus=[], disputes=[],
        todos=todos, sealed_sha256="b" * 64)
    if created_at is not None:
        row.created_at = created_at  # 投影按 created_at 回看，直设以固定窗口
    db_session.add(row)
    db_session.commit()
    return row


def _ids(entries, domain):
    return {entry["object_id"] for entry in entries if entry["domain"] == domain}


# ---------------------------------------------------------------- A4 只读纪律
def test_admin_only_and_six_field_shape(ai_context, client, settings, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    _approval(db_session, project, admin,
              expires_at=datetime.now(UTC) + timedelta(hours=2))
    denied = client.get(OPS_ROUTE, headers=access_headers(users["alice"], settings))
    assert denied.status_code == 403
    assert denied.json["error"]["code"] == "forbidden"
    allowed = client.get(OPS_ROUTE, headers=access_headers(admin, settings))
    assert allowed.status_code == 200
    items = allowed.json["data"]["items"]
    assert len(items) == allowed.json["data"]["total"] == 1
    assert set(items[0]) == REQUIRED_KEYS
    assert items[0]["domain"] == "automation_approval"
    assert items[0]["title"] == "solutions.export_sow"  # 审批域标题＝能力名
    assert items[0]["state"] == "pending"
    assert items[0]["queue"] == DOMAIN_QUEUES["automation_approval"]


def test_listing_has_no_write_side_effects(ai_context, client, settings, db_session):
    """A4：列待办零副作用——审批/offer/纪要状态不翻转、事件计数不变。"""
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    now = datetime.now(UTC)
    _approval(db_session, project, admin, expires_at=now + timedelta(hours=2))
    _offer(db_session, project, users["alice"], offered_at=now - timedelta(hours=1))
    _minutes(db_session, project, admin, todos=[{"text": "跟进交付风险"}])
    _awaiting_action(ai_context, db_session)

    def _snapshot():
        db_session.expire_all()
        approval = db_session.query(AutomationApproval).one()
        offer = db_session.query(DispatchOffer).one()
        minutes = db_session.query(ReviewMeetingMinutes).one()
        events = db_session.query(OperationEvent).count()
        return (approval.status, offer.status, minutes.todos, events)

    before = _snapshot()
    response = client.get(OPS_ROUTE, headers=access_headers(admin, settings))
    assert response.status_code == 200
    assert len(response.json["data"]["items"]) == 4  # 四域各一条
    assert _snapshot() == before  # 状态与事件计数逐位不变


def test_module_source_is_read_only_and_truth_layer_free():
    """A4/A6 静态钉：零真相层 token、零发信通道、零写路径原语。

    WP-3 换代：``record_event`` 从全禁改为**单点许可**——简报生成留痕是
    模块内唯一合法事件写入（恰一次调用、事件名钉死）；待办视图路径零写
    副作用由行为钉另行保证。
    """
    source = (Path(__file__).resolve().parents[1] / "src" / "fde_api" / "ops_todos.py") \
        .read_text(encoding="utf-8")
    for token in ("D:\\test\\FDE", "D:/test/FDE", "fdeops", "openfde"):
        assert token not in source, f"不得触真相层：{token}"
    assert "send_email" not in source and "fde_api.mailing" not in source, "零发信通道"
    for primitive in ("commit(", "session.add", ".delete(", "flush("):
        assert primitive not in source, f"只读模块不得含写路径原语：{primitive}"
    assert source.count("record_event(") == 1, "事件写入只许简报留痕单点"
    assert '"ops_brief_generated"' in source, "事件名钉死"


def test_route_not_in_ai_catalog():
    """A4：人工运营管理面不进 AI 目录（AI 不经目录不可调用本视图）。"""
    for row in CATALOG.values():
        assert not row["path"].startswith("/api/v1/ops"), row["path"]


#: 桌面端引用运营路由的唯一许可面（M2 WP-5 呈现面板）。
DESKTOP_OPS_PANEL = "desktop/src/renderer/src/system/OpsBriefPanel.tsx"


def _desktop_files_referencing(literal: str) -> set[str]:
    desktop_src = Path(__file__).resolve().parents[2] / "desktop" / "src"
    hits = set()
    for path in desktop_src.rglob("*.ts*"):
        if literal in path.read_text(encoding="utf-8", errors="ignore"):
            hits.add(path.relative_to(desktop_src.parents[1]).as_posix())
    return hits


def test_desktop_ops_route_reference_is_closed_to_presentation_panel():
    """A8 换代钉（WP-5 落地后）：路由字面量**只许**出现在呈现面板单点。

    批次二 WP-2 初版＝「桌面零引用」（WP-5 未做时的阶段性守卫，WP-5 挂面板
    即按设计转红——CI 实录）。换代不删钉、不放宽：语义从「零处」收紧为
    「引用闭集＝{呈现面板}」——守住「不在别处长出第二个调用点」。
    """
    assert _desktop_files_referencing(OPS_ROUTE) == {DESKTOP_OPS_PANEL}


# ------------------------------------------------------- queue 归类闭集（V1.0 §4.3）
def test_domain_queue_mapping_is_declared_closure():
    """域级归类口径钉死（变更须同步 PROGRESS 批次二节与任务书评审）。"""
    assert DOMAIN_QUEUES == {
        "automation_approval": "production_data_writes",
        "api_confirmation": "production_data_writes",
        "dispatch_offer": None,
        "meeting_todo": None,
    }


def test_queue_mapping_validated_at_module_import():
    """boot fail-fast：模块导入即校验 queue 映射闭集（源码静态钉）。"""
    source = (Path(__file__).resolve().parents[1] / "src" / "fde_api" / "ops_todos.py") \
        .read_text(encoding="utf-8")
    assert "\nvalidate_queue_mapping()\n" in source


def test_queue_mapping_stays_inside_v1_closure(monkeypatch):
    """queue 归类映射必须落在六类闭集内；闭集权威＝岗位卡装载器常量。"""
    validate_queue_mapping()  # 现行映射全过
    for queue in DOMAIN_QUEUES.values():
        assert queue is None or queue in HUMAN_APPROVAL_QUEUE
    monkeypatch.setitem(DOMAIN_QUEUES, "dispatch_offer", "bogus_queue")
    with pytest.raises(RuntimeError) as error:
        validate_queue_mapping()
    assert "bogus_queue" in str(error.value)


def test_four_domains_projected_with_declared_queues(ai_context, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    _approval(db_session, project, admin, expires_at=now + timedelta(hours=2))
    _offer(db_session, project, users["alice"], offered_at=now - timedelta(hours=1))
    _minutes(db_session, project, admin, todos=[{"text": "补齐验收材料"}])
    _awaiting_action(ai_context, db_session)
    entries = collect_ops_todos()
    assert {entry["domain"] for entry in entries} == set(DOMAIN_QUEUES)
    view = {entry["domain"]: entry for entry in entries}
    assert view["automation_approval"]["state"] == "pending"
    assert view["api_confirmation"]["state"] == "awaiting_confirmation"
    assert view["dispatch_offer"]["state"] == "offered"
    assert view["meeting_todo"]["state"] == MEETING_TODO_STATE
    for entry in entries:
        if entry["queue"] is not None:
            assert entry["queue"] in HUMAN_APPROVAL_QUEUE


# ------------------------------------------------- 跨视图一致性（与 expirations 同源）
def test_approval_domain_matches_expiration_projection(ai_context, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    _approval(db_session, project, admin, expires_at=now + timedelta(hours=2))
    _approval(db_session, project, admin, expires_at=now - timedelta(minutes=1),
              status="approved")  # 终态两边都不收
    ops = collect_ops_todos(domain="automation_approval")
    expiry = collect_expiration_entries(domain="automation_approval")
    assert _ids(ops, "automation_approval") == _ids(expiry, "automation_approval")


def test_confirmation_domain_shares_window_and_scan_authority(
    ai_context, db_session, monkeypatch
):
    users, _execute = ai_context
    _user, _project, identifier, _password = _awaiting_action(ai_context, db_session)
    first_ops = collect_ops_todos(domain="api_confirmation")
    assert len(first_ops) == 1
    monkeypatch.setattr("fde_api.control.api_actions.CONFIRMATION_WINDOW",
                        timedelta(minutes=30))
    second_ops = collect_ops_todos(domain="api_confirmation")
    second_expiry = collect_expiration_entries(domain="api_confirmation")
    # 窗口单一权威：monkeypatch 后两投影逐位同位移、同值。
    assert second_ops[0]["deadline_at"] == second_expiry[0]["deadline_at"]
    from datetime import datetime as _dt
    shift = (_dt.fromisoformat(second_ops[0]["deadline_at"])
             - _dt.fromisoformat(first_ops[0]["deadline_at"]))
    assert shift == timedelta(minutes=15)
    # 扫描上限共用 expirations 同一常量（防两处各养一份）。
    from fde_api import ops_todos
    assert ops_todos.CONFIRMATION_SCAN_LIMIT == CONFIRMATION_SCAN_LIMIT


def test_decided_confirmation_not_a_todo(ai_context, db_session):
    """已有结果的确认不再是待办（与 pending 列表同则）。"""
    users, _execute = ai_context
    admin = users["admin"]
    _user, _project, identifier, password = _awaiting_action(ai_context, db_session)
    assert len(collect_ops_todos(domain="api_confirmation")) == 1
    from fde_api.control.api_actions import decide_action
    assert decide_action(admin, identifier, password)["status"] == "completed"
    assert collect_ops_todos(domain="api_confirmation") == []


def test_offer_domain_is_superset_of_expiration_projection(ai_context, db_session):
    """待发现语义：无响应窗口的 offer 入本视图、不入到期投影（有期限集相等）。"""
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    offer, package = _offer(db_session, project, users["alice"],
                            offered_at=now - timedelta(hours=1))
    open_offer, _open_package = _offer(db_session, project, users["alice"],
                                       offered_at=None, response_window_hours=None,
                                       round_no=2)
    ops = collect_ops_todos(domain="dispatch_offer")
    expiry = collect_expiration_entries(domain="dispatch_offer")
    assert _ids(expiry, "dispatch_offer") == {offer.id}
    assert _ids(ops, "dispatch_offer") == {offer.id, open_offer.id}
    no_deadline = [row for row in ops if row["object_id"] == open_offer.id]
    assert no_deadline[0]["deadline_at"] is None


# ----------------------------------------------------- 纪要待办回看窗与投影形状
def test_meeting_todos_shape_owner_prefix_and_truncation(ai_context, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    long_text = "跟" * (TITLE_MAX_CHARS + 10)
    _minutes(db_session, project, admin, todos=[
        {"text": "补齐验收材料", "owner": "交付协调员"},
        {"text": long_text},
        {"n_text": "畸形行缺 text"},  # 畸形行防御性跳过
    ])
    entries = collect_ops_todos(domain="meeting_todo")
    assert len(entries) == 2
    first, second = entries
    assert first["object_id"].endswith(":0") and second["object_id"].endswith(":1")
    assert first["title"] == "[交付协调员] 补齐验收材料"
    assert second["title"] == "跟" * TITLE_MAX_CHARS + "…"
    assert len(second["title"]) == TITLE_MAX_CHARS + 1
    assert first["deadline_at"] is None and first["state"] == MEETING_TODO_STATE == "open"
    # 复合 object_id 全局唯一（同一纪要多条待办不撞号）。
    all_ids = [entry["object_id"] for entry in collect_ops_todos()]
    assert len(all_ids) == len(set(all_ids))


def test_meeting_todos_lookback_window(ai_context, db_session):
    """todos 无完成态位 ⇒ 只收回看窗内封存的纪要（边界 inclusive）。

    造数用**字面天数**（30/31），不用常量——否则常量变异时测试跟着漂移
    （恒真，变异幸存；本文件变异验证第 5 条实录）。
    """
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    _minutes(db_session, project, admin, todos=[{"text": "窗口内待办"}],
             created_at=now - timedelta(days=30))
    # 注入同一 now 固定窗口边界（等于回看窗边界也算窗内）。
    assert len(collect_ops_todos(domain="meeting_todo", now=now)) == 1
    assert MEETING_TODO_LOOKBACK_DAYS == 30  # 回看窗口径钉死（变更须回写 PROGRESS）
    _minutes(db_session, project, admin, todos=[{"text": "窗外陈旧待办"}],
             created_at=now - timedelta(days=31))
    assert len(collect_ops_todos(domain="meeting_todo", now=now)) == 1


# --------------------------------------------------------------- 排序与路由过滤
def test_sort_none_deadline_last_and_filters(ai_context, client, settings, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    due_offer, _pkg = _offer(db_session, project, users["alice"],
                             offered_at=now - timedelta(hours=25),
                             response_window_hours=24)  # deadline = now-1h（已到期）
    fresh_offer, _pkg2 = _offer(db_session, project, users["alice"],
                                offered_at=now - timedelta(hours=1),
                                response_window_hours=24, round_no=2)  # deadline = now+23h
    _approval(db_session, project, admin, expires_at=now + timedelta(hours=2))
    _minutes(db_session, project, admin, todos=[{"text": "无期限待办"}])
    entries = collect_ops_todos(now=now)
    # deadline 升序：到期 offer < 审批(+2h) < 未到期 offer(+23h)，无期限沉底。
    assert [entry["domain"] for entry in entries] == [
        "dispatch_offer", "automation_approval", "dispatch_offer", "meeting_todo",
    ]
    assert entries[-1]["deadline_at"] is None

    only_due = client.get(f"{OPS_ROUTE}?due=true",
                          headers=access_headers(admin, settings))
    items = only_due.json["data"]["items"]
    assert len(items) == 1 and items[0]["object_id"] == due_offer.id
    assert all(row["deadline_at"] is not None for row in items)
    assert "meeting_todo" not in {row["domain"] for row in items}

    only_domain = client.get(f"{OPS_ROUTE}?domain=meeting_todo",
                             headers=access_headers(admin, settings))
    assert {row["domain"] for row in only_domain.json["data"]["items"]} == {"meeting_todo"}

    limited = client.get(f"{OPS_ROUTE}?limit=1", headers=access_headers(admin, settings))
    assert limited.json["data"]["total"] == 1
    assert limited.json["data"]["items"][0]["object_id"] == due_offer.id
    assert fresh_offer.id != due_offer.id

    for query, code in (("domain=bogus", "invalid_domain"), ("due=maybe", "invalid_request"),
                        ("limit=abc", "invalid_request"), ("limit=501", "invalid_request")):
        response = client.get(f"{OPS_ROUTE}?{query}",
                              headers=access_headers(admin, settings))
        assert response.status_code == 400, query
        assert response.json["error"]["code"] == code, query


def test_default_limit_constant_matches_projection_budget(ai_context, db_session):
    assert DEFAULT_LIMIT == 100  # 路由缺省截断与 expirations 同款保守值
