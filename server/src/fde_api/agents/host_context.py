"""宿主代理任务书面料读取面（goal-sprint r3；P2′① 咬合的最后一块）。

轮询形态下 run 的 workspace（context.md / task.md / AGENTS.md 三件）由
服务端在发起时刻写入服务端侧工作区（``_write_workspace``）；宿主代理领取
后必须拿到**同一套渲染产物**才能 spawn zcode（任务书即白名单载体，两侧
各渲染一份＝漂移温床）。本模块把服务端已渲染的三件原样读出返回（有界），
宿主代理逐字落盘（见 ``agents/host_agent.py``）——渲染一次、消费两侧。

拆分缘起与依赖形态同 ``host_receipt.py``：agents/service.py 是行数预算
热点（1836，只许变小），本面独立成模块；service 侧 ``_settings`` /
``_verify_host_poll_token`` 一律**函数内惰性引用**（不造顶层 import 环
＋保 monkeypatch 语义）。路由不进 api_catalog（宿主机器面，与 bridge 同
族）；鉴权与回执面同款（X-Host-Poll-Token；仅限**本 token 已领取且未回
执**的 run——信息最小暴露）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fde_api.agents.models import AgentRun

# 面料总字节上限：context.md 本体可达大纪要分段量级（V31-P1），上限取
# 4 MB——超限 = 显式失败（413），宿主侧收不到面料即不 spawn（run 留在
# host_running 由失联标记 + 人工处置，H4 不自动重试）。
_HOST_CONTEXT_MAX_BYTES = 4 * 1024 * 1024

# 三件套文件名（与 workspace_files._write_workspace 渲染面同源；此处独立
# 常量避免 import 单向下依赖——workspace_files 只被 receipt/adapter 面引）。
_CONTEXT_FILES = ("context.md", "task.md", "AGENTS.md")


def fetch_host_run_context(*, presented_token: str, run_id: str) -> dict[str, Any]:
    """宿主代理读取已领取 run 的任务书面料（有界；仅限本 token 的在途 run）。

    状态闸（与回执面同族，信息最小暴露）：

    - run 不存在 → 404；
    - 非 host_poll 通道 / 未领取 → 409（不向提交方确认令牌值）；
    - 令牌与领取不一致 → 403；
    - 已回执（终态）→ 409。

    面料定位：``run.context_ref`` 是发起时刻登记的指针
    （``<workspace_root>/<org>/<run_id>/context.md`` 的 posix 形态）——剥去
    workspace_root 前缀后重新 join 到**当前 Settings 的工作区根**下读取
    （指针可能是旧根的相对串；文件真身永远相对当前根解析），并做根锚校验
    （resolve 后必须仍落在工作区根内，防指针被改写后越界读）。
    """
    from fde_api.agents import service as _svc

    settings = _svc._settings()
    _svc._require_host_poll_enabled(settings)
    token_hash = _svc._verify_host_poll_token(settings, presented_token)

    from fde_api.extensions import db

    with db.session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise _svc._error("agent_run_not_found", "run 不存在。", 404, detail={"run_id": run_id})
        if run.execution_provider != "host_poll":
            raise _svc._error(
                "host_context_rejected", "该 run 不属于宿主轮询通道。", 409, detail={"run_id": run_id}
            )
        if run.host_token_hash is None:
            raise _svc._error(
                "host_context_invalid_state",
                "该 run 未被领取或不在执行态。",
                409,
                detail={"run_id": run_id, "status": run.status},
            )
        if run.host_token_hash != token_hash:
            raise _svc._error("host_poll_forbidden", "读取令牌与领取不一致。", 403, detail={"run_id": run_id})
        if run.status != "host_running" or run.host_receipt_at is not None:
            raise _svc._error(
                "host_context_invalid_state",
                "该 run 未被领取或不在执行态。",
                409,
                detail={"run_id": run_id, "status": run.status},
            )
        context_ref = run.context_ref

    # 指针 → 当前工作区根下的真身路径（根锚校验后读；三件缺席返回空串——
    # 形状恒定，宿主侧逐字落盘不猜）。
    root = Path(settings.agent_workspace_root).resolve()
    prefix = f"{Path(settings.agent_workspace_root).as_posix().strip('/')}/"
    if not isinstance(context_ref, str) or not context_ref.startswith(prefix):
        raise _svc._error("host_context_invalid_state", "context_ref 指针形状无效。", 409, detail={"run_id": run_id})
    relative = context_ref[len(prefix):]
    base_dir = (root / relative).parent.resolve()
    if base_dir != root and root not in base_dir.parents:
        raise _svc._error("host_context_invalid_state", "context_ref 越界（根锚校验失败）。", 409, detail={"run_id": run_id})

    files: dict[str, str] = {}
    total = 0
    for name in _CONTEXT_FILES:
        path = base_dir / name
        if not path.is_file():
            files[name] = ""
            continue
        content = path.read_text(encoding="utf-8")
        total += len(content.encode("utf-8"))
        files[name] = content
        if total > _HOST_CONTEXT_MAX_BYTES:
            raise _svc._error(
                "host_context_too_large",
                f"任务书面料超过 {_HOST_CONTEXT_MAX_BYTES} 字节上限。",
                413,
                detail={"run_id": run_id, "limit": _HOST_CONTEXT_MAX_BYTES},
            )
    return {"run_id": run_id, "files": files}


__all__ = ["fetch_host_run_context"]
