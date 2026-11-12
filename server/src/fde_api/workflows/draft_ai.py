"""workflow DAG AI 起草管线（AI 原生化 N3b 本体轮，G-03 消解；ADR v1 §3 实施）。

三拍板（``docs/architecture/AI原生化N3b-DAG-AI起草ADR-v1.md``，交互拍板 2026-11-11）：

- **节点闭集不扩展**（§2）：AI 只产出既有四值 ``NODE_TYPES`` ＋
  ``ALLOWED_NODE_FIELDS`` 白名单字段（同一闭集就是全部可用面）；附契约推荐项
  「AI 起草图须含 ≥1 个 ``human_approval`` 节点」（``AI_DRAFT_REQUIRE_HUMAN_APPROVAL``，
  对齐编译器三节点形与首批模板——把「全自动图绕过人工」的结构风险关死）；
- **返件式草稿零落库**（§3）：本路由**只返回草稿 DAG＋validate 干跑明细**，
  业务域表零写入（事件与 ai_call_audits 照常留痕＝审计面非业务面）；人工采纳走
  既有 ``create_definition``（draft 态，第二道干跑）→ ``publish_definition``
  （admin＝D-2，第三道复验）——「AI 起草 DAG 草稿→validate 干跑→人工
  create_definition 发布」判据的字面落法；
- **并列双来源、闸唯一**（§4）：``compile_plan_workflow`` 确定性编译器缺省腿
  零改动；本模块为旁挂增强腿，**同输入域**（approved/published 方案＋published
  技能显式版本引用＋审批能力白名单，闸码与编译器同码）；三道 validate 干跑
  （AI 预检→create 复验→publish 复验，同一 ``validate_dag_against_registry``）
  ＋两道人工闸，AI 无任何旁路。

机制面沿 N3a 先例零新发明：``execute_ai_prompt`` 单一入口（purpose=
``workflow_dag_draft``＋prompt_version=``workflow-dag-prompt-v1`` 归因三元＋
预算门）＋契约/JSON 失败重试一次 409 ``ai_draft_contract_failed`` ＋输出端兜底
脱敏（词典故障 fail-closed／凭据串拒绝，覆盖 params/when 文本字段）＋确定性
归一（成功稿按 validate_dag 的确定性拓扑序重排、plan_ref 服务端注入、
``dag_sha256`` 指纹）。事件 ``workflow_dag_ai_drafted`` 只带指纹与计数
（**不带 DAG 全文**，原件永不进库——客户资料红线同构）。
"""
from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from fde_api.ai.prompt_registry import version_of

from fde_api.control.ai_server_client import DSHRuntimeError, execute_ai_prompt
from fde_api.guidance.enterprise_dict import DICT_FAILURE_CODE, RedactionConfigError
from fde_api.guidance.redaction import SensitiveCredentialDetected, redact_text_detailed
from fde_api.projects.events import record_event
from fde_api.workflows.definition_service import (
    ALLOWED_NODE_FIELDS,
    APPROVAL_CAPABILITIES,
    NODE_KEY_PATTERN,
    SKILL_REF_PATTERN,
    WorkflowDefinitionError,
    dag_sha256,
    published_skill_refs,
    validate_dag_against_registry,
)
from fde_api.workflows.models import NODE_TYPES

__all__ = [
    "AI_DRAFT_REQUIRE_HUMAN_APPROVAL",
    "MAX_AI_NODES",
    "WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT",
    "WORKFLOW_DAG_PROMPT_VERSION",
    "WORKFLOW_DAG_PURPOSE",
    "WorkflowDraftContractError",
    "build_dag_draft_user_prompt",
    "draft_workflow_dag",
    "validate_workflow_dag_draft",
]

# 提示词版本（N2 归因纪律；ADR §3 钉名 workflow-dag-prompt-v1）。
# N6/G-13：标签唯一权威＝ai/prompt_registry.py（ADR §3 钉名不变；正文改动必同步注册表升版本）。
WORKFLOW_DAG_PROMPT_VERSION = version_of("fde_api.workflows.draft_ai", "WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT")
# 审计 purpose（ai_call_audits NOT NULL CHECK；≤60 字自由文本域；ADR §3 钉名）。
WORKFLOW_DAG_PURPOSE = "workflow_dag_draft"

