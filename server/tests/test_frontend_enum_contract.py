"""C7：前端业务枚举防漂移一致性断言（goal-r2 WP29/J1 起改为三方一致）。

枚举真源已下沉服务端（`GET /api/v1/workbench/options`，实现见
server/src/fde_api/workbench/options.py）；前端保留一份本地兜底副本
（desktop/src/renderer/src/workbench/options.ts），服务端不可达时用它。

因此防漂移的检查点从「前端硬编码」变成**三方一致**：
  ① 业务服务常量（quote_service / contract_service / 门禁五态）
  ② 服务端选项表（workbench/options.py）
  ③ 前端本地兜底（workbench/options.ts 的 FALLBACK_OPTIONS）

任何一方改了枚举而另外两方没跟上，本测试先红——不会出现「服务端发了新值
前端哑掉」的静默漂移。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / "desktop" / "src" / "renderer" / "src"
OPTIONS_SERVER = REPO / "server" / "src" / "fde_api" / "workbench" / "options.py"
OPTIONS_CLIENT = DESKTOP / "workbench" / "options.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontend_const(source: str, const_name: str) -> str:
    """截取 `const NAME ... }` 的常量体文本，供成员断言。"""
    match = re.search(rf"const {const_name}[^=]*=\s*(?:Record<[^>]+>\s*)?\{{", source)
    assert match, f"frontend constant {const_name} not found"
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"frontend constant {const_name} not terminated")


def _server_option_values(source: str, const_name: str) -> list[str]:
    """服务端 options.py 里某个列表常量的 value 集合（按出现顺序）。"""
    match = re.search(rf"{const_name}[^=]*=\s*\[(.*?)\n\]", source, re.S)
    assert match, f"server option list {const_name} not found"
    return re.findall(r'"value":\s*"([^"]+)"', match.group(1))


def _client_option_values(source: str, group: str) -> list[str]:
    """前端兜底里某个选项组的 value 集合（按出现顺序）。"""
    match = re.search(rf"{group}:\s*\[(.*?)\n  \]", source, re.S)
    assert match, f"client fallback group {group} not found"
    return re.findall(r'value:\s*"([^"]+)"', match.group(1))


def test_tier_members_match_quote_service():
    server = _read(REPO / "server" / "src" / "fde_api" / "projects" / "quote_service.py")
    server_tiers = set(re.findall(r'^\s{4}"(\w+)":\s*\{', server, re.M)) & {"light", "standard", "flagship"}
    assert server_tiers == {"light", "standard", "flagship"}

    options = _read(OPTIONS_SERVER)
    client = _read(OPTIONS_CLIENT)
    assert set(_server_option_values(options, "PRICE_TIERS")) == server_tiers
    assert set(_client_option_values(client, "price_tiers")) == server_tiers


def test_gate_statuses_match_gate_board_labels():
    # 门禁五态是口径边界（不得扩张）：服务端选项表与前端兜底都必须是这五态
    expected = {"pending", "evidence", "passed", "conditional_pass", "failed"}

    options = _read(OPTIONS_SERVER)
    client = _read(OPTIONS_CLIENT)
    assert set(_server_option_values(options, "GATE_STATUSES")) == expected
    assert set(_client_option_values(client, "gate_statuses")) == expected


def test_bridge_flags_match_sync_flags():
    server = _read(REPO / "server" / "src" / "fde_api" / "bridge" / "sync.py")
    server_flags = set(re.findall(r'flags\.append\("(\w+)"\)', server))
    assert {"vanished", "unlinked", "orphan_openfde", "orphan_fdeops", "missing_openfde_pointer", "stale"} <= server_flags

    frontend = _frontend_const(_read(DESKTOP / "bridge" / "BridgePage.tsx"), "FLAG_LABELS")
    for flag in server_flags:
        assert f"{flag}:" in frontend, f"bridge flag {flag} missing in frontend FLAG_LABELS"


def test_sow_types_match_contract_service():
    server = _read(REPO / "server" / "src" / "fde_api" / "projects" / "contract_service.py")
    match = re.search(r"SOW_TYPES\s*=\s*\(([^)]*)\)", server)
    server_types = set(re.findall(r'"(\w)"', match.group(1)))
    assert server_types == {"a", "b", "c", "d"}

    options = _read(OPTIONS_SERVER)
    client = _read(OPTIONS_CLIENT)
    assert set(_server_option_values(options, "SOW_OPTIONS")) == server_types
    assert set(_client_option_values(client, "sow_options")) == server_types


def test_c_handling_options_match_quote_service():
    server = _read(REPO / "server" / "src" / "fde_api" / "projects" / "quote_service.py")
    match = re.search(r"C_HANDLING_OPTIONS\s*=\s*\(([^)]*)\)", server)
    server_options = set(re.findall(r'"(\w+)"', match.group(1)))
    assert server_options == {"scope_cut", "split_phases", "external_collab", "ticket_deal"}

    options = _read(OPTIONS_SERVER)
    client = _read(OPTIONS_CLIENT)
    assert set(_server_option_values(options, "C_HANDLING_OPTIONS")) == server_options
    assert set(_client_option_values(client, "c_handling_options")) == server_options


def test_business_categories_keep_legacy_values_on_both_sides():
    """业务阶段存库值仍是历史中文标签——服务端选项表与前端兜底必须一致。"""
    expected = ["商务合约", "预调研", "调研", "PoV验证", "生产部署", "培训预交接"]

    options = _read(OPTIONS_SERVER)
    client = _read(OPTIONS_CLIENT)
    server_match = re.search(r"BUSINESS_CATEGORIES[^=]*=\s*\[(.*?)\n\]", options, re.S)
    assert server_match, "server option list BUSINESS_CATEGORIES not found"
    assert re.findall(r'"value":\s*"([^"]+)"', server_match.group(1)) == expected

    client_match = re.search(r"business_categories:\s*\[(.*?)\n  \]", client, re.S)
    assert client_match, "client fallback group business_categories not found"
    assert re.findall(r'value:\s*"([^"]+)"', client_match.group(1)) == expected
