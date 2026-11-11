"""获客诊断工具 T-11：线索模型与认领闸（员工侧）。

这一组用例守的是**「谁来跟、归谁、算不算渠道带来的」必须机械可判**：

- **认领 ≠ 生效**（P-6）：申请只是 ``pending``；平台（admin）接受才生效；
- **认领窗口**（P-2：90 天）：过期即拒——窗口是机制不是提示；
- **一线一线**：同线索已有未决认领 ⇒ 拒（未决申请锁住线索）；
- **R4 仅本区域**：区域不符 ⇒ 拒；线索**未登记区域** ⇒ **fail-closed 拒**
  （无法判定本区域即不许认领）；
- **同主体自诊自认领** ⇒ **自动 C 档零转化费**（降档，不拒单）；
- **比例不落数**（P-2）：只落 A/B/C 三档结构 ＋ ``none/pending_pricing``；
- **不建平行 CRM**（P-3）：台账行是**代号化九字段**，真相层仍是本地
  ``leads.md``；服务端**不碰真相层文件**；
- **线索 ≠ 项目**：认领单与线索表**零外键指向 projects**。

这些用例不联网、不调模型——认领闸是纯规则层。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.diagnostics.claim_service import LEDGER_COLUMNS
from fde_api.diagnostics.models import LeadDiagnosticClaim, LeadDiagnosticSession

from conftest import INITIAL_PASSWORD
from test_diagnostics_mvp import _FakeRedis  # noqa: F401  （假 Redis：配额闸可测）

TOKEN_HEADER = "X-Diagnostic-Token"
LEADS_PREFIX = "/api/v1/diagnostics/leads"
# 员工侧请求的来源 IP（**与访客 IP 刻意不同**——否则「同 IP ⇒ 自认领」信号
# 在测试里必然命中，测不出真实的区分能力）。
STAFF_IP = "198.51.100.42"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_ledger_script():
    """载入落账脚本（``scripts/lead_ledger_append.py``）——列序防漂移的机械钉。"""
    path = REPO_ROOT / "scripts" / "lead_ledger_append.py"
    spec = importlib.util.spec_from_file_location("lead_ledger_append", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

FIRST_SCREEN_READY = {
    "org.industry": "制造与工业",
    "org.scale": "100–499人",
    "pol.qualification": ["规上工业企业"],
    "pol.declaration_history": "从未申报过",
    "pol.digitalization_project": "已有在推进的数字化改造",
}
DIAGNOSTIC_READY = {
    "org.main_business": "机械零部件加工",
    "biz.current_process": "老师傅凭经验排产，纸质工单",
    "biz.pain_stage": "生产与交付",
    "biz.decision_maker": "生产负责人",
    "ctx.free_text": "报价要问老工程师，一单两三天",
}


@pytest.fixture
def diag_app(app):
    """打开诊断面（部署闸开）+ 假 Redis。"""
    app.config["SETTINGS"] = app.config["SETTINGS"].model_copy(
        update={"diagnostics_enabled": True, "diagnostics_rate_fail_closed": True}
    )
    app.extensions["fde_api_redis"] = _FakeRedis()
    return app


@pytest.fixture
def diag_client(diag_app):
    return diag_app.test_client()


def _make_user(db_session, settings, *, role: str, email: str | None = None):
    user = User(
        username=f"diag.{role}.{uuid4().hex[:8]}",
        display_name=role,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        email=email,
        registration_state="active",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    headers = {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    return user, headers


def _lead(
    client,
    *,
    source_type: str = "direct",
    channel_ref: str | None = None,
    contact: str = "13800000001",
    region: str | None = None,
    remote_addr: str | None = None,
) -> dict:
    """跑完整匿名流程 ⇒ 一条**已留资**的线索（返回会话 id 与令牌）。"""
    env = {"REMOTE_ADDR": remote_addr} if remote_addr else None
    created = client.post(
        "/api/v1/diagnostics/sessions",
        json={"source_type": source_type, "channel_ref": channel_ref},
        environ_base=env,
    )
    assert created.status_code == 200, created.get_json()
    token = created.get_json()["data"]["token"]
    session_id = created.get_json()["data"]["id"]
    headers = {TOKEN_HEADER: token}
    assessed = client.post(
        "/api/v1/diagnostics/session/assessment",
        json={"answers": FIRST_SCREEN_READY},
        headers=headers,
        environ_base=env,
    )
    assert assessed.status_code == 200, assessed.get_json()
    answered = client.post(
        "/api/v1/diagnostics/session/answers",
        json={"answers": DIAGNOSTIC_READY},
        headers=headers,
        environ_base=env,
    )
    assert answered.status_code == 200, answered.get_json()
    captured = client.post(
        "/api/v1/diagnostics/session/lead",
        json={"contact": {"contact": contact, "consent": True, "region": region}},
        headers=headers,
        environ_base=env,
    )
    assert captured.status_code == 200, captured.get_json()
    return {"id": session_id, "token": token}


def _claim(client, headers, session_id, payload=None, environ_base=None):
    return client.post(
        f"{LEADS_PREFIX}/{session_id}/claims",
        json=payload if payload is not None else {"claimant_kind": "r2_entrepreneur"},
        headers=headers,
        environ_base=environ_base if environ_base is not None else {"REMOTE_ADDR": STAFF_IP},
    )


def _accept(client, headers, claim_id, payload):
    return client.post(
        f"{LEADS_PREFIX}/claims/{claim_id}/accept",
        json=payload,
        headers=headers,
        environ_base={"REMOTE_ADDR": STAFF_IP},
    )


def _reject(client, headers, claim_id, payload):
    return client.post(
        f"{LEADS_PREFIX}/claims/{claim_id}/reject",
        json=payload,
        headers=headers,
        environ_base={"REMOTE_ADDR": STAFF_IP},
    )


# ── 闸门与鉴权 ─────────────────────────────────────────────────────────


def test_staff_face_requires_login(diag_client):
    """员工面必须登录（匿名面与员工面是两条蓝图——边界不许糊）。"""
    response = diag_client.get(f"{LEADS_PREFIX}")
    assert response.status_code == 401


def test_disabled_gate_hides_staff_face_before_auth(client):
    """**闸门先于鉴权**：诊断面未启用 ⇒ 404（不确认面存在），不是 401。"""
    response = client.get(f"{LEADS_PREFIX}")
    assert response.status_code == 404, response.get_json()
    assert response.get_json()["error"]["code"] == "not_found"


def test_claim_request_is_pending_and_lead_stays_unclaimed(
    diag_client, db_session, settings
):
    """**认领 ≠ 生效**：申请只是 pending；线索状态不动。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)

    response = _claim(diag_client, partner_headers, lead["id"])
    assert response.status_code == 201, response.get_json()
    claim = response.get_json()["data"]
    assert claim["status"] == "pending"
    assert claim["attribution_tier"] is None

    row = db_session.scalars(
        select(LeadDiagnosticSession).where(LeadDiagnosticSession.id == lead["id"])
    ).one()
    assert row.status != "claimed"
    assert row.claimed_by_user_id is None
    assert admin_headers  # 平台账号仅作对照（此时未使用）


