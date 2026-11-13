"""宿主代理进程本体（goal-sprint r3；P2-b 架构半的最后一块）。

P2′①（#204）落了服务端咬合半（claim/receipt/status 三路由 + 状态机），
本模块落宿主半：**轮询循环 → spawn zcode → 回执** 的宿主侧进程，跑在
Windows 宿主（与服务端容器隔离；``bridge-poll.mjs`` 宿主纪律同构）。

生命周期红线（AGENTS.md 通道例外第 ⑤ 条）：**一次进程 = 至多一次
claim → 执行 → receipt**，run 终态即回收——代理进程与授权 run 一一对应，
不做常驻循环（连续消费由外部调度反复拉起，如 schtasks，同 bridge 形态）。

边界（与本仓既有闸逐条对齐，零放宽）：

- **H4 不变**：本进程只消费人经 ``start_run`` 受理的 ``queued`` run
  （execution_provider=host_poll），绝不发起/接管/重试 run；领取后执行
  失败一律如实回执 failed，重试由人。
- **凭据面**：零平台凭据注入（zcode 用宿主自身登录态）；本进程自身的
  配置（poll token 等）只经环境变量读取，不落 argv、不进日志。
- **spawn 真身**：``host_channel.run_host_channel``——preflight（N2 两
  事实）＋ argv 契约（zcode_contract 唯一源）＋超时熔断＋⑦出站闸全部
  复用，不另写一套。本模块在 claim 之前再跑一次同款 preflight（fail-fast：
  部署半态不领取，避免 run 白白挂 host_running）。
- **只读面料**：任务书三件（context.md/task.md/AGENTS.md）经服务端
  ``GET /agents/host/runs/<id>/context`` 原样取回逐字落盘——渲染一次、
  消费两侧，宿主侧不自行渲染任务书。
- **真相层零接触**：工作区锚定在配置的工作区根内（``FORBIDDEN_MOUNT_
  MARKERS`` 拒绝清单校验），绝不挂/写 ``D:\test\FDE\`` 真相层。

传输面可注入（``HostTransport``）：CI 无网络无 zcode 也能全行为覆盖；
``runner`` 同样可注入（单测用假 runner 断言 ctx/回执形状）。生产入口：
``python -m fde_api.agents.host_agent``（env 驱动，无参数；退出码见
``main``）。失败因宿主侧留痕（stderr + stdout JSON 行）；服务端回执面只
落终态与产物指纹（summary/失败文本不进服务端——红线：正文不复制）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from fde_api.agents.adapter import AgentRunContext, AgentRunResult, ManifestOutputScanner
from fde_api.agents.host_channel import (
    HostChannelError,
    HostChannelSettings,
    assert_host_workspace_allowed,
    run_host_channel,
)
from fde_api.agents.host_preflight import (
    default_cli_config_path,
    validate_default_model_selection,
    validate_provider_switch_pair,
)

# run_id 是宿主工作区路径段——服务端 uuid 形态外的值一律拒绝（防路径段注入；
# 服务端已校验，此处 belt-and-braces）。
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

# 工作区三件套（与服务端 _write_workspace 渲染面、host_context 读面同源）。
_WORKSPACE_FILES = ("context.md", "task.md", "AGENTS.md")
_OUTPUT_DIR = "output"

# 退出码（main 用）：0=干净收场（idle 或已回执）；2=配置缺失；3=preflight
# 未过（部署半态，未领取）；4=领取/面料/传输失败（run 可能挂 host_running
# → 服务端失联标记 + 人工）；5=执行后回执投递失败（同上）。
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_PREFLIGHT = 3
EXIT_CLAIM = 4
EXIT_RECEIPT = 5


class HostAgentError(RuntimeError):
    """宿主代理流程错误（领取/面料/传输段；携带机器可读 code）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class HostTransportError(HostAgentError):
    """传输面故障（网络/协议层；与业务码区分）。"""


