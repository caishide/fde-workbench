"""Redis-backed AI executions with live, provider-supplied stream events.

E8 可靠执行：执行体不再挂 daemon 线程（进程重启即丢），改为 outbox →
BackgroundJob → worker 消费的持久化模型。执行参数（operation/actor/payload）
随状态存 Redis，任务行只携带 execution_id；worker 重放/重复投递时按状态
幂等跳过，不产生重复副作用。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from flask import current_app

from fde_api.ai.ai_opportunity_service import discover_ai_opportunities
from fde_api.ai.industry_template_service import chat_about_template, generate_project_configuration, generate_template_draft
from fde_api.ai.memo_merge_service import merge_research_memos
from fde_api.ai.research_form_service import generate_project_research_form, generate_research_form
from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.jobs.handlers import register_handler
from fde_api.jobs.outbox import enqueue_outbox


EXECUTION_TTL_SECONDS = 60 * 60
MAX_EVENTS = 1_200

OPERATIONS: dict[str, tuple[Callable[..., dict[str, Any]], set[str]]] = {
    "industry_template_chat": (chat_about_template, {"admin"}),
    "project_draft_chat": (chat_about_template, {"admin", "project_lead"}),
    "industry_template_generate": (generate_template_draft, {"admin"}),
    "project_draft_generate": (generate_project_configuration, {"admin", "project_lead"}),
    "industry_research_form_generate": (generate_research_form, {"admin"}),
    "project_research_form_generate": (generate_project_research_form, {"admin", "project_lead", "fde_engineer"}),
    "project_ai_opportunities_discover": (discover_ai_opportunities, {"admin", "project_lead", "fde_engineer"}),
    "project_research_memos_merge": (merge_research_memos, {"admin", "project_lead", "fde_engineer"}),
}


class AIExecutionError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def start_execution(*, actor: User, operation: str, payload: object) -> dict[str, Any]:
    if operation not in OPERATIONS or not isinstance(payload, dict):
        raise AIExecutionError("invalid_request", "AI 执行请求格式不正确。", 400)
    _handler, roles = OPERATIONS[operation]
    if actor.role not in roles:
        raise AIExecutionError("forbidden", "当前账号没有执行该 AI 操作的权限。", 403)
    execution_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    state = {
        "id": execution_id,
        "operation": operation,
        "status": "running",
        "stage": "正在准备上下文",
        "actor_id": actor.id,
        # E8：执行参数随状态持久化（旧线程模型靠参数传递；worker 消费时
        # 只携带 execution_id，必须能从状态还原全部入参）。
        "payload": payload,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
    }
    redis = current_app.extensions["fde_api_redis"]
    redis.setex(_state_key(execution_id), EXECUTION_TTL_SECONDS, json.dumps(state, ensure_ascii=False))
    _append_event(redis, execution_id, {"type": "stage_changed", "text": "正在准备上下文"})
    # E8：任务落库（outbox → BackgroundJob），由 worker 消费；进程重启后
    # 任务仍在数据库里，不会像 daemon 线程一样直接丢失。
    session = db.session()
    try:
        with session.begin():
            enqueue_outbox(
                session,
                "ai.execute",
                execution_id,
                {"execution_id": execution_id},
            )
    finally:
        session.close()
    return _public_state(state, events=[])


def get_execution(*, actor: User, execution_id: str, after: int = 0) -> dict[str, Any]:
    redis = current_app.extensions["fde_api_redis"]
    state = _load_state(redis, execution_id)
    if state is None or state.get("actor_id") != actor.id:
        raise AIExecutionError("ai_execution_not_found", "AI 执行记录不存在或已过期。", 404)
    raw_events = redis.lrange(_events_key(execution_id), max(0, after), -1)
    events = [json.loads(item) for item in raw_events]
    return _public_state(state, events=events, event_offset=max(0, after))


def register_ai_execution_handler() -> None:
    """把 AI 执行注册为可被 worker 消费的持久化任务（E8）。"""
    register_handler("ai.execute", execute_ai_execution_job)


def execute_ai_execution_job(job: Any) -> None:
    """worker 入口：按 execution_id 取状态并执行；重放/终态一律幂等跳过。"""
    redis = current_app.extensions["fde_api_redis"]
    execution_id = job.target_id
    state = _load_state(redis, execution_id)
    if state is None:
        # 状态已过期（TTL）而任务行还在：无可执行内容，按成功收尾避免空转重试。
        return
    if state.get("status") != "running":
        # 重放/重复投递：终态执行不产生重复副作用。
        return
    _execute_operation(redis, state)


def _execute_operation(redis: Any, state: dict[str, Any]) -> None:
    execution_id = state["id"]
    actor_id = state["actor_id"]
    operation = state["operation"]
    payload = state.get("payload") or {}
    from fde_api.control.ai_server_client import ai_actor_id
    ai_actor_id.set(actor_id)
    # worker 调用点已有 app 上下文；再嵌套一层保证独立成栈（后台任务与
    # 请求上下文隔离）。
    app = current_app._get_current_object()
    with app.app_context():
        redis = current_app.extensions["fde_api_redis"]
        session = db.session()
        try:
            actor = session.get(User, actor_id)
            if actor is None or not actor.is_active:
                raise AIExecutionError("authentication_required", "登录状态已失效。", 401)
            handler, _roles = OPERATIONS[operation]
            _update_stage(redis, execution_id, "正在等待 AI 响应")

            def on_event(event: dict[str, str]) -> None:
                _append_event(redis, execution_id, event)

            if operation == "industry_research_form_generate":
                result = handler(payload, on_event=on_event)
            else:
                result = handler(actor=actor, payload=payload, on_event=on_event)
            _update_stage(redis, execution_id, "正在校验并整理结果")
            _finish(redis, execution_id, status="completed", result=result)
            _append_event(redis, execution_id, {"type": "completed", "text": "AI 处理完成"})
        except Exception as error:  # public error fields are deliberately filtered below
            code = getattr(error, "code", "internal_error")
            message = getattr(error, "message", None) or getattr(error, "public_message", None) or "AI 处理失败，请稍后重试。"
            status = int(getattr(error, "status", 500))
            _finish(redis, execution_id, status="failed", error={"code": code, "message": str(message), "status": status})
            _append_event(redis, execution_id, {"type": "failed", "text": str(message)})
        finally:
            session.close()


def _update_stage(redis: Any, execution_id: str, stage: str) -> None:
    state = _load_state(redis, execution_id)
    if state is None:
        return
    state["stage"] = stage
    state["updated_at"] = datetime.now(UTC).isoformat()
    redis.setex(_state_key(execution_id), EXECUTION_TTL_SECONDS, json.dumps(state, ensure_ascii=False))
    _append_event(redis, execution_id, {"type": "stage_changed", "text": stage})


def _finish(redis: Any, execution_id: str, *, status: str, result: Any = None, error: Any = None) -> None:
    state = _load_state(redis, execution_id)
    if state is None:
        return
    state.update(status=status, result=result, error=error, updated_at=datetime.now(UTC).isoformat())
    redis.setex(_state_key(execution_id), EXECUTION_TTL_SECONDS, json.dumps(state, ensure_ascii=False))
    redis.expire(_events_key(execution_id), EXECUTION_TTL_SECONDS)


def _append_event(redis: Any, execution_id: str, event: dict[str, str]) -> None:
    payload = {**event, "at": datetime.now(UTC).isoformat()}
    key = _events_key(execution_id)
    redis.rpush(key, json.dumps(payload, ensure_ascii=False))
    redis.ltrim(key, -MAX_EVENTS, -1)
    redis.expire(key, EXECUTION_TTL_SECONDS)


def _load_state(redis: Any, execution_id: str) -> dict[str, Any] | None:
    raw = redis.get(_state_key(execution_id))
    if raw is None:
        return None
    return json.loads(raw)


def _public_state(state: dict[str, Any], *, events: list[dict[str, Any]], event_offset: int = 0) -> dict[str, Any]:
    return {
        "id": state["id"],
        "operation": state["operation"],
        "status": state["status"],
        "stage": state["stage"],
        "created_at": state["created_at"],
        "updated_at": state["updated_at"],
        "result": state.get("result"),
        "error": state.get("error"),
        "events": events,
        "next_offset": event_offset + len(events),
    }


def _state_key(execution_id: str) -> str:
    return f"fde:ai-execution:{execution_id}:state"


def _events_key(execution_id: str) -> str:
    return f"fde:ai-execution:{execution_id}:events"