def test_accept_requires_admin_role(diag_client, db_session, settings):
    """平台接受＝**平台身份**的特权动作（普通成员 403）。"""
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]

    response = _accept(diag_client, member_headers, claim["id"], {"decision_note": "确认可跟"})
    assert response.status_code == 403


def test_accept_is_what_makes_the_claim_effective(diag_client, db_session, settings):
    """接受 ⇒ 认领生效（线索转 claimed ＋ 档位 ＋ 台账号）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]

    response = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "平台确认认领"})
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "accepted"
    assert data["attribution_tier"] == "B"
    assert data["fee_basis"] == "pending_pricing"
    assert re.fullmatch(r"L-\d{8}-\d{2}", data["ledger_line_no"])

    row = db_session.scalars(
        select(LeadDiagnosticSession).where(LeadDiagnosticSession.id == lead["id"])
    ).one()
    assert row.status == "claimed"
    assert row.attribution_tier == "B"


# ── 闸①：认领窗口 ─────────────────────────────────────────────────────


def test_claim_window_expired_is_rejected(diag_client, db_session, settings):
    """90 天窗口过期 ⇒ 拒（窗口是机制，不是提示）。"""
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    row = db_session.scalars(
        select(LeadDiagnosticSession).where(LeadDiagnosticSession.id == lead["id"])
    ).one()
    from datetime import UTC, datetime, timedelta

    row.claim_window_expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    response = _claim(diag_client, member_headers, lead["id"])
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "claim_window_expired"


# ── 闸②：一线一线 ─────────────────────────────────────────────────────


def test_second_claim_while_first_is_pending_is_rejected(diag_client, db_session, settings):
    """未决认领锁住线索（不并行认领）。"""
    _, first_headers = _make_user(db_session, settings, role="fde_engineer")
    _, second_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    assert _claim(diag_client, first_headers, lead["id"]).status_code == 201

    response = _claim(diag_client, second_headers, lead["id"])
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "claim_in_flight"


def test_rejected_claim_frees_the_lead_for_another_claimant(
    diag_client, db_session, settings
):
    """驳回**不改线索状态**——线索仍可被他人认领。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, first_headers = _make_user(db_session, settings, role="fde_engineer")
    _, second_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, first_headers, lead["id"]).get_json()["data"]

    rejected = _reject(diag_client, admin_headers, claim['id'], {"decision_note": "该线索不在服务范围"})
    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["status"] == "rejected"

    assert _claim(diag_client, second_headers, lead["id"]).status_code == 201


