"""生成提示词「禁行业黑话」条款钉（A端事件根治轮，2026-11-10）。

背景：somwyn 调研表生成出现「A端目标客户」——源文档（落地方案书）的行业黑话
被 AI 原样学舌进客户可见产物。拍板（蔡工，2026-11-10）：生成提示词加「用语纪律」
条款——平实中文、禁行业黑话、必要术语括号解释。

本文件钉住三个生成面都携带该条款：
- 调研表生成 ``ai/research_form_prompt.SYSTEM_PROMPT``（J-1 白名单模块常量，钉内容不破形状）
- 预调研分析 ``guidance/ai_prompt.build_presurvey_analysis_messages``（内联字面量）
- DOCX 分析 ``guidance/ai_prompt.build_kimi_presurvey_analysis_messages``（内联字面量）

行业模板面（industry_template_prompt）未接：治理面 admin 人工维护文本，
与 A 端事件链路无关（诚实边界，CHANGELOG 同轮注记）。
"""

from fde_api.ai.research_form_prompt import SYSTEM_PROMPT
from fde_api.guidance.ai_prompt import (
    build_kimi_presurvey_analysis_messages,
    build_presurvey_analysis_messages,
)
from fde_api.guidance.docx_extract import ExtractedBlock, ExtractedPresurvey

ANCHOR_JARGON = "行业黑话"
ANCHOR_EXPLAIN = "括号补一句平实中文解释"
ANCHOR_EXAMPLES = "A端/B端/C端"


def test_research_form_system_prompt_carries_plain_language_clause():
    assert ANCHOR_JARGON in SYSTEM_PROMPT
    assert ANCHOR_EXPLAIN in SYSTEM_PROMPT
    assert ANCHOR_EXAMPLES in SYSTEM_PROMPT


def test_presurvey_analysis_system_prompt_carries_plain_language_clause():
    presurvey = ExtractedPresurvey(
        blocks=(ExtractedBlock("paragraph-1", "客户希望上线智能询盘分配。"),)
    )
    messages = build_presurvey_analysis_messages(presurvey)
    system = messages[0]["content"]
    assert ANCHOR_JARGON in system
    assert ANCHOR_EXPLAIN in system
    assert ANCHOR_EXAMPLES in system


def test_kimi_docx_analysis_system_prompt_carries_plain_language_clause():
    messages = build_kimi_presurvey_analysis_messages("文档正文", "kimi-file:test-1")
    system = messages[0]["content"]
    assert ANCHOR_JARGON in system
    assert ANCHOR_EXPLAIN in system
    assert ANCHOR_EXAMPLES in system
