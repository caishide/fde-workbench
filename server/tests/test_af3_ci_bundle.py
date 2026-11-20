"""AF3-WP3：固定受信任 CI bundle（design-first 规格件 `_af3-wp3-ci-bundle-spec.md`
§3 语义表的实现钉——P1 批准〔W-A~W-E 推荐案，无异议按默认推进呈追认〕后编码）。

- **bundle 闭集 4 条**（lint/contract/unit_test/transform_test）——argv 逐字来自
  FROZEN whitelist v3 快照模板，零请求体拼接；未知 bundle_id → 403；
- **ci_protected 名单**（评审 T1/T2 防线）：conftest/ini/pyproject/setup 等
  Patch 条目命中 → 403 protected_path_rejected（v3 deny 语义扩展）；
- **结果结构**（05 §5「CI 绿但没执行新增断言」防线）：executed_checks nodeid 级
  ＋new_test_nodeids 相对绑定基线差集——RepoCIRun 落行（append-only 可复跑）；
- **verdict 三态诚实归因**：green/red/error（timeout/执行层失败不冒充 red）；
- grant op 闭集扩 `run_ci`（v3 agent_allowed）。
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from fde_api.auth.tokens import issue_access_token
from multi_tenant_harness import make_enterprise_org, make_user


@pytest.fixture(autouse=True)
def af3_repo_base(app, monkeypatch, tmp_path: Path) -> Path:
    base = tmp_path / "af3-repo-base"
    base.mkdir()
    monkeypatch.setitem(
        app.config,
        "SETTINGS",
        app.config["SETTINGS"].model_copy(update={"solution_repo_base": str(base)}),
    )
    return base


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30, check=True
    )
    return proc.stdout.strip()


def _make_sample_repo(root: Path) -> Path:
    """受控示例仓（规格件 §5 材料制备计划①的行内简版）：四域产物＋基线测试
    （全过）＋一个 T4 预置失败断言（产物值错误 → CI red；修复产物 → green，
    即「可复现失败→修复→复测」轨迹的种子，05 §2.1 T4）。"""
    repo = root
    for d in ("ontology", "transforms", "rules", "tests", "config", "tests", "tests/transforms"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "ontology" / "equipment.yaml").write_text(
        "kind: ontology\nname: equipment\nversion: 1.0.0\n", encoding="utf-8"
    )
    (repo / "transforms" / "pipe.yaml").write_text(
        "kind: transform\nname: pipe\nsteps:\n  - select: [a, b]\n", encoding="utf-8"
    )
    (repo / "rules" / "quality.json").write_text(
        '{"kind": "rule", "name": "quality", "condition": "a > 1"}\n', encoding="utf-8"
    )
    (repo / "config" / "settings.json").write_text(
        '{"kind": "config", "settings": {"threshold": 3}}\n', encoding="utf-8"
    )
    (repo / "tests" / "test_sample.py").write_text(
        "def test_baseline_passes():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    (repo / "tests" / "transforms" / "test_pipe.py").write_text(
        "def test_transform_baseline():\n    assert True\n", encoding="utf-8"
    )
    # T4 预置失败断言（断言产物值——产物错误时红；修复后绿）
    (repo / "tests" / "test_failing_assertion.py").write_text(
        'def test_product_value():\n'
        '    text = open("ontology/equipment.yaml", encoding="utf-8").read()\n'
        '    assert "version: 2.0.0" in text, "产物版本须为 2.0.0（预置失败断言）"\n',
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "init")
    return repo


@pytest.fixture
def sample_repo(tmp_path: Path, af3_repo_base: Path) -> Path:
    return _make_sample_repo(af3_repo_base / "solutions")


@pytest.fixture
def af3_world(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    db_session.commit()
    return {"org": org, "actor": actor}


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _bind(client, af3_world, settings, sample_repo, **overrides) -> str:
    payload: dict = {
        "repo_root": str(sample_repo),
        "workspace_root": str(sample_repo),
        "branch": f"af3/{uuid.uuid4().hex[:8]}",
        "allow_roots": ["ontology/", "transforms/", "rules/", "tests/", "config/"],
    }
    payload.update(overrides)
    resp = client.post(
        "/api/v1/solution-repo/bindings", json=payload, headers=_auth(af3_world["actor"], settings)
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["binding_id"]


def _run_ci(client, af3_world, settings, binding_id: str, bundle_id: str):
    return client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
        json={"bundle_id": bundle_id},
        headers=_auth(af3_world["actor"], settings),
    )


# ---- ① bundle 闭集与门（白名单 v3） ---------------------------------------------


class TestBundleGate:
    def test_unknown_bundle_rejected(self, client, af3_world, settings, sample_repo) -> None:
        binding_id = _bind(client, af3_world, settings, sample_repo)
        resp = _run_ci(client, af3_world, settings, binding_id, "arbitrary_command")
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "tool_not_allowed"

    def test_run_ci_in_agent_allowed_and_grantable(self) -> None:
        from fde_api.solution_repo.snapshot import load_whitelist

        snap = load_whitelist()
        assert snap["version"] == "3.0.0"
        assert "run_ci" in snap["git_ops"]["agent_allowed"]
        bundles = snap["ci_bundle"]["bundles"]
        assert set(bundles) == {"lint", "contract", "unit_test", "transform_test"}
        # ci_protected 名单（评审 T1/T2 防线）
        protected = snap["ci_bundle"]["ci_protected"]
        assert "tests/conftest.py" in protected and "conftest.py" in protected
        assert "pyproject.toml" in protected and "setup.py" in protected
        assert "requirements.txt" in protected

    def test_ci_protected_patch_rejected(self, client, af3_world, settings, sample_repo) -> None:
        """评审 T1：Patch 触 conftest → 403（ci_protected deny 扩展）。"""
        binding_id = _bind(client, af3_world, settings, sample_repo)
        plan = {
            "patch_id": "af3-patch-" + uuid.uuid4().hex[:8],
            "base_commit": _git(sample_repo, "rev-parse", "HEAD"),
            "entries": [
                {"path": "tests/conftest.py", "operation": "create", "content": "import os; os.system('echo pwn')\n"}
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/patches",
            json=plan,
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "protected_path_rejected"

    def test_dirty_tree_rejected_before_run(self, client, af3_world, settings, sample_repo) -> None:
        binding_id = _bind(client, af3_world, settings, sample_repo)
        (sample_repo / "ontology" / "dirty.yaml").write_text("d\n", encoding="utf-8")
        resp = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "dirty_tree_conflict"

    def test_grant_missing_run_ci_forbidden(self, client, af3_world, settings, sample_repo) -> None:
        binding_id = _bind(
            client, af3_world, settings, sample_repo,
            grant_json={"ops": ["status", "read_file"]},  # 不含 run_ci
        )
        resp = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "tool_not_allowed"


# ---- ② 执行语义（verdict 三态＋执行清单＋新增断言对拍） --------------------------


class TestBundleExecution:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        return _bind(client, af3_world, settings, sample_repo)

    def test_lint_green_on_valid_products(self, client, af3_world, settings, binding_id) -> None:
        resp = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()["data"]
        assert data["verdict"] == "green"
        assert data["exit_code"] == 0
        assert data["executed_checks"], "lint 绿须有执行清单（非空）"

    def test_lint_red_on_broken_yaml(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        (sample_repo / "ontology" / "broken.yaml").write_text("kind: [unclosed\n", encoding="utf-8")
        _git(sample_repo, "add", ".")
        _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "broken")
        resp = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["verdict"] == "red"
        assert data["exit_code"] != 0
        assert "broken.yaml" in (data.get("stdout_head") or "") or "broken.yaml" in (data.get("stderr_head") or "")

    def test_contract_red_on_missing_kind(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        (sample_repo / "ontology" / "incomplete.yaml").write_text("name: x\n", encoding="utf-8")
        _git(sample_repo, "add", ".")
        _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "incomplete")
        resp = _run_ci(client, af3_world, settings, binding_id, "contract")
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["verdict"] == "red"
        assert "incomplete.yaml" in (data.get("stdout_head") or "") + (data.get("stderr_head") or "")

    def test_unit_test_red_on_preset_failing_assertion(self, client, af3_world, settings, binding_id) -> None:
        """T4 种子：预置失败断言 → red（「可复现失败」面）。"""
        resp = _run_ci(client, af3_world, settings, binding_id, "unit_test")
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["verdict"] == "red"
        outcomes = {c["nodeid"]: c["outcome"] for c in data["executed_checks"]}
        failing = [nid for nid, oc in outcomes.items() if oc == "failed"]
        assert any("test_failing_assertion" in nid for nid in failing), outcomes

    def test_executed_checks_and_replay_row(self, client, af3_world, settings, binding_id) -> None:
        """RepoCIRun 落行（append-only 可复跑＝两次 run 两行）。"""
        first = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert first.status_code == 201
        second = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert second.status_code == 201
        assert first.get_json()["data"]["run_id"] != second.get_json()["data"]["run_id"]
        runs = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
            headers=_auth(af3_world["actor"], settings),
        )
        assert runs.status_code == 200
        assert len(runs.get_json()["data"]["items"]) == 2

    def test_new_test_nodeids_covers_agent_added_assertion(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        """评审 T7／05 §5「CI 绿须执行新增断言」：Agent patch 新增测试文件 →
        CI 后 new_test_nodeids 须含其 nodeid（对拍面）。"""
        # Agent patch 新增一个会通过的测试文件
        plan = {
            "patch_id": "af3-patch-" + uuid.uuid4().hex[:8],
            "base_commit": _git(sample_repo, "rev-parse", "HEAD"),
            "entries": [
                {
                    "path": "tests/test_added_by_agent.py",
                    "operation": "create",
                    "content": "def test_agent_added():\n    assert True\n",
                }
            ],
        }
        applied = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/patches",
            json=plan,
            headers=_auth(af3_world["actor"], settings),
        )
        assert applied.status_code == 201
        # 预置失败断言先修好（产物修复 → unit_test 其余绿）——直接修产物再 commit
        (sample_repo / "ontology" / "equipment.yaml").write_text(
            "kind: ontology\nname: equipment\nversion: 2.0.0\n", encoding="utf-8"
        )
        _git(sample_repo, "add", ".")
        _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "fix product")
        resp = _run_ci(client, af3_world, settings, binding_id, "unit_test")
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["verdict"] == "green"
        new_ids = data["new_test_nodeids"]
        assert any("test_added_by_agent" in nid for nid in new_ids), new_ids

    def test_runs_cross_tenant_404(self, client, af3_world, settings, sample_repo, db_session) -> None:
        binding_id = _bind(client, af3_world, settings, sample_repo)
        outsider = make_user(db_session, "project_lead", org_id=make_enterprise_org(db_session).id)
        db_session.commit()
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
            headers=_auth(outsider, settings),
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_run_forbidden_on_revoked_binding(self, client, af3_world, settings, sample_repo) -> None:
        binding_id = _bind(client, af3_world, settings, sample_repo)
        client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/revoke",
            headers=_auth(af3_world["actor"], settings),
        )
        resp = _run_ci(client, af3_world, settings, binding_id, "lint")
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "permission_revoked"
