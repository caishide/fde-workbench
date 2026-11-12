# -*- coding: utf-8 -*-
"""训练场 run 分布读数纯函数库（L 线 L2 轮，2026-11-12）。

**判定语义复用** ``scripts/diagnostic_eval/eval_lib.py`` 的分布原语
（``distribution_stats`` / ``noise_width`` / ``decidable_delta``——单一真身，
不复制实现；round16 方法论移植，设计稿 §2.2 推荐方案 A），只重登记本线
轴定义与规则号：

- 逐场景可比组三轴：``scenario_version × rubric_version × adapter_mode``
  （同轴重跑才是同位样本；组内按 ``scenario_key`` 各自成分布）；
- 锚点可比组两轴：``rubric_version × evaluator_version``（锚点输入固定
  ＋agent 配置固定 ⇒ 锚点 run 得分＝**纯评估侧噪声**，与被测能力无关；
  锚点可跨 run 合并、**不可跨轴合并**）；
- 判定规则 ``delta-noise-band-simulation-2026-11-12``（登记、留痕可推翻、
  **非校准阈值**）：Δ 可判定 ⇔ 参与两组样本数各 ≥3 ∧ |Δ| > 噪声带
  （参与分布的观测极差较大者，**严格大于**）；n 不足 ⇒ ``insufficient_data``
  （「还没资格判」≠「不可判定」）。

三条机械不变量在本文件机械执行（不靠文档自觉）：
① 失败/降级/缺评估的 run **不是 0 分、是无数据**（排除并如实计数）；
② score 缺失或 hard_fail 的评估行不进分布；
③ n<2 不编造 stdev（继承 ``distribution_stats``），n<min_runs ⇒ insufficient_data。

产物存放口径（沿 E-2 先例）：批跑 JSONL 与汇总落**真相层** ``--out-dir``；
仓库只存汇总＋指针＋sha256，零报告正文。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_DIAG_LIB = Path(__file__).resolve().parents[1] / "diagnostic_eval"
if str(_DIAG_LIB) not in sys.path:
    sys.path.insert(0, str(_DIAG_LIB))

import eval_lib  # noqa: E402  # 复用：分布原语单一真身（scripts 间复用，不进生产面）

RULE_ID = "delta-noise-band-simulation-2026-11-12"
MIN_DISTRIBUTION_RUNS = eval_lib.MIN_DISTRIBUTION_RUNS

# 评估层：L-A 确定性规则层 / L-B 模型层（分布读数按层分别进行，不混层）。
VALID_LAYERS = ("deterministic", "model")

SCENARIO_GROUP_KEYS = ("scenario_version", "rubric_version", "adapter_mode")
ANCHOR_GROUP_KEYS = ("rubric_version", "evaluator_version")

# 训练场 run 终态词表（server/src/fde_api/simulation/models.py::RUN_STATUSES）——
# 成功终态是 ``completed``（**没有** ``succeeded``）。写错词表 ⇒ 成功 run 被当失败，
# 分布读数全空（真机批跑撞出来的缺陷，已按服务端词表校正）。
RUN_STATUS_SUCCESS = "completed"

# 无分数的评估 verdict —— 这些行**不是 0 分，是无数据**：
# - hard_fail：硬性失败（终局判定，不是连续分数）
# - inconclusive：规则层「结论不可靠」（未核验占比过高）
# - unavailable：模型层未产分（provider 未配置 / 调用失败 / 输出不合契约）
NO_SCORE_VERDICTS = frozenset({"hard_fail", "inconclusive", "unavailable"})


def _axis(record: dict[str, Any], key: str) -> str:
    """取轴值（缺版本标签记空串——缺标签本身就是不可比信号）。"""
    evaluation = record.get("evaluation") or {}
    return str(record.get(key) or evaluation.get(key) or "")


def _layer_row(record: dict[str, Any], layer: str) -> dict[str, Any]:
    """取某层的评估行；同层多评估器（model:stub / model:server）取**所测层行**。

    记录里的 layers 按 ``evaluator_id`` 索引（同一 run 上 model:stub 与
    model:server 可并存，见服务端 evaluator.py 的分层落行）——故取层时按
    evaluator_id 定位，取不到再退回层名兜底。
    """
    evaluation = record.get("evaluation") or {}
    layers = evaluation.get("layers") or {}
    if not isinstance(layers, dict):
        return {}
    ids = evaluation.get("layer_evaluator_ids") or {}
    wanted = str(ids.get(layer) or "") if isinstance(ids, dict) else ""
    wanted = wanted or str(evaluation.get("layer_evaluator_id") or "")
    if wanted:
        row = layers.get(wanted)
        # 校验层标签——「所测层的评估器」不能串到别的层上去。
        if isinstance(row, dict) and (not row.get("layer") or row.get("layer") == layer):
            return row
    for row in layers.values():
        if isinstance(row, dict) and str(row.get("layer") or "") == layer:
            return row
    row = layers.get(layer)
    return row if isinstance(row, dict) else {}


def _layer_score(record: dict[str, Any], layer: str) -> float | None:
    """取某层分数；行缺失 / 无分数 verdict / 分数缺 ⇒ None（无数据）。"""
    row = _layer_row(record, layer)
    if not row:
        return None
    if str(row.get("verdict") or "") in NO_SCORE_VERDICTS:
        return None
    score = row.get("total_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    return float(score)


def _layer_axis(record: dict[str, Any], layer: str) -> tuple[str, str]:
    """取所测层的 (rubric_version, evaluator_version)——层感知轴。

    同一 run 上模型层可能同时存在 ``model:stub`` 与 ``model:server`` 两个
    评估器行；锚点组轴若只看顶层 evaluator_version，两者会被并进同一组，
    等于把两种评估器的分数混算成一条噪声带。
    """
    row = _layer_row(record, layer)
    rubric = str(row.get("rubric_version") or "")
    evaluator_id = str(row.get("evaluator_id") or "")
    if not rubric or not evaluator_id:
        evaluation = record.get("evaluation") or {}
        rubric = rubric or str(evaluation.get("rubric_version") or "")
        if not evaluator_id:
            evaluator_id = str(evaluation.get("evaluator_id") or "")
            if not evaluator_id:
                # 顶层 evaluator_version 形如 "rules@rubric-v1" ⇒ 取评估器段。
                evaluator_id = str(evaluation.get("evaluator_version") or "").split("@")[0]
    evaluator_version = f"{evaluator_id}@{rubric}" if evaluator_id or rubric else ""
    return rubric, evaluator_version


def collect_distributions(
    records: list[dict[str, Any]],
    *,
    anchor_keys: list[str] | tuple[str, ...] = (),
    layer: str = "model",
    min_runs: int = MIN_DISTRIBUTION_RUNS,
) -> dict[str, Any]:
    """把批跑 JSONL 记录聚合为逐场景分布与锚点分布（三条不变量在此执行）。

    ``records`` 是 ``run_batch.py`` 产出的记录行（一行一个 run）；锚点场景由
    ``anchor_keys`` 指名（输入固定＋配置固定的场景）。
    """
    if layer not in VALID_LAYERS:
        # fail-closed：未知评估层拒绝聚合（不静默回落 deterministic）。
        raise SystemExit(
            f"collect_distributions: 未知评估层 {layer!r}（合法取值 {VALID_LAYERS}）"
        )
    anchor_set = {str(key) for key in anchor_keys}
    scenario_groups: dict[str, dict[str, Any]] = {}
    anchor_groups: dict[str, dict[str, Any]] = {}
    excluded = {"failed_runs": 0, "score_rows": 0, "anchor_rows": 0}

    for record in records:
        scenario_key = str(record.get("scenario_key") or "")
        if not scenario_key:
            excluded["failed_runs"] += 1
            continue
        run_failed = (
            str(record.get("status") or "") != RUN_STATUS_SUCCESS
            or record.get("error")
            or bool(record.get("degraded"))
        )
        score = None if run_failed else _layer_score(record, layer)
        if run_failed:
            # 失败/降级 run 不是 0 分，是无数据（拿假 0 分进分布＝污染噪声带）。
            excluded["failed_runs"] += 1
        elif score is None:
            excluded["score_rows"] += 1
        if run_failed or score is None:
            continue

        rubric_version, evaluator_version = _layer_axis(record, layer)
        if scenario_key in anchor_set:
            group_key = "|".join([rubric_version, evaluator_version])
            group = anchor_groups.setdefault(group_key, {"runs": [], "scores": []})
            run_id = str(record.get("run_id") or "")
            if run_id and run_id not in group["runs"]:
                group["runs"].append(run_id)
            # 锚点取样：同一 fixed run 可反复评估（服务端重评＝更新同一行），
            # 每轮读数都是**一个**评估侧噪声样本 ⇒ 按记录追加，不按 run 去重。
            group["scores"].append(score)
        else:
            group_key = "|".join(
                [_axis(record, "scenario_version"), rubric_version, _axis(record, "adapter_mode")]
            )
            group = scenario_groups.setdefault(
                group_key, {"runs": [], "scenario_scores": {}}
            )
            run_id = str(record.get("run_id") or "")
            if run_id and run_id not in group["runs"]:
                group["runs"].append(run_id)
            group["scenario_scores"].setdefault(scenario_key, []).append(score)

    def _dist(values: list[float]) -> dict[str, Any]:
        return eval_lib.distribution_stats(values)

    return {
        "rule_id": RULE_ID,
        "layer": layer,
        "min_runs": min_runs,
        "excluded_rows": excluded,
        "scenario_groups": {
            key: {
                "runs": sorted(group["runs"]),
                "scenario_scores": {
                    name: _dist(values)
                    for name, values in sorted(group["scenario_scores"].items())
                },
            }
            for key, group in sorted(scenario_groups.items())
        },
        "anchor_groups": {
            key: {
                "runs": sorted(group["runs"]),
                "anchor_scores": {"anchor": _dist(group["scores"])},
            }
            for key, group in sorted(anchor_groups.items())
        },
    }


def decide_pair(
    delta: float,
    *dists: dict[str, Any],
    min_runs: int = MIN_DISTRIBUTION_RUNS,
) -> dict[str, Any]:
    """一组分数差的可判定性判定（复用 eval_lib 判定核心，重登记本线规则号）。"""
    verdict = eval_lib.decidable_delta(delta, *dists, min_runs=min_runs)
    verdict["rule_id"] = RULE_ID
    return verdict


def decide_against_anchor(
    summary: dict[str, Any],
    *,
    min_runs: int = MIN_DISTRIBUTION_RUNS,
) -> list[dict[str, Any]]:
    """逐场景分布 vs 锚点分布的两两判定（同轴组内逐场景 × 各锚点组）。

    语义同 round16：锚点分布＝纯评估侧噪声上界；逐场景分布＝生成+评估联合
    噪声。Δ 用均值差；噪声带＝参与分布的观测极差较大者。
    """
    verdicts: list[dict[str, Any]] = []
    anchor_groups = summary.get("anchor_groups") or {}
    scenario_groups = summary.get("scenario_groups") or {}
    for group_key, group in sorted(scenario_groups.items()):
        scenario_dists = group.get("scenario_scores") or {}
        for scenario_key, dist in sorted(scenario_dists.items()):
            delta_label = f"{scenario_key} vs anchor"
            if not anchor_groups:
                verdicts.append(
                    {
                        "rule_id": RULE_ID,
                        "pair": delta_label,
                        "decidable": None,
                        "reason": "no_anchor_distribution",
                        "n_list": [int(dist["n"])],
                        "noise_width": 0.0,
                        "abs_delta": None,
                    }
                )
                continue
            for anchor_key, anchor_group in sorted(anchor_groups.items()):
                anchor_dist = (anchor_group.get("anchor_scores") or {}).get("anchor")
                if anchor_dist is None:
                    continue
                delta = float(dist["mean"]) - float(anchor_dist["mean"])
                verdict = decide_pair(delta, dist, anchor_dist, min_runs=min_runs)
                verdict["pair"] = f"{scenario_key} vs anchor[{anchor_key}]"
                verdict["scenario_group"] = group_key
                verdicts.append(verdict)
    return verdicts


def render_summary_md(summary: dict[str, Any], verdicts: list[dict[str, Any]]) -> str:
    """渲染分布底册 markdown（仓库存汇总+指针；零报告正文零答案材料）。"""
    min_runs = int(summary.get("min_runs") or MIN_DISTRIBUTION_RUNS)
    layer = summary.get("layer") or "model"
    lines: list[str] = []
    lines.append("# 训练场·分数面分布（可判定性底册，L 线 L2）")
    lines.append("")
    lines.append(
        f"> **读数规则（`{summary.get('rule_id') or RULE_ID}`，非校准阈值）**："
        f"分数差 Δ 可判定 ⇔ 参与两组样本数各 ≥ {min_runs} ∧ |Δ| > 噪声带"
        "（参与分布的观测极差较大者，含锚点；**严格大于**）。锚点输入＋agent"
        "配置固定 ⇒ 锚点极差＝**纯评估侧噪声**；逐场景极差＝生成+评估联合噪声。"
        "n 不足 ⇒ insufficient_data（还没资格判）。通过线未校准前不判达标/不达标；"
        "单点分数差不构成能力结论。"
    )
    lines.append("")
    excluded = summary.get("excluded_rows") or {}
    lines.append(
        f"排除行（不是 0 分，是无数据）：failed_runs={excluded.get('failed_runs', 0)}"
        f" / score_rows={excluded.get('score_rows', 0)} / anchor_rows={excluded.get('anchor_rows', 0)}"
    )
    lines.append("")

    scenario_groups = summary.get("scenario_groups") or {}
    anchor_groups = summary.get("anchor_groups") or {}
    if not scenario_groups and not anchor_groups:
        lines.append("**尚无可用分布**（无可用 run）——insufficient_data。")
        return "\n".join(lines) + "\n"

    lines.append(f"## 锚点分布组（rubric × 评估器两轴——纯评估侧噪声，层={layer}）")
    lines.append("")
    for key, group in anchor_groups.items():
        dist = (group.get("anchor_scores") or {}).get("anchor") or {}
        runs = group.get("runs") or []
        n = int(dist.get("n", 0))
        readiness = "✅ 达最小样本" if n >= min_runs else f"⚠️ n<{min_runs}（insufficient_data）"
        lines.append(f"### 组 `{key}`（runs: {', '.join(runs) or '—'}）——{readiness}")
        lines.append("")
        if dist:
            lines.append(
                "| 对象 | n | 均值 | min | max | 极差 | stdev |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            stdev = dist.get("stdev")
            lines.append(
                "| anchor | {n} | {mean} | {mn} | {mx} | {rg} | {sd} |".format(
                    n=dist["n"], mean=dist["mean"], mn=dist["min"], mx=dist["max"],
                    rg=dist["range"], sd="—" if stdev is None else stdev,
                )
            )
        lines.append("")

    lines.append(f"## 逐场景分布组（scenario_version × rubric × adapter 三轴，层={layer}）")
    lines.append("")
    for key, group in scenario_groups.items():
        dists = group.get("scenario_scores") or {}
        runs = group.get("runs") or []
        sample_n = min((int(d["n"]) for d in dists.values()), default=0)
        readiness = "✅ 达最小样本" if sample_n >= min_runs else f"⚠️ n<{min_runs}（insufficient_data）"
        lines.append(f"### 组 `{key}`（runs: {', '.join(runs) or '—'}）——{readiness}")
        lines.append("")
        if dists:
            lines.append("| 场景 | n | 均值 | min | max | 极差 | stdev |")
            lines.append("|---|---|---|---|---|---|---|")
            for name, dist in dists.items():
                stdev = dist.get("stdev")
                lines.append(
                    "| {name} | {n} | {mean} | {mn} | {mx} | {rg} | {sd} |".format(
                        name=name, n=dist["n"], mean=dist["mean"], mn=dist["min"],
                        mx=dist["max"], rg=dist["range"],
                        sd="—" if stdev is None else stdev,
                    )
                )
        lines.append("")

    if verdicts:
        lines.append("## 逐场景 vs 锚点判定")
        lines.append("")
        lines.append("| 配对 | Δ | n | 噪声带 | 判定 |")
        lines.append("|---|---|---|---|---|")
        for verdict in verdicts:
            n_list = verdict.get("n_list") or []
            reason = verdict.get("reason") or ""
            decidable = verdict.get("decidable")
            label = (
                "insufficient_data"
                if decidable is None
                else ("decidable" if decidable else "within_noise")
            )
            lines.append(
                "| {pair} | {delta} | {n} | {w} | {label}{reason} |".format(
                    pair=verdict.get("pair"),
                    delta="—" if verdict.get("abs_delta") is None else round(verdict["abs_delta"], 1),
                    n="/".join(str(v) for v in n_list) or "—",
                    w=verdict.get("noise_width"),
                    label=label,
                    reason=f"（{reason}）" if reason and reason not in ("", "within_noise") else (f"（{reason}）" if reason else ""),
                )
            )
        lines.append("")
    return "\n".join(lines) + "\n"
