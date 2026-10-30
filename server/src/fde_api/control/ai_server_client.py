"""Shared AI Server entry point for chat and existing structured AI workflows."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import requests
from flask import current_app, g, has_request_context
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.control.dsh_runtime import DSHRuntimeError, dsh_runtime
from fde_api.control.mcp_gateway import issue_mcp_token
from fde_api.control.model_preferences import resolve_model_preference
from fde_api.extensions import db

logger = logging.getLogger(__name__)

# DSH 运行时不可用时，可以降级为「直连供应商」的故障码。
# 直连路径不需要 DSH 服务、不签发 MCP token，因此工具能力不可用，
# 但对话本身仍可继续 —— 否则在没有部署 DSH 的环境里 AI 完全没有出路。
# dsh_execution_conflict 不在列：那是幂等冲突，降级会导致同一次执行跑两遍。
DEGRADABLE_DSH_CODES = frozenset({
    "dsh_not_enabled",
    "dsh_not_configured",
    "dsh_unavailable",
    "dsh_authentication_failed",
    "dsh_timeout",
})


def _provider_usage_from_response(payload: dict[str, Any], model_name: str) -> dict[str, Any]:
    """Map an OpenAI-compatible usage block onto the DSH usage shape."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {"complete": False, "calls": []}
    try:
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return {"complete": False, "calls": []}
    return {
        "complete": True,
        "calls": [{
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }],
    }


