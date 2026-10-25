"""集成桥（P2，设计 §4）：真相层 → PG 的单向投影。

架构修订（v0.3.4）：openfde CLI 是宿主侧 Windows Node 工具（better-sqlite3 按
Win 编译 + pnpm/tsx），Linux 容器 subprocess 不到它——采集在宿主侧
（scripts/bridge-poll.mjs，Windows 计划任务 15 min），服务端三职责：
校验入站快照（runner）、规范化/解析（adapters）、投影 + orphan 判定（sync）。

A1：真相在文件，本模块只写投影表（bridge_engagements），绝不写真相层；
A3：命令白名单制（白名单定义在宿主采集器内，服务端只收结构化快照）；
A4：投影行按轨道带 source_uri + content_hash。
"""

from fde_api.bridge.adapters import (
    normalize_fdeops_dir,
    normalize_openfde_status,
)
from fde_api.bridge.routes import bridge_blueprint

__all__ = [
    "bridge_blueprint",
    "normalize_openfde_status",
    "normalize_fdeops_dir",
]
