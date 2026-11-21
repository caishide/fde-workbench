"""AE2-WP5 评测驱动钉：冻结复合任务集公开 2 任务 × 3 次独立运行 → 逐断言判定。

54 号 §3 WP5 / §5.2 出口条件机读锚（公开段）：
- 分母锚 ``expected_runs == 6``（公开 2×3；隐藏 3 运行在开箱后补录至 9——
  隐藏集 SEALED-PENDING，开箱前本钉只钉公开段）；
- 唯一任务数与运行次数分列（05:47）；
- 幂等率 100%（复放槽运行级一致）；
- 回滚零遗留（存在补偿过程的运行残留恒空）；
- 评分链只消费落盘记录（runner 产记录 → write_records → load_records → scorer）。
"""
from __future__ import annotations

from typing import Any

import _ae_mock_stack as mock_stack_module
import pytest
from ae_eval.ae2_runner import AE2_RUNS, load_public_tasks, provision_pinned_world, run_public_eval
from ae_eval.ae2_scorer import score_records
from ae_eval.records import load_records, write_records

TASKSET = str(load_public_tasks.__globals__["AE2_TASKSET_PATH"])  # 冻结件 byte 一致副本


@pytest.fixture(scope="module")
def mock_stack():
    """ephemeral 桩端口（跨 worker 与固定端口桩文件共存——沿 AE1 装置面）。"""
    stack = mock_stack_module.MockStack(erp_port=0, email_port=0)
    stack.start()
    yield stack
    stack.stop()


@pytest.fixture(scope="module")
def wb_service(test_settings):
    svc = mock_stack_module.WorkbenchService(test_settings)
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture(scope="module")
def wb_port(wb_service):
    return wb_service.port


class TestPublicEval:
    def test_public_composite_taskset_three_runs_full_report(
        self, db_session, test_settings, mock_stack, wb_service, wb_port, tmp_path
    ) -> None:
        """2 复合任务 × 3 独立运行 → 6 运行逐断言判定（评分链只消费落盘记录）。

        期望形态（计数锚）：唯一任务 2 / 运行 6 / 断言判定 87（T5-001 14×3＋
        T5-002 15×3——每运行记录只评本任务断言）/ 幂等复放检查 12（2 任务 ×
        replay2/replay3 × 3 轮）/ 回滚过程运行 3（仅 T5-002 有补偿过程）。
        """
        world = provision_pinned_world(db_session)
        records = run_public_eval(
            db_session=db_session,
            actor=world["user"],
            test_settings=test_settings,
            stack=mock_stack,
            wb_port=wb_port,
            runs=AE2_RUNS,
        )
        records_path = write_records(records, tmp_path / "ae2-records.jsonl")
        result = score_records(load_records(records_path), TASKSET, expected_runs=AE2_RUNS * 2)
        # 评测留痕（可选复核副本）：挂载目录存在才写——CI Linux runner 无此路径；
        # 权威证据面在仓内 docs/ai-fde/ae2/ 两件，此处缺失不构成证据丢失
        import json as _json
        from pathlib import Path as _Path

        _dump = _Path("C:/Users/P1/ae2-wp5-evidence")
        if _dump.parent.exists():
            _dump.mkdir(exist_ok=True)
            (_dump / "ae2-records.jsonl").write_bytes(records_path.read_bytes())
            (_dump / "ae2-result.json").write_text(_json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

        assert result["counts"]["unique_task_count"] == 2
        assert result["counts"]["run_count"] == 6
        assert result["counts"]["assertion_evaluations"] == 87
        assert "denominator_mismatch" not in result

        metrics = {metric["name"]: metric for metric in result["metrics"]}
        assert metrics["task_success_rate"]["numerator"] == 6
        assert metrics["task_success_rate"]["denominator"] == 6
        assert metrics["task_success_rate"]["rate"] == 1.0
        low, high = metrics["task_success_rate"]["wilson_95"]
        assert low < 1.0 <= high  # 小样本 Wilson 区间随报（05:66）

        assert metrics["idempotency_rate"]["numerator"] == 12
        assert metrics["idempotency_rate"]["denominator"] == 12
        assert metrics["idempotency_rate"]["rate"] == 1.0

        assert metrics["rollback_zero_residual_rate"]["denominator"] == 3  # 仅 T5-002 有补偿过程
        assert metrics["rollback_zero_residual_rate"]["numerator"] == 3
        assert metrics["rollback_zero_residual_rate"]["rate"] == 1.0

        assert result["failed_task_scores"] == []  # 公开集全绿

        # T5-002 失败注入腿逐条抽查（诚实失败态：审批闸拒绝＋fail-fast＋noop 补偿）
        t5_002 = [score for score in result["task_scores"] if score["task_id"] == "T5-002"]
        assert len(t5_002) == 3
        assert all(score["passed"] for score in t5_002)

    def test_denominator_anchor_mismatch_is_flagged(self, db_session, tmp_path) -> None:
        """分母锚机保护（沿 AE1 B-2）：落盘记录数 ≠ 预登记锚 → 顶层显著标注。"""
        from ae_eval.records import RunRecord

        record = RunRecord(task_id="T5-999", run_index=1, attempts={}, external_state={}, note="")
        path = write_records([record], tmp_path / "short.jsonl")
        result = score_records(load_records(path), TASKSET, expected_runs=9)
        assert result["denominator_mismatch"]["expected_runs"] == 9
        assert result["denominator_mismatch"]["actual_runs"] == 1

    def test_taskset_byte_copy_matches_docs_freeze(self) -> None:
        """冻结件双份 byte 一致（沿 AE1 纪律）：仓内副本 sha256 与 docs 仓冻结件一致。"""
        import hashlib
        from pathlib import Path

        local = Path(TASKSET).read_bytes()
        docs = Path("D:/test/Fde-Ontology/docs/ai-fde/_ae2-tasks-v1.json")
        if not docs.exists():  # CI 无 docs 仓挂载时跳过（锚随 PR 证据件落档）
            pytest.skip("docs 仓不在本机挂载路径")
        assert hashlib.sha256(local).hexdigest() == hashlib.sha256(docs.read_bytes()).hexdigest()
