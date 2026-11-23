"""Ecosystem OS M2 WP-3：运营简报确定性聚合机械钉（立项书 §四 A5/A6）。

验收落点：A5＝简报产出走既有文档/发信面零新通道（**系统内不存在简报直发
通道**：发信服务函数包外业务调用方闭集不变；本模块零发信引用）；A6＝生成
动作留痕（``ops_brief_generated`` 事件，changes 只带计数与指纹不带正文）＋
零真相层。简报本体＝返件式零落库（确定性聚合：待办条目＋招商漏斗计数＋需
总部介入事项；数字全部数据库现算，零模型调用——运营值班员卡拍板定稿＝纯
确定性聚合卡）。

造数纪律：凡钉「常量值」的断言一律字面造数（变异验证教训——用常量造数则
常量变异时测试跟着漂移恒真）。
"""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fde_api.commercial.models import RegionalPartner
from fde_api.dispatch.models import FdeProfile
from fde_api.meetings.models import ReviewMeetingMinutes
from fde_api.ops_todos import (
    BRIEF_DUE_LIST_LIMIT,
    BRIEF_TODO_TOP_LIMIT,
    compose_ops_brief,
)
from fde_api.workbench.models import OperationEvent
from test_ai_server_chat_mcp import access_headers, ai_context, make_project
from test_ecosystem_m2_ops_todos import _approval, _minutes, _offer

BRIEF_ROUTE = "/api/v1/ops/briefs/generate"
RESPONSE_KEYS = {
    "brief_markdown",
    "brief_sha256",
    "todo_total",
    "due_total",
    "funnel",
    "generated_at",
}


def _partner(db_session, user, *, stage="city_observer"):
    row = RegionalPartner(partner_code="PT-" + uuid4().hex[:8].upper(),
        region_name="广东省", applicant_user_id=user.id, stage=stage)
    db_session.add(row)
    db_session.commit()  # 简报走独立会话（读已提交），必须先提交
    return row


def _profile(db_session, user, *, status="active"):
    row = FdeProfile(user_id=user.id, status=status)
    db_session.add(row)
    db_session.commit()
    return row


