"""AF3-WP4：修复闭环（correction_loop 预算内失败→修复→复测＋CI 结果消费）
＋D2 审计 defer 清偿（20 号 §3 WP4；05 §2.1 T4「修复轨迹」＋05 §3「错误修复
成功率——预算内真实读取失败并通过复测」＋AF1① correction_loop「预算内收敛
不无限重试」＋AF2④「修复须消费服务端逐项错误」）。

- **轨迹原语组合**：失败 CI run（verdict=red）→ 修复 PatchPlan（apply）→
  同 bundle 复测（run_ci）→ green＝闭环 corrected；仍 red＝round+1；
  预算（max_rounds）耗尽 → budget_exhausted 诚实终态（不无限重试）。
- **≥3 类构建失败可修复**（05 §5 AF3 行）：T4 失败种子三类（lint 坏 YAML/
  单测产物值断言/契约缺 kind）各实测一条「red→修复→green」轨迹。
- **CI 结果消费**（AF2④）：correction 请求须携 `failed_run_id`（消费对象锚）
  且该 run 须 verdict=red——不锚失败结果的修复请求拒（停点纪律形态）。
- **D2 清偿**：绑定审计 events 携 actor_id/时刻（WP5 结构化台账的前置落位）。
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


def _make_seed_repo(root: Path) -> Path:
    """T4 失败种子三类（af3_sample_repo.py 同源）：lint 坏 YAML／单测产物值
    断言／契约缺 kind——三类 CI red 的材料真身。"""
    repo = root
    for d in ("ontology", "transforms", "rules", "config", "tests", "tests/transforms"):
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
    # 种子① lint：坏 YAML
    (repo / "ontology" / "broken-seed.yaml").write_text("kind: [unclosed\n", encoding="utf-8")
    # 种子② 单测：产物值断言（version 1.0.0 ≠ 断言的 2.0.0）
    (repo / "tests" / "test_failing_assertion.py").write_text(
        'def test_product_value():\n'
        '    text = open("ontology/equipment.yaml", encoding="utf-8").read()\n'
        '    assert "version: 2.0.0" in text, "产物版本须为 2.0.0"\n',
        encoding="utf-8",
    )
    # 种子③ 契约：缺 kind（contract schema 必备键）
    (repo / "config" / "missing-kind-seed.json").write_text(
        '{"settings": {"threshold": 1}}\n', encoding="utf-8"
    )
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "seed baseline")
    return repo


@pytest.fixture
def seed_repo(tmp_path: Path, af3_repo_base: Path) -> Path:
    return _make_seed_repo(af3_repo_base / "seed-solutions")


@pytest.fixture
def af3_world(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    db_session.commit()
    return {"org": org, "actor": actor}


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _bind(client, af3_world, settings, seed_repo) -> str:
    resp = client.post(
        "/api/v1/solution-repo/bindings",
        json={
            "repo_root": str(seed_repo),
            "workspace_root": str(seed_repo),
            "branch": f"af3/{uuid.uuid4().hex[:8]}",
            "allow_roots": ["ontology/", "transforms/", "rules/", "tests/", "config/"],
        },
        headers=_auth(af3_world["actor"], settings),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["binding_id"]


def _run_ci(client, af3_world, settings, binding_id: str, bundle_id: str):
    return client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
        json={"bundle_id": bundle_id},
        headers=_auth(af3_world["actor"], settings),
    )


def _make_red_run(client, af3_world, settings, binding_id: str, bundle_id: str) -> str:
    """制造一个 verdict=red 的 CI run，返回 run_id。"""
    resp = _run_ci(client, af3_world, settings, binding_id, bundle_id)
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["verdict"] == "red", data
    return data["run_id"]


class TestCorrectionLoop:
    """T4 失败种子三类实测轨迹：red → 修复 patch → 复测 green → corrected。"""

    def _corrected_assertions(self, resp) -> None:
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()["data"]
        assert data["status"] == "corrected"
        assert data["rounds_consumed"] == 1
        assert data["final_verdict"] == "green"
        assert data["failed_run_id"] and data["final_run_id"]
        assert data["failed_run_id"] != data["final_run_id"]
        return data

    def test_lint_seed_trajectory(self, client, af3_world, settings, seed_repo) -> None:
        """种子①：lint 坏 YAML → red → 修复（合法化）→ lint 复测 green。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "lint")
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {"path": "ontology/broken-seed.yaml", "operation": "update", "content": "kind: ontology\nname: fixed\n"}
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "lint", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        self._corrected_assertions(resp)
        assert _git(seed_repo, "status", "--porcelain") == ""

    def test_unit_test_seed_trajectory(self, client, af3_world, settings, seed_repo) -> None:
        """种子②：单测产物值断言失败 → red → 修复产物 version → unit_test 复测 green。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "unit_test")
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {
                    "path": "ontology/equipment.yaml",
                    "operation": "update",
                    "content": "kind: ontology\nname: equipment\nversion: 2.0.0\n",
                }
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "unit_test", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        self._corrected_assertions(resp)

    def test_contract_seed_trajectory(self, client, af3_world, settings, seed_repo) -> None:
        """种子③：契约缺 kind → contract red → 修复（补 kind）→ 复测 green——
        三类齐＝05 §5「≥3 类构建失败可修复」轨迹实测面。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "contract")
        # contract 扫全四域：种子仓的坏 YAML（lint 种子）在 contract 模式同样
        # 违例（解析失败）——修复 patch 须双 entry（多 entry 合法形态）。
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {
                    "path": "ontology/broken-seed.yaml",
                    "operation": "update",
                    "content": "kind: ontology\nname: fixed\nversion: 1.0.0\n",
                },
                {
                    "path": "config/missing-kind-seed.json",
                    "operation": "update",
                    "content": '{"kind": "config", "settings": {"threshold": 1}}\n',
                },
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "contract", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        self._corrected_assertions(resp)


