"""S-13 快照 ETag 完整性校验机械钉（2026-11-26 补接线轮）。

「Agent/Workflow 一律读快照并校验 ETag」此前声明强于实现——``_request`` 丢弃
响应头、``_verified_snapshot`` 无完整性校验（m1/VALIDATION §发布与快照 登记缺口）。
钉组六面：

1. client 世界三向 fail-closed：缺头（``etag_missing``）／错值（``etag_mismatch``）；
2. helper 直钉：缺锚与非对象文档（``snapshot_not_object``＝缺字段）；
3. mock 世界同步校验：篡改 etag（错值）与缺字段两向 + 种子自洽与包装体形状稳定；
4. 两世界 canonical 规则漂移钉（client ↔ mock 逐字节一致）；
5. 管理面映射：``_verified_snapshot`` → 502 ``snapshot_integrity``，文案零内部
   细节（S-07/Vex M6 条件(a)），拓扑细节只在异常链；
6. 「声明强于实现」AST 防回退钉：client 与 mock 的 ``get_version_snapshot``
   必须真调 ``verify_snapshot_integrity``（fragment 级）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fde_api.integrations import ontology_client, ontology_mock, service
from fde_api.integrations.ontology_client import (
    OntologyClient,
    OntologySnapshotIntegrityError,
    canonical_json_sha256,
    verify_snapshot_integrity,
)
from fde_api.integrations.ontology_mock import (
    MockOntologyAdapter,
    SEED_ONTOLOGY_ID,
    SEED_VERSION_ID,
)
from fde_api.integrations.service import BindingError

API_KEY = "wb-api-key"
SIGNING_KEY = "wb-signing-key"
CTX = {"actor_id": "u1", "org_id": "org-1", "project_id": "proj-1"}
DOCUMENT: dict[str, Any] = {"version": "1.0.0", "object_types": [{"key": "product", "title": "产品"}]}
ETAG = canonical_json_sha256(DOCUMENT)


class _FakeResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.content = body
        self.text = body.decode()
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return json.loads(self.content)  # type: ignore[no-any-return]


def _client() -> OntologyClient:
    return OntologyClient("http://runtime.test", API_KEY, SIGNING_KEY)


# ------------------------------------------------------- client 世界（HTTP 锚＝ETag 头）


def test_client_snapshot_etag_match_passes_and_strips_transport_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 + ETag 头与文档重算一致 → 通过；传输锚 ``_etag`` 不外泄（仅契约键 + _status）。"""

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(200, json.dumps(DOCUMENT).encode(), {"ETag": ETAG})

    monkeypatch.setattr("requests.request", fake_request)
    body = _client().get_version_snapshot(
        **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
    )
    assert body["_status"] == 200
    assert "_etag" not in body  # 传输锚已剥离——丢弃响应头的旧实现在此必红
    assert body["version"] == "1.0.0"


def test_client_snapshot_missing_etag_header_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺头（200 但无 ETag 头）→ etag_missing fail-closed，绝不返回未校验快照。"""

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(200, json.dumps(DOCUMENT).encode(), {})

    monkeypatch.setattr("requests.request", fake_request)
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        _client().get_version_snapshot(
            **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
        )
    assert excinfo.value.reason == "etag_missing"


def test_client_snapshot_wrong_etag_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """错值（ETag 头 ≠ 文档规范化重算）→ etag_mismatch fail-closed。"""

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(200, json.dumps(DOCUMENT).encode(), {"ETag": "0" * 64})

    monkeypatch.setattr("requests.request", fake_request)
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        _client().get_version_snapshot(
            **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
        )
    assert excinfo.value.reason == "etag_mismatch"


def test_client_snapshot_non_200_skips_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 200（404 等）不走校验——``_status`` 语义交调用方既有处置（409 version_not_published）。"""

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(404, json.dumps({"code": "not_found", "message": "version not found"}).encode())

    monkeypatch.setattr("requests.request", fake_request)
    body = _client().get_version_snapshot(
        **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id="ver-gone"
    )
    assert body["_status"] == 404