def test_lead_without_capture_cannot_be_claimed(diag_client, db_session, settings):
    """未留资的线索不可认领（没联系方式＝没法跟）。"""
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    created = diag_client.post("/api/v1/diagnostics/sessions", json={})
    session_id = created.get_json()["data"]["id"]
    response = _claim(diag_client, member_headers, session_id)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "lead_not_captured"


# ── 闸③：R4 仅本区域 ─────────────────────────────────────────────────


def test_r4_cannot_claim_other_region_lead(diag_client, db_session, settings):
    """R4 认领他区线索 ⇒ 拒。"""
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, region="浙江省")
    response = _claim(
        diag_client,
        partner_headers,
        lead["id"],
        {"claimant_kind": "r4_partner", "region_name": "江苏省"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "region_mismatch"


def test_r4_cannot_claim_lead_without_region(diag_client, db_session, settings):
    """线索未登记区域 ⇒ **fail-closed 拒**（无法判定本区域即不许认领）。"""
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    response = _claim(
        diag_client,
        partner_headers,
        lead["id"],
        {"claimant_kind": "r4_partner", "region_name": "浙江省"},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "lead_region_unknown"


def test_r4_can_claim_same_region_lead(diag_client, db_session, settings):
    """R4 认领本区域线索 ⇒ 放行。"""
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, region="浙江省")
    response = _claim(
        diag_client,
        partner_headers,
        lead["id"],
        {"claimant_kind": "r4_partner", "region_name": "浙江省"},
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["region_name"] == "浙江省"


def test_r4_claim_without_region_is_rejected(diag_client, db_session, settings):
    """R4 认领不声明区域 ⇒ 拒（区域是判定的必要输入）。"""
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, region="浙江省")
    response = _claim(
        diag_client, partner_headers, lead["id"], {"claimant_kind": "r4_partner"}
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "region_required"


# ── 闸④：同主体自诊自认领 ⇒ C 档零转化费 ──────────────────────────────


def test_self_claim_by_contact_is_downgraded_to_c_tier(diag_client, db_session, settings):
    """认领方账号邮箱 == 线索联系方式 ⇒ 自认领信号命中 ⇒ C 档零转化费。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(
        db_session, settings, role="fde_engineer", email="owner@enterprise.test"
    )
    lead = _lead(diag_client, contact="owner@enterprise.test")
    claim = _claim(diag_client, partner_headers, lead["id"]).get_json()["data"]
    assert claim["self_claim"] is True
    assert "contact" in claim["self_claim_signals"]

    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "自认领，按 C 档"}).get_json()["data"]
    assert accepted["attribution_tier"] == "C"
    assert accepted["fee_basis"] == "none"


def test_self_claim_by_ip_signal_is_detected(diag_client, db_session, settings):
    """同 IP ⇒ 自认领信号命中（IP 假名比对，不存明文 IP）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, remote_addr="203.0.113.77")
    claim = _claim(
        diag_client,
        partner_headers,
        lead["id"],
        environ_base={"REMOTE_ADDR": "203.0.113.77"},
    ).get_json()["data"]
    assert "ip" in claim["self_claim_signals"]

    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "同网段自认领"}).get_json()["data"]
    assert accepted["attribution_tier"] == "C"


