"""V3.3 M5-WP2④：client 熔断态只读视图 + S-16 双层枚举 / S-12 降级审批锁（TDD）。

分工边界（2026-11-14 P1 批准的分域共存）：client/mock 三新方法的同形契约
测试由 ``test_m5_wp2_client_mock_parity.py`` 承载；本文件只覆盖本会话域——
- ``OntologyClient.breaker_state``：Gate 回执固化「当时熔断降级态」的数据源（D29）；
- ``fde_api.ontology.dependency_gate``：S-16 双层枚举解析与 S-12 防降级旁路锁。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import requests

from fde_api.integrations.ontology_client import OntologyClient, OntologyUnavailable

API_KEY = "wb-api-key"
SIGNING_KEY = "wb-signing-key"


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"{}") -> None:
        self.status_code = status
        self.content = body
        self.text = body.decode()

    def json(self) -> dict[str, Any]:
        return json.loads(self.content)


# ---- client 熔断态只读视图（Gate 回执固化「当时降级态」的数据源，D29）----


def test_client_breaker_state_view(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.request", fake_request)
    monkeypatch.setattr(
        "fde_api.integrations.ontology_client.time.sleep", lambda s: sleeps.append(s)
    )
    clock = {"t": 100.0}
    monkeypatch.setattr(
        "fde_api.integrations.ontology_client.time.monotonic", lambda: clock["t"]
    )
    client = OntologyClient("http://runtime.test", API_KEY, SIGNING_KEY)
    assert client.breaker_state == "closed"
    # health() 直连不走熔断器（探活语义）；用走 _request 的幂等 GET 驱动计数
    for _ in range(5):  # 连续 5 次失败 → 打开（§2-4 阈值）
        with pytest.raises(OntologyUnavailable):
            client.get_change_set(
                actor_id="u1", org_id="org-1", project_id="proj-1", change_set_id="cs-1"
            )
    assert client.breaker_state == "open"
    clock["t"] += 31.0  # 越过 30s 恢复窗口 → 半开
    assert client.breaker_state == "half_open"
    monkeypatch.setattr(
        "fde_api.integrations.ontology_client.requests.request",
        lambda *a, **k: _FakeResponse(200, b"{}"),
    )
    client.get_change_set(
        actor_id="u1", org_id="org-1", project_id="proj-1", change_set_id="cs-1"
    )  # 半开试探成功 → 闭合
    assert client.breaker_state == "closed"


# ---- S-16 双层枚举解析（全局闸 → 单门禁等级，契约 §0/§3）----


def test_s16_dependency_resolution_layers() -> None:
    from fde_api.ontology.dependency_gate import resolve_ontology_dependency

    # strong：本体不可用一律挂起；weak：原规则运行+标注未校验（S-16 §3）
    assert resolve_ontology_dependency("strong", "optional", "none") == "strong"
    assert resolve_ontology_dependency("weak", "required", "required") == "weak"
    # per_gate：才读单门禁 required|optional|none；行值缺省回退模板默认，
    # 模板也缺省取 optional（本体辅助档——存量门禁行 NULL 升级后不被突然钳制）
    assert resolve_ontology_dependency("per_gate", "required", None) == "required"
    assert resolve_ontology_dependency("per_gate", "optional", "none") == "none"
    assert resolve_ontology_dependency("per_gate", None, None) == "optional"  # 全缺省
    # 非法全局值 fail-closed 取 strong（不可用即挂起，宁严勿松）
    assert resolve_ontology_dependency("bogus", "optional", "none") == "strong"


def test_s16_gate_row_downgrade_requires_owner_approval() -> None:
    """S-12 防降级旁路锁：下调依赖等级须 Owner 异人审批，同人自批 403。"""
    from fde_api.ontology.dependency_gate import (
        can_activate_downgrade,
        is_downgrade,
    )

    # 等级序：required > optional > none（下调 = 放松）
    assert is_downgrade("required", "optional") is True
    assert is_downgrade("optional", "required") is False
    assert is_downgrade("none", "none") is False
    # 异人审批闸：审批人 ≠ 提案人，且审批人须 Owner；熔断/降级窗口内禁生效
    assert can_activate_downgrade(proposer="u1", approver="u2", degraded=True) is False
    assert can_activate_downgrade(proposer="u1", approver="u1", degraded=False) is False
    assert can_activate_downgrade(proposer="u1", approver="u2", degraded=False) is True
