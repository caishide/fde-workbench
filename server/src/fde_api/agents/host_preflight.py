"""宿主 zcode spawn 前置校验（N2 真机联调实测事实接线，2026-11-13）。

两个事实来自 backlog T-Z1 段 2026-11-13 补充（N2 真机联调签核的实施级
前置，`docs/试点前联调-iptables与zcodeCLI-检查单.md` 回填表同源）：

1. **provider 覆盖开关成对校验**：`ZCODE_BUILTIN_PROVIDER_CONFIG_FILE` +
   `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` 必须成对设置（`FDE_CONFIG_DIR`
   无效——实测设了仍走内置 provider）。只设其一 = 部署半态，CLI provider
   解析行为未定义 ⇒ spawn 前显式失败（fail-closed，不带病起跑）。
2. **默认模型选择键在场校验**：`-p` 无 `--model` 开关（会被当未知选项
   报错）；默认模型持久化在 `~/.zcode/cli/config.json` 的
   `defaultModelSelection` 键（`{providerKey, modelId}`）。键缺失时 CLI
   EXIT=1「Select a model before sending a message」⇒ 与其让进程死在
   半路零留痕，不如 spawn 前显式失败——**明确失败并留痕，不得静默重试**
   （N2 登记原话）。

失败语义：抛 ``HostChannelError`` → 调用链既有映射（``_mark_l2`` + 503
agent_unavailable，零 spawn 零计费）——失败原因留痕在 run 上，重试由人
（H4，不自动重试）。

边界：本模块是宿主代理与 dev 直连通道共用的**唯一前置校验真身**
（§11.3 约束 ⑤ 同族纪律：形状来源不得各写一套）；r3 宿主代理进程接线
时复用同一对校验器，不得另写。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from fde_api.agents.host_channel import HostChannelError

# N2 事实①：provider 覆盖开关对（成对设置才有效——单边 = 部署半态）。
PROVIDER_BUILTIN_SWITCH = "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE"
PROVIDER_PERSONAL_SWITCH = "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE"
# N2 事实②：默认模型选择持久化键（zcode 0.17.1 实测）。
MODEL_SELECTION_KEY = "defaultModelSelection"


def default_cli_config_path() -> Path:
    """zcode CLI 配置缺省路径（N2 实测：``~/.zcode/cli/config.json``）。"""
    return Path.home() / ".zcode" / "cli" / "config.json"


def validate_provider_switch_pair(env: Mapping[str, str]) -> None:
    """N2 事实①：provider 覆盖开关成对校验（只设其一 ⇒ 显式失败）。"""
    from fde_api.agents.host_channel import HostChannelError  # 函数内懒导入：同包顶层环冻结

    builtin_set = bool(str(env.get(PROVIDER_BUILTIN_SWITCH, "")).strip())
    personal_set = bool(str(env.get(PROVIDER_PERSONAL_SWITCH, "")).strip())
    if builtin_set != personal_set:
        raise HostChannelError(
            "provider 覆盖开关必须成对设置："
            f"{PROVIDER_BUILTIN_SWITCH} 与 {PROVIDER_PERSONAL_SWITCH} 只设置了其一"
            "（N2 实测：单边设置属部署半态，CLI provider 解析未定义；"
            "FDE_CONFIG_DIR 不承担此职责）——已拒绝 spawn，请修正部署 env 后由人重试。"
        )


def validate_default_model_selection(config_path: Path) -> None:
    """N2 事实②：``defaultModelSelection`` 键在场校验。

    缺失/残缺/不可读一律显式拒绝（CLI 缺键行为 = EXIT=1「Select a model
    before sending a message」；spawn 前拦截把该失败从「进程半路死」提前
    为「明确失败留痕」）。
    """

    def _reject(reason: str) -> HostChannelError:
        from fde_api.agents.host_channel import HostChannelError

        return HostChannelError(
            "zcode 默认模型未配置："
            f"{config_path} 缺少可用的 {MODEL_SELECTION_KEY} 键（{reason}）——"
            "CLI 将以 EXIT=1「Select a model before sending a message」失败；"
            "已拒绝 spawn（明确失败不静默重试），请先在 zcode 内完成模型选择。"
        )

    if not config_path.is_file():
        raise _reject("配置文件不存在")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _reject(f"读取/解析失败：{error}") from error
    if not isinstance(payload, dict):
        raise _reject("配置顶层不是 JSON 对象")
    selection = payload.get(MODEL_SELECTION_KEY)
    if not isinstance(selection, dict):
        raise _reject("键缺失或不是对象")
    if not str(selection.get("providerKey", "")).strip() or not str(selection.get("modelId", "")).strip():
        raise _reject("providerKey/modelId 缺失或为空")
