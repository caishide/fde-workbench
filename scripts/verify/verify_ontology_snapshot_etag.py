#!/usr/bin/env python3
"""S-13 快照 ETag 校验 · 双仓回环验证（2026-11-26 补接线轮）。

逐腿实测并贴输出（只说通了不算）——验证 Workbench ``OntologyClient.get_version_snapshot``
对响应 ETag 的 fail-closed 校验在**真 HTTP 栈**上成立：

- **stub 腿（内置，随时可跑）**：本地 ``http.server`` 三向——①ETag 与文档重算一致 →
  通过；②缺 ETag 头 → ``etag_missing``；③错值 → ``etag_mismatch``。
- **runtime 腿（``--runtime-base-url``，需先另行启动 ontology-service）**：双仓真回环——
  先 ``GET /versions`` 取已发布版本（raw 签名请求），核「响应 ETag 头 ≡ 版本表
  snapshot_sha256」，再经 ``OntologyClient`` 读快照（新校验路径）必须通过。

运行时启动配方（仓外，见文档中心 90_诊断留痕/2026-11-26-ontology-etag/）::

    ontology-service/.venv/Scripts/python.exe -m uvicorn ontology_service.app:app \\
      --host 127.0.0.1 --port 8942   # env: ONTOLOGY_ENV=dev + ONTOLOGY_DATABASE_URL(sqlite)
                                     #      + ONTOLOGY_API_KEY + ONTOLOGY_SIGNING_KEY

runtime 腿凭据经环境变量传入（不进 argv）：``FDE_ETAG_LOOPBACK_API_KEY`` /
``FDE_ETAG_LOOPBACK_SIGNING_KEY``。

用法::

    python scripts/verify/verify_ontology_snapshot_etag.py
    python scripts/verify/verify_ontology_snapshot_etag.py \\
      --runtime-base-url http://127.0.0.1:8942 --ontology-id <oid> [--org-id org-fde-demo]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_WORKBENCH_SRC = Path(__file__).resolve().parents[2] / "server" / "src"
sys.path.insert(0, str(_WORKBENCH_SRC))

import requests  # noqa: E402

from fde_api.integrations.ontology_client import (  # noqa: E402
    OntologyClient,
    OntologySnapshotIntegrityError,
    build_context_header,
    canonical_json_sha256,
)

STUB_ONTOLOGY_ID = "ont-etag-probe"
STUB_DOCUMENT: dict[str, Any] = {"version": "9.9.9", "probe": "etag-loopback", "items": [1, 2]}
STUB_ETAG = canonical_json_sha256(STUB_DOCUMENT)
# version_id → (etag 或 None=缺头, document)
STUB_VERSIONS: dict[str, tuple[str | None, dict[str, Any]]] = {
    "ver-ok": (STUB_ETAG, STUB_DOCUMENT),
    "ver-no-etag": (None, STUB_DOCUMENT),
    "ver-bad-etag": ("0" * 64, STUB_DOCUMENT),
}


class _StubHandler(BaseHTTPRequestHandler):
    """三向快照桩：只实现快照端点，其余 404；忽略鉴权头（校验的是客户端侧）。"""

    def do_GET(self) -> None:  # noqa: N802 —— http.server 命名约定
        prefix = f"/api/v1/ontologies/{STUB_ONTOLOGY_ID}/versions/"
        if not self.path.startswith(prefix) or not self.path.endswith("/snapshot"):
            self.send_response(404)
            self.end_headers()
            return
        version_id = self.path[len(prefix) : -len("/snapshot")]
        etag, document = STUB_VERSIONS.get(version_id, (None, {}))
        if version_id not in STUB_VERSIONS:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(document).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if etag is not None:
            self.send_header("ETag", etag)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002,A003
        pass  # 静默访问日志——回环输出只留判定


def run_stub_legs() -> bool:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    client = OntologyClient(base, "stub-key", "stub-signing")
    ok = True
    try:
        # ① 正例：ETag 与文档重算一致 → 通过
        body = client.get_version_snapshot(
            actor_id="probe", org_id="org-probe", project_id="proj-probe",
            ontology_id=STUB_ONTOLOGY_ID, version_id="ver-ok",
        )
        leg1 = body.get("_status") == 200 and "_etag" not in body and body.get("probe") == "etag-loopback"
        print(f"[{'PASS' if leg1 else 'FAIL'}] stub① 正例（ETag=重算）: _status={body.get('_status')} _etag 已剥离={('_etag' not in body)}")
        ok &= leg1
        # ② 缺头 → etag_missing
        try:
            client.get_version_snapshot(
                actor_id="probe", org_id="org-probe", project_id="proj-probe",
                ontology_id=STUB_ONTOLOGY_ID, version_id="ver-no-etag",
            )
            print("[FAIL] stub② 缺头：未抛 OntologySnapshotIntegrityError")
            ok = False
        except OntologySnapshotIntegrityError as exc:
            leg2 = exc.reason == "etag_missing"
            print(f"[{'PASS' if leg2 else 'FAIL'}] stub② 缺头: reason={exc.reason}")
            ok &= leg2
        # ③ 错值 → etag_mismatch
        try:
            client.get_version_snapshot(
                actor_id="probe", org_id="org-probe", project_id="proj-probe",
                ontology_id=STUB_ONTOLOGY_ID, version_id="ver-bad-etag",
            )
            print("[FAIL] stub③ 错值：未抛 OntologySnapshotIntegrityError")
            ok = False
        except OntologySnapshotIntegrityError as exc:
            leg3 = exc.reason == "etag_mismatch"
            print(f"[{'PASS' if leg3 else 'FAIL'}] stub③ 错值: reason={exc.reason}")
            ok &= leg3
    finally:
        server.shutdown()
        server.server_close()
    return ok


def run_runtime_leg(base_url: str, ontology_id: str, org_id: str) -> bool:
    """双仓真回环：raw 读版本清单核 ETag ≡ snapshot_sha256，再走新校验路径读快照。"""
    api_key = os.environ.get("FDE_ETAG_LOOPBACK_API_KEY", "")
    signing_key = os.environ.get("FDE_ETAG_LOOPBACK_SIGNING_KEY", "")
    if not api_key or not signing_key:
        print("[FAIL] runtime 腿需要 FDE_ETAG_LOOPBACK_API_KEY / FDE_ETAG_LOOPBACK_SIGNING_KEY（env，不入 argv）")
        return False
    client = OntologyClient(base_url, api_key, signing_key)
    def _signed_headers() -> dict[str, str]:
        # 签名上下文头的 nonce 单次有效（复用即 403 replayed，S-03）——每次 raw
        # 请求独立签名；客户端腿由 OntologyClient 内部自签。
        return {
            "X-API-Key": api_key,
            "X-FDE-Context": build_context_header(
                "fde-etag-probe", org_id, "proj-etag-probe", signing_key
            ),
        }

    listing = requests.get(
        f"{base_url}/api/v1/ontologies/{ontology_id}/versions", headers=_signed_headers(), timeout=10
    )
    if listing.status_code != 200:
        print(f"[FAIL] runtime 版本清单: HTTP {listing.status_code}")
        return False
    items = listing.json().get("items", [])
    if not items:
        print("[FAIL] runtime 版本清单为空（无已发布版本）")
        return False
    top = items[0]
    version_id = str(top["id"])
    expected_sha = str(top.get("snapshot_sha256", ""))
    raw = requests.get(
        f"{base_url}/api/v1/ontologies/{ontology_id}/versions/{version_id}/snapshot",
        headers=_signed_headers(), timeout=10,
    )
    header_etag = raw.headers.get("ETag", "")
    leg0 = raw.status_code == 200 and header_etag == expected_sha
    if raw.status_code != 200:
        print(f"[FAIL] runtime raw 快照读: HTTP {raw.status_code}（签名头须每请求独立）")
        return False
    print(
        f"[{'PASS' if leg0 else 'FAIL'}] runtime 版本 {top.get('version')}（{version_id[:8]}…）"
        f": ETag 头 ≡ 版本表 snapshot_sha256={bool(header_etag == expected_sha)}"
    )
    body = client.get_version_snapshot(
        actor_id="fde-etag-probe", org_id=org_id, project_id="proj-etag-probe",
        ontology_id=ontology_id, version_id=version_id,
    )
    leg1 = body.get("_status") == 200 and "_etag" not in body
    recomputed = canonical_json_sha256({k: v for k, v in body.items() if not k.startswith("_")})
    leg2 = header_etag == expected_sha == recomputed
    print(
        f"[{'PASS' if leg1 else 'FAIL'}] runtime 客户端读快照（新校验路径）: 通过={leg1}，"
        f"三锚合一（响应头 ≡ 版本表 ≡ 客户端重算）={leg2}"
    )
    print(f"       ETag={header_etag}")
    return bool(leg0 and leg1 and leg2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-base-url", default="", help="ontology-service 基址（可选；缺省只跑 stub 腿）")
    parser.add_argument("--ontology-id", default="", help="runtime 腿的本体 ID")
    parser.add_argument("--org-id", default="org-fde-demo", help="runtime 腿的 org（默认演练 org）")
    args = parser.parse_args()

    ok = run_stub_legs()
    if args.runtime_base_url:
        if not args.ontology_id:
            print("[FAIL] runtime 腿须同时给 --ontology-id")
            return 1
        ok &= run_runtime_leg(args.runtime_base_url.rstrip("/"), args.ontology_id, args.org_id)
    print("\n================ 回环结果 ================")
    print("[PASS] 快照 ETag 校验在真 HTTP 栈上成立（fail-closed 三向＋正例）" if ok else "[FAIL] 存在失败腿")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
