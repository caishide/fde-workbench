from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict, cast


CLASSIFICATIONS = {"customer_stated", "ai_synthesized", "ai_inferred", "open_question", "human_added"}
LIST_FIELDS = (
    "key_business_problems", "priority_departments", "priority_roles", "priority_processes",
    "success_criteria", "out_of_scope", "data_security_redlines",
    "systems_and_deployment_constraints", "assumptions", "open_questions", "next_actions",
)
# PRD F1（架构方案 §3.2 ProblemItem 增强，goal-d1 S0-2）：问题清单条目可附
# 可签约优先级（severity）与 FDE 交付模块映射（module）。仅对
# key_business_problems 放开这两个可选键——其余 10 个字段维持精确键集，
# 防止 AI 输出漂移面扩大（human 编辑路径经 PATCH 存 JSON，同样放行）。
PROBLEM_FIELD = "key_business_problems"
SEVERITIES = ("high", "medium", "low")
ITEM_OPTIONAL_KEYS = {"severity", "module"}


class GuidanceItem(TypedDict):
    text: str
    classification: Literal["customer_stated", "ai_synthesized", "ai_inferred", "open_question", "human_added"]
    source_refs: list[str]
    confirmed: bool
    severity: NotRequired[Literal["high", "medium", "low"]]
    module: NotRequired[str]


class GuidanceDraft(TypedDict):
    customer_vision: str
    current_phase_objective: str
    executive_summary: str
    evidence: dict[str, str]


class GuidanceContractError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code, self.path, self.message = code, path, message


def validate_guidance_output(value: object, *, source_refs: set[str]) -> dict[str, Any]:
    required = {"customer_vision", "current_phase_objective", "executive_summary", "evidence", *LIST_FIELDS}
    if not isinstance(value, dict) or set(value) != required:
        raise GuidanceContractError("invalid_guidance", "", "AI 返回的项目指引字段不完整。")
    result: dict[str, Any] = {}
    for field in ("customer_vision", "current_phase_objective", "executive_summary"):
        text = value.get(field)
        if not isinstance(text, str) or not text.strip() or len(text) > 10_000:
            raise GuidanceContractError("invalid_text", field, f"{field} 内容为空或过长。")
        result[field] = text.strip()
    evidence = value.get("evidence")
    if not isinstance(evidence, dict) or any(ref not in source_refs for ref in evidence):
        raise GuidanceContractError("unknown_source_ref", "evidence", "引用了不存在的原文位置。")
    result["evidence"] = {str(k): str(v)[:1000] for k, v in evidence.items()}
    for field in LIST_FIELDS:
        raw_items = value.get(field)
        if not isinstance(raw_items, list) or len(raw_items) > 100:
            raise GuidanceContractError("invalid_items", field, f"{field} 格式不正确。")
        items: list[GuidanceItem] = []
        for index, raw in enumerate(raw_items):
            path = f"{field}[{index}]"
            base_keys = {"text", "classification", "source_refs", "confirmed"}
            allowed_keys = base_keys | (ITEM_OPTIONAL_KEYS if field == PROBLEM_FIELD else set())
            if not isinstance(raw, dict) or not base_keys <= set(raw) <= allowed_keys:
                raise GuidanceContractError("invalid_item", path, "项目指引条目格式不正确。")
            text, classification, refs, confirmed = raw["text"], raw["classification"], raw["source_refs"], raw["confirmed"]
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise GuidanceContractError("invalid_text", f"{path}.text", "条目内容为空或过长。")
            if classification not in CLASSIFICATIONS or type(confirmed) is not bool:
                raise GuidanceContractError("invalid_classification", path, "条目分类或确认状态无效。")
            if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                raise GuidanceContractError("invalid_source_ref", path, "原文引用格式不正确。")
            if any(ref not in source_refs for ref in refs):
                raise GuidanceContractError("unknown_source_ref", path, "引用了不存在的原文位置。")
            if classification not in {"open_question", "human_added"} and not refs:
                raise GuidanceContractError("missing_source_ref", path, "事实和 AI 判断必须引用原文。")
            item: dict[str, Any] = {"text": text.strip(), "classification": classification, "source_refs": refs, "confirmed": confirmed}
            if field == PROBLEM_FIELD:
                severity = raw.get("severity")
                if severity is not None:
                    if severity not in SEVERITIES:
                        raise GuidanceContractError("invalid_severity", path, "severity 仅可为 high/medium/low。")
                    item["severity"] = severity
                module = raw.get("module")
                if module is not None:
                    if not isinstance(module, str) or not module.strip() or len(module.strip()) > 80:
                        raise GuidanceContractError("invalid_module", path, "module 必须是 1–80 字的交付模块名。")
                    item["module"] = module.strip()
            items.append(cast(GuidanceItem, item))
        result[field] = items
    return result