def test_ordinary_claim_is_not_self_claim(diag_client, db_session, settings):
    """普通认领不误判自认领（信号为空 ⇒ 档位 B）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(
        db_session, settings, role="fde_engineer", email="partner@agency.test"
    )
    lead = _lead(diag_client, contact="buyer@client.test")
    claim = _claim(diag_client, partner_headers, lead["id"]).get_json()["data"]
    assert claim["self_claim"] is False
    assert claim["self_claim_signals"] == []


# ── 三档归因（P-2：比例不落数） ───────────────────────────────────────


def test_partner_reported_lead_is_tier_a(diag_client, db_session, settings):
    """渠道报备来的线索 ⇒ A 档（比例不落数，只落结构）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(
        diag_client,
        source_type="partner",
        channel_ref="R4-ZJ-001",
        region="浙江省",
    )
    claim = _claim(
        diag_client,
        partner_headers,
        lead["id"],
        {"claimant_kind": "r4_partner", "region_name": "浙江省"},
    ).get_json()["data"]
    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "渠道报备线索"}).get_json()["data"]
    assert accepted["attribution_tier"] == "A"
    assert accepted["fee_basis"] == "pending_pricing"


def test_manual_tier_override_requires_reason(diag_client, db_session, settings):
    """人工改档必须留理由（否则 400）——改档是留痕可推翻的动作。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]

    rejected = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "改档", "attribution_tier": "A"})
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["code"] == "override_reason_required"

    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "实为渠道报备", "attribution_tier": "A", "override_reason": "查台账确认为报备"}).get_json()["data"]
    assert accepted["attribution_tier"] == "A"
    assert accepted["tier_override"] is True


# ── 台账行（九字段、代号化、真相层在本地） ───────────────────────────


def test_ledger_row_has_nine_fields_and_no_contact(diag_client, db_session, settings):
    """台账行＝九字段 ＋ 线索号 ＋ 资料索引；**不含联系方式/姓名**。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, contact="13800000009", region="浙江省")
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]
    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "接受"}).get_json()["data"]

    row = accepted["ledger_row"]
    # Flask 的 jsonify 默认 sort_keys ⇒ 响应里的键序被排序，**列序以
    # LEDGER_COLUMNS 为准**（落账脚本按它写台账表的列序）。
    assert set(row.keys()) == set(LEDGER_COLUMNS)
    assert row["线索号"] == accepted["ledger_line_no"]
    assert row["来源"] == "自有"
    assert row["行业"] == "制造与工业"
    assert row["联系人角色"] == "生产负责人"
    assert row["痛点一句话"].startswith("报价要问老工程师")
    # 工具**不臆造**资格判定 ⇒ 待填
    assert row["资格五问得分"] == "待填"
    assert row["①状态"] == "诊断中"
    text = json.dumps(row, ensure_ascii=False)
    assert "13800000009" not in text
    assert "test@" not in text


