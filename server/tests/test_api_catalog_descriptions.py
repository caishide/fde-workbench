"""CR-060：api_catalog plugins 家族 desc 与实现一致（链路无密码确认环节）。"""

from fde_api.control.api_catalog import ENTRIES


def test_plugin_entries_do_not_claim_password_confirmation() -> None:
    rows = {row[0]: row for row in ENTRIES}
    request_desc = rows["plugins.request"][3]
    decide_desc = rows["plugins.decide"][3]
    assert "密码确认" not in request_desc
    assert "密码确认" not in decide_desc
    assert "运维员" in decide_desc