# AI 起草节点数上界（ADR §3「值本体轮定并钉测试」：首批模板 ≤8 节点、编译器
# 三节点形——24 给足编排余量同时封住供应商输出预算）。
MAX_AI_NODES = 24
# ADR §2 契约推荐项（留痕可推翻）：AI 起草图须含 ≥1 个 human_approval 节点。
AI_DRAFT_REQUIRE_HUMAN_APPROVAL = True

# 瞬时错误退避重试（discovery/N3a 同裁；同步路由面单次退避）。
_TRANSIENT_RETRY_CODES = frozenset({"ai_rate_limited", "ai_timeout", "ai_service_unavailable", "ai_unavailable"})
_RETRY_BACKOFF_SECONDS = 1.0
# 契约/JSON 失败即时重试上限（概率性畸形输出——discovery CONTRACT_RETRY_LIMIT 同值）。
_CONTRACT_RETRY_LIMIT = 1

_WORKFLOW_DAG_TYPES = "/".join(NODE_TYPES)
_WORKFLOW_DAG_FIELDS = "、".join(sorted(ALLOWED_NODE_FIELDS))

WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT = f"""你是制造业交付项目的工作流 DAG 起草器。输入是一个已审阅的交付方案（已代号化）\
与实施技能引用，你只做忠实编排，不得虚构引用。

输出一个 JSON 对象，恰好包含一个键 nodes。

nodes 是数组（1–{MAX_AI_NODES} 个），每项恰好包含基础键：
- key：节点键（1–60 字符、以小写字母开头，仅含小写字母/数字/下划线，全图唯一）；
- type：{_WORKFLOW_DAG_TYPES}（四值闭集）；
- depends_on：字符串数组（依赖节点的 key；无依赖为空数组）；
可选键：
- ref：skill 节点填实施技能引用（<skill_key>@<版本号>，逐字用输入给定的引用）；call/agent 节点填对应白名单引用；
- params：对象（自由文本参数；引用上游产出用 {{{{上游output}}}} 占位符）；
- when：非空表达式字符串或 null；
- output：1–60 字符标识符（供下游 {{{{...}}}} 引用）；
- max_retries：0–10 整数（默认 0）；max_cost_units：非负整数；
- timeout_seconds：1–86400 整数；input_schema/output_schema：JSON Schema 对象；
- failure_class：retryable/fatal/needs_human；plan_ref 由系统注入，不需要你写。

硬性纪律：
1. 图中**至少 1 个 type=human_approval 的节点**（人工确认点不可省略），其 capability
逐字用输入给定的审批能力；human_approval 节点不接受 ref；
2. type 不得使用四值闭集之外的任何值；节点不得出现列出的字段之外的任何字段；
3. params/when 里的占位符只能是 {{{{project_id}}}}/{{{{run_id}}}}/{{{{initiated_by_user_id}}}}
或某个上游节点的 output；不得引用不存在的节点或自环；
4. 只输出 JSON，不要输出任何其他文字；正文不得包含凭据（密码/密钥/令牌）。"""


class WorkflowDraftContractError(ValueError):
    """AI 起草输出契约违规（任一违规整批拒绝——重试一次仍违 ⇒ 409）。"""

    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code, self.path, self.message = code, path, message


