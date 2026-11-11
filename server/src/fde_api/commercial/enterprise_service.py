"""商业化 G6：企业空间与企业自助交付服务层（任务书 §10；ADR-010）。

- **四类注册入口齐备**（R1–R4 一一对应）：R1 企业自助注册＝本轮新增
  （``register_enterprise``，当事人自证，无 admin 门——免费额度的结构性防滥用
  是 USCC 一主体一份额度＋七项免费边界硬编码，ADR-004 §1.2 的 admin 闸只守
  staff 发起路径）；R2/R3＝G2 体验入口注册表；R4＝G5 区域合作商申请。
- **企业客户／企业自助用户＝同一主体两种状态**：``subject_key``（USCC）不变，
  读面派生 ``engagement_state``（self_service／paid_delivery）；付费交付态＝
  存在未被取代的付费选项选择行——**派生值不是账**，科目层零触碰，不另立
  第三套计费口径。
- **三档分流＝人工判定留痕**：``enterprise_triage_decisions``——判定人、时刻、
  定性依据（rationale 必填）＋可选书面依据（指针＋sha256，同有同无）；
  系统不做任何硬规则判定（本域零阈值常量，判定＝人的输入不是计算输出）；
  ``tier`` 值域复用 G2 ``DIAGNOSIS_PROJECT_TIERS`` 键闭集（单一权威）；
  前置闸＝诊断已完成（``diagnosis_not_completed``）。admin+密码双闸
  （交付咨询环节＝平台顾问，当前由 admin 承载，ADR-007 形态）。
- **三个付费选项由系统呈现**：派生自 DIAGNOSIS_PROJECT_TIERS＋固定跟进语，
  零金额零数值（哨兵用例钉住载荷无数字——本期不落数值红线）。
- **企业自主选择不被取消**：``enterprise_paid_option_choices`` append-only——
  全仓无删除/取消路径（源码扫描钉）；换主意＝企业绑定账号本人再选（旧行
  ``superseded_at`` 留痕）；admin 不可代选/取消/改选（403）；平台侧唯一写面
  ＝顾问跟进注记（admin+密码，只能补注记三元组）。
- **企业空间复用既有权限模型**：付费交付项目由 staff 立项后经既有
  ``add_project_member`` 把企业账号加为成员（``project_members`` 既有表），
  本域零平行权限表；企业空间的交付项目读面按 ``projects.enterprise_code ==
  subject.display_name``（企业代号＝项目域连接键）+ 既有 ``project_access``
  可见性过滤。
- 留痕：逐动作 ``operation_events``（Actor/前后状态/来源/请求 ID，密码不落事件）。
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.models import ROLE_ADMIN, ROLE_PROJECT_LEAD, User
from fde_api.auth.confirm_throttle import confirm_attempts_blocked, record_confirm_failure
from fde_api.auth.passwords import verify_password
from fde_api.commercial.models import (
    DIAGNOSIS_PROJECT_TIERS,
    ENGAGEMENT_STATES,
    ENTERPRISE_TRIAGE_TIERS,
    REGISTRATION_ENTRIES,
    CommercialEntitlement,
    EnterpriseFreeQuota,
    EnterprisePaidOptionChoice,
    EnterpriseQuotaSubject,
    EnterpriseTriageDecision,
    OrgMemberInvitation,
)
from fde_api.orgs.models import Org
from fde_api.commercial.quota_service import (
    _lock_quota,
    normalize_subject_key,
    serialize_quota,
)
from fde_api.commercial.service import CommercialServiceError
from fde_api.projects.permissions import project_access
from fde_api.projects.events import record_event
from fde_api.users.service import UserServiceError, register_self_service_user
from fde_api.workbench.models import Project

# 「本期不落数值」哨兵的靶面：付费选项载荷的文本不得出现数字
# （档位定性描述来自 G2 权威，本模块不添加任何数值字段）。
_DIGIT_RE = re.compile(r"[0-9]")

ADVISOR_FOLLOW_UP_NOTE = "由平台顾问跟进；企业自主选择，平台不代选、不取消、不改选。"


def _error(code: str, message: str, status: int = 400) -> CommercialServiceError:
    return CommercialServiceError(code, message, status)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_admin(actor: User) -> None:
    if actor.role != ROLE_ADMIN:
        raise _error("commercial_admin_required", "商业权益管理仅系统运维员可用。", 403)


def _confirm_password(session: Session, actor: User, password: object) -> None:
    """单次显式授权：admin 写原语须携带当前账号密码（高风险写默认人工确认）。"""
    if not isinstance(password, str) or not password:
        raise _error("invalid_request", "confirm_password 必填（高风险写人工确认）。")
    # CR-047：密码确认尝试限流——与 auth verify-password / ai 确认闸同 key 同阈值同窗口。
    if confirm_attempts_blocked(actor.id):
        raise _error("too_many_attempts", "密码错误次数过多，请 15 分钟后重试。", 429)
    current = session.get(User, actor.id)
    if current is None or not verify_password(current.password_hash, password):
        record_confirm_failure(actor.id)
        raise _error("invalid_password", "当前账号密码不正确。", 403)


def _require_str(value: object, field: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("invalid_request", f"{field} 必填。")
    value = value.strip()
    if len(value) > max_len:
        raise _error("invalid_request", f"{field} 长度不得超过 {max_len} 字符。")
    return value


def _validate_basis(basis_uri: object, basis_sha256: object) -> tuple[str, str] | None:
    """书面依据＝指针 + sha256 指纹（同有同无；原件永不入库）。"""
    if basis_uri is None and basis_sha256 is None:
        return None
    if basis_uri is None or basis_sha256 is None:
        raise _error("invalid_request", "书面依据指针与指纹必须同有同无。")
    if not isinstance(basis_uri, str) or not basis_uri.strip() or len(basis_uri) > 500:
        raise _error("invalid_request", "basis_uri 必填且 ≤500 字符。")
    digest = basis_sha256.strip().lower() if isinstance(basis_sha256, str) else ""
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise _error("invalid_request", "basis_sha256 必须是 64 位十六进制指纹。")
    return basis_uri.strip(), digest


def registration_entries_view() -> dict[str, dict[str, str]]:
    """四类注册入口注册表（R1–R4；齐备性由机器闸测试双向钉住）。"""
    return {role: dict(spec) for role, spec in REGISTRATION_ENTRIES.items()}


def paid_options() -> dict[str, dict[str, str]]:
    """三个付费选项（诊断完成后呈现；任务书 §10）。

    档位标签与描述派生自 G2 ``DIAGNOSIS_PROJECT_TIERS``（单一权威，不复制
    第二份措辞）；**零金额零数值**（哨兵用例断言载荷无数字）。
    """
    options: dict[str, dict[str, str]] = {}
    for key, tier in DIAGNOSIS_PROJECT_TIERS.items():
        options[key] = {
            "label": str(tier["label"]),
            "description": str(tier["description"]),
            "follow_up": ADVISOR_FOLLOW_UP_NOTE,
        }
    for spec in options.values():
        assert not _DIGIT_RE.search("".join(spec.values())), "付费选项载荷不得含数字"
    return options


def register_enterprise(
    session: Session,
    *,
    username: object,
    display_name: object,
    password: object,
    email: object,
    subject_key_raw: object,
    problem_description: object,
    org_id: object = None,
    request_id: object = None,
) -> dict[str, Any]:
    """企业自助注册主体与额度层（R1；**当事人自证**，无 admin 门）。

    多客户 M2 起由统一注册面（``fde_api/registration``）委托调用——本函数只管
    账号行之上的商业承载：身份分层（``commercial_role='R1'``，G1 结构复用）＋
    主体与免费额度（同主体幂等——已存在则**绝不新建、绝不重置**，ADR-004
    §1.2）＋事件留痕（事件 actor＝新注册的当事人本人）。账号行由
    ``register_self_service_user`` 建立：初始角色按 ADR-M2 §2 矩阵升为
    ``project_lead``（org 内——企业空间 M5 的组织者角色），注册状态落
    ``pending_email``（邮箱验证后推进，ADR-M4 状态机）；``email`` 必填
    （验证通道）、``org_id`` 由统一注册面按 subject_key get-or-create 后传入
    （建号即建 org，同主体幂等）。
    """
    subject_key = normalize_subject_key(subject_key_raw)
    display = _require_str(display_name, "display_name", max_len=160)
    problem = _require_str(problem_description, "problem_description", max_len=2000)
    if request_id is not None and not isinstance(request_id, str):
        raise _error("invalid_request", "request_id 必须是字符串。")
    if not isinstance(username, str) or not isinstance(password, str):
        raise _error("invalid_request", "username/password 必须是字符串。")
    if not isinstance(email, str) or not email:
        raise _error("invalid_request", "email 必填（注册面邮箱验证通道）。")
    if not isinstance(org_id, str) or not org_id:
        raise _error("invalid_request", "org_id 必填（统一注册面建号即建 org）。")
    try:
        user = register_self_service_user(
            session,
            username=username,
            display_name=display,
            password=password,
            role=ROLE_PROJECT_LEAD,
            email=email,
            org_id=org_id,
            registration_state="pending_email",
        )
    except UserServiceError as error:
        raise _error(error.code, error.message, error.status) from None
    subject = session.get(EnterpriseQuotaSubject, subject_key)
    quota_created = False
    quota: EnterpriseFreeQuota | None
    if subject is None:
        subject = EnterpriseQuotaSubject(
            subject_key=subject_key,
            display_name=display,
            first_user_id=user.id,
            problem_description=problem,
        )
        quota = EnterpriseFreeQuota(subject_key=subject_key, granted_by_user_id=user.id)
        session.add(subject)
        session.add(quota)
        quota_created = True
    else:
        # 同主体再注册：新账号可建（企业其他经办人），额度绝不新建/不重置；
        # 问题描述仅在主体尚无时补写（首次登记为准）。
        quota = session.get(EnterpriseFreeQuota, subject_key)
        if subject.problem_description is None:
            subject.problem_description = problem
    session.add(CommercialEntitlement(user_id=user.id, commercial_role="R1"))
    session.flush()
    record_event(
        session,
        user,
        "enterprise_self_registered",
        user,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "subject_key": subject_key,
            "display_name": subject.display_name,
            "quota_created": quota_created,
        },
    )
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "org_id": org_id,
        "subject_key": subject_key,
        "quota_created": quota_created,
        "quota_state": quota.state if quota is not None else None,
    }


def get_enterprise_space_view(
    session: Session, *, actor: User, subject_key_raw: object
) -> dict[str, Any]:
    """企业空间读面（绑定账号本人或 admin；他人一律 404——CR-062 拍板：不透主体存在性，对齐 regional partner 面先例）。"""
    subject_key = normalize_subject_key(subject_key_raw)
    subject = session.get(EnterpriseQuotaSubject, subject_key)
    quota = session.get(EnterpriseFreeQuota, subject_key)
    if actor.role != ROLE_ADMIN:
        # CR-062：他人先于存在性判断——404 同码同文案，USCC 批量探测不可分辨
        # 「主体不存在」与「主体存在但非本方」。
        if subject is None or quota is None or quota.bound_user_id != actor.id:
            raise _error("enterprise_space_not_found", "企业空间不存在。", 404)
    elif subject is None or quota is None:
        raise _error("enterprise_space_not_found", "企业空间不存在。", 404)
    triage_rows = session.scalars(
        select(EnterpriseTriageDecision)
        .where(EnterpriseTriageDecision.subject_key == subject_key)
        .order_by(EnterpriseTriageDecision.decided_at.desc())
    ).all()
    choice_rows = session.scalars(
        select(EnterprisePaidOptionChoice)
        .where(EnterprisePaidOptionChoice.subject_key == subject_key)
        .order_by(EnterprisePaidOptionChoice.chosen_at.desc())
    ).all()
    current_choice = next((r for r in choice_rows if r.superseded_at is None), None)
    # 交付项目读面：企业代号连接既有 projects.enterprise_code 域 + 既有可见性
    matched = session.scalars(
        select(Project).where(Project.enterprise_code == subject.display_name)
    ).all()
    projects_out = [
        {
            "project_id": item.id,
            "project_code": item.project_code,
            "name": item.name,
            "status": item.status,
        }
        for item in matched
        if project_access(actor, item).can_view
    ]
    # 成员邀请面（M5-1）：本 org 成员或 admin 可见邀请清单；org 按 subject_key 反查。
    invitations: list[dict[str, Any]] = []
    org_row = session.scalar(select(Org).where(Org.subject_key == subject_key))
    if org_row is not None:
        try:
            invitations = list_org_invitations(
                session, actor=actor, org_id_raw=org_row.id
            )
        except CommercialServiceError:
            # 非本 org 成员且非 admin（理论上本企业空间读面已 gating 到绑定账号/
            # admin，此处兜底不泄露邀请面）
            invitations = []
    return {
        "subject": {
            "subject_key": subject_key,
            "display_name": subject.display_name,
            "problem_description": subject.problem_description,
        },
        "quota": serialize_quota(quota, subject),
        "engagement_state": (
            "paid_delivery" if current_choice is not None else "self_service"
        ),
        "space": {
            "registration_entry": dict(REGISTRATION_ENTRIES["R1"]),
            "projects": projects_out,
        },
        "triage_decisions": [serialize_triage_decision(r) for r in triage_rows],
        "paid_options": {
            "options": paid_options(),
            "current_choice": (
                serialize_choice(current_choice) if current_choice is not None else None
            ),
            "advisor_follow_up": ADVISOR_FOLLOW_UP_NOTE,
        },
        "invitations": invitations,
        "org_id": org_row.id if org_row is not None else None,
        "registration_entries": registration_entries_view(),
    }


def record_triage_decision(
    session: Session,
    *,
    actor: User,
    subject_key_raw: object,
    tier: object,
    rationale: object,
    basis_uri: object = None,
    basis_sha256: object = None,
    request_id: object = None,
    confirm_password: object = None,
) -> dict[str, Any]:
    """三档分流人工判定（交付咨询环节；admin+密码双闸；诊断完成后才可判定）。"""
    _require_admin(actor)
    _confirm_password(session, actor, confirm_password)
    subject_key = normalize_subject_key(subject_key_raw)
    quota = session.get(EnterpriseFreeQuota, subject_key)
    if quota is None:
        raise _error("quota_not_found", "该主体尚无免费额度记录。", 404)
    if quota.state != "completed":
        raise _error("diagnosis_not_completed", "诊断完成后才能进行三档分流判定。", 409)
    if not isinstance(tier, str) or tier not in ENTERPRISE_TRIAGE_TIERS:
        raise _error(
            "invalid_tier",
            "分流档位必须是 " + "/".join(ENTERPRISE_TRIAGE_TIERS) + " 之一。",
        )
    rationale_text = _require_str(rationale, "rationale", max_len=2000)
    basis = _validate_basis(basis_uri, basis_sha256)
    row = EnterpriseTriageDecision(
        subject_key=subject_key,
        tier=tier,
        decided_by_user_id=actor.id,
        rationale=rationale_text,
        basis_uri=basis[0] if basis else None,
        basis_sha256=basis[1] if basis else None,
        request_id=request_id if isinstance(request_id, str) else None,
    )
    session.add(row)
    session.flush()
    record_event(
        session,
        actor,
        "enterprise_triage_decided",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "subject_key": subject_key,
            "tier": row.tier,
            "rationale": row.rationale,
        },
    )
    return serialize_triage_decision(row)


def record_paid_option_choice(
    session: Session,
    *,
    actor: User,
    subject_key_raw: object,
    option_key: object,
    request_id: object = None,
) -> dict[str, Any]:
    """企业选择付费选项（**只认绑定账号本人**；诊断完成后可选；换主意＝再选）。

    admin 即便越权调用也 403（不绑定主体）——「企业自主选择不被取消」的
    服务层保证；append-only：旧行写 ``superseded_at`` 取代，无任何取消路径。
    """
    subject_key = normalize_subject_key(subject_key_raw)
    quota = _lock_quota(session, subject_key)
    if quota.bound_user_id != actor.id:
        raise _error(
            "enterprise_choice_forbidden",
            "付费选项只能由企业绑定账号本人选择；平台不代选、不取消、不改选。",
            403,
        )
    if quota.state != "completed":
        raise _error("diagnosis_not_completed", "诊断完成后才能选择付费选项。", 409)
    if not isinstance(option_key, str) or option_key not in ENTERPRISE_TRIAGE_TIERS:
        raise _error(
            "invalid_paid_option",
            "付费选项必须是 " + "/".join(ENTERPRISE_TRIAGE_TIERS) + " 之一。",
        )
    active_rows = session.scalars(
        select(EnterprisePaidOptionChoice)
        .where(EnterprisePaidOptionChoice.subject_key == subject_key)
        .where(EnterprisePaidOptionChoice.superseded_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    superseded_at = _now()
    for row in active_rows:
        row.superseded_at = superseded_at
    choice = EnterprisePaidOptionChoice(
        subject_key=subject_key,
        option_key=option_key,
        chosen_by_user_id=actor.id,
    )
    session.add(choice)
    session.flush()
    record_event(
        session,
        actor,
        "enterprise_paid_option_choice_recorded",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "subject_key": subject_key,
            "option_key": choice.option_key,
            "superseded_previous": bool(active_rows),
        },
    )
    return serialize_choice(choice)


def record_advisor_note(
    session: Session,
    *,
    actor: User,
    subject_key_raw: object,
    choice_id: object,
    note: object,
    confirm_password: object = None,
    request_id: object = None,
) -> dict[str, Any]:
    """顾问跟进注记（admin+密码；只能补注记三元组，不能动选择本体）。"""
    _require_admin(actor)
    _confirm_password(session, actor, confirm_password)
    subject_key = normalize_subject_key(subject_key_raw)
    if session.get(EnterpriseFreeQuota, subject_key) is None:
        raise _error("quota_not_found", "该主体尚无免费额度记录。", 404)
    if not isinstance(choice_id, str) or not choice_id:
        raise _error("invalid_request", "choice_id 必填。")
    choice = session.get(EnterprisePaidOptionChoice, choice_id)
    if choice is None or choice.subject_key != subject_key:
        raise _error("choice_not_found", "付费选项选择行不存在。", 404)
    if choice.advisor_note is not None:
        raise _error("advisor_note_already_recorded", "该选择行已有顾问跟进注记。", 409)
    note_text = _require_str(note, "note", max_len=500)
    choice.advisor_note = note_text
    choice.advisor_user_id = actor.id
    choice.advisor_at = _now()
    session.flush()
    record_event(
        session,
        actor,
        "enterprise_paid_option_advisor_note",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "subject_key": subject_key,
            "choice_id": choice.id,
            "option_key": choice.option_key,
        },
    )
    return serialize_choice(choice)


def serialize_triage_decision(row: EnterpriseTriageDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "subject_key": row.subject_key,
        "tier": row.tier,
        "tier_label": DIAGNOSIS_PROJECT_TIERS[row.tier]["label"],
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "rationale": row.rationale,
        "basis_uri": row.basis_uri,
        "basis_sha256": row.basis_sha256,
    }


def serialize_choice(row: EnterprisePaidOptionChoice) -> dict[str, Any]:
    return {
        "id": row.id,
        "subject_key": row.subject_key,
        "option_key": row.option_key,
        "option_label": DIAGNOSIS_PROJECT_TIERS[row.option_key]["label"],
        "chosen_by_user_id": row.chosen_by_user_id,
        "chosen_at": row.chosen_at.isoformat() if row.chosen_at else None,
        "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None,
        "advisor_note": row.advisor_note,
        "advisor_user_id": row.advisor_user_id,
        "advisor_at": row.advisor_at.isoformat() if row.advisor_at else None,
    }


# ── 企业组织成员邀请（M5-1）──────────────────────────────────────────────
# 邀请是 org 归属面，不是第二套权限体系（红线 8）：接受邀请唯一副作用＝把受邀
# 用户 users.org_id 置为本 org（归属维度，可见性由 project_org_scope_filter 既有
# 谓词覆盖）。一次性令牌 + 邮箱绑定（sec 评审：邀请是社会工程攻击面）。
ORG_INVITATION_HOURS = 72  # 邀请链接有效期（与注册验证令牌同量级，单一常量不落业务数值）
_INVITE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_invite_email(value: object) -> str:
    """邀请目标邮箱：NFKC 归一化小写；格式宽松校验（与 auth 邮箱归一化同口径）。"""
    if not isinstance(value, str) or not value.strip():
        raise _error("invalid_request", "invited_email 必填。")
    normalized = re.sub(r"\s+", "", value).strip().lower()
    if len(normalized) > 255 or not _INVITE_EMAIL_RE.match(normalized):
        raise _error("invalid_email", "invited_email 格式不正确。")
    return normalized


def _new_invite_token() -> tuple[str, str, datetime]:
    """一次性邀请令牌：明文只回传一次（给邀请人生成链接），库内只存 sha256 指纹。"""
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=ORG_INVITATION_HOURS)
    return raw, digest, expires


def _org_or_404(session: Session, org_id_raw: object) -> Org:
    if not isinstance(org_id_raw, str) or not org_id_raw:
        raise _error("invalid_request", "org_id 必填。")
    org = session.get(Org, org_id_raw)
    if org is None:
        raise _error("org_not_found", "组织不存在。", 404)
    return org


def _require_org_member(actor: User, org: Org) -> None:
    """邀请人必须是该 org 成员（users.org_id == org.id）或 admin（平台能力）。"""
    if actor.role == ROLE_ADMIN:
        return
    if actor.org_id != org.id:
        raise _error(
            "org_member_required",
            "只有本组织成员或系统运维员可以邀请成员。",
            403,
        )


def invite_org_member(
    session: Session,
    *,
    actor: User,
    org_id_raw: object,
    invited_email: object,
    request_id: object = None,
) -> dict[str, Any]:
    """发起组织成员邀请（返回一次性明文令牌，邀请人自行发送链接）。

    邀请人＝本 org 成员（project_lead 等）或 admin。每 org 同邮箱至多一份
    待接受邀请（部分唯一索引兜底；此处先友好 409）。令牌指纹入库，明文只回传一次。
    """
    org = _org_or_404(session, org_id_raw)
    _require_org_member(actor, org)
    email = _validate_invite_email(invited_email)
    # 友好预检：已存在待接受邀请（同 org+邮箱）
    pending = session.scalar(
        select(OrgMemberInvitation).where(
            OrgMemberInvitation.org_id == org.id,
            OrgMemberInvitation.invited_email == email,
            OrgMemberInvitation.accepted_at.is_(None),
            OrgMemberInvitation.revoked_at.is_(None),
        )
    )
    if pending is not None:
        raise _error("invitation_already_pending", "该邮箱已有待接受的邀请。", 409)
    raw, digest, expires = _new_invite_token()
    invitation = OrgMemberInvitation(
        org_id=org.id,
        invited_email=email,
        token_sha256=digest,
        token_expires_at=expires,
        created_by_user_id=actor.id,
    )
    session.add(invitation)
    session.flush()
    record_event(
        session,
        actor,
        "org_member_invited",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "org_id": org.id,
            "invited_email": email,
            "invitation_id": invitation.id,
        },
    )
    return {
        "invitation_id": invitation.id,
        "org_id": org.id,
        "invited_email": email,
        # 明文令牌仅此一次回传（邀请人据此拼装邀请链接外发）
        "token": raw,
        "expires_at": expires.isoformat(),
    }


def accept_org_member_invitation(
    session: Session,
    *,
    actor: User,
    raw_token: object,
    request_id: object = None,
) -> dict[str, Any]:
    """接受邀请（明文令牌；接受即归属）。

    安全闸门（sec 评审结论）：① 令牌必须存在且未被消费/撤销/过期；
    ② actor.email 必须与 invited_email 归一化相等（令牌泄露只被目标账号消费）；
    ③ actor 必须是平台身份（org_id IS NULL）——禁止把已归属别家 org 的账号拽过来。
    """
    if not isinstance(raw_token, str) or not raw_token.strip():
        raise _error("invalid_request", "token 必填。")
    digest = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    invitation = session.scalar(
        select(OrgMemberInvitation).where(OrgMemberInvitation.token_sha256 == digest)
    )
    if invitation is None:
        raise _error("invitation_not_found", "邀请不存在或已失效。", 404)
    now = datetime.now(timezone.utc)
    if invitation.revoked_at is not None:
        raise _error("invitation_revoked", "该邀请已被撤销。", 410)
    if invitation.accepted_at is not None:
        raise _error("invitation_already_accepted", "该邀请已被接受。", 409)
    if invitation.token_expires_at is not None and invitation.token_expires_at < now:
        raise _error("invitation_expired", "该邀请已过期。", 410)
    actor_email = (actor.email or "").strip().lower()
    if actor_email != invitation.invited_email:
        raise _error(
            "invitation_email_mismatch",
            "接受邀请的账号邮箱与受邀邮箱不一致。",
            403,
        )
    if actor.org_id is not None:
        raise _error(
            "already_in_org",
            "当前账号已归属于某个组织，无法重复加入。",
            409,
        )
    org = session.get(Org, invitation.org_id)
    if org is None:
        raise _error("org_not_found", "邀请所属组织不存在。", 404)
    # g.current_user 在鉴权装饰器里已被 detach（装饰器关闭了取用户的 session），
    # 此处必须在事务 session 内重新取回 actor 行再改属性，否则脱离会话的修改
    # 不会被 flush/提交（M5-1 实测：分离的 actor 改 org_id 静默不落库）。
    actor_user = session.get(User, actor.id)
    if actor_user is None:
        raise _error("actor_not_found", "当前账号不存在。", 404)
    actor_user.org_id = org.id
    invitation.accepted_by_user_id = actor.id
    invitation.invited_user_id = actor.id
    invitation.accepted_at = now
    session.flush()
    record_event(
        session,
        actor,
        "org_member_invitation_accepted",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "org_id": org.id,
            "invitation_id": invitation.id,
        },
    )
    return serialize_org_invitation(invitation)


def revoke_org_member_invitation(
    session: Session,
    *,
    actor: User,
    invitation_id_raw: object,
    request_id: object = None,
) -> dict[str, Any]:
    """撤销待接受邀请（仅邀请人或 admin；已接受/已过期不可撤销）。"""
    if not isinstance(invitation_id_raw, str) or not invitation_id_raw:
        raise _error("invalid_request", "invitation_id 必填。")
    invitation = session.get(OrgMemberInvitation, invitation_id_raw)
    if invitation is None:
        raise _error("invitation_not_found", "邀请不存在。", 404)
    if invitation.accepted_at is not None:
        raise _error("invitation_already_accepted", "已接受的邀请不可撤销。", 409)
    if invitation.revoked_at is not None:
        raise _error("invitation_already_revoked", "该邀请已被撤销。", 409)
    if actor.role != ROLE_ADMIN and invitation.created_by_user_id != actor.id:
        raise _error("org_member_required", "只有邀请人或系统运维员可以撤销邀请。", 403)
    invitation.revoked_at = datetime.now(timezone.utc)
    session.flush()
    record_event(
        session,
        actor,
        "org_member_invitation_revoked",
        actor,
        {
            "request_id": request_id if isinstance(request_id, str) else str(uuid4()),
            "org_id": invitation.org_id,
            "invitation_id": invitation.id,
        },
    )
    return serialize_org_invitation(invitation)


def list_org_invitations(
    session: Session, *, actor: User, org_id_raw: object
) -> list[dict[str, Any]]:
    """列出某 org 的全部邀请（pending/accepted/revoked 全量，按创建时间倒序）。

    可见性：本 org 成员（users.org_id == org.id）或 admin。
    """
    org = _org_or_404(session, org_id_raw)
    _require_org_member(actor, org)
    rows = session.scalars(
        select(OrgMemberInvitation)
        .where(OrgMemberInvitation.org_id == org.id)
        .order_by(OrgMemberInvitation.created_at.desc())
    ).all()
    return [serialize_org_invitation(r) for r in rows]


def serialize_org_invitation(row: OrgMemberInvitation) -> dict[str, Any]:
    state = "pending"
    if row.revoked_at is not None:
        state = "revoked"
    elif row.accepted_at is not None:
        state = "accepted"
    return {
        "id": row.id,
        "org_id": row.org_id,
        "invited_email": row.invited_email,
        "invited_user_id": row.invited_user_id,
        "created_by_user_id": row.created_by_user_id,
        "state": state,
        "accepted_by_user_id": row.accepted_by_user_id,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "expires_at": row.token_expires_at.isoformat() if row.token_expires_at else None,
    }


__all__ = [
    "ADVISOR_FOLLOW_UP_NOTE",
    "CommercialServiceError",
    "ENGAGEMENT_STATES",
    "accept_org_member_invitation",
    "get_enterprise_space_view",
    "invite_org_member",
    "list_org_invitations",
    "paid_options",
    "record_advisor_note",
    "record_paid_option_choice",
    "record_triage_decision",
    "register_enterprise",
    "registration_entries_view",
    "revoke_org_member_invitation",
    "serialize_choice",
    "serialize_org_invitation",
    "serialize_triage_decision",
]