def test_ledger_line_numbers_are_daily_monotonic(diag_client, db_session, settings):
    """同日两条生效认领 ⇒ 线索号连号（L-<YYYYMMDD>-01 / -02）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    numbers = []
    for _ in range(2):
        lead = _lead(diag_client)
        claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]
        accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "接受"}).get_json()["data"]
        numbers.append(accepted["ledger_line_no"])
    assert len(set(numbers)) == 2
    seqs = sorted(int(item.rsplit("-", 1)[1]) for item in numbers)
    assert seqs == [1, 2]


def test_ledger_row_is_not_written_by_the_server(diag_client, db_session, settings):
    """**服务端不碰真相层文件**：接受后 ``ledger_written_at`` 仍为空。

    落账由宿主侧脚本写 ``D:\\test\\FDE\\leads.md``（真相层在容器外）。
    """
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]
    accepted = _accept(diag_client, admin_headers, claim['id'], {"decision_note": "接受"}).get_json()["data"]
    assert accepted["ledger_written_at"] is None


# ── 线索池（按区可见、代号化） ─────────────────────────────────────────


def test_pool_is_region_scoped_for_r4(diag_client, db_session, settings):
    """R4 只看本区域线索；平台看全部。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, partner_headers = _make_user(db_session, settings, role="fde_engineer")
    _lead(diag_client, region="浙江省")
    _lead(diag_client, region="江苏省")

    scoped = diag_client.get(
        f"{LEADS_PREFIX}?claimant_kind=r4_partner&region_name=浙江省",
        headers=partner_headers,
    ).get_json()["data"]
    assert len(scoped) == 1
    assert scoped[0]["region_name"] == "浙江省"

    everything = diag_client.get(
        f"{LEADS_PREFIX}?claimant_kind=r2_entrepreneur", headers=admin_headers
    ).get_json()["data"]
    assert len(everything) == 2


def test_pool_never_exposes_contact_or_name(diag_client, db_session, settings):
    """池子里**看不到**联系方式与姓名（代号化）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _lead(diag_client, contact="13800000042")
    items = diag_client.get(
        f"{LEADS_PREFIX}?claimant_kind=r2_entrepreneur", headers=admin_headers
    ).get_json()["data"]
    text = json.dumps(items, ensure_ascii=False)
    assert "13800000042" not in text
    assert "contact" not in text
    assert "lead_contact" not in text


def test_pool_hides_claimed_leads(diag_client, db_session, settings):
    """已认领的线索不进池子（一线一线）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]
    _accept(diag_client, admin_headers, claim["id"], {"decision_note": "接受"})
    items = diag_client.get(
        f"{LEADS_PREFIX}?claimant_kind=r2_entrepreneur", headers=admin_headers
    ).get_json()["data"]
    assert all(item["id"] != lead["id"] for item in items)


# ── 认领单列表（裁定队列 ＋ 我的申请） ─────────────────────────────────


def test_claims_list_admin_sees_pending_queue_with_lead_summary(
    diag_client, db_session, settings
):
    """admin 拿到全量裁定队列：投影带认领人账号名与线索摘要（代号化）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    member, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client, region="浙江省")
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]

    items = diag_client.get(
        f"{LEADS_PREFIX}/claims?status=pending", headers=admin_headers
    ).get_json()["data"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == claim["id"]
    assert row["status"] == "pending"
    assert row["claimant_username"] == member.username
    assert row["lead"] is not None
    assert row["lead"]["id"] == lead["id"]
    assert row["lead"]["region_name"] == "浙江省"
    # 代号化纪律：摘要里看不到联系方式明文
    assert "contact" not in json.dumps(row, ensure_ascii=False)


def test_claims_list_non_admin_sees_only_own(diag_client, db_session, settings):
    """非 admin 只看**自己的**申请（别人的认领单不可枚举）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    first, first_headers = _make_user(db_session, settings, role="fde_engineer")
    second, second_headers = _make_user(db_session, settings, role="project_lead")
    lead_a = _lead(diag_client)
    lead_b = _lead(diag_client)
    mine = _claim(diag_client, first_headers, lead_a["id"]).get_json()["data"]
    theirs = _claim(diag_client, second_headers, lead_b["id"]).get_json()["data"]

    items = diag_client.get(f"{LEADS_PREFIX}/claims", headers=first_headers).get_json()["data"]
    ids = {row["id"] for row in items}
    assert ids == {mine["id"]}
    assert theirs["id"] not in ids

    # admin 缺省（status=all）能看到两条
    everything = diag_client.get(
        f"{LEADS_PREFIX}/claims", headers=admin_headers
    ).get_json()["data"]
    assert {row["id"] for row in everything} == {mine["id"], theirs["id"]}


