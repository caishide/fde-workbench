"""AE2-WP4：编排路由（54 号 v0.2-ACTIVE §3 WP4）。

四条新增路由（既有三路由语义零改动——禁改清单第 10 项）：
``POST /api/v1/action-tasks``（提交多步任务，含复放）／
``GET  /api/v1/action-tasks/<run_id>``（运行详情）／
``GET  /api/v1/action-tasks/<run_id>/nodes``（节点清单＝WP2 服务面出口）／
``POST /api/v1/action-tasks/<run_id>/compensation``（触发补偿，B11 幂等）。

验收（54 号 §3 WP4 ①–⑥）：①信封沿 ``{data,error}``；②留痕齐备零明文
（审计钉见 test_ae_task_audit.py）；③–④敏感键/哨兵零命中（审计钉）；⑤非法图
422 零副作用；⑥审计 append-only（路由面无 PATCH/DELETE）。
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

import pytest
from flask import Flask

from fde_api.auth.tokens import issue_access_token
from multi_tenant_harness import make_enterprise_org, make_user

SENTINEL = "AE-SENTINEL-SECRET-0001"


class AllowAllWhitelist:
    def check(self, connector_id: str, method: str) -> None:
        return None


class TaskDispatch:
    def __init__(self, *, fail_action_ids: set[str] | None = None, delay: float = 0.0) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.fail_action_ids = fail_action_ids or set()
        self.delay = delay

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.calls += 1
        if self.delay:
            import time

            time.sleep(self.delay)
        if request["action_id"] in self.fail_action_ids:
            raise RuntimeError("dispatch exploded")
        return {"available": 3, "quantity": 1}


@pytest.fixture
def route_env(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    org_b = make_enterprise_org(db_session)
    actor_b = make_user(db_session, "project_lead", org_id=org_b.id)
    db_session.commit()
    return {"org": org, "actor": actor, "org_b": org_b, "actor_b": actor_b}


@pytest.fixture
def wired_orchestrator(monkeypatch):
    """把编排执行器生产装配点替换为测试桩（白名单放行＋派发桩）。

    真实装配＝routes 模块级 ``_wired_orchestrator()``（WP4 落位）；桩注入
    只替 dispatch/whitelist 两点，路由本体与生产装配路径同构验证。"""

    from fde_api.action_execution import routes as ae_routes

    dispatch = TaskDispatch()

    def _factory() -> dict[str, Any]:
        return {"whitelist_gate": AllowAllWhitelist(), "dispatch": dispatch, "compensator": None}

    monkeypatch.setattr(ae_routes, "_wired_orchestrator", _factory)
    return {"dispatch": dispatch}


def _auth_headers(actor: Any, test_settings: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(actor, test_settings)}"}


def _node(key: str, depends: tuple[str, ...] = (), **act_over: Any) -> dict[str, Any]:
    action: dict[str, Any] = {
        "action_id": f"mock.erp.{key}",
        "connector_id": "mock.erp",
        "method": "query_inventory",
        "params": {"sku": {"kind": "literal", "value": f"SKU-{key}"}},
        "dry_run": False,
        "risk_level": 1,
        "timeout_seconds": 30,
    }
    action.update(act_over)
    return {"node_key": key, "depends_on": list(depends), "action": action, "rollback_supported": True}


def _payload(org_id: str, requester_id: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "org_id": org_id,
        "requester_id": requester_id,
        "idempotency_key": "ae2-route-" + uuid4().hex[:10],
        "definition": {"nodes": nodes},
    }


def _make_run(client, route_env, test_settings, wired_orchestrator, *, nodes=None, fail=None) -> dict[str, Any]:
    """经路由真实提交一个运行（提交路径同构验证）；fail＝注入派发失败的 action_id。"""
    payload = _payload(
        route_env["org"].id,
        route_env["actor"].id,
        nodes or [_node("n1"), _node("n2", ("n1",))],
    )
    if fail:
        wired_orchestrator["dispatch"].fail_action_ids = fail
    resp = client.post(
        "/api/v1/action-tasks", json=payload, headers=_auth_headers(route_env["actor"], test_settings)
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


# ---- ① 提交路由：信封 201 ＋ 复放同响应 ＋ 未认证 401 --------------------------


class TestSubmitRoute:
    def test_submit_envelope_201_and_replay_same_response(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        from fde_api.action_execution import service as ae_service
        from fde_api.action_execution.models import ActionTaskRun

        payload = _payload(route_env["org"].id, route_env["actor"].id, [_node("n1"), _node("n2", ("n1",))])
        headers = _auth_headers(route_env["actor"], test_settings)
        resp = client.post("/api/v1/action-tasks", json=payload, headers=headers)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["error"] is None
        assert body["data"]["status"] == "succeeded"
        assert [n["node_key"] for n in body["data"]["nodes"]] == ["n1", "n2"]
        assert wired_orchestrator["dispatch"].calls == 2

        replay = client.post("/api/v1/action-tasks", json=payload, headers=headers)
        assert replay.status_code == 201  # 复放沿提交面口径：同载荷同状态码
        assert replay.get_json()["data"] == body["data"]  # 逐字一致（B7）
        assert wired_orchestrator["dispatch"].calls == 2  # 零重复外呼

        rows = (
            db_session.query(ActionTaskRun)
            .filter(ActionTaskRun.idempotency_key == payload["idempotency_key"])
            .all()
        )
        assert len(rows) == 1  # 同键一行真身
        run_row = rows[0]
        assert run_row.audit_json.get("orchestration") == "fail_fast"

    def test_submit_unauthenticated_is_401(self, app: Flask, client, db_session, route_env, wired_orchestrator) -> None:
        payload = _payload(route_env["org"].id, route_env["actor"].id, [_node("n1")])
        resp = client.post("/api/v1/action-tasks", json=payload)
        assert resp.status_code == 401
        assert wired_orchestrator["dispatch"].calls == 0

    def test_submit_invalid_graph_422_zero_side_effects(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        """验收⑤：图含环/未知依赖 → 422 且零副作用（无运行行、零外呼）。"""
        from sqlalchemy import select

        from fde_api.action_execution.models import ActionTaskRun

        payload = _payload(
            route_env["org"].id,
            route_env["actor"].id,
            [_node("n1", ("n2",)), _node("n2", ("n1",))],
        )
        headers = _auth_headers(route_env["actor"], test_settings)
        resp = client.post("/api/v1/action-tasks", json=payload, headers=headers)
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["data"] is None
        assert body["error"]["code"] == "validation_failed"
        assert wired_orchestrator["dispatch"].calls == 0
        # 零副作用判据＝本幂等键零运行行（库内他测试经 routes 落的行不在此判据域）
        assert (
            db_session.scalars(
                select(ActionTaskRun).where(ActionTaskRun.idempotency_key == payload["idempotency_key"])
            ).all()
            == []
        )

    def test_submit_cross_tenant_org_is_404(self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings) -> None:
        payload = _payload(route_env["org_b"].id, route_env["actor"].id, [_node("n1")])
        headers = _auth_headers(route_env["actor"], test_settings)
        resp = client.post("/api/v1/action-tasks", json=payload, headers=headers)
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"
        assert wired_orchestrator["dispatch"].calls == 0

    def test_submit_viewer_is_403(self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings) -> None:
        from multi_tenant_harness import make_user as _make_user

        viewer = _make_user(db_session, "viewer", org_id=route_env["org"].id)
        db_session.commit()
        payload = _payload(route_env["org"].id, viewer.id, [_node("n1")])
        resp = client.post("/api/v1/action-tasks", json=payload, headers=_auth_headers(viewer, test_settings))
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "permission_revoked"


# ---- ② 详情／节点清单路由：200 ＋ 跨租户 404 不泄露 -----------------------------


class TestDetailRoutes:
    def test_get_detail_200_and_cross_tenant_404(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        data = _make_run(client, route_env, test_settings, wired_orchestrator)
        headers = _auth_headers(route_env["actor"], test_settings)
        resp = client.get(f"/api/v1/action-tasks/{data['execution_id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["execution_id"] == data["execution_id"]
        assert resp.get_json()["data"]["nodes"][0]["node_key"] == "n1"

        # C2：跨租户读取 → 404（响应体不含他租户任何内容）
        resp_b = client.get(
            f"/api/v1/action-tasks/{data['execution_id']}",
            headers=_auth_headers(route_env["actor_b"], test_settings),
        )
        assert resp_b.status_code == 404
        assert route_env["org"].id not in resp_b.get_data(as_text=True)

    def test_get_detail_unknown_id_is_404(self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings) -> None:
        resp = client.get(
            "/api/v1/action-tasks/does-not-exist", headers=_auth_headers(route_env["actor"], test_settings)
        )
        assert resp.status_code == 404

    def test_get_nodes_200_sequence_matches_contract(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        data = _make_run(client, route_env, test_settings, wired_orchestrator)
        resp = client.get(
            f"/api/v1/action-tasks/{data['execution_id']}/nodes",
            headers=_auth_headers(route_env["actor"], test_settings),
        )
        assert resp.status_code == 200
        nodes = resp.get_json()["data"]
        assert [n["node_key"] for n in nodes] == ["n1", "n2"]
        assert nodes[1]["depends_on_json"] == ["n1"]  # 依赖快照（节点行权威载体）
        assert nodes[0]["action_execution_id"]  # 指向 AE1 执行行

        resp_b = client.get(
            f"/api/v1/action-tasks/{data['execution_id']}/nodes",
            headers=_auth_headers(route_env["actor_b"], test_settings),
        )
        assert resp_b.status_code == 404  # C2 节点面同口径


# ---- ③ 补偿触发路由：失败运行 200 ＋ 成功运行 422 ＋ 跨租户 404 ------------------


class TestCompensationRoute:
    def test_compensation_on_failed_run_200_and_idempotent(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        data = _make_run(client, route_env, test_settings, wired_orchestrator, fail={"mock.erp.n2"})
        assert data["status"] == "rolled_back"  # inline 补偿已收口
        headers = _auth_headers(route_env["actor"], test_settings)
        resp = client.post(
            f"/api/v1/action-tasks/{data['execution_id']}/compensation", json={}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"] == data  # B11：快照逐字一致（幂等短路）

    def test_compensation_on_succeeded_run_422(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        data = _make_run(client, route_env, test_settings, wired_orchestrator)
        assert data["status"] == "succeeded"
        resp = client.post(
            f"/api/v1/action-tasks/{data['execution_id']}/compensation",
            json={},
            headers=_auth_headers(route_env["actor"], test_settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_compensation_cross_tenant_404(
        self, app: Flask, client, db_session, route_env, wired_orchestrator, test_settings
    ) -> None:
        data = _make_run(client, route_env, test_settings, wired_orchestrator, fail={"mock.erp.n2"})
        resp = client.post(
            f"/api/v1/action-tasks/{data['execution_id']}/compensation",
            json={},
            headers=_auth_headers(route_env["actor_b"], test_settings),
        )
        assert resp.status_code == 404


# ---- ⑥ append-only：路由面无 PATCH/DELETE -------------------------------------


class TestAppendOnlyRoutes:
    def test_blueprint_has_no_mutation_methods_for_tasks(self, app: Flask) -> None:
        """验收⑥：编排面路由集合闭集钉（四条；无 PATCH/DELETE 面）。"""
        from fde_api.action_execution.routes import action_execution_blueprint

        task_rules = [
            rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/v1/action-tasks")
        ]
        methods: dict[str, set[str]] = {}
        for task_rule in task_rules:
            rule_methods = task_rule.methods or set()
            methods[task_rule.rule] = {m for m in rule_methods if m not in ("HEAD", "OPTIONS")}
        assert set(methods) == {
            "/api/v1/action-tasks",
            "/api/v1/action-tasks/<run_id>",
            "/api/v1/action-tasks/<run_id>/nodes",
            "/api/v1/action-tasks/<run_id>/compensation",
        }
        for rule_path, route_methods in methods.items():
            assert "PATCH" not in route_methods and "DELETE" not in route_methods, rule_path
        assert methods["/api/v1/action-tasks"] == {"POST"}
        assert methods["/api/v1/action-tasks/<run_id>"] == {"GET"}
        assert methods["/api/v1/action-tasks/<run_id>/nodes"] == {"GET"}
        assert methods["/api/v1/action-tasks/<run_id>/compensation"] == {"POST"}
        assert action_execution_blueprint is not None
