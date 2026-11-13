# -*- coding: utf-8 -*-
"""训练场批跑器测试（L 线 L2 轮；脚本层位于 scripts/，经 importlib 直载）。

钉住批跑器与**服务端真实语义**对齐的四件事（本轮真机批跑撞出来的）：

① **状态词表**：服务端 ``models.py::RUN_STATUSES`` 的成功终态是 ``completed``
   （**没有** ``succeeded``）——批跑器写错词表 ⇒ 成功 run 当失败、评估永不触发。
② **锚点取样机制**：服务端 ``retry_run`` 只允许 failed/timeout/cancelled 的 run
   重试，completed 的 run 一律 409 ⇒ 锚点必须走「同一个 fixed run 反复 evaluate」。
③ **层行按 evaluator_id 索引**：同一 run 上模型层可同时存在 ``model:stub`` 与
   ``model:server`` 两行（服务端按评估器分行落库），按层名索引会让后写的覆盖
   先写的 ⇒ 两种评估器的分数互相污染。
④ **API 前缀**：模拟域蓝图前缀是 ``/api/v1/simulation``，主机根缺前缀即 404。

本文件**零真实案例材料**——全部用合成响应（批跑正文与判卷基准只存在于真相层，
仓库侧只有分数与轴值；设计稿 §2.2）。
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "simulation"
    / "run_batch.py"
)
_spec = importlib.util.spec_from_file_location("simulation_run_batch", _SCRIPT)
assert _spec is not None and _spec.loader is not None
run_batch = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("simulation_run_batch", run_batch)
_spec.loader.exec_module(run_batch)

_SERVER_MODELS = (
    Path(__file__).resolve().parents[1] / "src" / "fde_api" / "simulation" / "models.py"
)


# ---------------------------------------------------------------------------
# ① 状态词表（与服务端真值对齐）
# ---------------------------------------------------------------------------


def test_run_status_success_matches_server_truth():
    """批跑器的成功终态词必须与服务端 ``RUN_STATUSES`` 一致。

    服务端真值取自源码（不复制一份常量到测试里）——服务端改词表时本钉先红。
    """
    source = _SERVER_MODELS.read_text(encoding="utf-8")
    match = re.search(r"RUN_STATUSES\s*=\s*\(([^)]*)\)", source, re.S)
    assert match, "服务端 RUN_STATUSES 未找到"
    statuses = {item.strip().strip('"\'') for item in match.group(1).split(",") if item.strip()}
    assert "completed" in statuses
    assert "succeeded" not in statuses
    assert run_batch.RUN_STATUS_SUCCESS == "completed"


# ---------------------------------------------------------------------------
# ④ API 前缀归一
# ---------------------------------------------------------------------------


def test_api_base_normalises_prefix_and_is_idempotent():
    assert run_batch._api_base("http://127.0.0.1:8010") == "http://127.0.0.1:8010/api/v1"
    assert run_batch._api_base("http://127.0.0.1:8010/") == "http://127.0.0.1:8010/api/v1"
    # 幂等：已带前缀者原样保留。
    assert run_batch._api_base("http://127.0.0.1:8010/api/v1") == "http://127.0.0.1:8010/api/v1"
    assert run_batch._api_base("http://127.0.0.1:8010/api/v1/") == "http://127.0.0.1:8010/api/v1"


def test_refuse_inside_repo():
    repo = Path(run_batch._REPO_ROOT).resolve()
    with pytest.raises(SystemExit):
        run_batch._refuse_inside_repo(repo / "scripts" / "simulation" / "out")


# ---------------------------------------------------------------------------
# ③ 层行按 evaluator_id 索引（model:stub 与 model:server 并存不互相覆盖）
# ---------------------------------------------------------------------------


def _report_with_two_model_evaluators() -> dict:
    return {
        "layers": [
            {
                "layer": "deterministic",
                "evaluator_id": "rules",
                "total_score": 0.849,
                "verdict": "pass",
                "rubric_version": "rubric-v1",
            },
            {
                "layer": "model",
                "evaluator_id": "model:stub",
                "total_score": 0.5,
                "verdict": "fail",
                "rubric_version": "rubric-v1",
            },
            {
                "layer": "model",
                "evaluator_id": "model:server",
                "total_score": 0.72,
                "verdict": "pass",
                "rubric_version": "rubric-v1",
            },
        ]
    }


def test_normalize_report_keys_layers_by_evaluator_id():
    out = run_batch._normalize_report(_report_with_two_model_evaluators(), "server")
    # 三行全在，按 evaluator_id 索引 ⇒ 两行模型层互不覆盖。
    assert set(out["layers"]) == {"rules", "model:stub", "model:server"}
    assert out["layers"]["model:stub"]["total_score"] == 0.5
    assert out["layers"]["model:server"]["total_score"] == 0.72


def test_normalize_report_picks_requested_model_mode():
    report = _report_with_two_model_evaluators()
    server = run_batch._normalize_report(report, "server")
    stub = run_batch._normalize_report(report, "stub")
    assert server["layer_evaluator_id"] == "model:server"
    assert server["layers"]["model:server"]["total_score"] == 0.72
    assert stub["layer_evaluator_id"] == "model:stub"
    assert stub["layers"]["model:stub"]["total_score"] == 0.5
    assert server["rubric_version"] == "rubric-v1"
    assert server["evaluator_version"] == "model:server@rubric-v1"


def test_normalize_report_deterministic_layer_uses_rules_evaluator():
    out = run_batch._normalize_report(_report_with_two_model_evaluators(), "server", "deterministic")
    assert out["layer_evaluator_id"] == "rules"
    assert out["evaluator_version"] == "rules@rubric-v1"


# ---------------------------------------------------------------------------
# ② 锚点取样：同一 fixed run 反复 evaluate N 轮
# ---------------------------------------------------------------------------


def _fake_run(run_id: str, seed: int) -> dict:
    return {
        "id": run_id,
        "run_key": f"SC-A:normal:v2:seed{seed}:a1:cfg0",
        "status": run_batch.RUN_STATUS_SUCCESS,
        "seed": seed,
        "attempt": 1,
        "split": "train",
        "adapter_mode": "mock",
        "error": None,
    }


def _fake_report() -> dict:
    return {
        "layers": [
            {
                "layer": "model",
                "evaluator_id": "model:server",
                "total_score": 0.72,
                "verdict": "pass",
                "rubric_version": "rubric-v1",
            }
        ]
    }


def _run_cli(tmp_dir: Path, *extra: str) -> int:
    argv = [
        "run_batch.py",
        "--scenario",
        "SC-A",
        "--token-file",
        str(tmp_dir / "token.txt"),
        "--out-dir",
        str(tmp_dir / "out"),
        *extra,
    ]
    (tmp_dir / "token.txt").write_text("fake-token", encoding="utf-8")
    with mock.patch.object(sys, "argv", argv):
        return run_batch.main()


def test_anchor_evaluates_same_run_repeatedly(tmp_path):
    """锚点：只建**一个** run，随后对同一 run 反复 evaluate N 轮。

    服务端 retry 对 completed 的 run 一律 409 ⇒ 走「反复 evaluate 同一 run」。
    """
    created: list[dict] = []
    evaluated: list[str] = []

    def fake_run_once(base, token, scenario, *, adapter, seed):
        created.append({"scenario": scenario, "adapter": adapter, "seed": seed})
        return _fake_run("run-fixed", seed)

    def fake_evaluate(base, token, run_id, model_mode):
        evaluated.append(run_id)

    with mock.patch.object(run_batch, "_resolve_active_scenario", return_value={
        "id": "sc-1",
        "scenario_key": "SC-A",
        "version": 2,
        "split": "train",
    }), mock.patch.object(run_batch, "_run_once", side_effect=fake_run_once), mock.patch.object(
        run_batch, "_evaluate", side_effect=fake_evaluate
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        _run_cli(tmp_path, "--anchor", "SC-A", "--runs-per-scenario", "3", "--model-mode", "server")

    # 只建一个 run（固定输入＋固定 agent 配置）。
    assert len(created) == 1
    assert created[0]["seed"] == 42
    # 同一 run 反复评估三轮 ⇒ 三个评估侧噪声样本。
    assert evaluated == ["run-fixed", "run-fixed", "run-fixed"]

    lines = [
        json.loads(line)
        for line in (tmp_path / "out" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["eval_round"] for row in lines] == [1, 2, 3]
    assert {row["run_id"] for row in lines} == {"run-fixed"}
    assert all(row["status"] == run_batch.RUN_STATUS_SUCCESS for row in lines)
    assert all(row["evaluation"]["layer_evaluator_id"] == "model:server" for row in lines)
    assert all(row["evaluation"]["layers"]["model:server"]["total_score"] == 0.72 for row in lines)


def test_non_anchor_creates_distinct_runs_per_seed(tmp_path):
    """逐场景：换 seed 换产物（mock 适配器按 seed 取样）⇒ 读生成侧方差。"""
    created: list[int] = []

    def fake_run_once(base, token, scenario, *, adapter, seed):
        created.append(seed)
        return _fake_run(f"run-{seed}", seed)

    with mock.patch.object(run_batch, "_resolve_active_scenario", return_value={
        "id": "sc-1",
        "scenario_key": "SC-A",
        "version": 2,
        "split": "train",
    }), mock.patch.object(run_batch, "_run_once", side_effect=fake_run_once), mock.patch.object(
        run_batch, "_evaluate", return_value=None
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        _run_cli(tmp_path, "--runs-per-scenario", "3", "--model-mode", "server")

    assert created == [42, 43, 44]
    lines = [
        json.loads(line)
        for line in (tmp_path / "out" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["run_id"] for row in lines] == ["run-42", "run-43", "run-44"]
    assert [row["eval_round"] for row in lines] == [1, 1, 1]


def test_non_success_status_is_not_evaluated(tmp_path):
    """非成功终态（failed/timeout/cancelled）不触发评估 ⇒ 该 run 是无数据。"""
    evaluated: list[str] = []

    with mock.patch.object(run_batch, "_resolve_active_scenario", return_value={
        "id": "sc-1",
        "scenario_key": "SC-A",
        "version": 2,
        "split": "train",
    }), mock.patch.object(run_batch, "_run_once", return_value={
        "id": "run-failed",
        "run_key": "SC-A:normal:v2:seed42:a1:cfg0",
        "status": "failed",
        "seed": 42,
        "attempt": 1,
        "split": "train",
        "adapter_mode": "mock",
        "error": {"code": "adapter_unavailable"},
    }), mock.patch.object(
        run_batch, "_evaluate", side_effect=lambda base, token, run_id, model_mode: evaluated.append(run_id)
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        _run_cli(tmp_path, "--runs-per-scenario", "1", "--model-mode", "server")

    assert evaluated == []
    lines = [
        json.loads(line)
        for line in (tmp_path / "out" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines[0]["status"] == "failed"
    assert lines[0]["evaluation"]["layers"] == {}


def test_anchor_must_be_subset_of_scenario(tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(tmp_path, "--anchor", "SC-B", "--runs-per-scenario", "1")


# ---------------------------------------------------------------------------
# ③ 节流旗标：--call-interval-seconds（缺省 0.2＝既有行为零变化）
# ---------------------------------------------------------------------------


def _run_cli_capture_sleep(tmp_dir: Path, sleeps: list[float], *extra: str) -> int:
    with mock.patch.object(run_batch.time, "sleep", side_effect=sleeps.append), mock.patch.object(
        run_batch, "_resolve_active_scenario", return_value={
            "id": "sc-1",
            "scenario_key": "SC-A",
            "version": 2,
            "split": "train",
        }
    ), mock.patch.object(run_batch, "_run_once", return_value=_fake_run("run-fixed", 42)), mock.patch.object(
        run_batch, "_evaluate", return_value=None
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        return _run_cli(tmp_dir, "--anchor", "SC-A", "--model-mode", "server", *extra)


def test_call_interval_default_preserves_legacy_spacing(tmp_path):
    """缺省 0.2s＝登记改进位之前的固定间隔，零行为变化。"""
    sleeps: list[float] = []
    assert _run_cli_capture_sleep(tmp_path, sleeps, "--runs-per-scenario", "3") == 0
    assert sleeps == [0.2, 0.2, 0.2]


def test_call_interval_flag_feeds_sleep_spacing(tmp_path):
    """对限流敏感的 provider 加大间隔：旗标值逐轮透传给 sleep。"""
    sleeps: list[float] = []
    assert _run_cli_capture_sleep(tmp_path, sleeps, "--runs-per-scenario", "3", "--call-interval-seconds", "1.5") == 0
    assert sleeps == [1.5, 1.5, 1.5]


def test_call_interval_rejects_negative(tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(tmp_path, "--runs-per-scenario", "1", "--call-interval-seconds", "-1")


def test_idempotent_resume_skips_registered_rounds(tmp_path):
    """重跑同一命令不重复取样：幂等键＝(场景, run, 评估轮次)。"""
    calls = {"n": 0}

    def fake_run_once(base, token, scenario, *, adapter, seed):
        calls["n"] += 1
        return _fake_run("run-fixed", seed)

    with mock.patch.object(run_batch, "_resolve_active_scenario", return_value={
        "id": "sc-1",
        "scenario_key": "SC-A",
        "version": 2,
        "split": "train",
    }), mock.patch.object(run_batch, "_run_once", side_effect=fake_run_once), mock.patch.object(
        run_batch, "_evaluate", return_value=None
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        _run_cli(tmp_path, "--anchor", "SC-A", "--runs-per-scenario", "2", "--model-mode", "server")
        _run_cli(tmp_path, "--anchor", "SC-A", "--runs-per-scenario", "2", "--model-mode", "server")

    lines = [
        json.loads(line)
        for line in (tmp_path / "out" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2
    assert [row["eval_round"] for row in lines] == [1, 2]


def test_manifest_records_runbook_fingerprint(tmp_path):
    with mock.patch.object(run_batch, "_resolve_active_scenario", return_value={
        "id": "sc-1",
        "scenario_key": "SC-A",
        "version": 2,
        "split": "train",
    }), mock.patch.object(run_batch, "_run_once", side_effect=lambda base, token, scenario, *, adapter, seed: _fake_run("run-1", seed)), mock.patch.object(
        run_batch, "_evaluate", return_value=None
    ), mock.patch.object(run_batch, "_evaluation_report", return_value=_fake_report()):
        _run_cli(tmp_path, "--runs-per-scenario", "1", "--model-mode", "server")

    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 1
    assert manifest["scenarios"] == ["SC-A"]
    assert manifest["model_mode"] == "server"
    assert manifest["runs_sha256"]
    assert manifest["runs_file"] == "runs.jsonl"


def test_out_dir_inside_repo_is_refused(tmp_path):
    repo = Path(run_batch._REPO_ROOT).resolve()
    with pytest.raises(SystemExit):
        run_batch._refuse_inside_repo(repo)


def test_temp_dir_is_outside_repo():
    """真相层输出目录在仓外（守卫按本仓根路径比，不是按「祖先链有 .git」）。"""
    with tempfile.TemporaryDirectory() as tmp:
        assert not str(Path(tmp).resolve()).startswith(str(Path(run_batch._REPO_ROOT).resolve()))


def test_resolve_active_scenario_queries_effective_versions_not_stale_history():
    calls: list[str] = []

    def fake_http(method, url, *, token, body=None):
        calls.append(url)
        return 200, {
            "data": {
                "items": [
                    {
                        "id": "sc-vague",
                        "scenario_key": "SC-A",
                        "variant": "vague",
                        "version": 3,
                        "status": "active",
                    },
                    {
                        "id": "sc-normal",
                        "scenario_key": "SC-A",
                        "variant": "normal",
                        "version": 5,
                        "status": "active",
                    },
                ]
            }
        }

    with mock.patch.object(run_batch, "_http", side_effect=fake_http):
        picked = run_batch._resolve_active_scenario("http://127.0.0.1:8010/api/v1", "tok", "SC-A")

    assert len(calls) == 1
    assert "include_history=true" not in calls[0]
    assert "q=SC-A" in calls[0]
    assert picked["id"] == "sc-normal"
    assert picked["version"] == 5


def test_resolve_active_scenario_fails_when_effective_version_is_draft():
    def fake_http(method, url, *, token, body=None):
        return 200, {
            "data": {
                "items": [
                    {
                        "id": "sc-draft",
                        "scenario_key": "SC-DRAFT",
                        "variant": "normal",
                        "version": 3,
                        "status": "draft",
                    }
                ]
            }
        }

    with mock.patch.object(run_batch, "_http", side_effect=fake_http):
        with pytest.raises(SystemExit):
            run_batch._resolve_active_scenario("http://127.0.0.1:8010/api/v1", "tok", "SC-DRAFT")