@dataclass(frozen=True)
class HostAgentConfig:
    """宿主代理配置快照（全部来自环境变量；缺一即拒绝起跑）。"""

    api_base: str
    poll_token: str
    workspace_root: str
    zcode_bin: str
    cjs_path: str
    cli_config_path: str  # 空 = 缺省 ~/.zcode/cli/config.json
    egress_gate_enabled: bool
    egress_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HostAgentConfig:
        source = os.environ if env is None else env

        def _required(key: str) -> str:
            value = str(source.get(key, "")).strip()
            if not value:
                raise HostAgentError("config_missing", f"环境变量 {key} 未配置（宿主代理拒绝起跑）。")
            return value

        gate_enabled = str(source.get("FDE_AGENT_HOST_EGRESS_GATE_ENABLED", "")).strip() == "1"
        allowlist_raw = str(source.get("FDE_AGENT_HOST_EGRESS_ALLOWLIST", "")).strip()
        allowlist = tuple(item.strip() for item in allowlist_raw.split(",") if item.strip())
        if gate_enabled and not allowlist:
            # fail-closed（⑦ 同款）：闸开而白名单空 = 配置半态，不起跑。
            raise HostAgentError("config_missing", "出站闸已启用但 FDE_AGENT_HOST_EGRESS_ALLOWLIST 为空。")
        return cls(
            api_base=_required("FDE_AGENT_HOST_API_BASE").rstrip("/"),
            poll_token=_required("FDE_AGENT_HOST_POLL_TOKEN"),
            workspace_root=_required("FDE_AGENT_WORKSPACE_ROOT"),
            zcode_bin=_required("FDE_AGENT_HOST_ZCODE_BIN"),
            cjs_path=_required("FDE_AGENT_HOST_ZCODE_CJS"),
            cli_config_path=str(source.get("FDE_AGENT_HOST_ZCODE_CLI_CONFIG", "")).strip(),
            egress_gate_enabled=gate_enabled,
            egress_allowlist=allowlist,
        )


class HostTransport(Protocol):
    """服务端咬合面传输（生产 = HttpHostTransport；测试注入假件）。

    应答形状约定：HTTP 200 ⇒ 返回**拆信封后的内层 data**（服务端响应形
    如 ``{"data": …}``，routes._data 投影）；非 200 ⇒ 返回完整信封（内层
    ``error`` 可读失败码）。
    """

    def get_status(self) -> Mapping[str, Any]: ...

    def claim(self, run_id: str | None = None) -> tuple[int, Mapping[str, Any]]: ...

    def fetch_context(self, run_id: str) -> tuple[int, Mapping[str, Any]]: ...

    def receipt(self, run_id: str, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]: ...


