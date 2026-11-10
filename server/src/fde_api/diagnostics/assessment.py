"""首屏「政策补贴测算」卡——**纯规则、零 AI、零成本**。

这是漏斗的钩子位（P-1）：企业填 5 题即得结果，**免注册即时可见**；不烧任何
token，也不依赖模型可用性。

三条硬纪律（写进代码而不是只写进文档）：

1. **不落金额**——弹药库五条均未披露具体补贴额度，任何金额都是编造数字
   （R-4「未溯源数字 fail-closed」）。本模块只算**资格与准备度**。
2. **不落分数**——R-1「报告模板去掉无溯源分值」：没有可溯源行业基准前，
   只给定性档位，不给「XX/100」。
3. **原文口径与我方解读分层**——输出里 ``original_wording`` 是政策原文（逐字），
   ``interpretation`` 标注「我方解读」；两者不混写。

规则本身是**确定性函数**：同样的答案必得同样的结果（可测、可复现）。
"""
from __future__ import annotations

from typing import Any

from fde_api.diagnostics.policy_data import (
    INTERPRETATION_BY_POLICY_ID,
    POLICY_BY_ID,
    POLICY_CORRECTIONS,
    POLICY_SNAPSHOT_DATE,
    PolicyInterpretation,
)

# 定性档位（**不是分数**）
TIER_READY = "具备申报基础"
TIER_DIRECTION = "方向契合但缺前提"
TIER_NOT_READY = "尚不满足申报前提"
TIER_PREPARE = "先做基础准备"

TIERS: tuple[str, ...] = (TIER_READY, TIER_DIRECTION, TIER_NOT_READY, TIER_PREPARE)

_DIGITALIZATION_RUNNING = "已有在推进的数字化改造"
_DIGITALIZATION_STALLED = "做过但停滞"

_INTERPRETATION_LABEL = "我方解读"
_ORIGINAL_LABEL = "原文口径"


def _text(answers: dict[str, Any], key: str) -> str:
    value = answers.get(key)
    return value.strip() if isinstance(value, str) else ""


def _list(answers: dict[str, Any], key: str) -> list[str]:
    value = answers.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _matches(interpretation: PolicyInterpretation, answers: dict[str, Any]) -> bool:
    """适用性判定：行业 + 资质。"""
    industry = _text(answers, "org.industry")
    if interpretation.applicable_industries and industry not in interpretation.applicable_industries:
        return False
    qualifications = set(_list(answers, "pol.qualification"))
    if interpretation.requires_qualifications:
        return all(item in qualifications for item in interpretation.requires_qualifications)
    return True


def _tier(matched: list[PolicyInterpretation], answers: dict[str, Any]) -> str:
    digitalization = _text(answers, "pol.digitalization_project")
    matched_ids = {item.policy_id for item in matched}
    if "miit_lianyue_2026_343" in matched_ids and digitalization == _DIGITALIZATION_RUNNING:
        return TIER_READY
    if len(matched) >= 2 and digitalization in (_DIGITALIZATION_RUNNING, _DIGITALIZATION_STALLED):
        return TIER_DIRECTION
    if len(matched) >= 2:
        return TIER_NOT_READY
    return TIER_PREPARE


def _next_actions(
    tier: str,
    matched: list[PolicyInterpretation],
    answers: dict[str, Any],
) -> list[str]:
    declaration = _text(answers, "pol.declaration_history")
    actions: list[str] = []

    if tier == TIER_READY:
        actions.append(
            "对照 2026 年版《智能工厂梯度培育要素条件》逐项自查"
            "（AI 技术应用场景比例是硬指标）"
        )
        actions.append("向本地工信主管部门确认梯度培育申报口径、时间窗与所需材料")
        actions.append("选定具备行业模型调优与数据治理能力的服务商（279 号第十四条口径）")
    elif tier == TIER_DIRECTION:
        actions.append("先把手上的数字化改造收口——看 AI 应用场景能不能被数出来")
        actions.append("向本地工信主管部门确认申报口径与时间窗")
        actions.append("梳理资质缺口，缺哪项补哪项")
    elif tier == TIER_NOT_READY:
        actions.append("先启动最小可行的数字化改造（能出数、可验收的场景优先）")
        actions.append("把资质补齐作为并行事项推进")
        actions.append("记录当前基线（数量 / 周期 / 耗时），申报与后续诊断都要用")
    else:
        actions.append("先做一次现状盘点：有哪些系统、数据放在哪、谁在维护")
        actions.append("挑一个高频、可量化的小场景先跑通")
        actions.append("留存现状记录，作为后续申报与诊断的基线")

    if declaration == "申报过但未通过":
        actions.insert(0, "先拿到上次申报的退回意见——材料可以复用，问题要对着改")
    elif declaration == "申报并通过":
        actions.insert(0, "基于既有申报材料继续，后续新政策的申报响应会更快")
    elif declaration == "不清楚":
        actions.append("确认一下自己有没有申报过——这决定后续是从头报还是接续报")

    verification = [step for item in matched for step in item.verification_steps]
    for step in verification:
        if step not in actions:
            actions.append(step)
    return actions[:5]


def compute_assessment(answers: dict[str, Any]) -> dict[str, Any]:
    """由首屏答案算出政策补贴测算卡（纯规则、确定性）。

    ``answers`` 是首屏 5 个槽位的键值对。缺失槽位按「未知」处理——**不猜**。
    """
    matched = [
        interpretation
        for interpretation in INTERPRETATION_BY_POLICY_ID.values()
        if _matches(interpretation, answers)
    ]
    # 稳定排序：按政策条目在弹药库里的次序（dict 保序），保证输出可复现。
    ordered = sorted(
        matched,
        key=lambda item: list(INTERPRETATION_BY_POLICY_ID).index(item.policy_id),
    )
    tier = _tier(ordered, answers)

    policy_items: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for interpretation in ordered:
        entry = POLICY_BY_ID[interpretation.policy_id]
        policy_items.append(
            {
                "policy_id": entry.policy_id,
                "label": interpretation.label,
                "title": entry.title,
                "doc_number": entry.doc_number,
                "issued_on": entry.issued_on,
                "original_wording": entry.original_wording,
                "original_basis": _ORIGINAL_LABEL,
                "official_source_url": entry.official_source_url,
                "snapshot_date": entry.snapshot_date,
                "interpretation_basis": _INTERPRETATION_LABEL,
                "interpretation_note": interpretation.note,
            }
        )
        for requirement in interpretation.preparation_requirements:
            missing.append(
                {
                    "policy_id": entry.policy_id,
                    "requirement": requirement,
                    "basis": _INTERPRETATION_LABEL,
                }
            )

    return {
        "readiness_tier": tier,
        "matched_policies": policy_items,
        "missing_requirements": missing,
        "next_actions": _next_actions(tier, ordered, answers),
        "policy_snapshot_date": POLICY_SNAPSHOT_DATE,
        "basis_labels": {"original": _ORIGINAL_LABEL, "interpretation": _INTERPRETATION_LABEL},
        "disclaimers": [
            "本卡只算资格与准备度，不涉及补贴金额——政策原文未披露具体额度，"
            "任何金额都会是编造。",
            "政策口径按原文引用；「我方解读」已单独标注，不与原文混写。",
            f"政策快照日期 {POLICY_SNAPSHOT_DATE}；快照超 30 天须重核。",
            "本卡为规则测算，不构成申报结论——申报口径与时间窗以当地主管部门为准。",
        ],
        "policy_corrections": list(POLICY_CORRECTIONS),
    }