def test_claims_list_status_filter_is_closed_set(diag_client, db_session, settings):
    """status 过滤器闭集：非法值 400；rejected 要用显式 status 才看得到。"""
    _, admin_headers = _make_user(db_session, settings, role="admin", email="admin@x.test")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    lead = _lead(diag_client)
    claim = _claim(diag_client, member_headers, lead["id"]).get_json()["data"]
    _reject(diag_client, admin_headers, claim["id"], {"decision_note": "驳回"})

    bad = diag_client.get(
        f"{LEADS_PREFIX}/claims?status=whatever", headers=admin_headers
    )
    assert bad.status_code == 400
    assert bad.get_json()["error"]["code"] == "invalid_status"

    pending = diag_client.get(
        f"{LEADS_PREFIX}/claims?status=pending", headers=admin_headers
    ).get_json()["data"]
    assert all(row["status"] == "pending" for row in pending)
    rejected = diag_client.get(
        f"{LEADS_PREFIX}/claims?status=rejected", headers=admin_headers
    ).get_json()["data"]
    assert len(rejected) == 1
    assert rejected[0]["decision_note"] == "驳回"


def test_claims_list_gate_hides_before_auth(client):
    """**闸门先于鉴权**：诊断面未启用 ⇒ 404（与线索池同尺）。"""
    response = client.get(f"{LEADS_PREFIX}/claims")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


# ── 结构纪律 ───────────────────────────────────────────────────────────


def test_claim_tables_have_no_foreign_key_to_projects():
    """线索 ≠ 项目：认领单与线索表**零外键指向 projects**。"""
    for model in (LeadDiagnosticSession, LeadDiagnosticClaim):
        refs = [
            fk.target_fullname
            for fk in model.__table__.foreign_keys
            if "projects" in fk.target_fullname
        ]
        assert refs == [], model.__tablename__


def test_claim_model_exposes_no_ratio_field():
    """**比例不落数**（P-2）：认领单与线索表都没有任何比例/金额字段。"""
    banned = ("rate", "ratio", "percent", "commission", "amount", "fee_rate")
    for model in (LeadDiagnosticSession, LeadDiagnosticClaim):
        for column in model.__table__.columns:
            assert not any(word in column.name for word in banned), column.name


# ── 落账脚本（宿主侧写真相层） ─────────────────────────────────────────


def test_ledger_script_column_order_matches_service():
    """落账脚本的列序 ≡ 服务端 ``LEDGER_COLUMNS``（防漂移的机械钉）。"""
    script = _load_ledger_script()
    assert script.LEDGER_COLUMNS == LEDGER_COLUMNS


def test_ledger_script_inserts_row_after_last_ledger_row():
    """新行插到 §一 登记表**最后一行之后**（只插不改）。"""
    script = _load_ledger_script()
    original = (
        "| 线索号 | # | 来源 |\n"
        "|---|---|---|\n"
        "| L-20261008-01 | 1 | 自有 |\n"
        "| L-20261008-02 | 2 | 协会活动 |\n"
        "\n> 下面是表注\n"
    )
    new_line = "| L-20261112-01 | 1 | 自有 |"
    updated = script._insert_rows(original, [new_line])
    lines = updated.splitlines()
    assert lines[3] == "| L-20261008-02 | 2 | 协会活动 |"
    assert lines[4] == new_line
    assert lines[5] == ""
    assert lines[6] == "> 下面是表注"


def test_ledger_script_refuses_when_no_ledger_table_found():
    """找不到登记表 ⇒ **fail-closed**（不猜位置）。"""
    script = _load_ledger_script()
    with pytest.raises(SystemExit):
        script._insert_rows("# 没有表\n只有正文\n", ["| L-20261112-01 | 1 | 自有 |"])


def test_ledger_script_escapes_pipes_in_cells():
    """单元格里的竖线必须转义（否则台账表被打散）。"""
    script = _load_ledger_script()
    row = {column: "x" for column in LEDGER_COLUMNS}
    row["痛点一句话"] = "报价|排产"
    line = script._row_line(row)
    assert "报价\\|排产" in line
    # 未转义的竖线数 ＝ 列数 + 1（首尾分隔符 + 列间分隔符）——转义竖线不计入，
    # 否则台账表会被打散成多列。
    unescaped = re.sub(r"\\\|", "", line).count("|")
    assert unescaped == len(LEDGER_COLUMNS) + 1
