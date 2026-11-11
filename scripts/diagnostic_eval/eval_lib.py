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
