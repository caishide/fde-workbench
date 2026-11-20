"""AF3-WP2：类型化 Patch adapter——PatchPlan 键集精确契约＋patch_apply 原子应用
＋diff/log 读面＋D1 TOCTOU 复核＋D3 grant 要素（20 号 §3 WP2）。

纪律：
- **键集精确**（沿 AF2 WP2 TransformPlan 纪律）：PatchPlan 顶层键闭集
  ``{patch_id, base_commit, entries}``、entry 键闭集 ``{path, operation,
  content}``、operation 闭集 ``{create, update, delete}``、delete 无 content／
  create-update 必有 content——未知键/缺键/越值一律 422（details 列出未知键，
  AF2④ 结构化拒绝信息消费）；
- **修改源内容后旧批准失效**（04 §3.3）：``plan.base_commit`` 必须＝应用时刻
  HEAD（漂移 → 409 base_mismatch）；
- **原子应用＋受控提交**：逐条目写入→git add 受控路径→受控 commit（af3-bot
  身份）→applied_commit 返回（05 §2.1 T4「commit/产物 hash」证据锚）；任何
  失败路径逆序回滚＋工作树零残留（porcelain 空）＋RepoPatch failed 行留痕；
- **幂等**（AE1 同构）：同 (org, binding, patch_id) 重放＝复放首次结果（HTTP
  200 replayed），幂等查先于一切校验；
- **D3 grant 要素**（04 §3.3 绑定五要素）：``RepoBinding.grant_json``＝
  agent_allowed 子集白名单（null＝全量）；闭集外 op 绑定时 422、服务面越权 403；
- **D1 TOCTOU**：read_file 打开后 realpath 复核（Windows 无 O_NOFOLLOW）——
  复核逃逸即 422 symlink_escape_rejected；
- 白名单 **v2.0.0**（patch_apply 入 agent_allowed——20 号 §2 D2 授权链齐）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fde_api.auth.tokens import issue_access_token
from fde_api.solution_repo.patch_plan import validate_patch_plan
from multi_tenant_harness import make_enterprise_org, make_user


@pytest.fixture(autouse=True)
def af3_repo_base(app, monkeypatch, tmp_path: Path) -> Path:
    """评审 G1 围栏（WP1 同款）：本文件全部测试在显式 base 下运行。"""
    base = tmp_path / "af3-repo-base"
    base.mkdir()
    monkeypatch.setitem(
        app.config,
        "SETTINGS",
        app.config["SETTINGS"].model_copy(update={"solution_repo_base": str(base)}),
    )
    return base


@pytest.fixture
def sample_repo(tmp_path: Path, af3_repo_base: Path) -> Path:
    repo = af3_repo_base / "solutions"
    for d in ("ontology", "transforms", "rules", "tests", "config"):
        (repo / d).mkdir(parents=True)
    (repo / "ontology" / "equipment.yaml").write_text(
        "kind: ontology\nname: equipment\nversion: 1.0.0\n", encoding="utf-8"
    )
    (repo / "rules" / "quality.json").write_text('{"level": "basic"}\n', encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "init")
    return repo


def _git(repo: Path, *args: str) -> str:
    import subprocess

    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30, check=True
    )
    return proc.stdout.strip()


@pytest.fixture
def af3_world(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    outsider = make_user(db_session, "project_lead", org_id=make_enterprise_org(db_session).id)
    db_session.commit()
    return {"org": org, "actor": actor, "outsider": outsider}


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


def _plan(entries: list[dict], *, base_commit: str | None = None, **overrides) -> dict:
    plan: dict = {
        "patch_id": "af3-patch-" + uuid.uuid4().hex[:8],
        "base_commit": base_commit or ("0" * 40),
        "entries": entries,
    }
    plan.update(overrides)
    return plan


def _post_patch(client, af3_world, settings, binding_id: str, plan: dict, auth_user=None):
    return client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/patches",
        json=plan,
        headers=_auth(auth_user or af3_world["actor"], settings),
    )


# ---- ① PatchPlan 键集精确契约（纯函数面） ---------------------------------------


class TestPatchPlanContract:
    def test_valid_plan_normalizes(self) -> None:
        plan = _plan(
            [
                {"path": "ontology/a.yaml", "operation": "update", "content": "v2\n"},
                {"path": "ontology/new.yaml", "operation": "create", "content": "v1\n"},
                {"path": "rules/old.json", "operation": "delete"},
            ],
            base_commit="a" * 40,
        )
        normalized = validate_patch_plan(plan, allow_roots=("ontology/", "rules/", "transforms/", "tests/", "config/"))
        assert normalized["patch_id"] == plan["patch_id"]
        assert normalized["base_commit"] == "a" * 40
        assert [e["operation"] for e in normalized["entries"]] == ["update", "create", "delete"]

    def test_unknown_top_level_key_rejected(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "update", "content": "x"}])
        plan["sneaky_cmd"] = "rm -rf /"
        with pytest.raises(Exception) as ei:
            validate_patch_plan(plan, allow_roots=("ontology/",))
        assert "sneaky_cmd" in str(ei.value)

    def test_unknown_entry_key_rejected(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "update", "content": "x", "exec": "bash"}])
        with pytest.raises(Exception) as ei:
            validate_patch_plan(plan, allow_roots=("ontology/",))
        assert "exec" in str(ei.value)

    def test_operation_closed_set(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "chmod", "content": "x"}])
        with pytest.raises(Exception):
            validate_patch_plan(plan, allow_roots=("ontology/",))

    def test_delete_must_not_carry_content(self) -> None:
        plan = _plan([{"path": "rules/old.json", "operation": "delete", "content": "x"}])
        with pytest.raises(Exception):
            validate_patch_plan(plan, allow_roots=("rules/",))

    def test_create_update_require_content(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "update"}])
        with pytest.raises(Exception):
            validate_patch_plan(plan, allow_roots=("ontology/",))

    def test_entries_must_be_non_empty_list(self) -> None:
        with pytest.raises(Exception):
            validate_patch_plan(_plan([]), allow_roots=("ontology/",))
        with pytest.raises(Exception):
            validate_patch_plan(_plan("not-a-list"), allow_roots=("ontology/",))

    def test_patch_id_shape(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "update", "content": "x"}])
        plan["patch_id"] = "../evil id!"
        with pytest.raises(Exception):
            validate_patch_plan(plan, allow_roots=("ontology/",))

    def test_base_commit_must_be_40_hex(self) -> None:
        plan = _plan([{"path": "ontology/a.yaml", "operation": "update", "content": "x"}])
        plan["base_commit"] = "HEAD~1"
        with pytest.raises(Exception):
            validate_patch_plan(plan, allow_roots=("ontology/",))

    def test_protected_path_entry_rejected(self) -> None:
        plan = _plan([{"path": ".git/hooks/pre-commit", "operation": "create", "content": "#!/bin/sh\n"}])
        with pytest.raises(Exception) as ei:
            validate_patch_plan(plan, allow_roots=("ontology/",))
        assert ".git" in str(ei.value)

    def test_oversize_entries_rejected(self) -> None:
        big = "x" * 524289
        plan = _plan([{"path": "ontology/big.yaml", "operation": "create", "content": big}])
        with pytest.raises(Exception) as ei:
            validate_patch_plan(plan, allow_roots=("ontology/",))
        assert "bytes 超限" in str(ei.value)


# ---- ② patch_apply 服务面（原子应用＋受控提交＋幂等＋回滚） -----------------------


class TestPatchApply:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        return _bind(client, af3_world, settings, sample_repo)

    def _head(self, sample_repo: Path) -> str:
        return _git(sample_repo, "rev-parse", "HEAD")

    def test_apply_create_update_delete_commit(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        base = self._head(sample_repo)
        plan = _plan(
            [
                {"path": "ontology/equipment.yaml", "operation": "update", "content": "kind: ontology\nversion: 2.0.0\n"},
                {"path": "ontology/added.yaml", "operation": "create", "content": "new file\n"},
                {"path": "rules/quality.json", "operation": "delete"},
            ],
            base_commit=base,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()["data"]
        assert data["status"] == "applied"
        assert data["applied_commit"] != base
        assert len(data["applied_commit"]) == 40
        assert data["entries_applied"] == 3
        # 工作树干净（受控 commit 已落）
        assert _git(sample_repo, "status", "--porcelain") == ""
        # 内容落盘
        assert "version: 2.0.0" in (sample_repo / "ontology" / "equipment.yaml").read_text(encoding="utf-8")
        assert (sample_repo / "ontology" / "added.yaml").exists()
        assert not (sample_repo / "rules" / "quality.json").exists()
        # commit 历史含 patch_id（T4 证据锚）
        log = _git(sample_repo, "log", "--oneline", "-n", "2")
        assert plan["patch_id"] in log

    def test_base_mismatch_rejected(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        stale = self._head(sample_repo)
        _plan_and_commit_dummy(client, af3_world, settings, binding_id, sample_repo)  # HEAD 前进
        plan = _plan(
            [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
            base_commit=stale,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "base_mismatch"

    def test_dirty_tree_rejected(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        (sample_repo / "ontology" / "dirty.yaml").write_text("dirty\n", encoding="utf-8")
        plan = _plan(
            [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
            base_commit=self._head(sample_repo),
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "dirty_tree_conflict"

    def test_outside_allow_roots_entry_rejected(self, client, af3_world, settings, binding_id) -> None:
        plan = _plan(
            [{"path": "README.md", "operation": "create", "content": "x\n"}],
            base_commit="0" * 40,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "outside_allow_roots"

    def test_protected_path_entry_rejected_http(self, client, af3_world, settings, binding_id) -> None:
        plan = _plan(
            [{"path": ".git/hooks/pre-commit", "operation": "create", "content": "#!/bin/sh\nrm -rf /\n"}],
            base_commit="0" * 40,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "protected_path_rejected"

    def test_unknown_key_rejected_http(self, client, af3_world, settings, binding_id) -> None:
        plan = _plan(
            [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
            base_commit="0" * 40,
        )
        plan["hook_payload"] = {"cmd": "curl evil"}
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"
        assert "hook_payload" in str(resp.get_json()["error"])

    def test_oversize_rejected_http(self, client, af3_world, settings, binding_id) -> None:
        plan = _plan(
            [{"path": "ontology/big.yaml", "operation": "create", "content": "x" * 524289}],
            base_commit="0" * 40,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "oversize_patch"

    def test_idempotent_replay(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        """同 (org, binding, patch_id) 重放＝复放首次结果（零重复副作用）。"""
        base = self._head(sample_repo)
        plan = _plan(
            [{"path": "ontology/once.yaml", "operation": "create", "content": "once\n"}],
            base_commit=base,
        )
        first = _post_patch(client, af3_world, settings, binding_id, plan)
        assert first.status_code == 201
        applied_commit = first.get_json()["data"]["applied_commit"]
        replay = _post_patch(client, af3_world, settings, binding_id, plan)
        assert replay.status_code == 200
        assert replay.get_json()["data"]["status"] == "replayed"
        assert replay.get_json()["data"]["applied_commit"] == applied_commit
        # 工作树不变（零重复副作用）
        assert _git(sample_repo, "status", "--porcelain") == ""
        assert (sample_repo / "ontology" / "once.yaml").read_text(encoding="utf-8") == "once\n"

    def test_failed_apply_rolls_back_clean(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        """应用中途失败（create 目标为已存在目录）→ 逆序回滚＋工作树零残留＋
        RepoPatch failed 行留痕（不冒充成功）。"""
        base = self._head(sample_repo)
        plan = _plan(
            [
                {"path": "ontology/first-ok.yaml", "operation": "create", "content": "ok\n"},
                {"path": "rules", "operation": "create", "content": "collides-with-directory\n"},
            ],
            base_commit=base,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 500
        assert resp.get_json()["error"]["code"] == "git_operation_failed"
        # 零残留：first-ok.yaml 被回滚、工作树干净
        assert not (sample_repo / "ontology" / "first-ok.yaml").exists()
        assert _git(sample_repo, "status", "--porcelain") == ""
        assert self._head(sample_repo) == base  # HEAD 未前进
        # failed 行留痕（详情面可见）
        detail = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/patches/{plan['patch_id']}",
            headers=_auth(af3_world["actor"], settings),
        )
        assert detail.status_code == 200
        assert detail.get_json()["data"]["status"] == "failed"

    def test_cross_tenant_404(self, client, af3_world, settings, binding_id) -> None:
        plan = _plan(
            [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
            base_commit="0" * 40,
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan, auth_user=af3_world["outsider"])
        assert resp.status_code == 404


def _plan_and_commit_dummy(client, af3_world, settings, binding_id: str, sample_repo: Path) -> None:
    """经 patch_apply 推进 HEAD（造 base mismatch 的前置状态）。"""
    plan = _plan(
        [{"path": "ontology/dummy.yaml", "operation": "create", "content": "dummy\n"}],
        base_commit=_git(sample_repo, "rev-parse", "HEAD"),
    )
    resp = _post_patch(client, af3_world, settings, binding_id, plan)
    assert resp.status_code == 201, resp.get_json()


# ---- ③ D3 grant 要素（04 §3.3 绑定五要素落机器面） -------------------------------


class TestGrant:
    def test_bind_with_grant_subset(self, client, af3_world, settings, sample_repo) -> None:
        binding_id = _bind(
            client, af3_world, settings, sample_repo,
            grant_json={"ops": ["status", "read_file"]},
        )
        detail = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}",
            headers=_auth(af3_world["actor"], settings),
        )
        assert detail.get_json()["data"]["grant_json"] == {"ops": ["status", "read_file"]}

    def test_grant_blocks_unlisted_op(self, client, af3_world, settings, sample_repo) -> None:
        """grant 白名单外的 agent 操作 → 403 tool_not_allowed（第二道闸之后的
        绑定级第三道闸）。"""
        binding_id = _bind(
            client, af3_world, settings, sample_repo,
            grant_json={"ops": ["status", "read_file"]},  # 不含 patch_apply
        )
        plan = _plan(
            [{"path": "ontology/x.yaml", "operation": "create", "content": "x\n"}],
            base_commit=_git(sample_repo, "rev-parse", "HEAD"),
        )
        resp = _post_patch(client, af3_world, settings, binding_id, plan)
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "tool_not_allowed"

    def test_grant_outside_agent_allowed_rejected_at_bind(self, client, af3_world, settings, sample_repo) -> None:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json={
                "repo_root": str(sample_repo),
                "workspace_root": str(sample_repo),
                "branch": f"af3/{uuid.uuid4().hex[:8]}",
                "allow_roots": ["ontology/"],
                "grant_json": {"ops": ["push"]},  # human_only 永不入 grant
            },
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"


# ---- ④ diff/log 读面（agent_allowed diff/log 落位） ------------------------------


class TestChangesAndCommits:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        return _bind(client, af3_world, settings, sample_repo)

    def test_changes_clean(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/changes",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["dirty"] is False

    def test_changes_reports_pending(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        (sample_repo / "ontology" / "pending.yaml").write_text("pending\n", encoding="utf-8")
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/changes",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dirty"] is True
        assert any("pending.yaml" in row for row in data["porcelain"])

    def test_commits_lists_apply_history(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        plan = _plan(
            [{"path": "ontology/hist.yaml", "operation": "create", "content": "h\n"}],
            base_commit=_git(sample_repo, "rev-parse", "HEAD"),
        )
        applied = _post_patch(client, af3_world, settings, binding_id, plan)
        assert applied.status_code == 201
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/commits",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        commits = resp.get_json()["data"]["commits"]
        assert any(plan["patch_id"] in line for line in commits)

    def test_changes_cross_tenant_404(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/changes",
            headers=_auth(af3_world["outsider"], settings),
        )
        assert resp.status_code == 404


# ---- ⑤ D1 TOCTOU 复核（read_file 打开后 realpath 校验） --------------------------


class TestReadFileTocTou:
    def test_realpath_escape_rejected(self, client, af3_world, settings, monkeypatch, sample_repo) -> None:
        """打开后 realpath 复核被 patch 成恒指仓外 → 422 symlink_escape_rejected——
        证明「打开后复核」代码路径真实生效（D1 清偿钉；真实竞态窗口单线程
        不可复现，复核逻辑把窗口缩到打开之后）。"""
        import os

        binding_id = _bind(client, af3_world, settings, sample_repo)
        orig_realpath = os.path.realpath

        def _escape(p, *a, **kw):  # noqa: ANN001
            s = str(p)
            if s.endswith("equipment.yaml"):
                # 只劫持目标文件的 realpath（root resolve 走原实现，防连坐）
                return "Z:/outside-escaped"
            return orig_realpath(p, *a, **kw)

        monkeypatch.setattr(os.path, "realpath", _escape)
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/equipment.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "symlink_escape_rejected"
