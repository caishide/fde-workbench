"""多客户 M5-3：收尾验收——S1 端到端全链（leader 任务书 §M5 验收①②③）。

一家测试企业从公开自助注册到拿到三付费选项，全程无人工建号：

1. **公开自助注册**（POST /api/v1/commercial/enterprise-registrations，无鉴权）
   ⇒ ``quota_created=True``——建号步骤零 admin 参与（验收①核心断言）；
2. 绑定账号启动 → admin 登记六项交付物完成（G6 口径允许的人工闸，非建号）
   → 企业确认 ⇒ 诊断完成（L3 形态）；
3. 企业空间读面取 ``org_id``（M2 起统一注册面建号即建 org）；
4. 邀请链：第二账号公开注册（平台身份 ``org_id=NULL``）→ 绑定账号发起邀请
   （一次性令牌）→ 受邀人接受 ⇒ org 归属 + org 维度事件留痕
   （v1.1「成员变动可感知」最小承载）；
5. 三档分流：非 admin 403 → admin+密码双闸判定留痕；
6. 读面回看：``triage_decisions`` 长度 1、``diagnosis.all_completed`` 为真、
   ``paid_options`` 三键齐（验收②分流可回看＋六项判据聚合）；
7. 企业自主选择付费选项 ⇒ ``engagement_state`` 派生 ``paid_delivery``
   （验收①收口：注册到三付费选项全程无人工建号）。
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, text

from fde_api.auth.models import User
from fde_api.auth.tokens import issue_access_token
from fde_api.commercial.models import (
    ENTERPRISE_TRIAGE_TIERS,
    FREE_DIAGNOSIS_DELIVERABLES,
)
from fde_api.workbench.models import OperationEvent

from conftest import INITIAL_PASSWORD
from test_research_subjects_api import (  # noqa: F401  (pytest fixture)
    AuthorizedClient,
    admin_client,
    authorized_client_factory,
)
from test_commercial_enterprise_space import (  # noqa: F401  (pytest fixture)
    _open_registration_gate,
)

VALID_USCC = "91350100M000100Y43"  # 公开样本（mod-31 校验通过，同 G2/G6）
SELF_PASSWORD = "Enterprise!Pass2026"

REG_URL = "/api/v1/commercial/enterprise-registrations"
ACCEPT_INVITATION_URL = "/api/v1/commercial/orgs/invitations/accept"


def _space_url(uscc: str) -> str:
    return f"/api/v1/commercial/enterprise-spaces/{uscc}"


def _triage_url(uscc: str) -> str:
    return f"/api/v1/admin/commercial/enterprise-spaces/{uscc}/triage-decisions"


def _choices_url(uscc: str) -> str:
    return f"{_space_url(uscc)}/paid-option-choices"


def _authorized(client, settings, db_session, user_id: str) -> AuthorizedClient:
    """按已提交的注册结果行签发访问令牌（注册由路由事务提交，此处读库取行）。"""
    user = db_session.scalar(select(User).where(User.id == user_id))
    assert user is not None
    return AuthorizedClient(
        client, user, {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    )


def test_m5_s1_e2e_from_registration_to_paid_option(
    client, admin_client, settings, db_session
) -> None:
    invitee_email = f"m5.invitee.{uuid4().hex[:8]}@example.com"

    # ── ① 公开自助注册（无鉴权、无 admin 参与）——「全程无人工建号」核心断言 ──
    registration = client.post(
        REG_URL,
        json={
            "username": f"ent.{uuid4().hex[:10]}",
            "display_name": "M5 验收企业",
            "password": SELF_PASSWORD,
            "email": f"m5.owner.{uuid4().hex[:8]}@example.com",
            "subject_key": VALID_USCC,
            "problem_description": "订单履约周期过长，需要一次完整诊断。",
        },
    )
    assert registration.status_code == 200, registration.get_data(as_text=True)
    reg_data = registration.json["data"]
    assert reg_data["quota_created"] is True
    ent = _authorized(client, settings, db_session, reg_data["user_id"])

    # ── ② 绑定账号启动 → admin 登记六项交付物 → 企业确认（诊断完成 L3 形态）──
    started = ent.post(f"/api/v1/commercial/enterprise-quota/{VALID_USCC}/start", json={})
    assert started.status_code == 200, started.get_data(as_text=True)
    done = admin_client.post(
        f"/api/v1/admin/commercial/enterprise-quota/{VALID_USCC}/complete",
        json={
            "deliverables": {key: True for key in FREE_DIAGNOSIS_DELIVERABLES},
            "confirm_password": INITIAL_PASSWORD,
        },
    )
    assert done.status_code == 200, done.get_data(as_text=True)
    confirmed = ent.post(f"/api/v1/commercial/enterprise-quota/{VALID_USCC}/confirm", json={})
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)

    # ── ③ 读面取 org_id（M2 起统一注册面建号即建 org）──
    view = ent.get(_space_url(VALID_USCC))
    assert view.status_code == 200, view.get_data(as_text=True)
    org_id = view.json["data"]["org_id"]
    assert org_id

    # ── ④ 邀请链：第二账号公开注册（平台身份）→ 邀请 → 接受 ──
    founder = client.post(
        "/api/v1/auth/register/founder",
        json={
            "username": f"m5.founder.{uuid4().hex[:10]}",
            "display_name": "受邀同事",
            "password": SELF_PASSWORD,
            "email": invitee_email,
        },
    )
    assert founder.status_code == 201, founder.get_data(as_text=True)
    founder_data = founder.json["data"]
    assert founder_data["org_id"] is None  # 平台身份前置（接受邀请的安全闸门）
    invitee = _authorized(client, settings, db_session, founder_data["user_id"])

    invited = ent.post(
        f"/api/v1/commercial/orgs/{org_id}/invitations",
        json={"invited_email": invitee_email},
    )
    assert invited.status_code == 201, invited.get_data(as_text=True)
    invitation = invited.json["data"]
    assert invitation["token"]  # 一次性明文令牌只此一次回传

    accepted = invitee.post(ACCEPT_INVITATION_URL, json={"token": invitation["token"]})
    assert accepted.status_code == 200, accepted.get_data(as_text=True)

    # 成员变动可感知（v1.1 最小承载）：org 维度事件留痕 + 接受即归属
    invite_event = db_session.scalar(
        select(OperationEvent)
        .where(OperationEvent.event_type == "org_member_invitation_accepted")
        .order_by(OperationEvent.created_at.desc())
    )
    assert invite_event is not None
    assert invite_event.changes["org_id"] == org_id
    assert invite_event.changes["invitation_id"] == invitation["invitation_id"]
    # 路由在独立事务提交；以裸 SQL 绕过身份映射缓存读取已提交态
    stored_org_id = db_session.execute(
        text("SELECT org_id FROM users WHERE id = :uid"),
        {"uid": founder_data["user_id"]},
    ).scalar()
    assert stored_org_id == org_id

    # ── ⑤ 三档分流：非 admin 403 → admin+密码双闸判定留痕 ──
    denied = ent.post(
        _triage_url(VALID_USCC), json={"tier": "standardized", "rationale": "x"}
    )
    assert denied.status_code == 403
    decided = admin_client.post(
        _triage_url(VALID_USCC),
        json={
            "tier": "standardized",
            "rationale": "M5 验收：产品标准化程度高，走标准化交付路径。",
            "confirm_password": INITIAL_PASSWORD,
        },
    )
    assert decided.status_code == 200, decided.get_data(as_text=True)

    # ── ⑥ 读面回看：分流可回看 + 六项判据聚合 + 三付费选项齐 ──
    review = ent.get(_space_url(VALID_USCC))
    assert review.status_code == 200, review.get_data(as_text=True)
    data = review.json["data"]
    assert len(data["triage_decisions"]) == 1
    assert data["triage_decisions"][0]["tier"] == "standardized"
    assert data["diagnosis"]["all_completed"] is True
    assert sorted(data["paid_options"]["options"]) == sorted(ENTERPRISE_TRIAGE_TIERS)

    # ── ⑦ 企业自主选择付费选项 ⇒ paid_delivery（验收①收口）──
    chosen = ent.post(_choices_url(VALID_USCC), json={"option_key": "standardized"})
    assert chosen.status_code == 200, chosen.get_data(as_text=True)
    final = ent.get(_space_url(VALID_USCC))
    assert final.status_code == 200
    assert final.json["data"]["engagement_state"] == "paid_delivery"
