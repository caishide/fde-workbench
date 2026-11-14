"""本体注册表路由（V3 T-O2/T-O3/T-I1；设计 ontology-registry-v1 §4）。

- ``GET  /api/v1/projects/<id>/ontology/terms``（can_view，T-O1 的公开读面）：
  术语清单，``?q=`` 大小写不敏感匹配规范名或别名（别名命中返回属主行）。
- ``GET  /api/v1/projects/<id>/ontology/terms/<term_id>/impact``（can_view，
  V3 T-I1 影响分析）：引用该术语的研究客体/邻接边/表单清单——名字域纽带
  （规范名 ∪ 别名 ∪ 并入来源名），变集拍板前的人工影响面评审。
- ``GET  /api/v1/projects/<id>/ontology/relation-types``（can_view）：列出对项目
  生效的类型（全局 ∪ 项目内，项目内遮蔽同名全局）。
- ``GET  /api/v1/ontology/relation-types``（require_auth，T-O2c 全局只读面）：
  全局注册类型行（project_id 为空，不含项目内行）——无项目上下文的消费方
  （行业模板/调研定义编辑器）拉取注册类型选项；人工路径，不进 api_catalog。
- ``POST /api/v1/projects/<id>/ontology/relation-types``（can_manage）：登记类型；
  ``scope=global`` 另需管理员。人工路径——**有意不进 api_catalog**（AI 候选
  走 change_set）。
- ``POST /api/v1/projects/<id>/ontology/relation-types/<id>/retire``（can_manage）：
  停用类型（禁新边、存量边只读）。设计 §4 的表格未列本条，是为让 §5 用例 7
  的「retired 后建边 409」在人工路径上可达——偏差见 backlog T-O2 实施记录。
- 变更集（T-O3，AI 候选唯一入口的人工评审面）：
  ``POST   …/ontology/change-sets``（提出，draft，confirm 前不物化）、
  ``GET    …/ontology/change-sets``（清单，?status= 过滤）、
  ``GET    …/ontology/change-sets/<id>``（详情：载荷 + diff 摘要 + 指纹）、
  ``POST   …/ontology/change-sets/<id>/submit``（draft→in_review，算 base 指纹；
  设计 §4 未列本条，状态机的并发防护锚点——偏差见 backlog T-O3 实施记录）、
  ``POST   …/ontology/change-sets/<id>/confirm``（拍板：指纹复核 + 单事务逐项
  物化；验收分离，拍板人 ≠ 提交人）、
  ``POST   …/ontology/change-sets/<id>/reject``（否决，留 reason）。
  七条全部**有意不进 api_catalog**（同 signoff 纪律：AI 不可触达拍板路径）。
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from fde_api.auth.decorators import require_auth
from fde_api.errors import error_response
from fde_api.extensions import db
from fde_api.ontology import service
from fde_api.ontology.evidence_pack import (
    EvidencePackError,
    export_evidence_pack,
    import_annotation_receipt,
)
from fde_api.ontology.glossary_promotion import (
    GlossaryPromotionError,
    list_promoted_terms,
    promote_glossary_terms,
)
from fde_api.ontology.governance import (
    GovernanceError,
    build_review_queue,
    build_upgrade_blast_radius,
)

ontology_blueprint = Blueprint(
    "project_ontology", __name__, url_prefix="/api/v1/projects/<project_id>/ontology"
)


@ontology_blueprint.errorhandler(service.OntologyServiceError)
def service_error(error):
    return error_response(error.code, error.message, error.status)


@ontology_blueprint.errorhandler(EvidencePackError)
def evidence_pack_error(error):
    return error_response(error.code, str(error), error.status)


@ontology_blueprint.errorhandler(GovernanceError)
def governance_error(error):
    return error_response(error.code, str(error), error.status)


@ontology_blueprint.errorhandler(GlossaryPromotionError)
def glossary_promotion_error(error):
    return error_response(error.code, str(error), error.status)


global_ontology_blueprint = Blueprint(
    "global_ontology", __name__, url_prefix="/api/v1/ontology"
)


@global_ontology_blueprint.errorhandler(service.OntologyServiceError)
def global_service_error(error):
    return error_response(error.code, error.message, error.status)


@global_ontology_blueprint.get("/relation-types")
@require_auth
def list_global_relation_types():
    """全局注册类型只读面（T-O2c）：?kind= 按种类过滤，全状态返回。

    无项目上下文的消费方（行业模板/调研定义编辑器）从此面拉取注册类型
    选项；只收全局行——项目内类型只对本项目生效，进全局模板会在其他项目
    实例化时落空。人工路径——有意不进 api_catalog（沿 T-O2 纪律）。
    """
    data = service.list_global_relation_types(kind=request.args.get("kind"))
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/terms")
@require_auth
def list_terms(project_id: str):
    """术语只读面（can_view）：?q= 匹配规范名或别名。"""
    data = service.list_project_terms(
        actor=g.current_user,
        project_id=project_id,
        q=request.args.get("q"),
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/terms/<term_id>/impact")
@require_auth
def term_impact(project_id: str, term_id: str):
    """术语影响分析（can_view）：引用它的 subjects/links/forms 清单。

    人工评审读面——有意不进 api_catalog（沿 T-O3 纪律：本体治理面 AI
    不可直达）。
    """
    data = service.impact_project_term(
        actor=g.current_user,
        project_id=project_id,
        term_id=term_id,
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/relation-types")
@require_auth
def list_relation_types(project_id: str):
    """类型注册表（can_view）：?kind= 按种类过滤（subject_type / link_type）。"""
    data = service.list_project_relation_types(
        actor=g.current_user,
        project_id=project_id,
        kind=request.args.get("kind"),
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/relation-types")
@require_auth
def create_relation_type(project_id: str):
    """登记类型（can_manage；scope=global 另需管理员）。人工路径——不进 api_catalog。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise service.OntologyServiceError(
            "invalid_request", "请求内容必须为 JSON 对象。", 400
        )
    data = service.create_relation_type(
        actor=g.current_user, project_id=project_id, payload=payload
    )
    return jsonify({"data": data, "error": None}), 201


