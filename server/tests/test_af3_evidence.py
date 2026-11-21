"""AF3-WP5：证据绑定与审计台账聚合＋故障恢复（20 号 §3 WP5；05 §5 AF3 行
「所有成功提案均绑定 commit/hash/真实 CI」＋AF1③ 证据自检「逐字引用自检」
＋AF2③ evidence_verbatim 溯源）。

- **evidence 聚合端点**：GET /bindings/<id>/evidence——一次取证包＝绑定快照
  ＋Patch 行（plan_sha256/applied_commit）＋CI runs（verdict/executed_checks
  摘要）＋corrections 轨迹＋审计 events（actor/at——D2 清偿承接）；
- **evidence_verbatim 逐字取证**：GET /bindings/<id>/evidence/file?path=…&
  commit=<sha>——按指定 commit 读取产物内容＋sha256（逐字对拍锚：提案引用
  的文件内容必须与该 commit 的 blob 逐字一致——AF2③ 溯源）；
- **审计台账聚合**：GET /bindings/<id>/audit——binding audit events（actor/
  at）＋patch/ci/correction 三类行计数与清单（WP5 结构化台账）；
- **故障恢复**：CI error run 复跑可恢复（verdict error→复跑 green）；
  correction failed 后换新 patch_id 重试可 corrected——两条恢复路径钉。
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


@pytest.fixture
def sample_repo(tmp_path: Path, af3_repo_base: Path) -> Path:
    repo = af3_repo_base / "solutions"
    for d in ("ontology", "transforms", "rules", "tests", "config"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    (repo / "ontology" / "equipment.yaml").write_text(
        "kind: ontology\nname: equipment\nversion: 1.0.0\n", encoding="utf-8"
    )
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Test", "commit", "-m", "init")
    return repo


@pytest.fixture
def af3_world(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    outsider = make_user(db_session, "project_lead", org_id=make_enterprise_org(db_session).id)
    db_session.commit()
    return {"org": org, "actor": actor, "outsider": outsider}


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _bind(client, af3_world, settings, sample_repo) -> str:
    resp = client.post(
        "/api/v1/solution-repo/bindings",
        json={
            "repo_root": str(sample_repo),
            "workspace_root": str(sample_repo),
            "branch": f"af3/{uuid.uuid4().hex[:8]}",
            "allow_roots": ["ontology/", "transforms/", "rules/", "tests/", "config/"],
        },
        headers=_auth(af3_world["actor"], settings),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["binding_id"]


def _apply(client, af3_world, settings, binding_id: str, sample_repo: Path, name: str) -> dict:
    plan = {
        "patch_id": "af3-patch-" + uuid.uuid4().hex[:8],
        "base_commit": _git(sample_repo, "rev-parse", "HEAD"),
        "entries": [
            {"path": f"ontology/{name}.yaml", "operation": "create", "content": f"kind: ontology\nname: {name}\n"}
        ],
    }
    resp = client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/patches",
        json=plan,
        headers=_auth(af3_world["actor"], settings),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


@pytest.fixture
def applied(client, af3_world, settings, sample_repo) -> dict:
    binding_id = _bind(client, af3_world, settings, sample_repo)
    patch = _apply(client, af3_world, settings, binding_id, sample_repo, "applied")
    return {"binding_id": binding_id, "patch": patch}


# ---- ① evidence 聚合端点（成功提案绑定 commit/hash/真实 CI） -----------------------


class TestEvidenceBundle:

    def test_evidence_bundle_aggregates(self, client, af3_world, settings, applied) -> None:
        """一次取证包＝绑定快照＋Patch 行＋CI runs＋corrections＋审计 events。"""
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        ev = resp.get_json()["data"]
        assert ev["binding"]["binding_id"] == applied["binding_id"]
        assert ev["binding"]["base_commit"] == applied["patch"]["base_commit"]
        patch_ids = [p["patch_id"] for p in ev["patches"]]
        assert applied["patch"]["patch_id"] in patch_ids
        patch_row = next(p for p in ev["patches"] if p["patch_id"] == applied["patch"]["patch_id"])
        # 成功提案绑定 commit/hash：applied_commit＋plan_sha256 在证据包内
        assert patch_row["applied_commit"] == applied["patch"]["applied_commit"]
        assert patch_row["plan_sha256"] == applied["patch"]["plan_sha256"]
        assert ev["ci_runs"] == []  # 未跑 CI 时如实空集
        assert ev["corrections"] == []
        assert ev["audit_events"], "审计 events（actor/at）必须在证据包内"

    def test_evidence_binds_real_ci_after_run(self, client, af3_world, settings, applied) -> None:
        """「绑定真实 CI」：patch 应用后跑 unit_test → CI run（head_commit＝
        applied_commit）进入证据包——commit/hash/真实 CI 三绑定齐。"""
        run = client.post(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/ci/runs",
            json={"bundle_id": "unit_test"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert run.status_code == 201
        ci = run.get_json()["data"]
        assert ci["head_commit"] == applied["patch"]["applied_commit"]
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence",
            headers=_auth(af3_world["actor"], settings),
        )
        ev = resp.get_json()["data"]
        assert len(ev["ci_runs"]) == 1
        assert ev["ci_runs"][0]["head_commit"] == applied["patch"]["applied_commit"]
        assert ev["ci_runs"][0]["verdict"] in ("green", "red", "error")

    def test_evidence_cross_tenant_404(self, client, af3_world, settings, applied) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence",
            headers=_auth(af3_world["outsider"], settings),
        )
        assert resp.status_code == 404


# ---- ② evidence_verbatim 逐字取证（AF2③ 溯源） ------------------------------------


class TestEvidenceVerbatim:
    def test_verbatim_file_content_and_sha(self, client, af3_world, settings, applied, sample_repo) -> None:
        """按 commit 逐字取证：内容与 sha256＝提案引用文件的 git blob 对拍锚。"""
        commit = applied["patch"]["applied_commit"]
        rel = "ontology/applied.yaml"
        expected_sha = _git(sample_repo, "rev-parse", f"{commit}:{rel}")
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence/file",
            query_string={"path": rel, "commit": commit},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()["data"]
        assert data["sha256"] == expected_sha
        assert "name: applied" in data["content"]

    def test_verbatim_unknown_commit_rejected(self, client, af3_world, settings, applied) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence/file",
            query_string={"path": "ontology/equipment.yaml", "commit": "0" * 40},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "not_found"

    def test_verbatim_bad_sha_format_rejected(self, client, af3_world, settings, applied) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence/file",
            query_string={"path": "ontology/equipment.yaml", "commit": "HEAD"},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "validation_failed"

    def test_verbatim_protected_path_rejected(self, client, af3_world, settings, applied) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/evidence/file",
            query_string={"path": ".git/config", "commit": "1" * 40},
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "protected_path_rejected"


# ---- ③ 审计台账聚合（D2 承接） ----------------------------------------------------


class TestAuditLedger:
    def test_audit_ledger_aggregates(self, client, af3_world, settings, applied) -> None:
        resp = client.get(
            f"/api/v1/solution-repo/bindings/{applied['binding_id']}/audit",
            headers=_auth(af3_world["actor"], settings),
        )
        assert resp.status_code == 200
        ledger = resp.get_json()["data"]
        assert ledger["binding_events"], "binding audit events（actor/at）"
        ev = ledger["binding_events"][0]
        assert ev["actor_id"] and ev["at"]
        counts = ledger["row_counts"]
        assert counts["patches"] == 1
        assert counts["ci_runs"] == 0
        assert counts["corrections"] == 0


# ---- ④ 故障恢复（error 复跑／failed 换 id 重试） ----------------------------------




# ---- ④ 故障恢复（error 复跑／failed 换 id 重试） ----------------------------------


class TestRecovery:
    def test_ci_red_then_recover_green(self, client, af3_world, settings, sample_repo) -> None:
        """CI red→修复→复跑 green（verdict 可随工作树修复翻转——恢复语义钉）。"""
        binding_id = _bind(client, af3_world, settings, sample_repo)
        result = _run_and_fix(client, af3_world, settings, binding_id, sample_repo)
        assert result["first_verdict"] == "red"
        assert result["recovered_verdict"] == "green"

    def test_correction_failed_then_new_patch_id_corrected(self, client, af3_world, settings, sample_repo) -> None:
        """correction failed（patch 应用执行失败）→ 换新 patch_id 重试 →
        corrected——故障恢复第二路径（H4 前置语义的恢复出口）。"""
        import unittest.mock as mock

        from fde_api.solution_repo.git_ops import GitFailed, GitRunner

        binding_id = _bind(client, af3_world, settings, sample_repo)
        # 先造真实失败源（red 锚——evidence 版种子仓初跑 lint 是 green）
        (sample_repo / "ontology" / "broken-seed.yaml").write_text("kind: [unclosed\n", encoding="utf-8")
        _git(sample_repo, "add", ".")
        _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "broken")
        # 第一条轨迹：commit 失败 → failed
        orig_run = GitRunner.run

        def _fail_commit(self, *args, **kwargs):
            if args and args[0] == "commit":
                raise GitFailed(" ".join(args), 128, "simulated")
            return orig_run(self, *args, **kwargs)

        with mock.patch.object(GitRunner, "run", _fail_commit):
            r1 = client.post(
                f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
                json={
                    "failed_run_id": _make_red_run(client, af3_world, settings, binding_id),
                    "bundle_id": "lint",
                    "patches": [
                        {
                            "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
                            "base_commit": _git(sample_repo, "rev-parse", "HEAD"),
                            "entries": [{"path": "ontology/f1.yaml", "operation": "create", "content": "x\n"}],
                        }
                    ],
                },
                headers=_auth(af3_world["actor"], settings),
            )
            assert r1.status_code == 201
            assert r1.get_json()["data"]["status"] == "failed"
        # 恢复：换新 patch_id（修 broken-seed）→ corrected
        recovered = client.post(
            f"/api/v1/solution-repo/bindings/{binding_id}/corrections",
            json={
                "failed_run_id": _make_red_run(client, af3_world, settings, binding_id),
                "bundle_id": "lint",
                "patches": [
                    {
                        "patch_id": "af3-fix-" + uuid.uuid4().hex[:8],
                        "base_commit": _git(sample_repo, "rev-parse", "HEAD"),
                        "entries": [
                            {"path": "ontology/broken-seed.yaml", "operation": "update", "content": "kind: ontology\n"}
                        ],
                    }
                ],
            },
            headers=_auth(af3_world["actor"], settings),
        )
        assert recovered.status_code == 201
        data = recovered.get_json()["data"]
        assert data["status"] == "corrected"
        assert _git(sample_repo, "status", "--porcelain") == ""


def _make_red_run(client, af3_world, settings, binding_id: str) -> str:
    resp = client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
        json={"bundle_id": "lint"},
        headers=_auth(af3_world["actor"], settings),
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["verdict"] == "red"
    return data["run_id"]


def _run_and_fix(client, af3_world, settings, binding_id: str, sample_repo: Path) -> dict:
    """先 red（坏 YAML）→ 修复 → 复跑 green（verdict 可随工作树修复翻转）。"""
    (sample_repo / "ontology" / "recover.yaml").write_text("kind: [unclosed\n", encoding="utf-8")
    _git(sample_repo, "add", ".")
    _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "broken")
    first = client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
        json={"bundle_id": "lint"},
        headers=_auth(af3_world["actor"], settings),
    )
    first_verdict = first.get_json()["data"]["verdict"]
    (sample_repo / "ontology" / "recover.yaml").write_text("kind: ontology\n", encoding="utf-8")
    _git(sample_repo, "add", ".")
    _git(sample_repo, "-c", "user.email=af3@test.local", "-c", "user.name=T", "commit", "-m", "fix")
    second = client.post(
        f"/api/v1/solution-repo/bindings/{binding_id}/ci/runs",
        json={"bundle_id": "lint"},
        headers=_auth(af3_world["actor"], settings),
    )
    return {"first_verdict": first_verdict, "recovered_verdict": second.get_json()["data"]["verdict"]}
