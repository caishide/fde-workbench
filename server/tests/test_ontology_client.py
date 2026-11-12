"""OntologyClient 单元测试（纯 mock，不依赖 MySQL/runtime）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import urlparse

import pytest

from fde_api.integrations.ontology_client import (
    OntologyClient,
    OntologyClientError,
    OntologyUnavailable,
    build_context_header,
)

API_KEY = "wb-api-key"
SIGNING_KEY = "wb-signing-key"


def _verify_header(header: str, signing_key: str) -> dict[str, object]:
    head, sig = header.split(".", 1)
    expected = hmac.new(
        signing_key.encode(), head.encode(), hashlib.sha256
    ).digest()
    padded = sig + "=" * (-len(sig) % 4)
    assert hmac.compare_digest(base64.urlsafe_b64decode(padded), expected)
    raw = base64.urlsafe_b64decode(head + "=" * (-len(head) % 4))
    return json.loads(raw)  # type: ignore[no-any-return]


def test_context_header_roundtrip() -> None:
    header = build_context_header("u1", "org1", "p1", SIGNING_KEY, ts=1700000000, nonce="abcd1234")
    payload = _verify_header(header, SIGNING_KEY)
    assert payload["actor_id"] == "u1"
    assert payload["org_id"] == "org1"
    assert payload["project_id"] == "p1"
    assert payload["ts"] == 1700000000
    assert payload["nonce"] == "abcd1234"


def test_context_header_wrong_key_fails() -> None:
    header = build_context_header("u1", "org1", "p1", "other-key")
    with pytest.raises(AssertionError):
        _verify_header(header, SIGNING_KEY)


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"{}") -> None:
        self.status_code = status
        self.content = body
        self.text = body.decode()

    def json(self) -> dict[str, object]:
        return json.loads(self.content)


def _client() -> OntologyClient:
    return OntologyClient("http://runtime.test", API_KEY, SIGNING_KEY)


def test_submit_candidates_payload_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(method: str, url: str, **kwargs: object) -> _FakeResponse:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return _FakeResponse(201, json.dumps({"id": "cs-1"}).encode())

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.request", fake_request)
    client = _client()
    items = [{"op": "create", "entity_type": "object_types", "entity_key": "stage", "payload": {}}]
    first = client.submit_candidates(
        actor_id="u1", org_id="org1", project_id="p1",
        ontology_id="ont-1", title="候选", items=items, captured_from="discovery:doc-9",
    )
    assert first["id"] == "cs-1"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-API-Key"] == API_KEY
    payload = _verify_header(headers["X-FDE-Context"], SIGNING_KEY)
    assert payload["org_id"] == "org1"
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["captured_from"] == "discovery:doc-9"
    assert body["proposed_json"] == items
    # 内容寻址幂等：同 items 再提交 → 同幂等键
    idem1 = headers["X-Idempotency-Key"]
    client.submit_candidates(
        actor_id="u1", org_id="org1", project_id="p1",
        ontology_id="ont-1", title="候选", items=items, captured_from="discovery:doc-9",
    )
    assert isinstance(captured["headers"], dict)
    assert captured["headers"]["X-Idempotency-Key"] == idem1


def test_health_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests as _requests

    def fake_get(*args: object, **kwargs: object) -> object:
        raise _requests.ConnectionError("refused")

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.get", fake_get)
    assert _client().health() is False


def test_request_unavailable_maps_to_ontology_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests as _requests

    def fake_request(*args: object, **kwargs: object) -> object:
        raise _requests.ConnectionError("refused")

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.request", fake_request)
    with pytest.raises(OntologyUnavailable):
        _client().get_change_set(actor_id="u", org_id="o", project_id="p", change_set_id="cs")


def test_5xx_maps_to_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(502)

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.request", fake_request)
    with pytest.raises(OntologyClientError):
        _client().get_change_set(actor_id="u", org_id="o", project_id="p", change_set_id="cs")


def test_4xx_passthrough_with_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(*args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(409, json.dumps({"code": "base_conflict"}).encode())

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.request", fake_request)
    body = _client().get_change_set(actor_id="u", org_id="o", project_id="p", change_set_id="cs")
    assert body["_status"] == 409
    assert body["code"] == "base_conflict"


def test_health_true_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: object) -> _FakeResponse:
        assert urlparse(url).path == "/healthz"
        return _FakeResponse(200)

    monkeypatch.setattr("fde_api.integrations.ontology_client.requests.get", fake_get)
    assert _client().health() is True
