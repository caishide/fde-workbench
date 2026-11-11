"""诊断评测批跑 · 纯函数库（获客诊断工具任务书 T-07/T-08/T-09，2026-11-11）。

**分层纪律（评测集污染隔离）**：本模块属于**评测器侧**——仓库 ``scripts/``
不在生成器可见面（``server/src``）的扫描范围内，因此它*被允许*知道答案素材
的存储形状（装配评分对照材料是评测器的本职）；生成器可见面（``diagnostics/``）
保持零答案材料，由 ``server/tests/test_diagnostic_eval_contamination.py`` 的
N1–N7 静态钉机械钉死、零豁免。两侧的分界线就本模块的位置本身。

**产物存放口径（E-2）**：报告原件、评分明细、元验证夹具全量落**真相层**
``eval-runs/<run_id>/``；仓库只存汇总 + 指针 + sha256（T-09 曲线文档）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# 真相层根（与 fixtures 同步脚本同一个环境变量——一层配置两层用）
TRUTH_ROOT_ENV = "FDE_DIAG_EVAL_TRUTH_ROOT"
TRUTH_ROOT_DEFAULT = Path(r"D:\test\FDE\knowledge\诊断案例集")

RUNS_DIRNAME = "eval-runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# 答案素材字段 → 评分对照材料的小节标题（**只在本层出现**的形状知识）
_REFERENCE_SECTIONS: tuple[tuple[str, str, bool], ...] = (
    # (卡片字段名, 材料小节标题, 是否列表)
    ("problems_expected", "关键问题清单（评分对照基准；前三条界定关键问题）", True),
    ("solution_direction", "参考方案方向（判方向不判措辞）", False),
    ("result", "结果口径（案例披露的业务结果）", False),
    ("human_boundary", "人机边界要点（人机责任边界）", False),
    ("fde_actions_expected", "交付动作参考", True),
    ("must_not_hallucinate", "禁编造清单（报告出现下列约束/系统/数字而无来源即编造）", True),
)

# 元验证夹具锚点 → 参考案例卡（锚点报告与哪张卡的对照材料配对——脚本侧知识）
ANCHOR_CARD_BY_ID = {"A1": "somwyn", "A2": "datawhale-023"}
# 锚点评分对象类型：真实交付复盘 vs 人工成稿诊断建议
ANCHOR_DOC_TYPE_BY_KIND = {
    "internal_accepted_delivery": "delivery_review",
    "internal_authored_reference": "diagnosis_advice",
}


# ── 真相层路径 ───────────────────────────────────────────────────────


def truth_root() -> Path:
    raw = os.environ.get(TRUTH_ROOT_ENV)
    root = Path(raw) if raw else TRUTH_ROOT_DEFAULT
    if not root.is_dir():
        raise SystemExit(
            f"真相层不在场：{root}（设 {TRUTH_ROOT_ENV} 指向案例集根目录）——"
            "无 oracle 不跑评测（fail-closed，不静默产出）"
        )
    return root


def fixtures_dir(repo_root: Path) -> Path:
    return repo_root / "server" / "tests" / "fixtures" / "diagnostic_eval"


ANSWER_MAPPING_FILENAME = "answer_mapping.json"
PLACEHOLDER_UNFILLED = "（未填写）"


def load_fixtures(repo_root: Path) -> dict[str, dict[str, Any]]:
    """读仓库侧输入 fixtures（考卷）：case_id → fixture。"""
    base = fixtures_dir(repo_root)
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(base.glob("*.json")):
        if path.name in ("answer_key_digests.json", ANSWER_MAPPING_FILENAME):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(payload.get("case_id") or "")
        if case_id:
            out[case_id] = payload
    if not out:
        raise SystemExit(f"评测 fixtures 为空：{base}（先跑 sync_from_truth_layer.py）")
    return out


def load_card(root: Path, case_id: str) -> dict[str, Any]:
    path = root / "cards" / f"{case_id}.json"
    if not path.is_file():
        raise SystemExit(f"案例卡缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.match(run_id):
        raise SystemExit(f"run_id 非法（须形如 2026-11-11 或 ev1）：{run_id!r}")
    return root / RUNS_DIRNAME / run_id


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── 输入装配（考卷 → 生产会话流） ────────────────────────────────────


def split_fixture_answers(
    fixture: dict[str, Any], *, slot_keys: dict[str, set[str]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把 fixture 的问卷槽位答案拆成（首屏答案, 诊断答案）。

    ``slot_keys`` = {"first_screen": {...}, "diagnostic": {...}}（来自
    ``fde_api.diagnostics.questionnaire``——生产闸对未知槽位键一律拒绝，
    这里先在脚本侧做同一道校验，把报错提前到入会话之前）。自由文本痛点
    落 ``ctx.free_text`` 槽位（问卷「补充」族的自由表述位）。
    """
    sim_input = fixture.get("sim_input") or {}
    slots = sim_input.get("questionnaire_slots") or {}
    first: dict[str, Any] = {}
    diag: dict[str, Any] = {}
    overlap = slot_keys["first_screen"] & slot_keys["diagnostic"]
    if overlap:
        raise SystemExit(f"首屏与诊断槽位键重叠：{sorted(overlap)}")
    allowed = slot_keys["first_screen"] | slot_keys["diagnostic"]
    unknown = sorted(set(slots) - allowed)
    if unknown:
        raise SystemExit(f"{fixture.get('case_id')}: fixtures 含未定义槽位 {unknown}")
    for key, value in slots.items():
        if key in slot_keys["first_screen"]:
            first[key] = value
        else:
            diag[key] = value
    free_text = str(sim_input.get("free_text_pain") or "").strip()
    if free_text:
        diag["ctx.free_text"] = free_text
    return first, diag