def validate_workflow_dag_draft(payload: object) -> list[dict[str, Any]]:
    """AI 输出形状闸（ADR §3 机制 2 上半）：顶层形状闭集＋节点形状闭集＋契约推荐项。

    只做 AI 特有约束（形状/闭集/人工确认点）；registry 对账（published 技能/
    在册 agent/审批能力/占位符可达性/环检测）**不在此重复**——交
    ``validate_dag_against_registry`` 全尺校验（同一闸尺，零第二套逻辑）。
    返回节点列表（原样形状，未归一）。
    """
    if not isinstance(payload, dict) or set(payload) != {"nodes"}:
        raise WorkflowDraftContractError("invalid_draft", "", "AI 返回的起草结果字段不完整（须为 {nodes}）。")
    raw_nodes = payload["nodes"]
    if not isinstance(raw_nodes, list) or not raw_nodes or len(raw_nodes) > MAX_AI_NODES:
        raise WorkflowDraftContractError(
            "invalid_nodes", "nodes", f"节点数组格式不正确（1–{MAX_AI_NODES} 个）。"
        )
    nodes: list[dict[str, Any]] = []
    has_human_approval = False
    for index, raw in enumerate(raw_nodes):
        path = f"nodes[{index}]"
        if not isinstance(raw, dict):
            raise WorkflowDraftContractError("node_not_object", path, "节点必须是对象。")
        extra = set(raw) - ALLOWED_NODE_FIELDS
        if extra:
            raise WorkflowDraftContractError(
                "unknown_field", path, f"节点不支持字段：{'、'.join(sorted(extra))}。"
            )
        key = raw.get("key")
        if not isinstance(key, str) or not NODE_KEY_PATTERN.fullmatch(key):
            raise WorkflowDraftContractError(
                "invalid_node_key", f"{path}.key",
                "key 须为 1–60 字符、以小写字母开头，仅含小写字母/数字/下划线。",
            )
        node_type = raw.get("type")
        if node_type not in NODE_TYPES:
            raise WorkflowDraftContractError(
                "unknown_node_type", f"{path}.type",
                f"节点 type 须为 {_WORKFLOW_DAG_TYPES}（闭集不扩展——ADR 拍板一）。",
            )
        if node_type == "human_approval":
            has_human_approval = True
        nodes.append(raw)
    if AI_DRAFT_REQUIRE_HUMAN_APPROVAL and not has_human_approval:
        raise WorkflowDraftContractError(
            "human_approval_required", "nodes",
            "AI 起草图必须包含至少 1 个 human_approval 节点（ADR 拍板一契约推荐项）。",
        )
    return nodes


def build_dag_draft_user_prompt(
    plan: dict[str, Any], *, implementation_skill_ref: str, approval_capability: str
) -> str:
    """拼装 DAG 起草的用户提示词（确定性：条目按 serialize_plan 序＝sort_order）。

    输入面=已代号化的方案行数据＋调用方白名单实参——零外部文字进模型。
    """
    title = str(plan.get("title") or "未命名交付方案").replace("{{", "").replace("}}", "")
    raw_items = plan.get("items")
    items: list[Any] = list(raw_items) if isinstance(raw_items, list) else []
    lines = [f"【交付方案】《{title[:200]}》（status={plan.get('status')}，version={plan.get('version')}）", ""]
    lines.append("【方案条目】")
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(f"- [{item.get('item_type')}] {str(item.get('title') or '待补')[:200]}")
    if not items:
        lines.append("（无条目）")
    lines += [
        "",
        f"【实施技能引用】（skill 节点 ref 逐字使用）：{implementation_skill_ref}",
        f"【审批能力】（human_approval 节点 capability 逐字使用）：{approval_capability}",
        "",
        "【任务】为以上方案起草执行工作流 DAG 草稿（对齐三节点形：方案确认→实施→验收确认；"
        "可按方案条目增补实施/确认节点），按系统指令输出的 JSON 契约返回。",
    ]
    return "\n".join(lines)


def _redact_value(value: Any, *, project_code: str, sink: list[dict[str, Any]]) -> Any:
    """输出端兜底脱敏（discovery/N3a 第③层同构）：命中词典/疑似均替换并记复核。"""
    if isinstance(value, str):
        result = redact_text_detailed(value, project_code=project_code)
        for suspect in result.suspects:
            sink.append({"name": suspect.name, "occurrences": suspect.occurrences, "matched_dict": False})
        for name in result.replaced:
            sink.append({"name": name, "occurrences": 1, "matched_dict": True})
        return result.text
    if isinstance(value, list):
        return [_redact_value(item, project_code=project_code, sink=sink) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, project_code=project_code, sink=sink) for key, item in value.items()}
    return value


