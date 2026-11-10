"""诊断报告输出契约（T-10b）——R-1~R-7 的机械闸。

**为什么要有这一层**：AI 报告是公网免注册面（首个公网免注册写面），输出会
直接给访客看；「模型说了什么」不可信，必须**结构上**拦住六类失真。rubric v0.1
的 AI 预评（83/88/88/91/86/88，六卡全 pass ⇒ 阈值零区分力）已经把失真类型
列清，本模块把它们逐条变成**可断言**的检查。

**七条需求 → 机械闸**（来源：实施任务书 §3 T-10 需求清单）：

| 需求 | 机械闸 |
|---|---|
| R-1 去掉无溯源分值 | 输出结构**无分数字段**；数字闸只认问卷/测算卡里出现过的数字 |
| R-2 政策层只引原文口径 | **原文口径由服务端注入**（模型只输出 policy_id；未知编号拒收） |
| R-3 第一三要素 | ``first_step`` 必填且三要素非空，``when`` 闭集＝「本周」 |
| R-4 未溯源数字 fail-closed | 数字闸：数字必须在问卷/测算卡里出现过，否则该句须写「待澄清」 |
| R-5 问题↔动作一一映射 | ``actions`` 必须覆盖 ``findings`` 的每个 id，且不得有悬空引用 |
| R-6 不得把选型期写成已完成 | 建议段禁用词闸（**只扫建议段**——见下） |
| R-7 识别→定位→处置→回写闭环 | ``closing_loop`` 四段键齐全且非空 |

**R-6 扫描范围的取舍（留痕可推翻）**：禁用词闸只扫**建议段**
（``first_step`` / ``actions`` / ``closing_loop``）——「把选型期写成已完成」的
失真发生在**建议**里（把「要做的事」写成「做完的事」）。现状段若客户自述
「去年已完成改造」，那是**客户的原话**而非模型的失真；闸若扫现状段会把客户
的真实表述判成失真，白白烧掉一次 AI 调用还交不出报告。现状段的一致性另有
约束（问卷是闭集选项）。

**数字闸的口径**：数字**不是一律禁**——客户自己在问卷里写的数字（人数、周期、
台数）是有来源的。闸的判据是「这个数字能不能在问卷/测算卡里找到」；找不到
⇒ 该句必须写「待澄清」说明缺什么（R-4 的两个出口：fail-closed 或标待澄清，
本实现取「标待澄清」这一出口，因为「fail-closed」会把客户自述也一并毙掉）。
"""
from __future__ import annotations

import json
import re
from typing import Any

from fde_api.diagnostics.policy_data import (
    INTERPRETATION_BY_POLICY_ID,
    INTERPRETATION_LABEL,
    ORIGINAL_LABEL,
    POLICY_BY_ID,
)
from fde_api.diagnostics.prompts import (
    FIRST_STEP_WHEN,
    LOOP_STAGES,
    REPORT_VERSION,
)

# 顶层键闭集（多一个键＝模型自创结构＝拒收）
TOP_LEVEL_KEYS = (
    "headline",
    "findings",
    "first_step",
    "actions",
    "closing_loop",
    "policy_ids",
    "open_questions",
)

FINDING_KEYS = ("id", "problem", "stage")
ACTION_KEYS = ("finding_id", "action", "expected_output")
FIRST_STEP_KEYS = ("when", "what", "output")
CLOSING_LOOP_KEYS = ("identified", "located", "handled", "written_back")

# 建议段禁用词（R-6）——只扫建议段，理由见模块说明
FORBIDDEN_COMPLETION_PHRASES = (
    "已完成改造",
    "改造已完成",
    "已实现自动化",
    "已全面打通",
    "已全部打通",
)

# 待澄清标记（R-4 的出口）
CLARIFY_MARKER = "待澄清"

# 建议段字段（禁用词闸的扫描面）
ADVICE_FIELDS = ("first_step", "actions", "closing_loop")

MAX_HEADLINE_CHARS = 200
MAX_TEXT_CHARS = 600
MAX_FINDINGS = 6
MAX_OPEN_QUESTIONS = 8
MAX_ACTIONS = 12

_FINDING_ID_RE = re.compile(r"^f[1-9]$")
# 数字识别：阿拉伯数字 ＋ **中文数字＋量词**（只认「数+量词」的形态——裸「一」
# 会把「第一次」「一致」「一起」这类正常汉语全部误判成数字）。
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_CN_NUMBER_RE = re.compile(
    r"[零一二三四五六七八九十百千万两几半]\s*"
    r"(?:个月|星期|个|家|人|台|套|条|项|年|月|天|周|倍|万|亿|元|块|%|％)"
)