class TestBudgetAndDiscipline:
    def test_budget_exhausted_honest_terminal(self, client, af3_world, settings, seed_repo) -> None:
        """预算内收敛纪律：max_rounds=1 且修复无效（patch 不改任何失败项）→
        复测仍 red → budget_exhausted 诚实终态（不无限重试、不冒充 corrected）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "unit_test")
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                # 无效修复：改一个与失败断言无关的文件
                {"path": "rules/quality.json", "operation": "update", "content": '{"kind": "rule", "name": "quality", "condition": "a > 2"}\n'}
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "unit_test", "patches": [plan], "max_rounds": 1},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "budget_exhausted"
        assert data["final_verdict"] == "red"
        assert data["rounds_consumed"] == 1

    def test_failed_run_must_be_red(self, client, af3_world, settings, seed_repo) -> None:
        """CI 结果消费纪律：correction 必须锚 red run——green run 不可作为修复
        对象（停点纪律形态：不锚失败结果的修复请求拒）。

        前置：先经一条 correction 修复 lint 种子（broken-seed）→ 后续 lint run
        才是 green（种子仓 lint 初跑必红）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        seed_run_id = _make_red_run(client, af3_world, settings, binding_id, "lint")
        fix = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {"path": "ontology/broken-seed.yaml", "operation": "update", "content": "kind: ontology\nname: fixed\n"}
            ],
        }
        corrected = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": seed_run_id, "bundle_id": "lint", "patches": [fix]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert corrected.get_json()["data"]["status"] == "corrected"
        green_run_id = _run_ci(client, af3_world, settings, binding_id, "lint").get_json()["data"]["run_id"]
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
        }
        resp2 = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": green_run_id, "bundle_id": "lint", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp2.status_code == 422
        assert resp2.get_json()["error"]["code"] == "validation_failed"

    def test_unknown_failed_run_404(self, client, af3_world, settings, seed_repo) -> None:
        binding_id = _bind(client, af3_world, settings, seed_repo)
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": str(uuid.uuid4()), "bundle_id": "lint", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 404


class TestAuditActorTimestamp:
    """评审 D2 清偿：绑定审计 events 携 actor_id/时刻（WP5 结构化台账前置）。"""

    def test_audit_events_carry_actor_and_timestamp(self, client, af3_world, settings, seed_repo) -> None:
        binding_id = _bind(client, af3_world, settings, seed_repo)
        detail = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}",
            headers=_auth(af3_world["actor"], settings),
        )
        events = detail.get_json()["data"]["audit_json"]["events"]
        assert events, "bind 事件必须在场"
        ev = events[-1]
        assert ev.get("actor_id") == af3_world["actor"].id
        assert ev.get("at")  # ISO 时刻（UTC）


# ---- 评审批次补钉（vg 读回断言＋H1/H4/H5 专钉） -------------------------------------


