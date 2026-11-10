"""诊断报告生成提示词（T-10b）。

**提示词＝生成器可见面**——评测集污染隔离纪律（R-4）：本模块**不引用**真相层
路径、案例卡与答案键；只引用仓库内已落的两类素材：①已代号化的问卷答案
②政策弹药库原文口径（``policy_data.py``）。

**R-1~R-7 逐条落进提示词**（rubric v0.1 的 AI 预评归因直接转成生成侧条款）：

- R-1 去掉无溯源分值——报告里**不出现分数**；
- R-3 必须给出「第一步（本周可做 + 做什么 + 产出什么）」三要素；
- R-4 未溯源数字 fail-closed 或标「待澄清」；
- R-5 每个已识别问题在建议段**有对应动作**（一一映射）；
- R-6 不得把选型期写成已完成 / 不得编造基线数字；
- R-7 「识别 → 定位 → 处置 → 回写」闭环四段齐。

**政策原文口径由服务端注入**（R-2）：模型**只输出 policy_id 列表**，不写任何
政策原文或解读——原文口径/我方解读/出处/快照日期全部由 ``policy_data`` 落库，
**模型无从编造政策口径**（fail-closed by construction）。
"""
from __future__ import annotations

import json
from typing import Any

from fde_api.diagnostics.policy_data import (
    POLICY_ENTRIES,
    POLICY_INTERPRETATION,
    POLICY_SNAPSHOT_DATE,
)

# 报告版本与提示词版本（两层都要能追责：报告结构变了 vs 提示词变了）
REPORT_VERSION = "diagnostic-report-v1"
REPORT_PROMPT_VERSION = "diagnostic-report-prompt-v1"

# AI 调用用途（G-16 归因；purpose 是开放字符串，DB 侧只约束非空与长度）
REPORT_PURPOSE = "diagnostic_report"

# 闭集：问题所处环节（R-7 闭环四段）
LOOP_STAGES = ("identify", "locate", "handle", "writeback")

# 闭集：第一步的时间窗（R-3「本周可做」）
FIRST_STEP_WHEN = ("本周",)

# 用语纪律（与本仓其他生成面同款条款，见 guidance/ai_prompt.py）
_PLAIN_LANGUAGE = (
    "用语纪律：所有面向读者的表述使用平实中文，不得使用行业黑话或缩略行话"
    "（如「A端/B端/C端」「赋能」「抓手」「闭环」「颗粒度」等）；"
    "确需使用专业术语时，在该词后用括号补一句平实中文解释。"
)

DIAGNOSTIC_REPORT_SYSTEM_PROMPT = f"""你是面向中小企业的数字化与政策申报诊断顾问。
你要基于企业自填的诊断问卷答案，输出一份**可执行**的诊断建议。

# 硬约束（违反即整份报告作废）

1. **不要分数、不要评级、不要百分比**（R-1）。整份报告不出现任何评分式结论。
2. **不要编造数字**（R-4）。凡涉及规模、金额、比例、周期、时间的具体数字，
   你没有来源就**不要写**；确实必须提到时，在该句里写「待澄清」并说明缺什么。
3. **不要把还在选型或准备阶段的事写成已经完成**（R-6）。禁用表述包括但不限于
   「已完成改造」「改造已完成」「已实现自动化」「已全面打通」。
4. **每个识别出来的问题都要有对应动作**（R-5）。`actions` 里必须覆盖 `findings`
   里的每一个 `id`，一对一，不允许有悬空动作。
5. **必须给出第一步**（R-3）：`first_step` 三要素齐全——`when` 只能是「本周」，
   `what` 写本周要做什么，`output` 写做完能拿出什么（看得见的产物）。
6. **闭环四段齐**（R-7）：`closing_loop` 依次写清「识别到什么 → 定位在哪 →
   怎么处置 → 如何回写」。回写指的是结论沉淀成可复用的东西（台账、文档、
   清单），不是「做完就完」。
7. **不确定就写进 `open_questions`**，不要猜。缺信息比错信息好。

# 政策层（R-2）

政策原文口径由系统提供，**你不得自己写政策原文或政策解读**。
你只在 `policy_ids` 里列出与本次诊断真正相关的政策编号（可选子集）。
系统会用原文口径替换你这一段。

# 用语纪律

{_PLAIN_LANGUAGE}

# 输出格式

**只输出一个 JSON 对象**，不要输出 JSON 以外的任何文字（不要 Markdown 代码块、
不要解释、不要前后缀）。结构如下：

{{
  "headline": "一句话结论（不超过 60 字）",
  "findings": [
    {{"id": "f1", "problem": "问题的一句话描述", "stage": "identify|locate|handle|writeback"}}
  ],
  "first_step": {{"when": "本周", "what": "本周做什么", "output": "做完拿出什么"}},
  "actions": [
    {{"finding_id": "f1", "action": "对应动作", "expected_output": "这个动作的产出"}}
  ],
  "closing_loop": {{
    "identified": "识别到什么",
    "located": "定位在哪",
    "handled": "怎么处置",
    "written_back": "如何回写"
  }},
  "policy_ids": ["政策编号"],
  "open_questions": ["待澄清的问题"]
}}

约束：`findings` 至少 1 条、最多 6 条，`id` 从 `f1` 起连续编号；
`findings[].stage` 只能是 `identify`、`locate`、`handle`、`writeback` 之一；
`actions[].finding_id` 必须出现在 `findings` 的 `id` 里。
"""


def _policy_brief() -> list[dict[str, Any]]:
    """给模型看的政策清单（**只给编号与标题**）。

    ★原文口径与解读**不进提示词**：模型只输出编号，原文与解读由服务端装配
    （R-2 fail-closed by construction——模型没有原文可抄，也就无从编造）。
    """
    return [
        {
            "policy_id": entry.policy_id,
            "title": entry.title,
            "doc_number": entry.doc_number,
            "snapshot_date": entry.snapshot_date,
        }
        for entry in POLICY_ENTRIES
    ]


def build_report_prompt(
    *,
    answers: dict[str, Any],
    assessment: dict[str, Any],
    slot_labels: dict[str, str],
) -> str:
    """装配 user 侧提示词（**不含政策原文**，只含编号与标题）。

    输入只有两件：①企业自填答案（已代号化）②首屏政策补贴测算卡（纯规则
    结果）。测算卡是**规则算出来的**，不是模型说的——模型据此叙事，不改写它。
    """
    brief = {
        "policy_snapshot_date": POLICY_SNAPSHOT_DATE,
        "policies": _policy_brief(),
        "policy_note": (
            "政策原文口径与官方出处由系统提供，你只需在 policy_ids 里选编号；"
            "不要在报告里引用或转述政策条文。"
        ),
        "interpretation_count": len(POLICY_INTERPRETATION),
    }
    payload = {
        "answers": answers,
        "answer_labels": slot_labels,
        "assessment": assessment,
        "policy_brief": brief,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
