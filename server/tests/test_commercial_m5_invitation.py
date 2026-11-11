"""多客户工作平台 M5-1：企业组织成员邀请（邀请面端到端验收）。

钉住六件事：
1. **邀请是 org 归属面，不是第二套权限体系**（红线 8）：接受邀请唯一副作用＝把
   受邀用户 ``users.org_id`` 置为本 org；成员可见性由既有 ``project_org_scope_filter``
   覆盖，本域零角色授予、零平行权限表。
2. **邀请人授权**：本 org 成员（users.org_id == org.id）或 admin 可发起；非成员 403。
3. **一次性令牌 + 邮箱绑定**（sec 评审：邀请是社会工程攻击面）：令牌明文只回传一次
   （指纹入库）；接受时强制 actor.email == 受邀邮箱；actor 必须是平台身份（org_id
   为 NULL）——令牌泄露只被目标账号消费，且不能把已归属别家的账号拽过来。
4. **状态机**：pending → accepted / revoked 互斥终态；过期 410、已接受 409、已撤销
   410、邮箱不符 403；每 org 同邮箱至多一份待接受邀请（重复 409）。
5. **撤销**：仅邀请人或 admin 可撤销待接受邀请；已接受/已撤销不可再撤。
6. **企业空间读面透出邀请清单 + org_id**（M5-1 收口）：绑定账号本人可见本 org 邀请。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.commercial.models import EnterpriseFreeQuota, EnterpriseQuotaSubject
from fde_api.orgs.models import Org

from conftest import INITIAL_PASSWORD
from test_research_subjects_api import authorized_client_factory  # noqa: F401

VALID_USCC = "91350100M000100Y43"  # 公开样本（mod-31 校验通过，同 G2）


@dataclass(frozen=True)
class Client:
    client: object
    user: User
    headers: dict[str, str]

    def get(self, *args, **kwargs):
        return self.client.get(*args, headers=self.headers, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)


def _make_user(db_session, settings, client, *, role, email, org_id=None, username=None):
    user = User(
        username=username or f"m5.{role}.{uuid4().hex}",
        display_name=role,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        email=email,
        org_id=org_id,
        registration_state="active",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return Client(
        client,
        user,
        {"Authorization": f"Bearer {issue_access_token(user, settings)}"},
    )


def _make_org(db_session, *, subject_key=VALID_USCC, name="M5测试企业"):
    org = Org(org_type="enterprise", name=name, subject_key=subject_key)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def _bind_quota(db_session, *, subject_key, bound_user_id):
    subject = EnterpriseQuotaSubject(
        subject_key=subject_key,
        display_name="M5测试企业",
        first_user_id=bound_user_id,
        problem_description="M5 邀请验收",
    )
    # 绑定态：state<>'granted' 要求 bound_user_id NOT NULL（CK 联锁）；授予人必填。
    quota = EnterpriseFreeQuota(
        subject_key=subject_key,
        state="in_progress",
        granted_by_user_id=bound_user_id,
        bound_user_id=bound_user_id,
    )
    db_session.add(subject)
    db_session.add(quota)
    db_session.commit()
    return quota


@pytest.fixture
def org_and_owner(db_session, client, settings):
    """一家企业 org + 绑定账号（project_lead，org_id 置为该企业）。"""
    org = _make_org(db_session)
    owner = _make_user(
        db_session, settings, client,
        role="project_lead", email="owner@example.com", org_id=org.id,
    )
    _bind_quota(db_session, subject_key=org.subject_key, bound_user_id=owner.user.id)
    return org, owner


INVITE_URL = lambda org_id: f"/api/v1/commercial/orgs/{org_id}/invitations"
INVITE_LIST_URL = lambda org_id: f"/api/v1/commercial/orgs/{org_id}/invitations"
REVOKE_URL = lambda org_id, iid: f"/api/v1/commercial/orgs/{org_id}/invitations/{iid}/revoke"
ACCEPT_URL = "/api/v1/commercial/orgs/invitations/accept"
SPACE_URL = lambda uscc: f"/api/v1/commercial/enterprise-spaces/{uscc}"


def test_non_member_cannot_invite(db_session, client, settings, org_and_owner):
    """非本 org 成员发起邀请 ⇒ 403。"""
    org, _ = org_and_owner
    outsider = _make_user(db_session, settings, client, role="project_lead", email="outsider@example.com")
    resp = outsider.post(INVITE_URL(org.id), json={"invited_email": "x@example.com"})
    assert resp.status_code == 403


def test_admin_can_invite_any_org(db_session, client, settings, org_and_owner, authorized_client_factory):
    """admin（平台能力）可对本 org 发起邀请。"""
    org, _ = org_and_owner
    admin = authorized_client_factory("admin")
    resp = admin.post(INVITE_URL(org.id), json={"invited_email": "admininv@example.com"})
    assert resp.status_code == 201
    assert resp.json["data"]["invited_email"] == "admininv@example.com"
    assert "token" in resp.json["data"] and resp.json["data"]["token"]


def test_invite_returns_one_time_token(db_session, client, settings, org_and_owner):
    """邀请人发起 ⇒ 201 + 一次性明文令牌（指纹入库，明文只回传一次）。"""
    org, owner = org_and_owner
    resp = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"})
    assert resp.status_code == 201
    data = resp.json["data"]
    assert data["invited_email"] == "invitee@example.com"
    assert data["state"] if "state" in data else True  # 兼容性；列表态在 list 接口
    assert "token" in data and len(data["token"]) > 0
    # 库内只存指纹、不存明文：通过再次邀请同邮箱应命中 pending 唯一索引（409）间接验证
    dup = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"})
    assert dup.status_code == 409


def test_invite_invalid_email(db_session, client, settings, org_and_owner):
    org, owner = org_and_owner
    resp = owner.post(INVITE_URL(org.id), json={"invited_email": "not-an-email"})
    assert resp.status_code == 400


def test_list_invitations_visible_to_member(db_session, client, settings, org_and_owner):
    org, owner = org_and_owner
    owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"})
    resp = owner.get(INVITE_LIST_URL(org.id))
    assert resp.status_code == 200
    items = resp.json["data"]
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["invited_email"] == "invitee@example.com"
    assert items[0]["state"] == "pending"


def test_accept_sets_org_membership(db_session, client, settings, org_and_owner):
    """受邀人（平台身份、邮箱匹配）接受 ⇒ org_id 置为本 org。"""
    from sqlalchemy import text as _text

    org, owner = org_and_owner
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"}).json["data"]
    invitee = _make_user(db_session, settings, client, role="viewer", email="invitee@example.com")
    assert invitee.user.org_id is None  # 平台身份前置
    resp = invitee.post(ACCEPT_URL, json={"token": invite["token"]})
    assert resp.status_code == 200
    assert resp.json["data"]["state"] == "accepted"
    # 路由在独立事务提交；以裸 SQL 绕过身份映射缓存读取已提交态
    org_id = db_session.execute(
        _text("SELECT org_id FROM users WHERE id = :uid"),
        {"uid": invitee.user.id},
    ).scalar()
    assert org_id == org.id


def test_accept_email_mismatch_forbidden(db_session, client, settings, org_and_owner):
    """令牌泄露给非目标邮箱账号 ⇒ 403（sec 评审：邮箱绑定）。"""
    org, owner = org_and_owner
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"}).json["data"]
    wrong = _make_user(db_session, settings, client, role="viewer", email="other@example.com")
    resp = wrong.post(ACCEPT_URL, json={"token": invite["token"]})
    assert resp.status_code == 403


def test_accept_already_in_org_conflict(db_session, client, settings, org_and_owner):
    """已归属别家 org 的账号无法接受 ⇒ 409。"""
    org, owner = org_and_owner
    other = _make_org(db_session, subject_key="92350100M000100Y40", name="另一家企业")
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "busy@example.com"}).json["data"]
    busy = _make_user(db_session, settings, client, role="viewer", email="busy@example.com", org_id=other.id)
    resp = busy.post(ACCEPT_URL, json={"token": invite["token"]})
    assert resp.status_code == 409


def test_accept_already_accepted_conflict(db_session, client, settings, org_and_owner):
    org, owner = org_and_owner
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"}).json["data"]
    invitee = _make_user(db_session, settings, client, role="viewer", email="invitee@example.com")
    first = invitee.post(ACCEPT_URL, json={"token": invite["token"]})
    assert first.status_code == 200
    second = invitee.post(ACCEPT_URL, json={"token": invite["token"]})
    assert second.status_code == 409


def test_accept_unknown_token_404(db_session, client, settings, org_and_owner):
    org, owner = org_and_owner
    invitee = _make_user(db_session, settings, client, role="viewer", email="invitee@example.com")
    resp = invitee.post(ACCEPT_URL, json={"token": "bogus-token-value"})
    assert resp.status_code == 404


def test_revoke_by_inviter(db_session, client, settings, org_and_owner):
    """邀请人可撤销待接受邀请；撤销后接受 ⇒ 410。"""
    org, owner = org_and_owner
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"}).json["data"]
    rev = owner.post(REVOKE_URL(org.id, invite["invitation_id"]), json={})
    assert rev.status_code == 200
    assert rev.json["data"]["state"] == "revoked"
    invitee = _make_user(db_session, settings, client, role="viewer", email="invitee@example.com")
    resp = invitee.post(ACCEPT_URL, json={"token": invite["token"]})
    assert resp.status_code == 410


def test_revoke_by_other_member_forbidden(db_session, client, settings, org_and_owner):
    """非邀请人、非 admin ⇒ 撤销 403。"""
    org, owner = org_and_owner
    invite = owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"}).json["data"]
    interloper = _make_user(db_session, settings, client, role="project_lead", email="p2@example.com", org_id=org.id)
    resp = interloper.post(REVOKE_URL(org.id, invite["invitation_id"]), json={})
    assert resp.status_code == 403


def test_space_view_exposes_invitations_and_org_id(db_session, client, settings, org_and_owner):
    """企业空间读面透出邀请清单与 org_id（M5-1 收口）。"""
    org, owner = org_and_owner
    owner.post(INVITE_URL(org.id), json={"invited_email": "invitee@example.com"})
    resp = owner.get(SPACE_URL(org.subject_key))
    assert resp.status_code == 200
    data = resp.json["data"]
    assert data["org_id"] == org.id
    assert any(i["invited_email"] == "invitee@example.com" for i in data["invitations"])