class TestReviewBatchPatches:
    def test_trajectory_persisted_and_read_back(self, client, af3_world, settings, seed_repo) -> None:
        """评审 vg1：RepoCorrection 落行读回断言（删持久化块测试必须红——
        T4「修复轨迹」证据本体）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "lint")
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {"path": "ontology/broken-seed.yaml", "operation": "update", "content": "kind: ontology\nname: fixed\n"}
            ],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "lint", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        listed = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            headers=_auth(af3_world["actor"], settings),
        )
        assert listed.status_code == 200
        items = listed.get_json()["data"]["items"]
        match = [i for i in items if i["failed_run_id"] == failed_run_id]
        assert match, "轨迹行必须真实落库并经读回面可见"
        row = match[0]
        assert row["status"] == "corrected"
        assert row["patches_applied"] == [plan["patch_id"]]
        assert row["rounds_consumed"] == 1

    def test_revoke_event_carries_actor(self, client, af3_world, settings, seed_repo) -> None:
        """评审 vg2：revoke 事件 actor_id 采纳断言（D2 清偿完整性——bind/revoke
        全事件）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/revoke",
            headers=_auth(af3_world["actor"], settings),
        )
        detail = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}",
            headers=_auth(af3_world["actor"], settings),
        )
        events = detail.get_json()["data"]["audit_json"]["events"]
        revoke_events = [e for e in events if e["event"] == "revoke"]
        assert revoke_events and revoke_events[-1]["actor_id"] == af3_world["actor"].id

    def test_anchor_staleness_rejected(self, client, af3_world, settings, seed_repo) -> None:
        """评审 H5：patches[0].base_commit 与失败 run 的 head_commit 不一致 → 422
        （锚时效——防他人已修好二次计入成功）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "lint")
        plan = {
            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
            "base_commit": "0" * 40,  # 与 failed run head 不一致
            "entries": [{"path": "ontology/broken-seed.yaml", "operation": "update", "content": "kind: ontology\nname: fixed\n"}],
        }
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "lint", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_used_patch_id_rejected(self, client, af3_world, settings, seed_repo) -> None:
        """评审 H4 前置：已使用 patch_id（含 failed 行）重提 → 422（AF2④）。"""
        binding_id = _bind(client, af3_world, settings, seed_repo)
        failed_run_id = _make_red_run(client, af3_world, settings, binding_id, "unit_test")
        # 先造一个 failed patch 行：commit 步骤失败
        from fde_api.solution_repo.git_ops import GitFailed, GitRunner

        plan = {
            "patch_id": "af3-fix-poison-" + uuid.uuid4().hex[:8],
            "base_commit": _git(seed_repo, "rev-parse", "HEAD"),
            "entries": [
                {"path": "ontology/first.yaml", "operation": "create", "content": "x\n"},
                {"path": "ontology/second.yaml", "operation": "create", "content": "y\n"},
            ],
        }
        orig_run = GitRunner.run

        def _fail_commit(self, *args, **kwargs):
            if args and args[0] == "commit":
                raise GitFailed(" ".join(args), 128, "simulated")
            return orig_run(self, *args, **kwargs)

        import unittest.mock as mock

        with mock.patch.object(GitRunner, "run", _fail_commit):
            bad = client.post(
                f"/api/v1/solution-repo/bindings/{binding_id}/patches",
                json=plan,
                headers=_auth(af3_world["actor"], settings),
            )
            assert bad.status_code == 500  # failed 行已落
        # 重提同 patch_id（异体 plan）经 POST /patches → 200 failed 原态复放
        # （WP3 H1：failed 终态行按原失败快照复放，不伪 replayed）；
        # **闭环内已用 patch_id → 422**（start_correction 预校验——不给失败重放
        # 洗白通道）。
        plan["entries"] = [{"path": "ontology/first.yaml", "operation": "create", "content": "fixed\n"}]
        plan["base_commit"] = _git(seed_repo, "rev-parse", "HEAD")
        replay = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/patches",
            json=plan,
            headers=_auth(af3_world["actor"], settings),
        )
        assert replay.status_code == 200
        assert replay.get_json()["data"]["status"] == "failed"
        # 闭环面：同 patch_id 重提 → 422（start_correction 预校验）
        loop_resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={"failed_run_id": failed_run_id, "bundle_id": "unit_test", "patches": [plan]},
            headers=_auth(af3_world["actor"], settings),
        )
        assert loop_resp.status_code == 422
        assert loop_resp.get_json()["error"]["code"] == "validation_failed"