def _finalize_nodes(
    nodes: list[dict[str, Any]], *, session: Session, project_code: str, plan_id: str
) -> tuple[dict[str, Any], Any]:
    """归一：脱敏 params/when → plan_ref 服务端注入 → 全尺校验 → 拓扑序重排。

    全尺校验（``validate_dag_against_registry``）跑在**最终**草稿上（脱敏与
    plan_ref 注入之后）——预检明细如实描述人工将采纳的图；errors 非空按契约
    失败处理（同尺闸不因来源放松）。
    """
    redaction_entries: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    for node in nodes:
        item = dict(node)
        if "params" in item:
            item["params"] = _redact_value(item.get("params"), project_code=project_code, sink=redaction_entries)
        if "when" in item:
            item["when"] = _redact_value(item.get("when"), project_code=project_code, sink=redaction_entries)
        item["plan_ref"] = plan_id  # 服务端权威注入（AI 不参与——与编译器三节点形对齐）
        prepared.append(item)
    dag: dict[str, Any] = {"nodes": prepared}
    validation = validate_dag_against_registry(session, dag)
    if validation.errors:
        first = validation.errors[0]
        raise WorkflowDraftContractError(
            "dag_invalid", first.node_key or "nodes",
            f"AI 起草图未通过 registry 全尺校验：{first.message}",
        )
    by_key = {node["key"]: node for node in prepared}
    dag = {"nodes": [by_key[key] for key in validation.order]}
    return dag, (validation, redaction_entries)


