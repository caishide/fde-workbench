"""多客户 M4 批次 B：企业 org AI 月度预算治理面（admin+密码双闸）。

任务书 §7-M4「AI 预算闸从整实例单值改为按主体额度」的**配置面**：预算值挂
``orgs.ai_monthly_token_budget``（M4 批次 B 加列；``NULL``＝未配置回落实例值，
``0``＝不限额，沿 E7 心智），判定单一权威点在 ``ai/auditing.py::
subject_budget_exceeded``——本模块只承载「读 + 设」两件事：

- **读面**：admin 只读（预算值＋当月 org 全员用量＋回退来源标注）。
- **写面**：admin 门＋密码确认双闸（G2 授予先例；密码确认尝试限流同闸）。
  逐动作 ``operation_events`` 留痕（带 request_id，**密码不落事件**）。
- **零数值预写**（G 线纪律）：本模块不播种任何预算数值，未配置即回退。
- 治理面**不进 api_catalog**（与 commercial 治理面同款边界）。
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from fde_api.ai.auditing import org_tokens_used_this_month
from fde_api.auth.confirm_throttle import confirm_attempts_blocked, record_confirm_failure
from fde_api.auth.models import User
from fde_api.auth.passwords import verify_password
from fde_api.orgs.models import Org
from fde_api.projects.events import record_event


class OrgBudgetServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _error(code: str, message: str, status: int) -> OrgBudgetServiceError:
    return OrgBudgetServiceError(code, message, status)


def _require_admin(actor: User) -> None:
    if actor.role != "admin":
        raise _error("commercial_admin_required", "企业 AI 预算管理仅系统管理员可用。", 403)


def _confirm_password(session: Session, actor: User, password: object) -> None:
    if not isinstance(password, str) or not password:
        raise _error("invalid_request", "confirm_password 必填（高风险写人工确认）。", 400)
    # CR-047：密码确认尝试限流——与 auth verify-password / ai 确认闸同 key 同阈值同窗口。
    if confirm_attempts_blocked(actor.id):
        raise _error("too_many_attempts", "密码错误次数过多，请 15 分钟后重试。", 429)
    current = session.get(User, actor.id)
    if current is None or not verify_password(current.password_hash, password):
        record_confirm_failure(actor.id)
        raise _error("invalid_password", "当前账号密码不正确。", 403)


def _load_org(session: Session, org_id: object) -> Org:
    if not isinstance(org_id, str) or not org_id:
        raise _error("invalid_request", "org_id 必填。", 400)
    org = session.get(Org, org_id)
    if org is None:
        raise _error("org_not_found", "组织不存在。", 404)
    return org


def _normalize_budget(raw: object) -> int | None:
    """预算值闭集：``None``（清回未配置）或 ≥0 整数（0=不限额）。"""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _error("invalid_budget", "budget 必须是非负整数或 null（未配置回落实例值）。", 400)
    if raw < 0:
        raise _error("invalid_budget", "budget 必须是非负整数或 null（未配置回落实例值）。", 400)
    return raw


def get_org_ai_budget(session: Session, *, actor: User, org_id: str) -> dict[str, Any]:
    """admin 只读：预算值＋当月 org 全员用量＋回退来源标注。"""
    _require_admin(actor)
    org = _load_org(session, org_id)
    configured = org.ai_monthly_token_budget
    return {
        "org_id": org.id,
        "org_name": org.name,
        "org_type": org.org_type,
        "subject_key": org.subject_key,
        "configured_budget": configured,
        # effective＝判定实际采用的值：未配置回落实例值由读侧标注，不在库层编造。
        "fallback_to_instance": configured is None,
        "tokens_used_this_month": org_tokens_used_this_month(session, org.id),
    }


def set_org_ai_budget(
    session: Session,
    *,
    actor: User,
    org_id: str,
    budget: object,
    confirm_password: object,
) -> dict[str, Any]:
    """设定企业 org AI 月度预算（admin+密码双闸；零数值预写纪律由调用方保证）。"""
    _require_admin(actor)
    _confirm_password(session, actor, confirm_password)
    org = _load_org(session, org_id)
    normalized = _normalize_budget(budget)
    previous = org.ai_monthly_token_budget
    org.ai_monthly_token_budget = normalized
    session.flush()
    record_event(
        session,
        actor,
        "org_ai_budget_set",
        actor,
        {
            "request_id": str(uuid4()),
            "org_id": org.id,
            "org_name": org.name,
            "previous_budget": previous,
            "budget": normalized,
        },
    )
    return {
        "org_id": org.id,
        "configured_budget": normalized,
        "fallback_to_instance": normalized is None,
        "changed": previous != normalized,
    }
