"""C7：前端业务枚举防漂移一致性断言。

前端渲染层仍硬编码档位/门禁五态/桥 flags/SOW 类型/C 分支选项的**显示标签**
（服务端下发是后续 UI 重构项，本轮不搬）。这里钉住「枚举成员集合」一致：
服务端新增/改名枚举而前端没跟上时，本测试先红——不会出现「服务端发了新值
前端哑掉」的静默漂移。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DESKTOP = REPO / "desktop" / "src" / "renderer" / "src"


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


def test_tier_members_match_quote_service():
    server = _read(REPO / "server" / "src" / "fde_api" / "projects" / "quote_service.py")
    server_tiers = set(re.findall(r'^\s{4}"(\w+)":\s*\{', server, re.M)) & {"light", "standard", "flagship"}
    assert server_tiers == {"light", "standard", "flagship"}

    frontend = _read(DESKTOP / "projects" / "CommercialBoard.tsx")
    tiers_match = re.search(r"const TIERS[^=]*=\s*\[", frontend)
    assert tiers_match, "frontend TIERS not found"
    for tier in server_tiers:
        assert f'value: "{tier}"' in frontend, f"tier {tier} missing in frontend TIERS"


def test_gate_statuses_match_gate_board_labels():
    frontend = _frontend_const(_read(DESKTOP / "projects" / "GateBoard.tsx"), "STATUS_LABEL")
    for status in ("pending", "evidence", "passed", "conditional_pass", "failed"):
        assert f"{status}:" in frontend, f"gate status {status} missing in frontend STATUS_LABEL"


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

    frontend = _read(DESKTOP / "projects" / "CommercialBoard.tsx")
    for sow in server_types:
        assert f'value: "{sow}"' in frontend, f"sow type {sow} missing in frontend SOW options"


def test_c_handling_options_match_quote_service():
    server = _read(REPO / "server" / "src" / "fde_api" / "projects" / "quote_service.py")
    match = re.search(r"C_HANDLING_OPTIONS\s*=\s*\(([^)]*)\)", server)
    server_options = set(re.findall(r'"(\w+)"', match.group(1)))
    assert server_options == {"scope_cut", "split_phases", "external_collab", "ticket_deal"}

    frontend = _read(DESKTOP / "projects" / "CommercialBoard.tsx")
    for option in server_options:
        assert f'"{option}"' in frontend, f"c_handling {option} missing in frontend options"
