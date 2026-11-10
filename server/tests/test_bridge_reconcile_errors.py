"""CR-069：bridge reconcile 错误码区分——真无快照 409 no_snapshot；投影 DB 故障 500 sync_failed。

此前 except BridgeSyncError 一律 409 no_snapshot：DB 故障被误报为「没有可重放
快照」，运维排障方向被误导（查采集链路而非数据库）。
"""
from __future__ import annotations

import pytest

from conftest import INITIAL_PASSWORD

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token


@pytest.fixture
def lead_client(app, db_session, settings):
    user = User(
        username=f"bridge-reconcile.{__import__('uuid').uuid4().hex[:6]}",
        display_name="桥重投影",
        role="project_lead",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = issue_access_token(user, settings)
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_reconcile_distinguishes_no_snapshot_from_db_failure(
    lead_client, monkeypatch
):
    client, headers = lead_client

    from fde_api.bridge.sync import BridgeSyncError

    def no_snap():
        raise BridgeSyncError("no successful snapshot to reproject")

    monkeypatch.setattr("fde_api.bridge.routes.reproject_last", no_snap)
    resp = client.post("/api/v1/bridge/reconcile", headers=headers)
    assert resp.status_code == 409
    assert resp.json["error"]["code"] == "no_snapshot"

    def boom():
        raise BridgeSyncError("snapshot apply failed: connection refused")

    monkeypatch.setattr("fde_api.bridge.routes.reproject_last", boom)
    resp = client.post("/api/v1/bridge/reconcile", headers=headers)
    assert resp.status_code == 500
    assert resp.json["error"]["code"] == "sync_failed"
