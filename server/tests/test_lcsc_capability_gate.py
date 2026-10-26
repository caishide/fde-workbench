"""F1：立创工具能力门槛——不再对任何 AI 授权账号默认开放。

lcsc_search / lcsc_runs_read 属上游 fork 既有能力（非 FDE 交付线），此前
能力位为 None（无门槛）。收敛到 system_operator 后：能力集、MCP token、
call_tool、工具清单四个入口全部收敛。
"""
from fde_api.control.access import capabilities_for_level


def test_lcsc_capability_only_for_system_operator():
    assert "lcsc.browse" not in capabilities_for_level("assistant_read")
    assert "lcsc.browse" not in capabilities_for_level("project_operator")
    assert "lcsc.browse" not in capabilities_for_level("project_manager")
    assert "lcsc.browse" in capabilities_for_level("system_operator")


def test_lcsc_tools_carry_the_capability_bit():
    from fde_api.control.mcp_gateway import TOOLS

    assert TOOLS["lcsc_search"][1] == "lcsc.browse"
    assert TOOLS["lcsc_runs_read"][1] == "lcsc.browse"


def test_tools_listing_hides_lcsc_from_non_operators():
    """工具清单按能力过滤：非系统运维员看不到立创工具（前端卡片随之隐藏）。"""
    from fde_api.control.mcp_gateway import TOOLS

    for level in ("assistant_read", "project_operator", "project_manager"):
        allowed = set(capabilities_for_level(level))
        visible = [key for key, definition in TOOLS.items()
                   if definition[1] is None or definition[1] in allowed]
        assert "lcsc_search" not in visible
        assert "lcsc_runs_read" not in visible

    allowed = set(capabilities_for_level("system_operator"))
    visible = [key for key, definition in TOOLS.items()
               if definition[1] is None or definition[1] in allowed]
    assert "lcsc_search" in visible
