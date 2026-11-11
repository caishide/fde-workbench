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

**数字闸 v2 口径重界定（2026-11-11，curve 3 断点；留痕可推翻）**
——curve 2 真机归因发现三个独立缺陷，全部是**闸的口径/机制**问题，不是模型
编数字：

| 缺陷 | 现象 | v2 处置 |
|---|---|---|
| D1 口径错位 | 闸扫「任何数字串」，而 R-4 的声明域是**规模/金额/比例/周期/时间的量值断言**；中文泛指量词（「输出一套清单」里的「一套」）被当成无源业务数字 ⇒ curve 2 三张卡全灭在 `report_unsourced_number`，零真实信号 | **分层作用域**：现状层（结论与问题清单）＝对客户事实的断言 ⇒ 全量必检；处方层（第一步/动作/闭环处置回写）里的计数与周期是**建议参数**或对已有事实的复述 ⇒ 免检；**金额与比例类任何层都必检**（基线数字编造的重灾面） |
| D2 裁决依赖输入里的偶然字面 | 「一个」在 somwyn 卡放行、在 datawhale-001 卡拒收——差别只在**规则生成的测算卡措辞**里偶然出现了「挑一个高频…」（闸把整个测算卡当数字来源） | **可溯源集合重界定**：来源＝**客户答案 ＋ 政策引文编号/日期**；测算卡的规则生成文本（下一步建议/免责声明/我方解读/缺口清单）**不再**是数字来源 |
| D3 修复不可达 | 契约失败后重试是**同提示词重抽**（盲重抽），模型看不到拒因 ⇒ 可修的违规（删词/改写/标待澄清）两次都烧光 ⇒ 一个量词毙掉整份报告 | **拒因回灌**：第二次尝试带上拒因与修法指引（生成侧由 `jobs.py` 接线） |

