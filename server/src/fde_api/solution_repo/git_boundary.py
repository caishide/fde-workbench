"""Git 操作两级闭集判定（AF3-WP1；D2 已批「边界规则落机器可检」）。

纯函数面：``resolve_op(op, whitelist)`` ——
- ``agent_allowed`` 精确命中 → 放行（服务面按端点暴露，本判定是第二道闸）；
- ``human_only`` 命中 → 拒（403 tool_not_allowed；push/merge/受保护分支直写/
  hookspath 配置永不入 agent 面——04 §3.3：Patch 能写 hook = 下一次人工 git
  操作替 Agent 执行代码）；
- **未知名 fail-closed 拒**（不视为 human_only 放行到人工面——防止误把未知
  操作当待办）。
"""
from __future__ import annotations


from fde_api.solution_repo.path_guard import Verdict

CODE_TOOL_NOT_ALLOWED = "tool_not_allowed"

_OK = Verdict(ok=True, code="", reason="")


def resolve_op(op: str, *, whitelist: dict) -> Verdict:
    """Git 操作闭集判定（第二道闸；第一道＝路由层只暴露 agent_allowed 端点）。"""
    git_ops = whitelist.get("git_ops") or {}
    allowed = set(git_ops.get("agent_allowed") or ())
    human_only = set(git_ops.get("human_only") or ())
    if op in allowed:
        return _OK
    if op in human_only:
        return Verdict(False, CODE_TOOL_NOT_ALLOWED, f"操作须人工执行（human_only）：{op}")
    # 未知名 fail-closed：闭集外一律拒，不放入人工面。
    return Verdict(False, CODE_TOOL_NOT_ALLOWED, f"操作不在白名单闭集内：{op}")
