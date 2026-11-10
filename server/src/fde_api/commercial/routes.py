"""商业化 G1 读面路由：本人/管理员查看权益与对外编号推导（只读零写入）。

- 读权限：本人或 admin；他人 403（权益属个人敏感面）。
- 不进 api_catalog：商业治理面，AI 不可调用（dispatch admin/本体治理同款边界）。
- 写面在 ``admin_routes.py``（admin + 密码确认 + 审计事件）。
"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from redis.exceptions import RedisError

from fde_api.auth.decorators import require_auth
from fde_api.commercial.attribution_service import (
    get_opportunity,
    list_opportunities,
    submit_opportunity,
    withdraw_opportunity,
)
from fde_api.commercial.billing_service import (
    elect_deduction_method,
    get_active_election,
    list_certification_records,
    list_packages,
    serialize_election,
)
from fde_api.commercial.ledger_service import (
    get_revenue_entry,
    list_revenue_entries,
    reconcile_revenue,
)
from fde_api.commercial.quota_service import (
    confirm_diagnosis,
    free_diagnosis_profile,
    get_quota_view,
    start_diagnosis,
)
from fde_api.commercial.regional_service import (
    apply_city_observer,
    get_or_create_gate,
    get_partner,
    list_partners,
    list_tiers,
    serialize_gate,
    serialize_partner,
    serialize_tier,
)
from fde_api.commercial.enterprise_service import (
    get_enterprise_space_view,
    record_paid_option_choice,
    register_enterprise,
)
from fde_api.commercial.service import CommercialServiceError, get_entitlement_for_view
from fde_api.errors import error_response
from fde_api.extensions import db

commercial_blueprint = Blueprint(
    "commercial", __name__, url_prefix="/api/v1/commercial"
)


@commercial_blueprint.errorhandler(CommercialServiceError)
def _handle_service_error(error: CommercialServiceError):
    return (
        jsonify(
            {
                "data": None,
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": None,
                },
            }
        ),
        error.status,
    )


@commercial_blueprint.get("/entitlements/<user_id>")
@require_auth
def get_entitlement_route(user_id: str):
    with db.session() as session:
        data = get_entitlement_for_view(session, actor=g.current_user, user_id=user_id)
        return jsonify({"data": data, "error": None})


# ── 商业化 G2：企业免费额度（读面：绑定账号本人或 admin）──


@commercial_blueprint.get("/enterprise-quota/<subject_key>")
@require_auth
def get_quota_route(subject_key: str):
    with db.session() as session:
        data = get_quota_view(session, actor=g.current_user, subject_key_raw=subject_key)
        return jsonify({"data": data, "error": None})


@commercial_blueprint.post("/enterprise-quota/<subject_key>/start")
@require_auth
def start_quota_route(subject_key: str):
    with db.session() as session, session.begin():
        data = start_diagnosis(session, actor=g.current_user, subject_key_raw=subject_key)
        return jsonify({"data": data, "error": None})


@commercial_blueprint.post("/enterprise-quota/<subject_key>/confirm")
@require_auth
def confirm_quota_route(subject_key: str):
    with db.session() as session, session.begin():
        data = confirm_diagnosis(session, actor=g.current_user, subject_key_raw=subject_key)
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/free-diagnosis-profile")
@require_auth
def free_diagnosis_profile_route():
    return jsonify({"data": free_diagnosis_profile(), "error": None})


# ── 商业化 G3：收入科目层读面 + 扣费方式自证面 ──


@commercial_blueprint.get("/packages")
@require_auth
def packages_route():
    """套餐目录（**不含价目**——价格走 quotes/payments 收款台账）。"""
    return jsonify({"data": {"packages": list_packages()}, "error": None})


@commercial_blueprint.get("/revenue-ledger")
@require_auth
def list_revenue_ledger_route():
    """科目列表（本人只见自己的；admin 见全量）——「三类科目分别可查」。"""
    with db.session() as session:
        data = list_revenue_entries(
            session,
            actor=g.current_user,
            subject_type=request.args.get("subject_type"),
            subject_user_id=request.args.get("subject_user_id"),
            status=request.args.get("status"),
            limit=request.args.get("limit", 100),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/revenue-ledger/reconciliation")
@require_auth
def reconcile_revenue_route():
    """科目对账汇总（按科目×名目 + 与收款台账差异计数）。"""
    with db.session() as session:
        data = reconcile_revenue(
            session,
            actor=g.current_user,
            subject_type=request.args.get("subject_type"),
            subject_user_id=request.args.get("subject_user_id"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/revenue-ledger/<entry_id>")
@require_auth
def get_revenue_ledger_route(entry_id: str):
    with db.session() as session:
        data = get_revenue_entry(session, actor=g.current_user, entry_id=entry_id)
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/deduction-election")
@require_auth
def get_deduction_election_route():
    """本人扣费方式选定状态（未选定 ⇒ 首单扣费闸不放行）。"""
    with db.session() as session:
        row = get_active_election(session, g.current_user.id)
        return jsonify(
            {
                "data": {
                    "elected": row is not None,
                    "election": serialize_election(row) if row is not None else None,
                },
                "error": None,
            }
        )


@commercial_blueprint.post("/deduction-election")
@require_auth
def elect_deduction_route():
    """本人**书面选定**扣费方式（当事人自证动作，ADR-007 §2.4）。

    他人/admin 不得代选定——本路由不接受 user_id 参数，actor 即被计费人。
    """
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    with db.session() as session, session.begin():
        data = elect_deduction_method(
            session,
            actor=g.current_user,
            method=payload.get("method"),
            source_uri=payload.get("source_uri"),
            content_hash=payload.get("content_hash"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/certification-records/<user_id>")
@require_auth
def certification_records_route(user_id: str):
    """认证记录读面（本人或 admin）——认证挂模拟考核的可见入口。"""
    with db.session() as session:
        data = list_certification_records(
            session, actor=g.current_user, user_id=user_id
        )
        return jsonify({"data": data, "error": None})


# ── 商业化 G4：商机归属与渠道保护（读面 + 当事人自证面）──


@commercial_blueprint.post("/opportunities")
@require_auth
def submit_opportunity_route():
    """① 报备（**当事人自证动作**：缴 3980 席位订阅费者提交自己的企业线索）。

    拉单资格**不限角色**（ADR-011 §5-F 补充拍板 12；席位费已缴闸，见
    attribution_service._require_sourcer_seat）。非 admin 治理写（报备不是
    关键流转）；证据只存指针 + sha256 指纹。
    """
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    with db.session() as session, session.begin():
        data = submit_opportunity(
            session,
            actor=g.current_user,
            enterprise_code=payload.get("enterprise_code"),
            title=payload.get("title"),
            note=payload.get("note"),
            source_uri=payload.get("source_uri"),
            content_hash=payload.get("content_hash"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/opportunities")
@require_auth
def list_opportunities_route():
    """商机列表（admin 全量；本人只见自己报备/归属/售前的）。"""
    with db.session() as session:
        data = list_opportunities(
            session,
            actor=g.current_user,
            status=request.args.get("status"),
            enterprise_code=request.args.get("enterprise_code"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/opportunities/<opportunity_id>")
@require_auth
def get_opportunity_route(opportunity_id: str):
    """商机详情（含保护期**派生**状态与「企业是否已自助注册」派生事实）。"""
    with db.session() as session:
        data = get_opportunity(
            session, actor=g.current_user, opportunity_id=opportunity_id
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.post("/opportunities/<opportunity_id>/withdraw")
@require_auth
def withdraw_opportunity_route(opportunity_id: str):
    """撤回商机（**报备人自证动作**；他人 403；撤回不动归属事实）。"""
    with db.session() as session, session.begin():
        data = withdraw_opportunity(
            session, actor=g.current_user, opportunity_id=opportunity_id
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.post("/regional-partners")
@require_auth
def apply_regional_partner_route():
    """申请成为城市观察伙伴（**免费；当事人自证动作**；任务书 §9 第一阶段）。"""
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    with db.session() as session, session.begin():
        data = apply_city_observer(
            session,
            actor=g.current_user,
            partner_code=payload.get("partner_code"),
            region_name=payload.get("region_name"),
            note=payload.get("note"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/regional-partners")
@require_auth
def list_regional_partners_route():
    """区域伙伴列表（admin 全量；非 admin 只见本人申请的）。"""
    with db.session() as session:
        rows = list_partners(session, actor=g.current_user)
        return jsonify({"data": [serialize_partner(r) for r in rows], "error": None})


@commercial_blueprint.get("/regional-partners/<partner_id>")
@require_auth
def get_regional_partner_route(partner_id: str):
    """区域伙伴详情（含阶段注记派生——区域代理显示「暂不启用」；他人 404）。"""
    with db.session() as session:
        data = get_partner(session, actor=g.current_user, partner_id=partner_id)
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/regional-partner-tiers")
@require_auth
def list_regional_tiers_route():
    """正式区域合作商三档定价目录（BP v4.0 基准；目录可见 ≠ 可签约——售卖开关在 admin 面）。"""
    with db.session() as session:
        rows = list_tiers(session)
        gate = serialize_gate(get_or_create_gate(session))
        return jsonify(
            {"data": {"tiers": [serialize_tier(r) for r in rows], "sale_gate_status": gate["status"]}, "error": None}
        )


# ── 注册面节流（G6 遗留挂账清偿：复用 #250 登录限流模式）──
# Redis INCR+TTL、fail-open 缺省可切 fail-closed、429 结构化错误、
# ProxyFix 之后 remote_addr 取真实客户端 IP。
# 阈值为**技术防滥用闸**（公开入口洪泛／批量注册建号），不是任务书 §17 那类
# 商业数值红线（保护期长度/续期条件/分成比例/认证费金额等一概不落数）。
# 与登录限流的三点刻意差异：
#   ①按来源 IP 单键——注册时没有既有用户名可入键，攻击者可随意换名，
#     键必须落在 IP 上；
#   ②**成功不清零**——注册成功同样创建账号，若成功清零则「注册→清零→再注册」
#     即可绕过配额；这是容量上限，不是失败锁定；
#   ③计数发生在任何解析与 argon2 计算之前——被限的请求零成本拒绝。
REGISTRATION_RATE_MAX_ATTEMPTS = 10
REGISTRATION_RATE_WINDOW_SECONDS = 3600


def _registration_rate_key(remote_addr: str | None) -> str:
    ip = remote_addr or "unknown"
    return f"commercial:register:{ip}"


def _registration_throttle(remote_addr: str | None) -> int | None:
    """记一次注册尝试；超限返回应等待秒数（未超限返回 None）。

    Redis 不可用时行为可配置（#250 同款，不得静默）：
      fail-open（缺省）→ 记 WARNING 后放行（内网部署假设，Redis 挂不挡注册）；
      fail-closed（FDE_REGISTRATION_RATE_FAIL_CLOSED=1，对外暴露部署从严）
        → 记 WARNING 后一律按超限处理（429）。
    """
    try:
        redis = current_app.extensions["fde_api_redis"]
    except KeyError:
        return None
    settings = current_app.config["SETTINGS"]
    key = _registration_rate_key(remote_addr)
    try:
        attempts = redis.incr(key)
        if attempts == 1:
            redis.expire(key, REGISTRATION_RATE_WINDOW_SECONDS)
        if attempts > REGISTRATION_RATE_MAX_ATTEMPTS:
            return max(int(redis.ttl(key) or REGISTRATION_RATE_WINDOW_SECONDS), 1)
    except RedisError:
        current_app.logger.warning(
            "registration rate limiter unavailable (ip=%s); failing %s",
            remote_addr,
            "closed" if settings.registration_rate_fail_closed else "open",
        )
        if settings.registration_rate_fail_closed:
            return REGISTRATION_RATE_WINDOW_SECONDS
        return None
    return None


# ── 商业化 G6：企业空间与企业自助交付（读/自证面；ADR-010）──


@commercial_blueprint.post("/enterprise-registrations")
def register_enterprise_route():
    """企业自助注册（R1；**当事人自证，公开入口无鉴权**——免费额度的结构性
    防滥用＝USCC 一主体一份额度；治理面不进 api_catalog）。"""
    retry_after = _registration_throttle(request.remote_addr)
    if retry_after is not None:
        return error_response(
            "registration_rate_limited",
            f"注册尝试过于频繁，请约 {retry_after // 60 + 1} 分钟后再试。",
            429,
        )
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    with db.session() as session, session.begin():
        data = register_enterprise(
            session,
            username=payload.get("username"),
            display_name=payload.get("display_name"),
            password=payload.get("password"),
            subject_key_raw=payload.get("subject_key"),
            problem_description=payload.get("problem_description"),
            request_id=payload.get("request_id"),
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.get("/enterprise-spaces/<subject_key>")
@require_auth
def get_enterprise_space_route(subject_key: str):
    """企业空间读面（绑定账号本人或 admin；他人 403）——业务问题/额度/三档
    分流回看/付费选项与现行选择/交付项目（既有权限模型可见性过滤）。"""
    with db.session() as session:
        data = get_enterprise_space_view(
            session, actor=g.current_user, subject_key_raw=subject_key
        )
        return jsonify({"data": data, "error": None})


@commercial_blueprint.post("/enterprise-spaces/<subject_key>/paid-option-choices")
@require_auth
def record_paid_option_choice_route(subject_key: str):
    """企业选择付费选项（**只认绑定账号本人**；诊断完成后可选；换主意＝再选，
    append-only 无取消路径）。"""
    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    with db.session() as session, session.begin():
        data = record_paid_option_choice(
            session,
            actor=g.current_user,
            subject_key_raw=subject_key,
            option_key=payload.get("option_key"),
            request_id=payload.get("request_id"),
        )
        return jsonify({"data": data, "error": None})
