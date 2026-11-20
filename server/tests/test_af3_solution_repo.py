"""AF3-WP1：仓库绑定服务面＋离线本地 Git 读面＋分支面＋越权闭集（20 号 §3 WP1）。

绑定语义（04 §3.3）：每次工作区绑定 repo、基线 commit、分支、路径白名单与
执行 grant；**不进他人 dirty tree**（绑定时刻 porcelain 非空即 409）；
**离线本地 Git 先通**（GitRunner 受控 subprocess：固定 argv 构造、禁 shell、
超时、清 GIT_* 环境——防环境注入）。

D2 已批边界（机器可检）：Agent 面＝status/read_file/diff/log/branch_create
闭集；push/merge/受保护分支直写/hookspath 配置永不入 agent 面（human_only；
未知名 fail-closed 拒绝）。patch_apply 归 WP2 类型化 adapter 接线。

S-AF3 钉落位：S-AF3-08（dirty tree）＝TestBindRepo::test_dirty_tree_rejected；
S-AF3-10（push 诉求）＝TestGitBoundary＋TestRouteSurface（结构保证：无 push
端点）；越权面纯函数钉＝TestGitBoundary。
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from fde_api.auth.tokens import issue_access_token
from fde_api.solution_repo.git_boundary import resolve_op
from fde_api.solution_repo.snapshot import load_whitelist
from multi_tenant_harness import make_enterprise_org, make_user


@pytest.fixture(scope="module")
def whitelist_snapshot() -> dict:
    return load_whitelist()


@pytest.fixture(autouse=True)
def af3_repo_base(app, monkeypatch, tmp_path: Path) -> Path:
    """评审 G1：受控基目录围栏——本文件全部测试在显式 base 下运行（服务端
    SETTINGS.solution_repo_base 指向 tmp 子目录）；sample_repo 必须建在其下，
    否则绑定被围栏 422 拒（fail-closed 默认＝未配置即禁绑定）。"""
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
    """受控示例仓（离线本地 git）：建在受控基目录下（围栏内）＋allow_roots
    五目录＋一个可读产物＋初始提交。"""
    repo = af3_repo_base / "solutions"
    for d in ("ontology", "transforms", "rules", "tests", "config"):
        (repo / d).mkdir(parents=True)
    (repo / "ontology" / "equipment.yaml").write_text(
        "kind: ontology\nname: equipment\nversion: 1.0.0\n", encoding="utf-8"
    )
    (repo / "config" / "settings.json").write_text('{"a": 1}\n', encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "init")
    return repo


def _git(repo: Path, *args: str) -> str:
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


def _bind_payload(repo: Path, **overrides) -> dict:
    payload: dict = {
        "repo_root": str(repo),
        "workspace_root": str(repo),
        "branch": f"af3/{uuid.uuid4().hex[:8]}",
        "allow_roots": ["ontology/", "transforms/", "rules/", "tests/", "config/"],
    }
    payload.update(overrides)
    return payload


class TestBindRepo:
    def test_bind_success(self, client, af3_world, settings, sample_repo) -> None:
        payload = _bind_payload(sample_repo)  # 评审 G10：同一 payload 复用（等值断言不得自指失效）
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=payload,
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()["data"]
        assert data["status"] == "active"
        assert data["branch"] == payload["branch"]  # 响应分支＝请求分支（绑定核心语义真钉）
        assert len(data["base_commit"]) == 40
        assert data["allow_roots"] == ["ontology/", "transforms/", "rules/", "tests/", "config/"]

    def test_bind_rejects_repo_outside_base(self, client, af3_world, settings, tmp_path) -> None:
        """评审 G1：受控基目录外的仓 → 422（围栏 fail-closed）。"""
        outside = tmp_path / "outside-repo"
        outside.mkdir()
        (outside / "ontology").mkdir()
        _git(outside, "init")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(outside),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejected_when_base_unconfigured(self, client, af3_world, settings, app, monkeypatch, tmp_path) -> None:
        """评审 G1：solution_repo_base 未配置（空串）＝绑定面整体停用（fail-closed）。"""
        monkeypatch.setitem(
            app.config,
            "SETTINGS",
            app.config["SETTINGS"].model_copy(update={"solution_repo_base": ""}),
        )
        repo = tmp_path / "any-repo"
        repo.mkdir()
        (repo / "ontology").mkdir()
        _git(repo, "init")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_empty_repo(self, client, af3_world, settings, af3_repo_base) -> None:
        """评审 G5：零提交空仓 → 422（rev-parse HEAD 探测，非 500）。"""
        repo = af3_repo_base / "empty-repo"
        repo.mkdir()
        _git(repo, "init")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_non_git_repo(self, client, af3_world, settings, af3_repo_base) -> None:
        plain = af3_repo_base / "plain"
        plain.mkdir()
        (plain / "ontology").mkdir()
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(plain),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_dirty_tree_rejected(self, client, af3_world, settings, sample_repo) -> None:
        """S-AF3-08：不进他人 dirty tree——绑定时刻 porcelain 非空即 409。"""
        (sample_repo / "ontology" / "dirty.yaml").write_text("dirty\n", encoding="utf-8")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "dirty_tree_conflict"

    def test_bind_requires_branch_no_fabrication(self, client, af3_world, settings, sample_repo) -> None:
        """停点纪律（AF2① 携带）：branch 缺失 → 422，禁臆造参数继续。"""
        payload = _bind_payload(sample_repo)
        payload.pop("branch")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=payload,
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_existing_branch(self, client, af3_world, settings, sample_repo) -> None:
        _git(sample_repo, "branch", "af3/existing")
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, branch="af3/existing"),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_protected_allow_root(self, client, af3_world, settings, sample_repo) -> None:
        """allow_roots 声明含保护部件（.git）→ 422——白名单自身不得引入四拒路径。"""
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, allow_roots=["ontology/", ".git/hooks/"]),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_allow_root_outside_snapshot_set(self, client, af3_world, settings, sample_repo) -> None:
        """评审 G3：绑定声明超出快照封闭集（server/）→ 422——快照 allow_roots
        是 FROZEN 规则集而非死数据；扩集走白名单 v2＋决策单。"""
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, allow_roots=["ontology/", "server/"]),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_bind_rejects_missing_allow_root_dir(self, client, af3_world, settings, sample_repo) -> None:
        """评审 G11：allow_roots 目录不存在 → 422（防「绑定成功但读面全 422」死绑定）。"""
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, allow_roots=["ontology/", "rules/"]),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201  # rules/ 在仓内存在（对照组：成功）
        missing_repo = sample_repo.parent / "repo-missing-root"
        for d in ("ontology", "transforms", "tests", "config"):
            (missing_repo / d).mkdir(parents=True)
        (missing_repo / "ontology" / "placeholder.yaml").write_text("x\n", encoding="utf-8")
        _git(missing_repo, "init")
        _git(missing_repo, "add", ".")
        _git(missing_repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "init")
        resp2 = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(missing_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp2.status_code == 422
        assert resp2.get_json()["error"]["code"] == "validation_failed"
        assert "rules" in str(resp2.get_json()["error"]["details"])

    def test_bind_duplicate_conflict(self, client, af3_world, settings, sample_repo) -> None:
        payload = _bind_payload(sample_repo, branch="af3/dup-check")
        first = client.post(
            "/api/v1/solution-repo/bindings", json=payload, headers=_auth(af3_world["actor"], settings)
        )
        assert first.status_code == 201
        second = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, branch="af3/dup-check"),
            headers=_auth(af3_world["actor"], settings),
        )
        assert second.status_code == 409
        assert second.get_json()["error"]["code"] == "binding_exists"

    def test_bind_missing_repo_root(self, client, af3_world, settings) -> None:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(Path("/nonexistent/repo/path")),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422


class TestReadFile:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        return resp.get_json()["data"]["binding_id"]

    def test_read_allowed_file(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/equipment.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        assert "kind: ontology" in resp.get_json()["data"]["content"]

    def test_read_outside_allow_roots(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "README.md"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "outside_allow_roots"

    def test_read_protected_path(self, client, af3_world, settings, binding_id) -> None:
        """S-AF3-01：.git/** 读诉求 → 403（读取面同样四拒——读 .git/config 可泄露配置）。"""
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": ".git/config"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "protected_path_rejected"

    def test_read_traversal(self, client, af3_world, settings, binding_id) -> None:
        """S-AF3-04：穿越形态 → 422。"""
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/../../escape.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "path_escape_rejected"

    def test_read_symlink_escape(self, client, af3_world, settings, binding_id, sample_repo, tmp_path) -> None:
        """S-AF3-05：symlink 逃逸实探（Windows 无特权时 skip——CI ubuntu 实跑）。"""
        outside = tmp_path / "outside-secret.yaml"
        outside.write_text("secret", encoding="utf-8")
        try:
            (sample_repo / "ontology" / "evil.yaml").symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symlink 特权缺失（{exc}）——CI ubuntu-24.04 实跑")
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/evil.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "symlink_escape_rejected"

    def test_read_missing_file(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/absent.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_read_oversize_file_rejected(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        """评审 G9：读取上限负向钉（>1MB → 422，details 携 size/max_bytes）——
        上限分支此前零验证（vg 预验证：删判断全部测试照绿）。"""
        big = sample_repo / "ontology" / "large.yaml"
        big.write_text("x" * (1048576 + 1), encoding="utf-8")
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/large.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"
        details = resp.get_json()["error"]["details"] or {}
        assert details.get("max_bytes") == 1048576
        assert details.get("size") == 1048577

    def test_read_cross_tenant_404(self, client, af3_world, settings, binding_id) -> None:
        """跨租户 404 不泄露（沿 AE1 get_execution 同款纪律）。"""
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/equipment.yaml"},
            headers=_auth(af3_world["outsider"], settings),
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"


class TestStatusSurface:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        return resp.get_json()["data"]["binding_id"]

    def test_status_clean(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/status",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dirty"] is False
        assert data["porcelain"] == []

    def test_status_reports_dirty_after_change(self, client, af3_world, settings, binding_id, sample_repo) -> None:
        (sample_repo / "ontology" / "later.yaml").write_text("later\n", encoding="utf-8")
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/status",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["dirty"] is True
        assert any("later.yaml" in row for row in data["porcelain"])

    def test_status_cross_tenant_404(self, client, af3_world, settings, binding_id) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/status",
            headers=_auth(af3_world["outsider"], settings),
        )
        assert resp.status_code == 404


class TestListBindings:
    """评审 G8：列表端点租户隔离验证（vg 预验证——此前零覆盖，删 org 过滤
    全部测试照绿；载荷含 repo_root 服务器路径，跨租户泄露即路径情报泄露）。"""

    def test_list_scoped_to_own_org(self, client, af3_world, settings, sample_repo) -> None:
        payload = _bind_payload(sample_repo, branch="af3/list-a")
        first = client.post(
            "/api/v1/solution-repo/bindings", json=payload, headers=_auth(af3_world["actor"], settings)
        )
        assert first.status_code == 201
        listed = client.get("/api/v1/solution-repo/bindings", headers=_auth(af3_world["actor"], settings))
        assert listed.status_code == 200
        data = listed.get_json()["data"]
        ids = {row["binding_id"] for row in data["items"]}
        assert first.get_json()["data"]["binding_id"] in ids
        assert data["count"] == len(data["items"])
        assert data["limit"] == 100

    def test_list_cross_tenant_empty(self, client, af3_world, settings, sample_repo) -> None:
        """A 建绑定后，outsider（他租户）列表为空且不含 A 的 repo_root。"""
        created = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo, branch="af3/list-b"),
            headers=_auth(af3_world["actor"], settings),
        )
        assert created.status_code == 201
        listed = client.get("/api/v1/solution-repo/bindings", headers=_auth(af3_world["outsider"], settings))
        assert listed.status_code == 200
        data = listed.get_json()["data"]
        assert data["count"] == 0
        assert data["items"] == []


class TestBranchSurface:
    @pytest.fixture
    def binding_id(self, client, af3_world, settings, sample_repo) -> str:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        return resp.get_json()["data"]["binding_id"]

    def test_branch_create(self, client, af3_world, settings, binding_id) -> None:
        resp = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/branches",
            json={"name": "af3/feature-x"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["branch"] == "af3/feature-x"

    def test_branch_invalid_name(self, client, af3_world, settings, binding_id) -> None:
        for bad in ("../escape", "-evil", "af3//x", "", "a.", "af3/.hidden", "af3/x@{y", "x@"):
            resp = client.post(
                f"/api/v1/solution-repo/bindings/{binding_id}/branches",
                json={"name": bad},
                headers=_auth(af3_world["actor"], settings),
            )
            assert resp.status_code == 422, bad
            assert resp.get_json()["error"]["code"] == "validation_failed", bad

    def test_branch_duplicate(self, client, af3_world, settings, binding_id) -> None:
        payload = {"name": "af3/dup-branch"}
        first = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/branches",
            json=payload,
            headers=_auth(af3_world["actor"], settings),
        )
        assert first.status_code == 201
        second = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/branches",
            json=payload,
            headers=_auth(af3_world["actor"], settings),
        )
        assert second.status_code == 422


class TestGitBoundary:
    """D2 闭集纯函数钉：agent_allowed 全通过／human_only 全拒／未知名 fail-closed。"""

    def test_agent_allowed_ops_pass(self, whitelist_snapshot) -> None:
        allowed = whitelist_snapshot["git_ops"]["agent_allowed"]
        for op in allowed:
            verdict = resolve_op(op, whitelist=whitelist_snapshot)
            assert verdict.ok is True, op

    def test_human_only_ops_rejected(self, whitelist_snapshot) -> None:
        """S-AF3-10：push/merge/受保护分支直写/hookspath 诉求 → 403 面（tool_not_allowed）。"""
        for op in ("push", "merge", "branch_delete", "remote_config", "protected_branch_write", "hooks_path_config"):
            verdict = resolve_op(op, whitelist=whitelist_snapshot)
            assert verdict.ok is False, op
            assert verdict.code == "tool_not_allowed", op
        assert resolve_op("patch_apply", whitelist=whitelist_snapshot).ok is False

    def test_unknown_op_fails_closed(self, whitelist_snapshot) -> None:
        verdict = resolve_op("format_disk", whitelist=whitelist_snapshot)
        assert verdict.ok is False
        assert verdict.code == "tool_not_allowed"


class TestRouteSurface:
    def test_no_push_endpoint_in_blueprint(self, app) -> None:
        """结构保证：solution-repo 路由规则闭集——不存在 push/merge/远端配置端点
        （D2 human_only 面永不入 agent 面；结构级保证优于文档级）。"""
        rules = {
            r.rule
            for r in app.url_map.iter_rules()
            if r.rule.startswith("/api/v1/solution-repo")
        }
        assert rules == {
            "/api/v1/solution-repo/bindings",
            "/api/v1/solution-repo/bindings/<binding_id>",
            "/api/v1/solution-repo/bindings/<binding_id>/revoke",
            "/api/v1/solution-repo/bindings/<binding_id>/files",
            "/api/v1/solution-repo/bindings/<binding_id>/status",
            "/api/v1/solution-repo/bindings/<binding_id>/branches",
        }

    def test_revoke_then_read_forbidden(self, client, af3_world, settings, sample_repo) -> None:
        resp = client.post(
            "/api/v1/solution-repo/bindings",
            json=_bind_payload(sample_repo),
            headers=_auth(af3_world["actor"], settings),
        )
        binding_id = resp.get_json()["data"]["binding_id"]
        rv = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/revoke",
            headers=_auth(af3_world["actor"], settings),
        )
        assert rv.status_code == 200
        assert rv.get_json()["data"]["status"] == "revoked"
        # 撤权后读面 403（permission_revoked）——撤权即时生效（AF1② 撤权语义域内同构）。
        rr = client.get(
            f"/api/v1/solution-repo/bindings/{binding_id}/files",
            query_string={"path": "ontology/equipment.yaml"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert rr.status_code == 403
        assert rr.get_json()["error"]["code"] == "permission_revoked"