class ReportContractError(Exception):
    """输出契约违规（code + 面向内部的可读原因）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise ReportContractError(code, message)


def parse_report_json(text: str) -> dict[str, Any]:
    """从模型输出里取出 JSON 对象。

    模型常带 Markdown 代码块或前后缀说明——**容错取最外层 JSON**，但**不做
    任何语义修补**：解析不出来就是契约失败（fail-closed），不猜、不兜底。
    """
    if not isinstance(text, str) or not text.strip():
        _fail("report_output_invalid", "模型没有返回内容。")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        _fail("report_output_invalid", "模型输出里没有 JSON 对象。")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as error:
        _fail("report_output_invalid", f"模型输出不是合法 JSON：{error.msg}")
    if not isinstance(payload, dict):
        _fail("report_output_invalid", "模型输出的顶层不是对象。")
    return payload


def _string(value: Any, *, field: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        _fail("report_contract_invalid", f"{field} 必须是字符串。")
    text = value.strip()
    if not text:
        _fail("report_contract_invalid", f"{field} 不能为空。")
    if len(text) > max_chars:
        _fail("report_contract_invalid", f"{field} 超长（上限 {max_chars} 字）。")
    return text


def number_tokens(text: str) -> set[str]:
    """文本里的数字串（``70%`` → ``70``；``1.5`` → ``1.5``；``三个月`` → ``三个月``）。"""
    tokens = set(_NUMBER_RE.findall(text))
    tokens |= {match.group(0).replace(" ", "") for match in _CN_NUMBER_RE.finditer(text)}
    return tokens


def allowed_number_tokens(*corpora: Any) -> set[str]:
    """可溯源数字集合（问卷答案 + 测算卡）。

    客户自己写的数字（人数、周期、台数）**有来源**——数字闸认它们；找不到
    来源的数字必须写「待澄清」（R-4）。
    """
    tokens: set[str] = set()
    for corpus in corpora:
        if corpus is None:
            continue
        text = json.dumps(corpus, ensure_ascii=False, sort_keys=True)
        tokens |= number_tokens(text)
    return tokens


def _check_numbers(text: str, *, field: str, allowed: set[str]) -> None:
    if CLARIFY_MARKER in text:
        return
    for token in number_tokens(text):
        if token not in allowed:
            _fail(
                "report_unsourced_number",
                f"{field} 里的数字「{token}」没有来源（问卷与测算卡里都没有）——"
                f"请删掉或在该句写「{CLARIFY_MARKER}」并说明缺什么。",
            )


def _check_forbidden(text: str, *, field: str) -> None:
    for phrase in FORBIDDEN_COMPLETION_PHRASES:
        if phrase in text:
            _fail(
                "report_forbidden_claim",
                f"{field} 出现禁用表述「{phrase}」——建议段不得把选型期写成已完成。",
            )


def validate_report_payload(
    payload: dict[str, Any], *, allowed_numbers: set[str] | None = None
) -> dict[str, Any]:
    """结构 + 语义校验；不合规即抛 ``ReportContractError``（fail-closed）。"""
    allowed = allowed_numbers or set()

    missing = [key for key in TOP_LEVEL_KEYS if key not in payload]
    if missing:
        _fail("report_contract_invalid", f"报告缺少字段：{missing}")
    unknown = sorted(set(payload) - set(TOP_LEVEL_KEYS))
    if unknown:
        _fail("report_contract_invalid", f"报告含未定义字段：{unknown}")

    headline = _string(payload["headline"], field="headline", max_chars=MAX_HEADLINE_CHARS)
    _check_numbers(headline, field="headline", allowed=allowed)

    findings_raw = payload["findings"]
    if not isinstance(findings_raw, list) or not findings_raw:
        _fail("report_contract_invalid", "findings 至少要有一条。")
    if len(findings_raw) > MAX_FINDINGS:
        _fail("report_contract_invalid", f"findings 最多 {MAX_FINDINGS} 条。")
    findings: list[dict[str, str]] = []
    seen_ids: list[str] = []
    for index, item in enumerate(findings_raw, start=1):
        if not isinstance(item, dict):
            _fail("report_contract_invalid", f"findings[{index - 1}] 必须是对象。")
        if set(item) != set(FINDING_KEYS):
            _fail(
                "report_contract_invalid",
                f"findings[{index - 1}] 字段必须是 {list(FINDING_KEYS)}。",
            )
        finding_id = item["id"]
        if not isinstance(finding_id, str) or not _FINDING_ID_RE.match(finding_id):
            _fail("report_contract_invalid", f"findings[{index - 1}] 的 id 形如 f1。")
        if finding_id != f"f{index}":
            _fail("report_contract_invalid", "findings 的 id 必须从 f1 起连续编号。")
        problem = _string(item["problem"], field=f"findings[{index - 1}].problem")
        stage = item["stage"]
        if stage not in LOOP_STAGES:
            _fail(
                "report_contract_invalid",
                f"findings[{index - 1}].stage 只能是 {list(LOOP_STAGES)} 之一。",
            )
        _check_numbers(problem, field=f"findings[{index - 1}].problem", allowed=allowed)
        findings.append({"id": finding_id, "problem": problem, "stage": stage})
        seen_ids.append(finding_id)

    first_step_raw = payload["first_step"]
    if not isinstance(first_step_raw, dict):
        _fail("report_contract_invalid", "first_step 必须是对象。")
    if set(first_step_raw) != set(FIRST_STEP_KEYS):
        _fail("report_contract_invalid", f"first_step 字段必须是 {list(FIRST_STEP_KEYS)}。")
    when = first_step_raw["when"]
    if when not in FIRST_STEP_WHEN:
        _fail("report_contract_invalid", f"first_step.when 只能是 {list(FIRST_STEP_WHEN)} 之一。")
    first_step = {
        "when": when,
        "what": _string(first_step_raw["what"], field="first_step.what"),
        "output": _string(first_step_raw["output"], field="first_step.output"),
    }
    for key in ("what", "output"):
        _check_numbers(first_step[key], field=f"first_step.{key}", allowed=allowed)
        _check_forbidden(first_step[key], field=f"first_step.{key}")

    actions_raw = payload["actions"]
    if not isinstance(actions_raw, list) or not actions_raw:
        _fail("report_contract_invalid", "actions 至少要有一条。")
    if len(actions_raw) > MAX_ACTIONS:
        _fail("report_contract_invalid", f"actions 最多 {MAX_ACTIONS} 条。")
    actions: list[dict[str, str]] = []
    covered: set[str] = set()
    for index, item in enumerate(actions_raw, start=1):
        if not isinstance(item, dict):
            _fail("report_contract_invalid", f"actions[{index - 1}] 必须是对象。")
        if set(item) != set(ACTION_KEYS):
            _fail(
                "report_contract_invalid",
                f"actions[{index - 1}] 字段必须是 {list(ACTION_KEYS)}。",
            )
        finding_ref = item["finding_id"]
        if not isinstance(finding_ref, str) or finding_ref not in seen_ids:
            _fail(
                "report_contract_invalid",
                f"actions[{index - 1}].finding_id「{finding_ref}」不在 findings 里。",
            )
        action_text = _string(item["action"], field=f"actions[{index - 1}].action")
        expected = _string(
            item["expected_output"], field=f"actions[{index - 1}].expected_output"
        )
        for field_name, value in (("action", action_text), ("expected_output", expected)):
            _check_numbers(value, field=f"actions[{index - 1}].{field_name}", allowed=allowed)
            _check_forbidden(value, field=f"actions[{index - 1}].{field_name}")
        actions.append(
            {
                "finding_id": finding_ref,
                "action": action_text,
                "expected_output": expected,
            }
        )
        covered.add(finding_ref)
    uncovered = [fid for fid in seen_ids if fid not in covered]
    if uncovered:
        _fail(
            "report_action_unmapped",
            f"问题 {uncovered} 没有对应动作——每个识别出来的问题都要有动作（R-5）。",
        )

    closing_raw = payload["closing_loop"]
    if not isinstance(closing_raw, dict):
        _fail("report_contract_invalid", "closing_loop 必须是对象。")
    if set(closing_raw) != set(CLOSING_LOOP_KEYS):
        _fail(
            "report_contract_invalid",
            f"closing_loop 字段必须是 {list(CLOSING_LOOP_KEYS)}（识别→定位→处置→回写）。",
        )
    closing_loop = {
        key: _string(closing_raw[key], field=f"closing_loop.{key}") for key in CLOSING_LOOP_KEYS
    }
    for key in CLOSING_LOOP_KEYS:
        _check_numbers(closing_loop[key], field=f"closing_loop.{key}", allowed=allowed)
        _check_forbidden(closing_loop[key], field=f"closing_loop.{key}")

    policy_ids_raw = payload["policy_ids"]
    if not isinstance(policy_ids_raw, list):
        _fail("report_contract_invalid", "policy_ids 必须是数组。")
    policy_ids: list[str] = []
    for item in policy_ids_raw:
        if not isinstance(item, str):
            _fail("report_contract_invalid", "policy_ids 只能放政策编号字符串。")
        if item not in POLICY_BY_ID:
            _fail("report_contract_unknown_policy", f"未知政策编号「{item}」。")
        if item in policy_ids:
            _fail("report_contract_invalid", f"政策编号「{item}」重复。")
        policy_ids.append(item)

    questions_raw = payload["open_questions"]
    if not isinstance(questions_raw, list):
        _fail("report_contract_invalid", "open_questions 必须是数组。")
    if len(questions_raw) > MAX_OPEN_QUESTIONS:
        _fail("report_contract_invalid", f"open_questions 最多 {MAX_OPEN_QUESTIONS} 条。")
    open_questions = [
        _string(item, field=f"open_questions[{index}]", max_chars=MAX_TEXT_CHARS)
        for index, item in enumerate(questions_raw)
    ]

    return {
        "headline": headline,
        "findings": findings,
        "first_step": first_step,
        "actions": actions,
        "closing_loop": closing_loop,
        "policy_ids": policy_ids,
        "open_questions": open_questions,
    }


def _policy_opportunity(policy_id: str) -> dict[str, Any]:
    """政策机会条目——**原文口径与我方解读都由服务端装配**（R-2）。

    模型只负责「选哪几条」；原文口径、官方出处、快照日期与我方解读全部来自
    ``policy_data``——模型没有原文可抄，也就无从编造（R-2 fail-closed）。
    """
    entry = POLICY_BY_ID[policy_id]
    interpretation = INTERPRETATION_BY_POLICY_ID.get(policy_id)
    reading_lines: list[str] = []
    if interpretation is not None:
        reading_lines.append(f"{interpretation.label}（{INTERPRETATION_LABEL}）")
        if interpretation.preparation_requirements:
            reading_lines.append(
                "享受前提：" + "；".join(interpretation.preparation_requirements)
            )
        if interpretation.verification_steps:
            reading_lines.append("下一步确认：" + "；".join(interpretation.verification_steps))
        if interpretation.note:
            reading_lines.append(f"提示：{interpretation.note}")
    return {
        "policy_id": entry.policy_id,
        "title": entry.title,
        "doc_number": entry.doc_number,
        "issued_on": entry.issued_on,
        "original_basis": ORIGINAL_LABEL,
        "official_text": entry.original_wording,
        "official_source_url": entry.official_source_url,
        "snapshot_date": entry.snapshot_date,
        "interpretation_basis": INTERPRETATION_LABEL,
        "our_reading": (
            "；".join(reading_lines) if reading_lines else "（本条暂无我方解读，仅引原文口径）"
        ),
    }


def assemble_report(
    *,
    payload: dict[str, Any],
    assessment: dict[str, Any] | None,
    model_info: dict[str, Any] | None = None,
    generated_at: str,
    prompt_version: str,
) -> dict[str, Any]:
    """把已通过校验的模型输出装配成**三层报告**（服务端结构，模型不可改）。"""
    opportunities = [_policy_opportunity(pid) for pid in payload["policy_ids"]]
    return {
        "version": REPORT_VERSION,
        "prompt_version": prompt_version,
        "generated_at": generated_at,
        "layers": {
            # ①现状与问题
            "situation": {
                "headline": payload["headline"],
                "findings": payload["findings"],
                "open_questions": payload["open_questions"],
            },
            # ②定位与处置（含第一步三要素与闭环四段）
            "action": {
                "first_step": payload["first_step"],
                "actions": payload["actions"],
                "closing_loop": payload["closing_loop"],
            },
            # ③政策与申报机会（原文口径 + 我方解读，出处与快照日期）
            "policy": {"opportunities": opportunities},
        },
        "assessment_tier": (assessment or {}).get("tier"),
        "model": model_info or {},
    }


def report_share_view(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """分享页只读视图——**摘要层**，不含企业自填原文与联系方式。

    分享链接可能被转发给第三方；把访客自述的长文本带出去等于绕过「留资才给
    全文」的闸（D-2）。故分享视图只带：结论一句话、第一步三要素、政策机会、
    问题标题、闭环四段的存在性。
    """
    if not report:
        return None
    layers = report.get("layers") or {}
    situation = layers.get("situation") or {}
    action = layers.get("action") or {}
    policy = layers.get("policy") or {}
    closing = action.get("closing_loop") or {}
    return {
        "version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "headline": situation.get("headline"),
        "findings": [
            {"id": item.get("id"), "title": item.get("problem"), "stage": item.get("stage")}
            for item in situation.get("findings") or []
        ],
        "first_step": action.get("first_step"),
        "policy_opportunities": policy.get("opportunities") or [],
        "loop_completed": {
            "identified": bool(closing.get("identified")),
            "located": bool(closing.get("located")),
            "handled": bool(closing.get("handled")),
            "written_back": bool(closing.get("written_back")),
        },
        "notice": "这是诊断摘要。完整报告需留资后在本人的诊断会话内查看。",
    }