def load_answer_mapping(repo_root: Path) -> dict[str, Any]:
    """读考卷适配表（考卷口语原话值 → 生产问卷闭集）。"""
    path = fixtures_dir(repo_root) / ANSWER_MAPPING_FILENAME
    if not path.is_file():
        raise SystemExit(f"答案映射缺失：{path}（生产问卷是闭集，考卷需逐条适配）")
    return load_json(path)


def apply_answer_mapping(
    case_id: str,
    answers: dict[str, Any],
    mapping: dict[str, Any],
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把考卷的口语原话值适配成生产问卷可接受的值（fail-closed）。

    映射规则在 ``answer_mapping.json``（评测器侧裁量、逐条可审计）：
    - ``kind=choice/multi``：原话值必须逐条登记，目标值 null=省略该槽位；
    - ``kind=free``：占位符 ``（未填写）`` → 省略，其余原文直通；
    - 未登记值 ⇒ SystemExit——宁可断考卷，不可静默代答；
    - ``overrides``（``_case_overrides[case_id]``）：必答槽位考卷未涵盖时的
      考官按卡补填（值 null=移除），同样逐条登记、进映射文件指纹。
    """
    out: dict[str, Any] = {}
    for key, raw in answers.items():
        rule = mapping.get(key)
        if not isinstance(rule, dict) or not rule.get("kind"):
            raise SystemExit(f"{case_id}: 槽位 {key} 缺映射规则（kind/values）")
        values = rule.get("values") or {}
        kind = str(rule["kind"])
        if raw in values:
            value = values[raw]
        elif kind == "free" and str(raw) != PLACEHOLDER_UNFILLED:
            value = raw
        else:
            raise SystemExit(f"{case_id}: {key} 值未登记映射：{raw!r}")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        out[key] = value
    for key, value in (overrides or {}).items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


# ── 参考材料装配（评分器侧本职） ─────────────────────────────────────


def build_reference_material(card: dict[str, Any], *, include_profile: bool = True) -> str:
    """把案例卡的答案素材装配成评分对照文本（小节标题用通用措辞）。"""
    blocks: list[str] = []
    if include_profile:
        profile = card.get("company_profile") or {}
        if profile:
            lines = [
                f"- {key}: {value}" for key, value in profile.items() if str(value).strip()
            ]
            if lines:
                blocks.append("## 企业背景（代号化）\n" + "\n".join(lines))
    ground = card.get("ground_truth")
    if not isinstance(ground, dict):
        raise SystemExit(f"{card.get('case_id')}: 案例卡缺答案素材块（评测不可跑）")
    for field_name, title, is_list in _REFERENCE_SECTIONS:
        value = ground.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if is_list:
            items = [str(item).strip() for item in (value or []) if str(item).strip()]
            if not items:
                continue
            body = "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))
        else:
            body = str(value).strip()
        blocks.append(f"## {title}\n{body}")
    if not blocks:
        raise SystemExit(f"{card.get('case_id')}: 参考材料装配为空")
    return "\n\n".join(blocks)


def parse_band(raw: str) -> tuple[float, float]:
    """解析夹具期望带「78 – 98」→ (78.0, 98.0)。"""
    numbers = re.findall(r"\d+(?:\.\d+)?", str(raw))
    if len(numbers) < 2:
        raise SystemExit(f"期望带形状不合法：{raw!r}")
    return float(numbers[0]), float(numbers[1])


# ── 曲线聚合与渲染（T-09） ───────────────────────────────────────────


def aggregate_runs(root: Path) -> list[dict[str, Any]]:
    """扫真相层 eval-runs/：按 run 目录聚合 run.json + scores.json。

    只有 run.json 没有 scores.json 的 run 也会带出（generation-only 半程态，
    曲线文档如实标注「未评分」）。
    """
    runs: list[dict[str, Any]] = []
    base = root / RUNS_DIRNAME
    if not base.is_dir():
        return runs
    for path in sorted(base.glob("*/run.json")):
        run = load_json(path)
        scores_path = path.parent / "scores.json"
        scores = load_json(scores_path) if scores_path.is_file() else None
        runs.append({"run_id": path.parent.name, "run": run, "scores": scores})
    runs.sort(key=lambda item: str(item["run"].get("created_at") or item["run_id"]))
    return runs


def render_curve_md(
    runs: list[dict[str, Any]],
    *,
    doc_number: int,
    breakpoints: list[str] | None = None,
) -> str:
    """渲染版本化曲线文档（仓库存汇总+指针+sha256；零报告正文零答案内容）。

    **双版本标签纪律**：每个点必须同时携带 ``eval_set_version`` 与
    ``prompt_version``（+ judge/rubric 版本）——防「只改了考题」的伪进化；
    C 类考题修复处由调用方传 ``breakpoints`` 打版本断点。
    """
    lines: list[str] = []
    lines.append(f"# 诊断评测·评分曲线 {doc_number}")
    lines.append("")
    lines.append(
        "> **协议语义（v0）**：本曲线只呈现「同评测集版本下的重跑对比」。单点"
        "（首轮）**不构成进化证据也不构成能力结论**（insufficient_data）；判定"
        "带为候选阈值（E-1 拍板：**oracle 数据攒够前不校准**）。任何一列分数要"
        "成为「生成器已进化」的判定输入，前提是该 run 的元验证闸为 pass。"
    )
    lines.append("")
    if not runs:
        lines.append("**尚无评测 run**（真相层 eval-runs/ 为空）——insufficient_data。")
        if breakpoints:
            lines.append("")
            lines.append("## 版本断点（C 类考题/评分规则修复）")
            lines.append("")
            for point in breakpoints:
                lines.append(f"- {point}")
        return "\n".join(lines) + "\n"

    lines.append("## 各 run 版本标签（双标签纪律）")
    lines.append("")
    lines.append(
        "| run | 时间 | eval_set_version | prompt_version | report 版本 | 数字闸版本 "
        "| judge/rubric | 元验证闸 | 可作进化判定输入 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for item in runs:
        run = item["run"]
        scores = item["scores"] or {}
        meta = scores.get("meta_gate") or {}
        usable = scores.get("usable_as_evolution_evidence")
        usable_label = (
            "是" if usable is True else ("否（元验证未过）" if usable is False else "未评分")
        )
        lines.append(
            "| {run} | {created} | `{ev}` | `{pv}` | `{rv}` | `{gate_ver}` "
            "| {judge} | {gate} | {usable} |".format(
                run=item["run_id"],
                created=str(run.get("created_at") or "—"),
                ev=str(run.get("eval_set_version") or item["run_id"]),
                pv=str(run.get("prompt_version") or "—"),
                rv=str(run.get("report_version") or "—"),
                gate_ver=str(run.get("number_gate_version") or "—"),
                judge=str(scores.get("judge_version") or "—"),
                gate=str(meta.get("verdict") or "—"),
                usable=usable_label,
            )
        )
    lines.append("")

    for item in runs:
        scores = item["scores"]
        lines.append(f"## run `{item['run_id']}` 逐卡评分")
        lines.append("")
        if not scores:
            lines.append("（未评分——judge 半程未跑或失败，见真相层 run.json）")
            lines.append("")
            continue
        meta = scores.get("meta_gate") or {}
        lines.append(f"- 元验证闸：**{meta.get('verdict') or '—'}**")
        for anchor in meta.get("anchors") or []:
            line = (
                f"  - 锚点 {anchor.get('anchor_id')}：{anchor.get('total')} 分"
                f"（期望带 {anchor.get('expected_band')}，带内={anchor.get('in_band')}）"
            )
            if anchor.get("parroting_suspected"):
                line += "——复述作废（分数不构成能力证据）"
            note = str(anchor.get("note") or "").strip()
            if str(anchor.get("status") or "") != "evaluated" and note:
                line += f"——{note}"
            lines.append(line)
        counters = meta.get("counterexamples") or []
        blocked = sum(1 for c in counters if c.get("blocked"))
        lines.append(f"  - 反例拦截：{blocked}/{len(counters)}")
        lines.append("")
        lines.append("| 卡 | ①覆盖/40 | ②方向/30 | ③遗漏幻觉/20 | ④落地/10 | 总分 | 判定 | 复述作废 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        cases = scores.get("cases") or {}
        for case_id, row in sorted(cases.items()):
            dims = row.get("dimensions") or {}
            lines.append(
                "| {case} | {a} | {b} | {c} | {d} | **{total}** | {verdict} | {parrot} |".format(
                    case=case_id,
                    a=dims.get("problem_coverage", "—"),
                    b=dims.get("solution_alignment", "—"),
                    c=dims.get("omission_hallucination", "—"),
                    d=dims.get("actionability", "—"),
                    total=row.get("total", "—"),
                    verdict=row.get("verdict", "—"),
                    parrot="是" if row.get("score_invalid") else "否",
                )
            )
        lines.append("")
        lines.append(
            f"原件指针：真相层 `{RUNS_DIRNAME}/{item['run_id']}/`"
            f"（reports sha256 见该目录 run.json / scores.json）"
        )
        lines.append("")

    if breakpoints:
        lines.append("## 版本断点（C 类考题/评分规则修复）")
        lines.append("")
        for point in breakpoints:
            lines.append(f"- {point}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ── 分数面可判定性（T-09 读数规则：同考卷同生成器多 run 分布） ─────────
#
# 登记事实（curve 3，2026-11-11）：锚点 A2 同一输入两次评分 77→84 ⇒ judge
# 单点噪声 ≥7 分，逐卡 ±10 以内属噪声域 ⇒ **单点分数差不可作能力变化判定**。
# 读数规则（本节登记，留痕可推翻；**非校准阈值**——E-1：oracle 数据攒够前
# 不校准任何通过线）：分数差 Δ 可判定 ⇔ 参与两组样本数各 ≥ MIN_DISTRIBUTION_RUNS
# ∧ |Δ| > 噪声带（参与分布的观测极差较大者，含锚点纯 judge 噪声极差）。
# 锚点输入逐字节固定（真相层夹具）⇒ 锚点重跑得分＝**纯 judge 噪声**，与生成器
# 版本无关——故锚点分布按 judge 轴分组、逐卡分布按四轴分组，两者不可混用。

DECIDABLE_RULE_ID = "delta-noise-band-2026-11-11"

# 逐卡可比组四轴：考卷×生成器×数字闸×评分规则全同，重跑得分才是同位样本。
COMPARABLE_KEYS = (
    "eval_set_version",
    "prompt_version",
    "number_gate_version",
    "judge_version",
)
# 锚点可比组两轴：锚点输入固定，只随评分规则与元夹具版本变。
ANCHOR_GROUP_KEYS = ("judge_version", "meta_fixture_version")

# 每组最少样本数（2026-11-11 登记：每卡 ≥3 run 取分布——n=3 的极差只偏窄
# 不放宽，是「可判定」的必要条件而非充分条件，读数时如实携带 n）。
MIN_DISTRIBUTION_RUNS = 3


def comparable_key(item: dict[str, Any]) -> tuple[str, ...]:
    """逐卡可比组键（四轴；缺版本标签记空串——缺标签本身就是不可比信号）。"""
    run = item.get("run") or {}
    scores = item.get("scores") or {}
    return tuple(str(run.get(key) or scores.get(key) or "") for key in COMPARABLE_KEYS)


def anchor_group_key(item: dict[str, Any]) -> tuple[str, ...]:
    """锚点可比组键（judge 轴：锚点输入固定，与生成器无关）。"""
    scores = item.get("scores") or {}
    meta = scores.get("meta_gate") or {}
    values = {
        "judge_version": scores.get("judge_version"),
        "meta_fixture_version": meta.get("meta_fixture_version"),
    }
    return tuple(str(values.get(key) or "") for key in ANCHOR_GROUP_KEYS)


def distribution_stats(values: list[float]) -> dict[str, Any]:
    """一组同位样本的分布读数（极差＝观测噪声宽度；n<2 ⇒ stdev=None 不编造）。"""
    if not values:
        raise SystemExit("distribution_stats: 空样本（不产空分布）")
    xs = sorted(float(v) for v in values)
    n = len(xs)
    mean = sum(xs) / n
    stdev: float | None = None
    if n >= 2:
        variance = sum((x - mean) ** 2 for x in xs) / (n - 1)
        stdev = round(variance**0.5, 1)
    return {
        "n": n,
        "mean": round(mean, 1),
        "min": xs[0],
        "max": xs[-1],
        "range": round(xs[-1] - xs[0], 1),
        "stdev": stdev,
    }


def score_distributions(
    runs: list[dict[str, Any]], *, min_runs: int = MIN_DISTRIBUTION_RUNS
) -> dict[str, Any]:
    """按可比组聚合逐卡分布与锚点分布。

    **只收 usable_as_evolution_evidence=True 的 run**（元验证不过的分数不得作
    判定输入——协议语义在这里机械执行，不靠文档自觉）；**只收 status=evaluated
    且未作废的行**——judge error 行与复述作废行不是 0 分，是**无数据**，进分布
    就是拿假 0 分污染噪声带。逐卡按四轴、锚点按 judge 轴各归各组。
    """
    case_groups: dict[tuple[str, ...], dict[str, Any]] = {}
    anchor_groups: dict[tuple[str, ...], dict[str, Any]] = {}
    excluded = {"case_rows": 0, "anchor_rows": 0}
    for item in runs:
        scores = item.get("scores")
        if not scores or scores.get("usable_as_evolution_evidence") is not True:
            continue
        run_id = str((item.get("run") or {}).get("run_id") or "")
        case_group = case_groups.setdefault(
            comparable_key(item), {"runs": [], "case_scores": {}}
        )
        if run_id not in case_group["runs"]:
            case_group["runs"].append(run_id)
        for case_id, row in (scores.get("cases") or {}).items():
            row = row or {}
            if str(row.get("status") or "") != "evaluated" or row.get("score_invalid"):
                excluded["case_rows"] += 1
                continue
            case_group["case_scores"].setdefault(str(case_id), []).append(float(row["total"]))
        anchor_group = anchor_groups.setdefault(
            anchor_group_key(item), {"runs": [], "anchor_scores": {}}
        )
        if run_id not in anchor_group["runs"]:
            anchor_group["runs"].append(run_id)
        for anchor in (scores.get("meta_gate") or {}).get("anchors") or []:
            if str(anchor.get("status") or "") != "evaluated" or anchor.get(
                "parroting_suspected"
            ):
                excluded["anchor_rows"] += 1
                continue
            anchor_group["anchor_scores"].setdefault(
                str(anchor.get("anchor_id")), []
            ).append(float(anchor["total"]))

    def _dist_group(group: dict[str, Any], field: str) -> dict[str, Any]:
        source = group[{"cases": "case_scores", "anchors": "anchor_scores"}[field]]
        return {
            "runs": sorted(group["runs"]),
            field: {
                name: distribution_stats(values) for name, values in sorted(source.items())
            },
        }

    return {
        "rule_id": DECIDABLE_RULE_ID,
        "min_runs": min_runs,
        "excluded_rows": excluded,
        "case_groups": {
            "|".join(key): _dist_group(group, "cases") for key, group in sorted(case_groups.items())
        },
        "anchor_groups": {
            "|".join(key): _dist_group(group, "anchors")
            for key, group in sorted(anchor_groups.items())
        },
    }


def noise_width(*dists: dict[str, Any]) -> float:
    """噪声带＝参与分布的观测极差较大者（n<2 的分布无宽度，不参与取大）。"""
    widths = [float(d["range"]) for d in dists if d.get("n", 0) >= 2]
    return max(widths) if widths else 0.0


def decidable_delta(
    delta: float,
    *dists: dict[str, Any],
    min_runs: int = MIN_DISTRIBUTION_RUNS,
) -> dict[str, Any]:
    """分数差可判定性判定（读数规则 DECIDABLE_RULE_ID，非校准阈值）。

    返回 ``decidable=True/False``（可判/噪声域）或 ``None``（n 不足 ⇒
    insufficient_data——不是「不可判定」，是还没资格判）。
    """
    width = noise_width(*dists)
    n_list = [int(d["n"]) for d in dists]
    if any(n < min_runs for n in n_list):
        return {
            "rule_id": DECIDABLE_RULE_ID,
            "decidable": None,
            "reason": "insufficient_data",
            "n_list": n_list,
            "noise_width": width,
            "abs_delta": abs(delta),
        }
    readable = abs(delta) > width
    return {
        "rule_id": DECIDABLE_RULE_ID,
        "decidable": readable,
        "reason": "" if readable else "within_noise",
        "n_list": n_list,
        "noise_width": width,
        "abs_delta": abs(delta),
    }


def render_distribution_md(summary: dict[str, Any]) -> str:
    """渲染分布底册 markdown（仓库存汇总+指针；零报告正文零答案材料）。"""
    min_runs = int(summary.get("min_runs") or MIN_DISTRIBUTION_RUNS)
    lines: list[str] = []
    lines.append("# 诊断评测·分数面分布（可判定性底册）")
    lines.append("")
    lines.append(
        f"> **读数规则（`{summary.get('rule_id') or DECIDABLE_RULE_ID}`，非校准阈值）**："
        "分数差 Δ 可判定 ⇔ 参与两组样本数各 ≥ "
        f"{min_runs} ∧ |Δ| > 噪声带（参与分布的观测极差较大者，含锚点）。"
        "锚点输入逐字节固定 ⇒ 锚点极差＝**纯 judge 噪声**；逐卡极差＝生成+judge"
        "联合噪声。n 不足 ⇒ insufficient_data（还没资格判）。oracle 数据攒够前"
        "不校准任何通过线（E-1）；单点分数差不构成能力结论。"
    )
    lines.append("")

    case_groups = summary.get("case_groups") or {}
    anchor_groups = summary.get("anchor_groups") or {}
    if not case_groups and not anchor_groups:
        lines.append("**尚无可用分布**（无 usable run）——insufficient_data。")
        return "\n".join(lines) + "\n"

    lines.append("## 逐卡分布组（考卷×生成器×数字闸×judge 四轴全同才同组）")
    lines.append("")
    for key, group in case_groups.items():
        _render_dist_group(lines, key, group, "cases", min_runs)

    lines.append("## 锚点分布组（judge×元夹具两轴——纯 judge 噪声）")
    lines.append("")
    for key, group in anchor_groups.items():
        _render_dist_group(lines, key, group, "anchors", min_runs)
    return "\n".join(lines) + "\n"


def _render_dist_group(
    lines: list[str],
    key: str,
    group: dict[str, Any],
    field: str,
    min_runs: int,
) -> None:
    dists = group.get(field) or {}
    runs = group.get("runs") or []
    sample_n = min((d["n"] for d in dists.values()), default=0)
    readiness = "✅ 达最小样本" if sample_n >= min_runs else f"⚠️ n<{min_runs}（insufficient_data）"
    lines.append(f"### 组 `{key}`（runs: {', '.join(runs) or '—'}）——{readiness}")
    lines.append("")
    if not dists:
        lines.append("（该组无可分布样本）")
        lines.append("")
        return
    lines.append("| 对象 | n | 均值 | min | max | 极差 | stdev |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, dist in dists.items():
        stdev = dist.get("stdev")
        lines.append(
            "| {name} | {n} | {mean} | {mn} | {mx} | {rg} | {sd} |".format(
                name=name,
                n=dist["n"],
                mean=dist["mean"],
                mn=dist["min"],
                mx=dist["max"],
                rg=dist["range"],
                sd="—" if stdev is None else stdev,
            )
        )
    lines.append("")
