from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from fde_api.guidance.ai_schema import LIST_FIELDS
from fde_api.guidance.docx_extract import ExtractedBlock, ExtractedPresurvey
from fde_api.guidance.enterprise_vocab import EnterpriseDictionary, load_dictionary

# AI 结构化结论中的三个顶层长文本字段（与 jobs/service 的落库面一致）。
_DRAFT_TEXT_FIELDS = ("customer_vision", "current_phase_objective", "executive_summary")


class SensitiveCredentialDetected(ValueError):
    pass


_CREDENTIAL = re.compile(
    r"(?:密码|口令|密钥|secret|api[_ -]?key|access[_ -]?token|token)\s*[:：=]?\s*"
    r"(?:sk-|ak-|bearer\s+)?[A-Za-z0-9_./+=-]{12,}", re.IGNORECASE
)
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)(?:0\d{2,3}[- ]?)?\d{7,8}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_text(value: str) -> str:
    if _CREDENTIAL.search(value):
        raise SensitiveCredentialDetected("文档中疑似包含密码、密钥或令牌，请移除后重试。")
    value = _EMAIL.sub("[邮箱已脱敏]", value)
    value = _MOBILE.sub("[手机号已脱敏]", value)
    value = _ID_CARD.sub("[证件号已脱敏]", value)
    return _LANDLINE.sub("[电话已脱敏]", value)


def redact_presurvey(extracted: ExtractedPresurvey) -> ExtractedPresurvey:
    return ExtractedPresurvey(tuple(
        ExtractedBlock(block.source_ref, redact_text(block.text))
        for block in extracted.blocks
    ))


def redact_guidance_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    """T-A2：AI 结构化结论落库前的最后一道脱敏（上游 Q1：redact_text 之后、落库之前）。

    串联顺序：``redact_text``（PII 掩码；疑似凭据沿用既有硬拒语义向上抛）→
    企业名替换（词典收录→代号；未收录的模式命中**不替换**，交给
    :func:`collect_redaction_review` 的待复核清单）。词典机械性故障
    （:class:`~fde_api.guidance.enterprise_vocab.EnterpriseDictionaryError`）
    原样向上抛——拍板 6① fail-closed，由调用方硬阻断入库。

    非变异：返回新 dict，入参 draft 不改（重试路径每次从验证产物重新脱敏）。
    """
    dictionary = load_dictionary()
    result: dict[str, Any] = dict(draft)
    for field in _DRAFT_TEXT_FIELDS:
        result[field] = _redact_value(str(draft[field]), dictionary)
    evidence = draft.get("evidence") or {}
    result["evidence"] = {str(key): _redact_value(str(value), dictionary) for key, value in evidence.items()}
    for field in LIST_FIELDS:
        items = draft.get(field) or []
        result[field] = [{**item, "text": _redact_value(str(item["text"]), dictionary)} for item in items]
    return result


def _redact_value(value: str, dictionary: EnterpriseDictionary) -> str:
    # 先 PII 掩码再企业名替换（上游 Q1 钉的顺序）；replace 返回（新文本, 命中
    # 收录名），命中名在入库链无需单独留痕——复核面是派生的。
    text, _hits = dictionary.replace(redact_text(value))
    return text


def collect_redaction_review(data: Mapping[str, Any]) -> list[dict[str, str]]:
    """派生待复核清单（拍板 6①：疑似企业名未收录→放行+待复核）。

    只读推导，不落库不写回——清单是读面（serialize_analysis）与确认闸
    （confirm_analysis）共享的派生事实，与 B#13-C「derived state」同一手法。
    位置定位到字段级（列表条目带下标），复核人按位置打开对应字段人工处置。
    """
    dictionary = load_dictionary()
    hits: list[dict[str, str]] = []

    def scan(location: str, text: str) -> None:
        for match, _start, _end in dictionary.detect(text):
            hits.append({"field": location, "match": match})

    for field in _DRAFT_TEXT_FIELDS:
        scan(field, str(data.get(field) or ""))
    evidence = data.get("evidence")
    if isinstance(evidence, Mapping):
        for key in sorted(evidence, key=str):
            scan(f"evidence.{key}", str(evidence[key] or ""))
    for field in LIST_FIELDS:
        items = data.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items):
                text = item.get("text") if isinstance(item, Mapping) else None
                if isinstance(text, str):
                    scan(f"{field}[{index}].text", text)
    return hits