# ---------------------------------------------------------------- 路由闸与形状
def test_admin_only_and_response_shape(ai_context, client, settings, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    _approval(db_session, project, admin,
              expires_at=datetime.now(UTC) + timedelta(hours=2))
    denied = client.post(BRIEF_ROUTE, headers=access_headers(users["alice"], settings))
    assert denied.status_code == 403
    assert denied.json["error"]["code"] == "forbidden"
    allowed = client.post(BRIEF_ROUTE, headers=access_headers(admin, settings))
    assert allowed.status_code == 200
    data = allowed.json["data"]
    assert set(data) == RESPONSE_KEYS
    assert set(data["funnel"]) == {
        "delivery_packages", "dispatch_offers", "regional_partners", "fde_profiles",
    }
    unauth = client.post(BRIEF_ROUTE)
    assert unauth.status_code == 401


def test_brief_counts_and_markdown_sections(ai_context, client, settings, db_session):
    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    _approval(db_session, project, admin,
              expires_at=now - timedelta(minutes=30))  # 已到期（仍 pending）
    _approval(db_session, project, admin,
              expires_at=now + timedelta(hours=2))  # 未到期
    _offer(db_session, project, users["alice"], mode="assign",
           offered_at=now - timedelta(hours=25),
           response_window_hours=24)  # deadline = now-1h（已到期）
    _minutes(db_session, project, admin, todos=[{"text": "补齐验收材料"}])  # 无期限
    _partner(db_session, admin, stage="city_observer")
    _profile(db_session, users["alice"], status="active")

    response = client.post(BRIEF_ROUTE, headers=access_headers(admin, settings))
    assert response.status_code == 200
    data = response.json["data"]
    assert data["todo_total"] == 4 and data["due_total"] == 2
    markdown = data["brief_markdown"]
    # 三个小节按序在场；分域计数逐字命中（造数 4 项：审批 2／offer 1／纪要 1）
    assert markdown.index("## 一、运营待办（共 4 项，已到期 2 项）") < \
        markdown.index("## 二、招商漏斗") < markdown.index("## 三、需总部介入事项")
    assert "- automation_approval：2 项" in markdown
    assert "- dispatch_offer：1 项" in markdown
    assert "- meeting_todo：1 项" in markdown
    assert "api_confirmation" not in markdown.split("## 二、")[0].split("## 一、")[1], \
        "未播种的域不得凭空出现"
    # 漏斗段逐字命中（状态名排序渲染）
    assert "- 交付包：offered 1" in markdown
    assert "- 派单 offer：offered 1" in markdown
    assert "- 区域伙伴：city_observer 1" in markdown
    assert "- 交付者档案：active 1" in markdown
    # 需介入清单逐条带域与队列归类
    assert "[automation_approval｜production_data_writes]" in markdown
    assert "[dispatch_offer｜运营协调]" in markdown
    assert "系统无简报直发通道" in markdown


def test_due_boundary_is_inclusive(ai_context, db_session):
    """到期判定＝deadline <= now（等于边界也到期，与 expirations 投影同则）。"""
    users, _execute = ai_context
    admin = users["admin"]
    moment = datetime(2026, 11, 24, 9, 0, 0, tzinfo=UTC)
    project = make_project(db_session, admin)
    _approval(db_session, project, admin, expires_at=moment)
    brief = compose_ops_brief(now=moment)
    assert brief["todo_total"] == 1 and brief["due_total"] == 1


def test_brief_deterministic_and_fingerprinted(ai_context, db_session):
    """同一数据库状态 + 同一 now ⇒ 简报逐字节同文、指纹一致。"""
    import hashlib as _hashlib

    users, _execute = ai_context
    admin = users["admin"]
    now = datetime.now(UTC)
    project = make_project(db_session, admin)
    _minutes(db_session, project, admin, todos=[{"text": "跟进交付风险", "owner": "交付"}])
    first = compose_ops_brief(now=now)
    second = compose_ops_brief(now=now)
    assert first["brief_markdown"] == second["brief_markdown"]
    assert first["brief_sha256"] == second["brief_sha256"]
    assert first["brief_sha256"] == _hashlib.sha256(
        first["brief_markdown"].encode("utf-8")).hexdigest()


# ------------------------------------------------------------- A5 零新发信通道
def test_send_email_business_caller_closure_unchanged():
    """A5：包外业务调用方闭集＝仅注册验证邮件；简报不新增任何调用方。"""
    src = Path(__file__).resolve().parents[1] / "src" / "fde_api"
    hits = {
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "send_email(" in path.read_text(encoding="utf-8")
    }
    assert hits == {
        "mailing/service.py",       # 定义处
        "mailing/ses_client.py",    # SES 传输层实现（botocore 客户端方法）
        "registration/service.py",  # 包外唯一业务调用方（注册验证邮件）
    }
    outside = {hit for hit in hits if not hit.startswith("mailing/")}
    assert outside == {"registration/service.py"}
    assert "ops_todos.py" not in hits


def test_desktop_zero_reference_briefs():
    """A8 延续：桌面端零引用简报路由（WP-5 才挂呈现）。"""
    desktop_src = Path(__file__).resolve().parents[2] / "desktop" / "src"
    for path in desktop_src.rglob("*.ts*"):
        assert BRIEF_ROUTE not in path.read_text(encoding="utf-8", errors="ignore"), path


# --------------------------------------------------------------- A6 留痕与只读面
def test_event_metadata_without_full_text(ai_context, client, settings, db_session):
    """A6：生成留痕单条，changes 只带计数与 sha256 指纹，正文不落 changes。"""
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    _minutes(db_session, project, admin, todos=[{"text": "机密交付细节文本标记"}])
    response = client.post(BRIEF_ROUTE, headers=access_headers(admin, settings))
    assert response.status_code == 200
    db_session.expire_all()
    rows = db_session.query(OperationEvent) \
        .filter_by(event_type="ops_brief_generated").all()
    assert len(rows) == 1
    event = rows[0]
    data = response.json["data"]
    assert event.changes["brief_sha256"] == data["brief_sha256"]
    assert event.changes["todo_total"] == data["todo_total"]
    assert event.changes["due_total"] == data["due_total"]
    assert "运营简报" not in json.dumps(event.changes, ensure_ascii=False, default=str)
    assert event.changes["brief_sha256"] == hashlib.sha256(
        data["brief_markdown"].encode("utf-8")).hexdigest()


def test_route_write_scope_zero_business_writes(ai_context, client, settings, db_session):
    """返件式零落库：简报生成只 +1 事件，业务表零写入。"""
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    now = datetime.now(UTC)
    _approval(db_session, project, admin, expires_at=now + timedelta(hours=2))
    _offer(db_session, project, users["alice"], offered_at=now - timedelta(hours=1))
    _minutes(db_session, project, admin, todos=[{"text": "跟进"}])
    _partner(db_session, admin)
    _profile(db_session, users["alice"])

    from fde_api.control.models import AutomationApproval
    from fde_api.dispatch.models import DeliveryPackage, DispatchOffer

    def _snapshot():
        db_session.expire_all()
        return (
            db_session.query(AutomationApproval).count(),
            db_session.query(DispatchOffer).count(),
            db_session.query(DeliveryPackage).count(),
            db_session.query(ReviewMeetingMinutes).count(),
            db_session.query(RegionalPartner).count(),
            db_session.query(FdeProfile).count(),
            db_session.query(OperationEvent).count(),
        )

    before = _snapshot()
    response = client.post(BRIEF_ROUTE, headers=access_headers(admin, settings))
    assert response.status_code == 200
    after = _snapshot()
    assert after[:-1] == before[:-1]  # 业务六表逐位不变
    assert after[-1] == before[-1] + 1  # 仅事件 +1


# ----------------------------------------------------------------- 截断与限额
def test_todo_list_top_limit_truncation(ai_context, db_session):
    """正文最多逐条列出 10 条（字面断言），其余以「计数已含」标注。"""
    users, _execute = ai_context
    admin = users["admin"]
    project = make_project(db_session, admin)
    todos = [{"text": f"待办事项 {index}"} for index in range(12)]
    _minutes(db_session, project, admin, todos=todos)
    brief = compose_ops_brief()
    assert brief["todo_total"] == 12
    markdown = brief["brief_markdown"]
    # 待办清单行格式固定为「N. [域｜队列] 标题 — 截止 …」，数编号行即数逐条列出数
    numbered = [line for line in markdown.splitlines()
                if line[:1].isdigit() and ". [" in line[:6]]
    assert len(numbered) == 10 == BRIEF_TODO_TOP_LIMIT
    assert "（其余 2 项未逐条列出，计数已含）" in markdown
    assert BRIEF_DUE_LIST_LIMIT == 50  # 介入清单限额口径钉死