def _run_dag_ai(
    *, session: Session, user_id: str, project_id: str, project_code: str,
    prompt: str, execution_id: str, plan_id: str,
) -> tuple[dict[str, Any], Any, str | None]:
    """完整起草调用（克隆 N3a ``_run_draft_ai`` 纪律）。

    概率性契约/JSON/全尺失败即时重试一次；瞬时错误退避重试一次。成功返回
    （最终 dag, (validation, redaction_entries), 模型名）；不可恢复失败上抛
    ``WorkflowDraftContractError`` / ``json.JSONDecodeError`` / ``DSHRuntimeError``。
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            answer: Any = execute_ai_prompt(
                user_id=user_id,
                prompt=prompt,
                system_prompt=WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT,
                use_tools=False,
                project_id=project_id,
                execution_id=execution_id,
                purpose=WORKFLOW_DAG_PURPOSE,
                prompt_version=WORKFLOW_DAG_PROMPT_VERSION,
                return_metadata=True,
            )
            if not isinstance(answer, dict):
                answer = dict(text=answer, model={})
            text = answer.get("text")
            payload = json.loads(text) if isinstance(text, str) else text
            nodes = validate_workflow_dag_draft(payload)
            dag, (validation, redaction_entries) = _finalize_nodes(
                nodes, session=session, project_code=project_code, plan_id=plan_id,
            )
            model_name = str(((answer.get("model") or {}).get("name") or "")) or None
            return dag, (validation, redaction_entries), model_name
        except (json.JSONDecodeError, WorkflowDraftContractError):
            if attempts > _CONTRACT_RETRY_LIMIT:
                raise
            # 概率性契约/JSON/全尺失败：立即重试（discovery 同裁，留痕走异常冒泡）
        except DSHRuntimeError as error:
            if error.code not in _TRANSIENT_RETRY_CODES or attempts > _CONTRACT_RETRY_LIMIT:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS)


def draft_workflow_dag(
    session: Session,
    *,
    actor,
    project,
    plan: dict[str, Any],
    implementation_skill_ref: str,
    approval_capability: str,
) -> dict[str, Any]:
    """AI 起草 DAG 草稿（返件式：**业务域零写入**——只返回草稿＋干跑明细）。

    前置闸（同 ``compile_plan_workflow`` 输入域，闸码同码；全部在 AI 调用前——
    零烧费）：方案须 approved/published（409 ``plan_not_approved``）；skill 引用
    须 ``<key>@<版本号>`` 形且在 published 白名单（409 ``invalid_skill_ref`` /
    422 ``skill_ref_not_published``）；capability ∈ ``APPROVAL_CAPABILITIES``
    （409 ``invalid_capability``）。

    失败语义（fail-closed 家族一致）：契约/JSON/全尺违规 ⇒ 重试一次仍违 ⇒
    409 ``ai_draft_contract_failed``（零写入）；词典机制故障 ⇒ 422
    ``pseudonym_dict_unavailable``；凭据串 ⇒ 422 ``sensitive_credential_detected``。

    成功 ⇒ 响应携带 ``{draft: {dag_json, validate: {valid/errors/warnings/order},
    dag_sha256, plan_ref, implementation_skill_ref}}``；审计面照常留痕：
    ``workflow_dag_ai_drafted`` 事件（purpose/prompt_version/model/dag_sha256/
    node_count，**不带 DAG 全文**）＋ ai_call_audits（单一入口自记）。
    人工采纳走既有 ``create_definition`` → ``publish_definition``（闸不因来源放松）。
    """
    if plan.get("status") not in ("approved", "published"):
        raise WorkflowDefinitionError("plan_not_approved", "只接受 approved/published 交付方案。", 409)
    if not isinstance(implementation_skill_ref, str) or SKILL_REF_PATTERN.fullmatch(implementation_skill_ref) is None:
        raise WorkflowDefinitionError(
            "invalid_skill_ref", "implementation_skill_ref 须为 <skill_key>@<版本号>（published 显式版本）。", 409,
        )
    if approval_capability not in APPROVAL_CAPABILITIES:
        raise WorkflowDefinitionError(
            "invalid_capability",
            f"capability 不在工作流审批白名单（system.* 不开放）：{approval_capability!r}。",
            409,
        )
    published_refs = published_skill_refs(session)
    if implementation_skill_ref not in published_refs:
        raise WorkflowDefinitionError(
            "skill_ref_not_published",
            f"implementation_skill_ref 引用的技能版本不存在或未发布：{implementation_skill_ref}。",
            422,
            {"ref": implementation_skill_ref},
        )
    prompt = build_dag_draft_user_prompt(
        plan, implementation_skill_ref=implementation_skill_ref, approval_capability=approval_capability,
    )
    execution_id = f"workflow-dag:{project.id}:{uuid4().hex[:8]}"
    try:
        dag, (validation, redaction_entries), model_name = _run_dag_ai(
            session=session, user_id=actor.id, project_id=project.id,
            project_code=project.enterprise_code, prompt=prompt, execution_id=execution_id,
            plan_id=str(plan.get("id") or ""),
        )
    except (WorkflowDraftContractError, json.JSONDecodeError) as error:
        detail = getattr(error, "code", None) or "invalid_json"
        raise WorkflowDefinitionError(
            "ai_draft_contract_failed",
            f"AI 起草结果未通过契约校验（已自动重试仍失败：{detail}），请重跑或更换模型。",
            409,
        ) from error
    except SensitiveCredentialDetected:
        raise WorkflowDefinitionError(
            "sensitive_credential_detected",
            "AI 起草的节点参数疑似包含凭据，为守住「凭据不落库」红线已整批拒绝。请重跑。",
            422,
        ) from None
    except RedactionConfigError:
        raise WorkflowDefinitionError(
            DICT_FAILURE_CODE,
            "词典机制性故障导致 AI 起草失败（fail-closed 已阻断）。请联系管理员修复词典配置后重跑。",
            422,
        ) from None
    # ── 审计面（唯一写入：事件＋ai_call_audits；业务域表零写入）──
    final_sha = dag_sha256(dag)
    record_event(
        session,
        actor,
        "workflow_dag_ai_drafted",
        project,
        {
            "purpose": WORKFLOW_DAG_PURPOSE,
            "prompt_version": WORKFLOW_DAG_PROMPT_VERSION,
            "model": model_name,
            "dag_sha256": final_sha,
            "node_count": len(dag["nodes"]),
            "plan_ref": str(plan.get("id") or ""),
            "implementation_skill_ref": implementation_skill_ref,
            "approval_capability": approval_capability,
            **({"redaction_entries": redaction_entries} if redaction_entries else {}),
        },
    )
    return {
        "draft": {
            "dag_json": dag,
            "validate": {
                "valid": validation.ok,
                "errors": [issue.as_dict() for issue in validation.errors],
                "warnings": [issue.as_dict() for issue in validation.warnings],
                "order": list(validation.order),
            },
            "dag_sha256": final_sha,
            "plan_ref": str(plan.get("id") or ""),
            "implementation_skill_ref": implementation_skill_ref,
        },
        "model": model_name,
        "prompt_version": WORKFLOW_DAG_PROMPT_VERSION,
    }