@ontology_blueprint.post("/relation-types/<relation_type_id>/retire")
@require_auth
def retire_relation_type(project_id: str, relation_type_id: str):
    """停用类型（can_manage）：禁新边、存量边只读。"""
    data = service.retire_project_relation_type(
        actor=g.current_user,
        project_id=project_id,
        relation_type_id=relation_type_id,
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/candidates/generate")
@require_auth
def generate_candidates(project_id: str):
    """从已接受访谈事实生成本体术语候选（can_manage，V3.1 P0-2）。

    AI 只创建候选（change-set draft，captured_from=discovery:<id>）；采纳
    走既有 submit→confirm 人工管线（决策分离/指纹闸/事务物化全复用）。
    响应附跳过清单与跨项目同名告警（D-1 只读）。
    """
    payload = request.get_json(silent=True) or {}
    extraction_id = payload.get("extraction_id") if isinstance(payload, dict) else None
    if not isinstance(extraction_id, str) or not extraction_id:
        raise service.OntologyServiceError(
            "invalid_request", "extraction_id 必填。", 400
        )
    data = service.generate_discovery_candidates(
        actor=g.current_user,
        project_id=project_id,
        extraction_id=extraction_id,
    )
    return jsonify({"data": data, "error": None}), 201 if data.get("created") else 200


@ontology_blueprint.get("/candidates")
@require_auth
def list_candidates(project_id: str):
    """发现域候选变更集清单（can_view）：captured_from=discovery:% 投影。"""
    data = service.list_discovery_candidates(
        actor=g.current_user, project_id=project_id, limit=50
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/change-sets")
@require_auth
def list_change_sets(project_id: str):
    """变更集清单（can_view）：?status= 按状态过滤。"""
    data = service.list_project_change_sets(
        actor=g.current_user,
        project_id=project_id,
        status=request.args.get("status"),
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/change-sets/<change_set_id>")
@require_auth
def get_change_set(project_id: str, change_set_id: str):
    """变更集详情（can_view）：diff 评审读载荷、摘要与 base 指纹。"""
    data = service.get_project_change_set(
        actor=g.current_user,
        project_id=project_id,
        change_set_id=change_set_id,
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/change-sets")
@require_auth
def create_change_set(project_id: str):
    """提出候选变更集（can_manage）→ draft：confirm 前不物化（§5 用例 1）。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise service.OntologyServiceError(
            "invalid_request", "请求内容必须为 JSON 对象。", 400
        )
    data = service.propose_project_change_set(
        actor=g.current_user, project_id=project_id, payload=payload
    )
    return jsonify({"data": data, "error": None}), 201


@ontology_blueprint.post("/change-sets/<change_set_id>/submit")
@require_auth
def submit_change_set(project_id: str, change_set_id: str):
    """draft → in_review（can_manage）：计算 base 指纹（并发防护锚点）。"""
    data = service.submit_project_change_set(
        actor=g.current_user,
        project_id=project_id,
        change_set_id=change_set_id,
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/change-sets/<change_set_id>/confirm")
@require_auth
def confirm_change_set(project_id: str, change_set_id: str):
    """拍板确认（can_manage 且 ≠ 提交人）：指纹复核 + 单事务逐项物化。"""
    data = service.confirm_project_change_set(
        actor=g.current_user,
        project_id=project_id,
        change_set_id=change_set_id,
    )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/change-sets/<change_set_id>/reject")
@require_auth
def reject_change_set(project_id: str, change_set_id: str):
    """否决（can_manage 且 ≠ 提交人）：只改状态留 reason。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise service.OntologyServiceError(
            "invalid_request", "请求内容必须为 JSON 对象。", 400
        )
    data = service.reject_project_change_set(
        actor=g.current_user,
        project_id=project_id,
        change_set_id=change_set_id,
        payload=payload,
    )
    return jsonify({"data": data, "error": None})


# ---------------------------------------------------------------- M5-WP3
# 四组治理面（D29/D30/D31/改进单 4）：全部人工路径——**有意不进 api_catalog**
# （沿本体治理面纪律：AI 不可直达）；GET 读面登记进 M8 红队清单（见
# tests/test_m8_red_team_sweep.py）。


def _current_settings():
    """请求上下文内的 Settings（与 integrations/service 同款取法）。"""
    return current_app.config["SETTINGS"]


@ontology_blueprint.post("/evidence-packs/export")
@require_auth
def export_evidence_pack_route(project_id: str):
    """D30 冻结证据评审包导出（can_manage）：白名单物理投影 + 服务端 HMAC。

    缺 HMAC 密钥 ⇒ fail-closed 503 ``evidence_pack_not_configured``；
    导出事件 ``ontology_evidence_pack_exported`` 是 I7 异人签收验真的导出人锚。
    """
    with db.session() as session:
        data = export_evidence_pack(
            session,
            actor=g.current_user,
            project_id=project_id,
            settings=_current_settings(),
        )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/evidence-packs/receipt")
@require_auth
def import_annotation_receipt_route(project_id: str):
    """I7 批注回执签收（can_manage）：验签 → 导出留痕 → 异人 SoD 三闸。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise EvidencePackError("请求内容必须为 JSON 对象。")
    with db.session() as session:
        data = import_annotation_receipt(
            session,
            actor=g.current_user,
            project_id=project_id,
            payload=payload,
            settings=_current_settings(),
        )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/upgrade-blast-radius")
@require_auth
def upgrade_blast_radius_route(project_id: str):
    """升级爆炸半径报告（can_view）：WP1 diff × 本地四面聚合（D29 第②段）。

    ``to_version`` 原值传服务层——门控/绑定校验先行（M8 红队钉：无参请求
    必须落在 404/409 而非 400）。
    """
    with db.session() as session:
        data = build_upgrade_blast_radius(
            session,
            actor=g.current_user,
            project_id=project_id,
            to_version=request.args.get("to_version") or "",
            settings=_current_settings(),
        )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/review-queue")
@require_auth
def review_queue_route(project_id: str):
    """``<0.8``/冲突候选复核分流视图（can_view；D31，绝不产出 Gate 阻断）。"""
    with db.session() as session:
        data = build_review_queue(
            session,
            actor=g.current_user,
            project_id=project_id,
            settings=_current_settings(),
        )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.post("/glossary/promote")
@require_auth
def promote_glossary_route(project_id: str):
    """Glossary 单向晋升（can_manage）：confirmed 术语 → 模板包只读投影。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise GlossaryPromotionError("请求内容必须为 JSON 对象。")
    term_ids = payload.get("term_ids")
    if not isinstance(term_ids, list) or not term_ids:
        raise GlossaryPromotionError("term_ids 必须为非空数组。")
    with db.session() as session:
        data = promote_glossary_terms(
            session,
            actor=g.current_user,
            project_id=project_id,
            term_ids=term_ids,
        )
    return jsonify({"data": data, "error": None})


@ontology_blueprint.get("/glossary/promoted")
@require_auth
def list_promoted_glossary_route(project_id: str):
    """晋升只读投影清单（can_view）：promoted_readonly=True 的稳定白名单形状。"""
    with db.session() as session:
        data = list_promoted_terms(
            session, actor=g.current_user, project_id=project_id
        )
    return jsonify({"data": data, "error": None})