def direct_provider_completion(
    *,
    model: dict[str, Any],
    prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = 16384,
    timeout_seconds: int = 300,
    session: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call an OpenAI-compatible provider directly, without the DSH runtime.

    Used as the degraded path when no DSH runtime is deployed. The model
    descriptor must carry base_url / api_key / model — every producer of
    that dict (model preferences, system default, structured overrides)
    already does.
    """
    base_url = str(model.get("base_url") or "").rstrip("/")
    model_name = str(model.get("model") or "")
    api_key = model.get("api_key")
    if not base_url or not model_name:
        raise DSHRuntimeError("ai_model_not_configured", "尚未配置可直连的模型。", retryable=False)
    if not api_key:
        raise DSHRuntimeError("ai_model_not_configured", "尚未配置可直连的模型 API Key。", retryable=False)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    http = session or requests.Session()
    try:
        response = http.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_name, "messages": messages, "max_tokens": max_tokens},
            timeout=timeout_seconds,
        )
    except requests.Timeout as error:
        raise DSHRuntimeError("ai_timeout", "AI 请求超时，请稍后重试。", retryable=True) from error
    except requests.RequestException as error:
        raise DSHRuntimeError("ai_unavailable", "暂时无法连接 AI 服务。", retryable=True) from error

    if response.status_code == 429:
        raise DSHRuntimeError("ai_rate_limited", "AI 服务额度或频率受限，请稍后重试。", retryable=True)
    if response.status_code in (401, 403):
        raise DSHRuntimeError("ai_authentication_failed", "AI 服务认证失败，请检查 API Key。", retryable=False)
    if response.status_code >= 400:
        raise DSHRuntimeError(
            "ai_unavailable", "AI 服务返回错误，请稍后重试。", retryable=response.status_code >= 500)

    try:
        payload = response.json()
    except ValueError as error:
        raise DSHRuntimeError("ai_output_invalid", "AI 服务未返回有效结果。", retryable=True) from error
    if not isinstance(payload, dict):
        raise DSHRuntimeError("ai_output_invalid", "AI 服务未返回有效结果。", retryable=True)
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise DSHRuntimeError("ai_output_invalid", "AI 服务未返回有效结果。", retryable=True) from error
    if not isinstance(text, str) or not text.strip():
        raise DSHRuntimeError("ai_output_invalid", "AI 服务未返回有效结果。", retryable=True)
    return text, _provider_usage_from_response(payload, model_name)


ai_actor_id: ContextVar[str | None] = ContextVar("ai_actor_id", default=None)


def apply_runtime_plugin(*, action, plugin):
    from fde_api.control.service import ControlServiceError
    runtime = dsh_runtime.current.primary
    response = runtime._request("POST", "/v1/plugins/apply", json={"action": action, "plugin": plugin}, timeout=300)
    payload = runtime._json_object(response)
    if response.status_code >= 400:
        raise ControlServiceError(payload.get("error", "plugin_execution_failed"), payload.get("message", "AI Server 插件变更失败。"), response.status_code)
    return payload


def execute_ai_prompt(*, user_id: str, prompt: str, execution_id: str | None = None,
                      project_id: str | None = None, preference_id: str | None = None,
                      use_tools: bool = True, system_prompt: str | None = None,
                      max_tokens: int = 16384, model_override: dict | None = None,
                      capabilities: list[str] | None = None, deep_thinking: bool | None = None, all_projects: bool = False,
                      return_metadata: bool = False) -> str | dict:
    identifier = execution_id or str(uuid4())
    settings = current_app.config["SETTINGS"]
    runtime = dsh_runtime.current.primary
    dsh_usable = runtime.enabled
    with db.session() as session:
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            raise DSHRuntimeError("ai_access_denied", "账号已停用。", retryable=False)
        from fde_api.control.access import effective_ai_access
        level, _ = effective_ai_access(user)
        if level == "disabled":
            raise DSHRuntimeError("ai_access_denied", "管理员尚未为此账号开放 AI 权限。", retryable=False)
        model = model_override or resolve_model_preference(session, user_id, preference_id)
        if deep_thinking and model.get("provider") not in {"deepseek", "deepseek-official"}:
            from fde_api.control.service import ControlServiceError
            raise ControlServiceError("thinking_unsupported", "当前模型暂不支持手动深度思考，请关闭开关或选择 DeepSeek 模型。", 400)
        use_tools = use_tools and model.get("supports_tools", True)
        # 工具只能经由 DSH 转发；没有可用运行时时不签发 MCP token。
        token = issue_mcp_token(user, project_id=None if all_projects else project_id, capabilities=capabilities, execution_id=identifier) if (use_tools and dsh_usable) else None
    if not dsh_usable:
        # 没有部署 DSH 运行时：直接走供应商直连降级路径（带本地工具循环）。
        return _degraded_direct_result(
            model=model, prompt=prompt, system_prompt=system_prompt,
            max_tokens=max_tokens, timeout_seconds=settings.dsh_timeout_seconds,
            reason="dsh_not_enabled", return_metadata=return_metadata,
            user_id=user_id, project_id=project_id, execution_id=identifier,
            use_tools=use_tools)
    body = {"schema_version": "fde-dsh-v1", "execution_id": identifier,
            "actor": {"user_id": user_id}, "scope": {"project_id": project_id},
            "agent_profile": "fde-assistant" if use_tools else "fde-structured",
            "prompt": prompt, "model_config": model, "max_tokens": max_tokens}
    if deep_thinking is not None:
        body["deep_thinking"] = deep_thinking
    if token:
        body["mcp"] = {"url": settings.ai_internal_api_url.rstrip("/") + "/api/v1/internal/ai/mcp", "token": token}
    if system_prompt:
        body["system_prompt"] = system_prompt
    try:
        response = runtime._request("POST", "/v1/executions", json=body, timeout=settings.dsh_timeout_seconds,
                                    headers={"Idempotency-Key": identifier})
    except DSHRuntimeError as error:
        if error.code not in DEGRADABLE_DSH_CODES:
            raise
        logger.warning("DSH runtime unusable, degrading to direct provider call code=%s", error.code)
        return _degraded_direct_result(
            model=model, prompt=prompt, system_prompt=system_prompt,
            max_tokens=max_tokens, timeout_seconds=settings.dsh_timeout_seconds,
            reason=error.code, return_metadata=return_metadata,
            user_id=user_id, project_id=project_id, execution_id=identifier,
            use_tools=use_tools)
    if response.status_code >= 400:
        raise runtime._service_error(response.status_code)
    result = runtime._json_object(response)
    text = result.get("output", {}).get("text")
    if result.get("status") != "succeeded" or not isinstance(text, str) or not text.strip():
        raise DSHRuntimeError("ai_output_invalid", "AI Server 未返回有效结果。", retryable=True)
    if return_metadata:
        return {"text": text, "model": {"provider": model.get("provider", ""), "name": model.get("model", "")},
                "provider_usage": result.get("provider_usage", {"complete": False, "calls": []})}
    return text


def _degraded_direct_result(*, model: dict[str, Any], prompt: str, system_prompt: str | None,
                            max_tokens: int, timeout_seconds: int, reason: str,
                            return_metadata: bool, user_id: str | None = None,
                            project_id: str | None = None, execution_id: str | None = None,
                            use_tools: bool = True) -> str | dict:
    """Run the direct provider call and shape it like a normal AI Server result.

    When tools are wanted, the provider is called with the workbench tool
    catalogue and the model's tool calls are executed in-process — the same
    tools and the same capability gate the MCP route uses, just without the
    DSH hop. `degraded` marks the run as having bypassed the DSH runtime.
    """
    tool_trace: list[dict[str, Any]] = []
    if use_tools and user_id:
        from fde_api.control.ai_tool_loop import direct_tool_completion
        with db.session() as session:
            user = session.get(User, user_id)
            if user is not None:
                text, usage, tool_trace = direct_tool_completion(
                    model=model, prompt=prompt, user=user, project_id=project_id,
                    execution_id=execution_id or str(uuid4()),
                    system_prompt=system_prompt, max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds)
                if not return_metadata:
                    return text
                return {
                    "text": text,
                    "model": {"provider": model.get("provider", ""), "name": model.get("model", "")},
                    "provider_usage": usage,
                    "degraded": True,
                    "degraded_reason": reason,
                    "tools_available": True,
                    "tool_trace": tool_trace,
                }
    text, usage = direct_provider_completion(
        model=model, prompt=prompt, system_prompt=system_prompt,
        max_tokens=max_tokens, timeout_seconds=timeout_seconds)
    if not return_metadata:
        return text
    return {
        "text": text,
        "model": {"provider": model.get("provider", ""), "name": model.get("model", "")},
        "provider_usage": usage,
        "degraded": True,
        "degraded_reason": reason,
        "tools_available": False,
        "tool_trace": tool_trace,
    }


def structured_completion(*, messages, model: str, base_url: str, api_key, max_tokens: int, on_event=None, deep_thinking=None):
    actor = ai_actor_id.get()
    if not actor and has_request_context():
        user = getattr(g, "current_user", None)
        actor = user.id if user else None
    if not actor:
        # Background business jobs already authorize and build their own scoped
        # prompt. No MCP tools are enabled for these structured requests.
        with db.session() as session:
            actor = session.scalar(select(User.id).where(User.role == "admin", User.is_active.is_(True)).limit(1))
    if not actor:
        raise DSHRuntimeError("ai_access_denied", "没有可用的 AI 执行账号。", retryable=False)
    if on_event:
        on_event({"type": "stage_changed", "text": "AI Server 正在生成结构化结果"})
    key = api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else api_key
    from fde_api.control.model_preferences import ModelPreference
    from sqlalchemy import or_
    with db.session() as session:
        has_default = session.scalar(select(ModelPreference.id).where(ModelPreference.is_default.is_(True),
            or_(ModelPreference.owner_user_id == actor, ModelPreference.scope == "public")).limit(1)) is not None
    # DSH 路径的失败必须落在同一个错误分类里：调用方（kimi/deepseek 客户端）
    # 只把 DSHRuntimeError 转成自己的异常类型，其余异常会逃出去被上层当成
    # 未预期错误——重试语义与失败分类都会失效。
    from fde_api.control.service import ControlServiceError
    try:
        value = execute_ai_prompt(user_id=actor, prompt=json.dumps(messages, ensure_ascii=False), use_tools=False,
            system_prompt="按提供的messages逐条理解角色和要求。只输出一个合法JSON对象，不要Markdown代码块，不调用工具。",
            max_tokens=max_tokens, deep_thinking=deep_thinking, model_override=None if has_default else {"model": model, "base_url": base_url, "api_key": key,
                                                "provider": "deepseek" if "deepseek.com" in base_url else "openai-compatible"})
    except ControlServiceError as error:
        # 模型未配置/密钥不可用/无权限等确定性配置问题：重试也不会好。
        raise DSHRuntimeError(error.code, error.message, retryable=False) from error
    from fde_api.ai.deepseek import _parse_json_object
    try:
        parsed = _parse_json_object(value)
    except (json.JSONDecodeError, ValueError) as error:
        # 模型没按 JSON 合同输出（概率性现象）：可重试，且必须带
        # ai_output_invalid 这个分类——否则上层看不到可重试信号。
        logger.warning("AI Server returned non-JSON structured output")
        raise DSHRuntimeError("ai_output_invalid", "AI Server 返回格式不正确。", retryable=True) from error
    if not isinstance(parsed, dict):
        raise DSHRuntimeError("ai_output_invalid", "AI Server 返回格式不正确。", retryable=True)
    if on_event:
        on_event({"type": "content_delta", "text": json.dumps(parsed, ensure_ascii=False)})
    return parsed