class HttpHostTransport:
    """HTTP 传输（stdlib urllib；零新依赖）。非 2xx 一律返回 (code, body)。"""

    def __init__(self, *, api_base: str, poll_token: str, timeout_seconds: float = 30.0) -> None:
        self._api_base = api_base.rstrip("/")
        self._token = poll_token
        self._timeout = timeout_seconds

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> tuple[int, Mapping[str, Any]]:
        url = f"{self._api_base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"X-Host-Poll-Token": self._token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310 - URL 来自本机配置
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                body = response.read()
                code = response.status
        except urllib.error.HTTPError as error:
            body = error.read()
            code = error.code
        except (urllib.error.URLError, OSError) as error:
            raise HostTransportError("transport_failed", f"服务端传输失败：{error}") from error
        try:
            text = (body or b"").decode("utf-8")  # 非 2xx 无 body（HTTPError fp=None）如实按空对象
            parsed = json.loads(text) if text.strip() else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HostTransportError("transport_bad_payload", f"服务端响应不是 JSON：{error}") from error
        if not isinstance(parsed, dict):
            raise HostTransportError("transport_bad_payload", "服务端响应不是 JSON 对象。")
        return code, parsed

    def get_status(self) -> Mapping[str, Any]:
        _code, body = self._request("GET", "/api/v1/agents/host/status")
        data = body.get("data")
        return data if isinstance(data, Mapping) else body

    def claim(self, run_id: str | None = None) -> tuple[int, Mapping[str, Any]]:
        code, body = self._request("POST", "/api/v1/agents/host/claim", {"run_id": run_id} if run_id else {})
        if code == 200 and isinstance(body.get("data"), Mapping):
            return code, body["data"]
        return code, body

    def fetch_context(self, run_id: str) -> tuple[int, Mapping[str, Any]]:
        code, body = self._request("GET", f"/api/v1/agents/host/runs/{run_id}/context")
        if code == 200 and isinstance(body.get("data"), Mapping):
            return code, body["data"]
        return code, body

    def receipt(self, run_id: str, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
        return self._request("POST", f"/api/v1/agents/host/runs/{run_id}/receipt", dict(payload))


def preflight(config: HostAgentConfig) -> None:
    """起跑前部署面校验（N2 两事实；与 run_host_channel 同款校验器，fail-fast）。

    在 claim 之前执行——部署半态（provider 开关单边 / 默认模型未配置）不
    领取 run，避免 run 被领取后挂 host_running 等失联标记。spawn 前
    ``run_host_channel`` 内的同款校验是第二道防线（同一对校验器，幂等）。
    """
    validate_provider_switch_pair(os.environ)
    config_path = Path(config.cli_config_path) if config.cli_config_path else default_cli_config_path()
    validate_default_model_selection(config_path)


def materialize_workspace(config: HostAgentConfig, *, run_id: str, context: Mapping[str, Any]) -> Path:
    """宿主工作区落盘（run_id 为目录段；三件面料逐字写；根锚 + 拒绝清单校验）。"""
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise HostAgentError("claim_bad_payload", f"run_id 形状非法：{run_id!r}")
    workspace = Path(config.workspace_root) / run_id
    assert_host_workspace_allowed(str(workspace.resolve()))
    (workspace / _OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    files = context.get("files")
    if not isinstance(files, Mapping):
        raise HostAgentError("context_bad_payload", "context 响应缺 files 对象。")
    for name in _WORKSPACE_FILES:
        content = files.get(name)
        if isinstance(content, str):
            (workspace / name).write_text(content, encoding="utf-8")
    # 任务书缺席/空面料 = 服务端侧渲染面异常（读面缺文件返回空串）——不
    # spawn：空任务书的 run 只会产出不可校验的空转（fail-closed）。
    if not str(files.get("task.md") or "").strip():
        raise HostAgentError("context_bad_payload", "任务书面料缺 task.md 或为空（不 spawn）。")
    return workspace


def _sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None  # 扫描清单里有但文件缺失：不编指纹（服务端按缺指纹记 failure）
    return digest.hexdigest()


def build_receipt_payload(result: AgentRunResult, workspace: Path) -> dict[str, Any]:
    """执行结果 → 回执载荷（产物指纹宿主侧现算；正文零上传）。"""
    artifacts: list[dict[str, Any]] = []
    output_dir = workspace / _OUTPUT_DIR
    for artifact in result.artifacts:
        digest = _sha256_file(output_dir / artifact.path)
        if digest is None:
            continue  # 指纹缺失不占位——服务端按 sha256_missing 记 failure（人工处置）
        artifacts.append(
            {
                "path": artifact.path,
                "kind": artifact.kind,
                "source_refs": list(artifact.source_refs),
                "sha256": digest,
            }
        )
    payload: dict[str, Any] = {
        "status": result.status,
        # summary 是服务端必填对象；--json 汇总原样回传（解析归服务端，
        # 本进程只 spawn 一次不二次提取）。spawn 前失败路径无汇总 → 空对象。
        "summary": dict(result.summary_payload) if result.summary_payload else {},
        "token_cost": result.token_cost,
        "duration_ms": result.duration_ms,
        "degraded": result.degraded,
        "degraded_reason": result.degraded_reason,
        "artifacts": artifacts,
    }
    if isinstance(result.exit_code, int):
        payload["exit_code"] = result.exit_code
    if result.egress_audit:
        # ⑦ 审计证据随回执上行（goal-sprint r3）：summarize_audit 有界形状
        # （计数＋去重域名 ≤20），只记域名不记路径/内容——红线同构；宿主
        # 代理单发进程里这是审计留证的唯一出口（服务端择机落
        # agent_egress_audit 事件）。
        from fde_api.agents.host_egress_proxy import summarize_audit  # 闸可选依赖，懒导入

        payload["egress_audit"] = summarize_audit(result.egress_audit)
    return payload


def run_once(
    config: HostAgentConfig,
    *,
    transport: HostTransport | None = None,
    runner: Any | None = None,
) -> dict[str, Any]:
    """单次生命周期：status → claim → context → spawn → receipt。

    返回 ``{"outcome", "run_id", "status", "receipt"}``（outcome ∈ idle /
    receipted / failed_receipted）；抛 ``HostAgentError`` = 本进程职责外故
    障（调用方决定退出码）。``runner`` 缺省取模块级 ``run_host_channel``
    （调用时刻解析——测试 monkeypatch 模块属性即可全链替换）。
    """
    if transport is None:
        transport = HttpHostTransport(api_base=config.api_base, poll_token=config.poll_token)
    if runner is None:
        runner = run_host_channel

    preflight(config)

    # 「宿主在，标记就在」（P2′① 约束 3）：status 调用即触发服务端失联标记。
    transport.get_status()
    code, claim = transport.claim()
    if code == 404:
        return {"outcome": "idle", "run_id": None, "status": None, "receipt": None}
    if code != 200:
        raise HostAgentError(
            "claim_rejected", f"claim 被拒绝（HTTP {code}）：{claim.get('error', {}).get('code', 'unknown')}"
        )
    run_id = claim.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise HostAgentError("claim_bad_payload", "claim 载荷缺 run_id。")

    code, context = transport.fetch_context(run_id)
    if code != 200:
        raise HostAgentError(
            "context_rejected", f"context 读取失败（HTTP {code}）：run 挂 host_running 待失联标记/人工处置"
        )
    workspace = materialize_workspace(config, run_id=run_id, context=context)

    settings = HostChannelSettings(
        zcode_bin=config.zcode_bin,
        cjs_path=config.cjs_path,
        cli_config_path=config.cli_config_path,
    )
    ctx = AgentRunContext(
        run_id=run_id,
        # project_code 仅信息面（宿主侧不落库）；载荷只有 project_id，如实用之。
        project_code=str(claim.get("project_id") or ""),
        capability=str(claim.get("capability") or ""),
        workspace_host=str(workspace),
        allowed_tools=frozenset(str(tool) for tool in claim.get("allowed_tools") or []),
        credentials={},  # 宿主通道零凭据注入（红线：解密结果不进 argv/env/磁盘）
        timeout_ms=int(claim.get("max_duration_ms") or 300_000),
        max_cost_units=int(claim.get("max_cost_units") or 0),
    )
    egress_gate = None
    if config.egress_gate_enabled:
        from fde_api.agents.host_egress_proxy import HostEgressGate  # 函数内懒导入：闸可选依赖

        egress_gate = HostEgressGate(list(config.egress_allowlist))
    try:
        result: AgentRunResult = runner(ctx, settings, output_scanner=ManifestOutputScanner(workspace / _OUTPUT_DIR), egress_gate=egress_gate)
    except HostChannelError as error:
        # spawn 前失败（preflight 二道闸 / egress 启动 / 进程拉起）：如实回执
        # failed——run 不悬挂；失败因宿主侧留痕（本返回值 + stderr），服务端
        # 只落终态（summary 文本不进服务端）。
        failed_payload: dict[str, Any] = {
            "status": "failed",
            "summary": {},
            "degraded_reason": f"host_agent_spawn_failed:{error}",
            "artifacts": [],
        }
        code, receipt = transport.receipt(run_id, failed_payload)
        if code != 200:
            raise HostAgentError("receipt_rejected", f"失败回执投递被拒（HTTP {code}）") from error
        return {"outcome": "failed_receipted", "run_id": run_id, "status": "failed", "receipt": receipt}

    payload = build_receipt_payload(result, workspace)
    code, receipt = transport.receipt(run_id, payload)
    if code != 200:
        raise HostAgentError(
            "receipt_rejected", f"回执投递失败（HTTP {code}）：run 挂 host_running 待失联标记/人工处置"
        )
    return {
        "outcome": "receipted",
        "run_id": run_id,
        "status": result.status,
        "receipt": receipt,
        "workspace": str(workspace),
    }


def main(argv: list[str] | None = None) -> int:
    """进程入口（``python -m fde_api.agents.host_agent``）。stdout 一行 JSON 回执。"""
    del argv  # env 驱动，无参数面（外部调度只管反复拉起）
    try:
        config = HostAgentConfig.from_env()
    except HostAgentError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return EXIT_CONFIG
    try:
        outcome = run_once(config)
    except HostAgentError as error:
        print(json.dumps({"error": str(error), "code": error.code}), file=sys.stderr)
        return EXIT_RECEIPT if error.code == "receipt_rejected" else EXIT_CLAIM
    print(json.dumps(outcome, ensure_ascii=False))
    if outcome["outcome"] == "receipted" and outcome.get("status") not in (None, "completed"):
        # 已回执但终态非 completed（timeout/budget_exceeded/failed）：进程职责
        # 已尽（服务端拥有 run 终态），退出码仍为 0——非零会误报「代理故障」。
        return EXIT_OK
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - 进程入口
    raise SystemExit(main())

__all__ = [
    "EXIT_CLAIM",
    "EXIT_CONFIG",
    "EXIT_OK",
    "EXIT_PREFLIGHT",
    "EXIT_RECEIPT",
    "HostAgentConfig",
    "HostAgentError",
    "HostTransport",
    "HostTransportError",
    "HttpHostTransport",
    "build_receipt_payload",
    "materialize_workspace",
    "preflight",
    "run_once",
]