def test_request_without_want_etag_keeps_other_callers_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺省 ``want_etag=False``：其余调用方零变化——响应头在场也不回填 ``_etag``。"""

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(200, json.dumps({"ok": True}).encode(), {"ETag": ETAG})

    monkeypatch.setattr("requests.request", fake_request)
    body = _client().get_change_set(**CTX, change_set_id="cs-1")
    assert "_etag" not in body
    assert body["_status"] == 200


# ------------------------------------------------------- helper 直钉（三向闭集）


def test_verify_rejects_missing_anchor() -> None:
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        verify_snapshot_integrity(None, DOCUMENT)
    assert excinfo.value.reason == "etag_missing"


def test_verify_rejects_non_object_document() -> None:
    """缺字段向：快照文档非对象（列表/标量）→ snapshot_not_object，即便锚与重算一致。"""
    payload: list[int] = [1, 2]
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        verify_snapshot_integrity(canonical_json_sha256(payload), payload)
    assert excinfo.value.reason == "snapshot_not_object"


# ------------------------------------------------------- mock 世界（锚＝包装体 etag 字段）


def test_mock_snapshot_seed_self_consistent_and_shape_stable() -> None:
    """种子自洽（锚＝重算）且包装体形状稳定——「ontology_mock 同步出 ETag」的正面钉。"""
    body = MockOntologyAdapter().get_version_snapshot(
        **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
    )
    assert body["_status"] == 200
    assert body["etag"] == canonical_json_sha256(body["snapshot"])
    assert set(body) == {"id", "ontology_id", "version", "etag", "snapshot", "_status"}


def test_mock_snapshot_tampered_etag_fails_closed() -> None:
    """mock 世界错值：记录内 etag 被篡改 → 与 client 世界同语义 fail-closed。"""
    adapter = MockOntologyAdapter()
    adapter._versions[(SEED_ONTOLOGY_ID, SEED_VERSION_ID)]["etag"] = "f" * 64
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        adapter.get_version_snapshot(
            **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
        )
    assert excinfo.value.reason == "etag_mismatch"


def test_mock_snapshot_missing_etag_field_fails_closed() -> None:
    """mock 世界缺字段：记录缺 etag 字段 → etag_missing（模拟运行时漏发 ETag 头）。"""
    adapter = MockOntologyAdapter()
    del adapter._versions[(SEED_ONTOLOGY_ID, SEED_VERSION_ID)]["etag"]
    with pytest.raises(OntologySnapshotIntegrityError) as excinfo:
        adapter.get_version_snapshot(
            **CTX, ontology_id=SEED_ONTOLOGY_ID, version_id=SEED_VERSION_ID
        )
    assert excinfo.value.reason == "etag_missing"


# ------------------------------------------------------- 两世界规则漂移钉


def test_canonical_rules_agree_between_client_and_mock() -> None:
    """client ↔ mock canonical 规则逐字节一致（runtime 约定「Workbench 侧用同一规则」）。"""
    tricky: dict[str, Any] = {
        "b": 2,
        "a": {"y": "中文", "x": [1, 2, {"k": None, "j": True}]},
        "c": "",
    }
    assert ontology_client.canonical_json_sha256(tricky) == ontology_mock.canonical_json_sha256(tricky)


# ------------------------------------------------------- 管理面映射（_verified_snapshot）


class _IntegrityStubClient:
    def get_version_snapshot(self, **kwargs: Any) -> dict[str, Any]:
        raise OntologySnapshotIntegrityError("etag_mismatch")


class _ConsistentStubClient:
    def get_version_snapshot(self, **kwargs: Any) -> dict[str, Any]:
        # client 校验通过后的返回形状：契约键 + _status（_etag 已剥离）
        return {**DOCUMENT, "_status": 200}


def test_service_maps_integrity_failure_to_502_snapshot_integrity() -> None:
    with pytest.raises(BindingError) as excinfo:
        service._verified_snapshot(
            cast("Any", _IntegrityStubClient()),
            actor=cast("Any", SimpleNamespace(id="u1")),
            org_id="org-1",
            ontology_id=SEED_ONTOLOGY_ID,
            version_id=SEED_VERSION_ID,
            project_id="proj-1",
        )
    assert excinfo.value.status == 502
    assert excinfo.value.code == "snapshot_integrity"
    message = excinfo.value.message
    # S-07/Vex M6 条件(a)：原因码/锚值/拓扑不进管理面文案
    assert "http" not in message and "etag_mismatch" not in message and "runtime.test" not in message
    assert excinfo.value.__cause__ is not None  # 拓扑细节只在异常链（服务端日志可见）


def test_service_verified_snapshot_accepts_client_verified_body() -> None:
    out = service._verified_snapshot(
        cast("Any", _ConsistentStubClient()),
        actor=cast("Any", SimpleNamespace(id="u1")),
        org_id="org-1",
        ontology_id=SEED_ONTOLOGY_ID,
        version_id=SEED_VERSION_ID,
        project_id="proj-1",
    )
    assert out["version"] == "1.0.0"


# ------------------------------------------------------- 「声明强于实现」防回退钉


def test_docstring_claim_is_implemented_in_both_worlds() -> None:
    """AST 钉：client 与 mock 的 ``get_version_snapshot`` 必须真调共享校验器。"""
    for module in (ontology_client, ontology_mock):
        module_file = getattr(module, "__file__", None)
        assert module_file is not None, module.__name__
        tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_version_snapshot":
                calls = [
                    item.func.id
                    for item in ast.walk(node)
                    if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
                ]
                assert "verify_snapshot_integrity" in calls, module.__name__
                found = True
        assert found, module.__name__