**v2 的边界（诚实声明）**：处方层免检的是「计数/周期」类——**编造的客户事实
若出现在处方层，契约闸不拦**（例：「把 3 台设备的台账补齐」里的「3 台」）；
兜底层是 rubric ③（编造基线数字单列重罚）与展示闸 C1（无源数字不得进展示
层）。契约闸的职责被限定为「**这个数字有没有合法来源**」，「用得对不对」
（是否张冠李戴、是否冒充基线）归 judge 层——两层分工，不互相顶替。
"""
from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

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

# 数字闸版本（2026-11-11 curve 3 断点：口径重界定，见模块说明）
NUMBER_GATE_VERSION = "number-gate-v2"

# 数字闸的作用域分层（v2）——判据是「这句话在断言客户事实，还是在提建议」
LAYER_SITUATION = "situation"  # 现状层：结论与问题清单＝对客户现状的断言
LAYER_ADVICE = "advice"  # 处方层：第一步/动作/闭环处置回写＝建议与产出

# 量词分类（v2）——数字闸按「数 + 量词」判定这个数是什么性质的断言
# 金额/比例：基线数字编造的重灾面（补贴额、成本率、倍数）⇒ 任何层必检
MONEY_UNITS = frozenset({"元", "块", "%", "％", "倍"})
# 周期：现状层＝客户事实（周期多久），处方层＝建议节奏 ⇒ 分层判定
PERIOD_UNITS = frozenset({"天", "周", "月", "年", "个月", "星期"})
# 计数：现状层＝客户事实（几台/几人），处方层＝产出数量或对已列对象的复述
COUNT_UNITS = frozenset({"个", "家", "人", "台", "套", "条", "项"})
ALL_UNITS = MONEY_UNITS | PERIOD_UNITS | COUNT_UNITS

MAX_HEADLINE_CHARS = 200
MAX_TEXT_CHARS = 600
MAX_FINDINGS = 6
MAX_OPEN_QUESTIONS = 8
MAX_ACTIONS = 12

_FINDING_ID_RE = re.compile(r"^f[1-9]$")
# 数字识别（v2）：**数 + 量词**才算一个量值断言——
# ① 阿拉伯数字（可带量词：「99人」「30%」「3台」）；
# ② 中文数字 + 量词（「两套」「三天」「三个月」）。
# 只认「数+量词」形态：裸「一」会把「第一次」「一致」「一起」这类正常汉语
# 全部误判成数字。
_UNIT_PATTERN = r"个月|星期|个|家|人|台|套|条|项|年|月|天|周|倍|元|块|%|％"
_NUMBER_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT_PATTERN})?")
_CN_NUMBER_RE = re.compile(
    rf"([零一二三四五六七八九十百千万两几半])\s*({_UNIT_PATTERN})"
)
# 中文数字取值（单字 + 量词形态——「十」是十、「万」是一万）
_CN_VALUES: dict[str, float | None] = {
    "零": 0.0,
    "一": 1.0,
    "二": 2.0,
    "两": 2.0,
    "三": 3.0,
    "四": 4.0,
    "五": 5.0,
    "六": 6.0,
    "七": 7.0,
    "八": 8.0,
    "九": 9.0,
    "十": 10.0,
    "百": 100.0,
    "千": 1000.0,
    "万": 10000.0,
    "亿": 100000000.0,
    "半": 0.5,
    # 「几」是泛指（几家/几台）——不是量值断言（v2：泛指量词不构成数字）
    "几": None,
}


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


class NumberToken(NamedTuple):
    """一个量值断言的解析结果（v2）。

    ``value``：数值（``None``＝泛指量词「几家」，不是量值断言）；
    ``unit``：量词（空串＝裸数字）；``surface``：原始字面（报错提示用）。
    """

    value: float | None
    unit: str
    surface: str


# 比对键（不含字面）：中文数字与阿拉伯数字归一后可比（「两套」≡「2套」）
NumberKey = tuple[float | None, str]


def number_tokens(text: str) -> list[NumberToken]:
    """文本里的量值断言（v2：**数 + 量词**才算一个断言）。

    「70%」→ (70, %)、「1.5」→ (1.5, 裸)、「三个月」→ (3, 个月)、
    「两套」→ (2, 套)、「十几家」→ 泛指（值 None，不是量值断言）。
    """
    tokens: list[NumberToken] = []
    for match in _NUMBER_RE.finditer(text):
        tokens.append(
            NumberToken(float(match.group(1)), match.group(2) or "", match.group(0).strip())
        )
    for match in _CN_NUMBER_RE.finditer(text):
        tokens.append(
            NumberToken(
                _CN_VALUES[match.group(1)],
                match.group(2),
                match.group(0).replace(" ", ""),
            )
        )
    return tokens


def allowed_number_tokens(*corpora: Any) -> set[NumberKey]:
    """可溯源数字集合（这些语料里出现过的「数 + 量词」都算有来源）。

    客户自己写的数字（人数、周期、台数）**有来源**——数字闸认它们；找不到
    来源的数字必须写「待澄清」（R-4）。
    """
    keys: set[NumberKey] = set()
    for corpus in corpora:
        if corpus is None:
            continue
        text = json.dumps(corpus, ensure_ascii=False, sort_keys=True)
        keys |= {(token.value, token.unit) for token in number_tokens(text)}
    return keys


# 政策引文字段（数字可作来源：官方编号与日期）。**不含**政策原文口径里的
# 量值——政策自己的「70%」「2027 目标」不是客户事实的来源，否则报告里任何
# 百分比都能借政策口径放行。
POLICY_CITATION_KEYS = (
    "policy_id",
    "title",
    "doc_number",
    "issued_on",
    "snapshot_date",
    "official_source_url",
)


def sourced_number_tokens(answers: Any, assessment: Any) -> set[NumberKey]:
    """可溯源数字集合 v2＝**客户答案 ＋ 政策引文编号/日期**。

    曲线 3 归因 D2：v1 把**整个测算卡**当数字来源，于是「挑一个高频场景」这类
    规则生成措辞里的「一个」也让「公司只有一个系统」放行——裁决取决于测算卡
    措辞的偶然字面，不是数字本身有没有来源。v2 只认两类来源：
    ① 客户自己写的答案；② 政策引文的编号与日期。
    """
    keys = allowed_number_tokens(answers)
    if isinstance(assessment, dict):
        keys |= allowed_number_tokens(assessment.get("policy_snapshot_date"))
        for policy in assessment.get("matched_policies") or []:
            if not isinstance(policy, dict):
                continue
            keys |= allowed_number_tokens(
                {key: policy.get(key) for key in POLICY_CITATION_KEYS}
            )
    return keys


def _number_in_scope(token: NumberToken, *, layer: str) -> bool:
    """这个数字是不是本闸要管的范围（v2 分层口径）。

    判据＝「**这个数字断言了一个量级吗**」：

    - 泛指量词（「几家」）⇒ 不是数字，不在闸内；
    - 金额与比例（元/块/%/倍）⇒ 量级断言，**任何层必检**（基线数字编造的重灾面）；
    - 值＝1 的计数与周期（「一套」「一个月」）⇒ 中文里多为泛指/单数用法
      （a set of… / a month），不构成量级断言 ⇒ 免检；
    - 裸数字（无量词，如「46」）⇒ 量级断言，只在现状层必检；
    - 计数与周期（值≥2）⇒ 量级断言：现状层必检（客户事实）；处方层免检
      （建议节奏／产出数量／对问卷里已列对象的复述——复述必有来源，天然放行）。

    **兜底分工（诚实声明）**：值＝1 的计数放行，意味着「公司只有一个系统」
    这类客户事实类编造**不再由契约闸拦**——它由 rubric ③ 的**案例禁编造清单**
    与展示闸 C1 兜底（评分器按案例卡逐条核）。理由是**代价不对称**：契约闸的
    误拒会直接毙掉整份报告（访客拿不到任何东西），而漏放交给评分层扣分。
    """
    if token.value is None:
        return False
    if token.unit in MONEY_UNITS:
        return True
    if token.value == 1 and token.unit in (COUNT_UNITS | PERIOD_UNITS):
        return False
    return layer == LAYER_SITUATION


def _check_numbers(text: str, *, field: str, allowed: set[NumberKey], layer: str) -> None:
    if CLARIFY_MARKER in text:
        return
    for token in number_tokens(text):
        if not _number_in_scope(token, layer=layer):
            continue
        if (token.value, token.unit) not in allowed:
            _fail(
                "report_unsourced_number",
                f"{field} 里的数字「{token.surface}」没有来源（问卷答案与政策引文里都没有）——"
                f"请删掉这个数字、改写成不带数字的说法，或在该句写「{CLARIFY_MARKER}」并说明缺什么。",
            )


def _check_forbidden(text: str, *, field: str) -> None:
    for phrase in FORBIDDEN_COMPLETION_PHRASES:
        if phrase in text:
            _fail(
                "report_forbidden_claim",
                f"{field} 出现禁用表述「{phrase}」——建议段不得把选型期写成已完成。",
            )


def validate_report_payload(
    payload: dict[str, Any], *, allowed_numbers: set[NumberKey] | None = None
) -> dict[str, Any]:
    """结构 + 语义校验；不合规即抛 ``ReportContractError``（fail-closed）。"""
    allowed: set[NumberKey] = allowed_numbers or set()

    missing = [key for key in TOP_LEVEL_KEYS if key not in payload]
    if missing:
        _fail("report_contract_invalid", f"报告缺少字段：{missing}")
    unknown = sorted(set(payload) - set(TOP_LEVEL_KEYS))
    if unknown:
        _fail("report_contract_invalid", f"报告含未定义字段：{unknown}")

    headline = _string(payload["headline"], field="headline", max_chars=MAX_HEADLINE_CHARS)
    _check_numbers(headline, field="headline", allowed=allowed, layer=LAYER_SITUATION)

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
        _check_numbers(
            problem,
            field=f"findings[{index - 1}].problem",
            allowed=allowed,
            layer=LAYER_SITUATION,
        )
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
        _check_numbers(
            first_step[key],
            field=f"first_step.{key}",
            allowed=allowed,
            layer=LAYER_ADVICE,
        )
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
            _check_numbers(
                value,
                field=f"actions[{index - 1}].{field_name}",
                allowed=allowed,
                layer=LAYER_ADVICE,
            )
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
        _check_numbers(
            closing_loop[key],
            field=f"closing_loop.{key}",
            allowed=allowed,
            layer=LAYER_ADVICE,
        )
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
        # 数字闸版本随报告落库：这份报告是在哪一版数字口径下过闸的
        # （curve 3 断点＝number-gate-v2；口径变 ⇒ 报告的可比性变）。
        "number_gate_version": NUMBER_GATE_VERSION,
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
