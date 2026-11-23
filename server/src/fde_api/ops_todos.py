"""运营待办只读聚合视图＋运营简报（Ecosystem OS M2 WP-2/WP-3；立项书 v0.1 §五）。

裁决落点（沿 ``expirations.py`` B#13-D 先例）：**服务层只读 union ＋
admin-only 路由，零 DDL**。四域待办合并为一张六字段逻辑视图：
``domain`` / ``object_id`` / ``title`` / ``deadline_at`` / ``state`` /
``queue``——AI 自动化审批（pending）、AI API 确认（无结果）、派单响应
（offered）、评审纪要待办（近窗封存）。

只读纪律（立项书 A4）：列待办不产生任何执行结果——人工决策动作仍走既有
闸（automation_approvals 的裁定、api_actions 的确认、dispatch 的响应、
纪要侧无写面）；本模块不 import 任何写路径、不写任何源行、零事件追加。

留痕与红线（立项书 A6）：视图本身零副作用（读前后事件计数不变，测试钉）；
模块内零真相层引用（红线：客户真实资料只留 ``D:\\test\\FDE`` 等本地目录）。

``queue`` 字段＝V1.0 §4.3 Human Approval Queue 归类：**声明式域级映射**
（``DOMAIN_QUEUES``，逐域归类不逐项判定；``None``＝运营协调面，不属六类
人工审批）。闭集单一权威取 ``agents.hq_cards.HUMAN_APPROVAL_QUEUE``（批次
一机械钉已钉死 seed ≡ 常量），映射值出闭集模块导入即炸（boot fail-fast）。

与 ``expirations``（到期投影）的关系：三域谓词同源（审批 pending／确认无
结果／offer offered），确认域共用同一窗口常量与扫描上限（模块属性访问，
变异敏感）；**差异＝本视图是「待发现」语义**——无响应窗口的 offer 与无
期限的纪要待办仍入投影（``deadline_at`` 为 null、排序沉底、due 过滤跳过），
而到期投影只收有期限项。

WP-3 运营简报（``POST /api/v1/ops/briefs/generate``）：**确定性聚合、返件式
零落库**——简报正文（Markdown）全部由数据库现算拼装（待办条目＋招商漏斗
计数＋需总部介入事项），零模型调用零编造数字（数字溯源纪律；运营值班员卡
拍板定稿＝纯确定性聚合卡 ``prompt_purposes: []``）。落一条
``ops_brief_generated`` 事件（changes 只带计数与 sha256 指纹，不带正文），
简报本体不持久化——人工经既有文档/发信面处置；**系统内不存在简报直发
通道**（``mailing.routes`` 设计声明：发送路径不设 HTTP 路由），A5 断言钉
发信服务函数调用方闭集不变。漏斗口径＝交付包/派单 offer/区域伙伴/交付者
档案四段只读计数（注册申请段留待需要时扩）。
"""
import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select

from fde_api.agents.hq_cards import HUMAN_APPROVAL_QUEUE
from fde_api.auth.decorators import require_auth
from fde_api.commercial.models import RegionalPartner
from fde_api.control import api_actions
from fde_api.control.api_actions import _result
from fde_api.control.models import AutomationApproval
from fde_api.dispatch.models import DeliveryPackage, DispatchOffer, FdeProfile
from fde_api.dispatch.offer_service import offer_deadline
from fde_api.errors import error_response
from fde_api.expirations import CONFIRMATION_SCAN_LIMIT
from fde_api.extensions import db
from fde_api.meetings.models import ReviewMeetingMinutes
from fde_api.workbench.models import OperationEvent

blueprint = Blueprint("ops", __name__, url_prefix="/api/v1/ops")

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

#: 纪要待办回看窗口（天）：todos 是纯文本留痕（无完成态位），只收近窗
#: 封存的纪要，防无完成态的陈旧待办永久堆积。
MEETING_TODO_LOOKBACK_DAYS = 30

#: 纪要待办正文的标题截断宽度（源文本最长 2000 字，投影标题防膨胀）。
TITLE_MAX_CHARS = 80

#: domain → V1.0 §4.3 审批队列归类（声明式域级映射，归类口径见 PROGRESS
#: 批次二节）：AI 对生产面的动作审批/确认归「生产数据写入」；派单响应与
#: 纪要待办属运营协调面，不落六类。
DOMAIN_QUEUES: dict[str, str | None] = {
    "automation_approval": "production_data_writes",
    "api_confirmation": "production_data_writes",
    "dispatch_offer": None,
    "meeting_todo": None,
}

#: 纪要待办投影状态词（源域无状态位，投影词表统一 ``open``）。
MEETING_TODO_STATE = "open"

#: 简报待办正文最多逐条列出的条数（其余以分域计数呈现，总量字段不受影响）。
BRIEF_TODO_TOP_LIMIT = 10

#: 「需总部介入」已到期清单最多逐条列出的条数。
BRIEF_DUE_LIST_LIMIT = 50

# 每域待办行的内部形态：(domain, object_id, deadline_at | None, state, title)
_RawTodo = tuple[str, str, Any, str, str]


def validate_queue_mapping() -> None:
    """queue 映射必须落在 V1.0 §4.3 六类闭集内（权威＝岗位卡装载器常量）。

    模块导入即校验（boot fail-fast）；测试负例直接改 ``DOMAIN_QUEUES`` 后
    重调本函数。
    """
    for name, queue in DOMAIN_QUEUES.items():
        if queue is not None and queue not in HUMAN_APPROVAL_QUEUE:
            raise RuntimeError(
                f"ops_todos: queue {queue!r} of domain {name!r} is outside "
                "the V1.0 §4.3 human approval queue closure"
            )


validate_queue_mapping()


def _approval_todos(session, now: datetime, limit: int) -> list[_RawTodo]:
    rows = session.scalars(
        select(AutomationApproval)
        .where(AutomationApproval.status == "pending")
        .order_by(AutomationApproval.expires_at, AutomationApproval.id)
        .limit(limit)
    )
    return [
        ("automation_approval", row.id, row.expires_at, row.status, row.capability)
        for row in rows
    ]


def _confirmation_todos(session, now: datetime, limit: int) -> list[_RawTodo]:
    # 与 expirations._confirmation_entries 同谓词同则（跨视图一致性有机械钉）：
    # 已有结果（finished/cancelled/started=uncertain 防重放态）的确认不再是待办。
    requested = session.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.target_type == "ai_api_action",
            OperationEvent.event_type == "ai.api.requested",
        )
        .order_by(OperationEvent.created_at.desc(), OperationEvent.id.desc())
        .limit(CONFIRMATION_SCAN_LIMIT)
    )
    candidates = [row for row in requested if row.changes.get("confirmation_required")]
    if not candidates:
        return []
    related = session.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.target_type == "ai_api_action",
            OperationEvent.target_id.in_([row.target_id for row in candidates]),
        )
        .order_by(OperationEvent.created_at, OperationEvent.id)
    )
    by_id: dict[str, list[OperationEvent]] = defaultdict(list)
    for row in related:
        by_id[row.target_id].append(row)
    entries: list[_RawTodo] = []
    for row in candidates:
        if _result(by_id.get(row.target_id, [])) is not None:
            continue
        # 窗口常量取模块属性而非 from-import 绑定：与 B#13-C 保持单一权威，
        # monkeypatch CONFIRMATION_WINDOW 时两投影同步位移。
        deadline = row.created_at + api_actions.CONFIRMATION_WINDOW
        title = str(row.changes.get("operation") or "unknown_operation")
        entries.append(
            ("api_confirmation", row.target_id, deadline, "awaiting_confirmation", title)
        )
    return entries


def _offer_todos(session, now: datetime, limit: int) -> list[_RawTodo]:
    rows = session.execute(
        select(DispatchOffer, DeliveryPackage)
        .join(DeliveryPackage, DispatchOffer.package_id == DeliveryPackage.id)
        .where(DispatchOffer.status == "offered")
        .order_by(DispatchOffer.offered_at, DispatchOffer.id)
        .limit(limit)
    )
    entries: list[_RawTodo] = []
    for offer, package in rows:
        # 与 expirations 的差异：无响应窗口的 offer 仍是待响应事项，入投影
        # （deadline_at 为 null 沉底）；到期投影只收有期限项。
        deadline = offer_deadline(offer, package)
        title = f"{package.package_code}·R{offer.dispatch_round}"
        entries.append(("dispatch_offer", offer.id, deadline, offer.status, title))
    return entries


def _meeting_todos(session, now: datetime, limit: int) -> list[_RawTodo]:
    horizon = now - timedelta(days=MEETING_TODO_LOOKBACK_DAYS)
    rows = session.scalars(
        select(ReviewMeetingMinutes)
        .where(ReviewMeetingMinutes.created_at >= horizon)
        .order_by(ReviewMeetingMinutes.created_at.desc(), ReviewMeetingMinutes.id)
        .limit(limit)
    )
    entries: list[_RawTodo] = []
    for minutes in rows:
        for index, todo in enumerate(minutes.todos or []):
            if not isinstance(todo, dict) or not isinstance(todo.get("text"), str):
                continue  # 封存校验外的畸形行不进投影（防御性跳过，不写回）
            owner = todo.get("owner")
            prefix = f"[{owner}] " if isinstance(owner, str) and owner else ""
            text = todo["text"]
            if len(text) > TITLE_MAX_CHARS:
                text = text[:TITLE_MAX_CHARS] + "…"
            entries.append(
                (
                    "meeting_todo",
                    f"{minutes.id}:{index}",
                    None,
                    MEETING_TODO_STATE,
                    prefix + text,
                )
            )
    return entries


_COLLECTORS = {
    "automation_approval": _approval_todos,
    "api_confirmation": _confirmation_todos,
    "dispatch_offer": _offer_todos,
    "meeting_todo": _meeting_todos,
}

#: 无期限项排序沉底的占位下界（只与自身比较，绝不与真实期限比较——键的
#: 首元 ``is None`` 已把两组隔离）。
_SORT_FLOOR = datetime.min


def collect_ops_todos(
    *,
    now: datetime | None = None,
    domain: str | None = None,
    due: bool | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """只读 union：跨域运营待办投影（六字段；每域最多取 ``limit`` 行）。

    合并后先做 due 过滤（无期限项不参与该语义，过滤即整体排除），再按
    「有期限在前按 deadline 升序、无期限沉底」稳定排序并截断；注入 ``now``
    供测试固定边界。
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    session = db.session()
    try:
        collectors = _COLLECTORS.values() if domain is None else [_COLLECTORS[domain]]
        raw: list[_RawTodo] = []
        for collector in collectors:
            raw.extend(collector(session, current, limit))
        if due is not None:
            raw = [row for row in raw if row[2] is not None and (row[2] <= current) is due]
        raw.sort(key=lambda row: (row[2] is None, row[2] or _SORT_FLOOR, row[0], row[1]))
        return [
            {
                "domain": name,
                "object_id": object_id,
                "title": title,
                "deadline_at": deadline.astimezone(UTC).isoformat()
                if deadline is not None
                else None,
                "state": state,
                "queue": DOMAIN_QUEUES[name],
            }
            for name, object_id, deadline, state, title in raw[:limit]
        ]
    finally:
        session.close()


@blueprint.get("/todos")
@require_auth
def list_ops_todos_route():
    if g.current_user.role != "admin":
        return error_response("forbidden", "运营待办聚合视图仅平台管理员可读。", 403)
    args = request.args
    domain = args.get("domain")
    if domain is not None and domain not in DOMAIN_QUEUES:
        return error_response(
            "invalid_domain",
            "domain 只接受 " + "/".join(sorted(DOMAIN_QUEUES)) + "。",
            400,
        )
    due: bool | None = None
    due_raw = args.get("due")
    if due_raw is not None:
        normalized = due_raw.lower()
        if normalized not in {"true", "false"}:
            return error_response("invalid_request", "due 只接受 true/false。", 400)
        due = normalized == "true"
    limit = DEFAULT_LIMIT
    limit_raw = args.get("limit")
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
        except ValueError:
            return error_response("invalid_request", "limit 必须是整数。", 400)
        if not 1 <= limit <= MAX_LIMIT:
            return error_response("invalid_request", f"limit 须在 1..{MAX_LIMIT}。", 400)
    items = collect_ops_todos(domain=domain, due=due, limit=limit)
    return jsonify({"data": {"items": items, "total": len(items)}, "error": None})


# ---------------------------------------------------------------------------
# WP-3 运营简报（确定性聚合，返件式零落库，见模块头 WP-3 段）
# ---------------------------------------------------------------------------

#: 招商漏斗四段的展示标签（键即返回体 funnel 字段名；段内计数按状态名排序）。
_BRIEF_FUNNEL_LABELS: dict[str, str] = {
    "delivery_packages": "交付包",
    "dispatch_offers": "派单 offer",
    "regional_partners": "区域伙伴",
    "fde_profiles": "交付者档案",
}


def _funnel_counts(session) -> dict[str, dict[str, int]]:
    """四段只读计数（GROUP BY；零 DDL，全部命中既有状态机闭集列）。"""
    return {
        "delivery_packages": dict(
            session.execute(
                select(DeliveryPackage.dispatch_status, func.count())
                .group_by(DeliveryPackage.dispatch_status)
            ).all()
        ),
        "dispatch_offers": dict(
            session.execute(
                select(DispatchOffer.status, func.count()).group_by(DispatchOffer.status)
            ).all()
        ),
        "regional_partners": dict(
            session.execute(
                select(RegionalPartner.stage, func.count()).group_by(RegionalPartner.stage)
            ).all()
        ),
        "fde_profiles": dict(
            session.execute(
                select(FdeProfile.status, func.count()).group_by(FdeProfile.status)
            ).all()
        ),
    }


def _render_brief_markdown(
    current: datetime,
    items: list[dict[str, Any]],
    due_items: list[dict[str, Any]],
    funnel: dict[str, dict[str, int]],
) -> str:
    """确定性拼装简报正文（排序键全部显式；同一数据库状态 + 同一 now ⇒ 逐字节同文）。"""
    by_domain: dict[str, int] = defaultdict(int)
    for entry in items:
        by_domain[entry["domain"]] += 1
    lines = [f"# 运营简报 {current.date().isoformat()}", ""]
    lines.append(f"## 一、运营待办（共 {len(items)} 项，已到期 {len(due_items)} 项）")
    lines.append("")
    for domain in sorted(by_domain):
        lines.append(f"- {domain}：{by_domain[domain]} 项")
    lines.append("")
    top = items[:BRIEF_TODO_TOP_LIMIT]
    if top:
        lines.append(f"待办清单（按截止时间升序，前 {BRIEF_TODO_TOP_LIMIT} 条；无期限项沉底）：")
        lines.append("")
        for index, entry in enumerate(top, start=1):
            deadline = entry["deadline_at"] or "无期限"
            queue = entry["queue"] or "运营协调"
            lines.append(
                f"{index}. [{entry['domain']}｜{queue}] {entry['title']} — 截止 {deadline}"
            )
    if len(items) > len(top):
        lines.append(f"（其余 {len(items) - len(top)} 项未逐条列出，计数已含）")
    lines.append("")
    lines.append("## 二、招商漏斗")
    lines.append("")
    for key in sorted(funnel):
        counts = funnel[key]
        rendered = " / ".join(f"{status} {count}" for status, count in sorted(counts.items()))
        lines.append(f"- {_BRIEF_FUNNEL_LABELS.get(key, key)}：{rendered or '（空）'}")
    lines.append("")
    lines.append(f"## 三、需总部介入事项（已到期 {len(due_items)} 项）")
    lines.append("")
    for entry in due_items[:BRIEF_DUE_LIST_LIMIT]:
        queue = entry["queue"] or "运营协调"
        lines.append(
            f"- [{entry['domain']}｜{queue}] {entry['title']} — 截止 {entry['deadline_at']}"
        )
    if len(due_items) > BRIEF_DUE_LIST_LIMIT:
        lines.append(f"（其余 {len(due_items) - BRIEF_DUE_LIST_LIMIT} 项已到期未逐条列出）")
    lines.append("")
    lines.append(
        "（本简报由系统确定性聚合生成：数字全部来自数据库现算，不含模型生成内容；"
        "系统无简报直发通道，人工决策仍走既有审批/确认/响应闸。）"
    )
    return "\n".join(lines)


def compose_ops_brief(*, now: datetime | None = None) -> dict[str, Any]:
    """确定性聚合运营简报（只读；返件式零落库，正文不持久化）。

    注入 ``now`` 供测试固定日期与到期边界。
    """
    current = (now or datetime.now(UTC)).astimezone(UTC)
    items = collect_ops_todos(now=current, limit=MAX_LIMIT)
    due_items = [
        entry
        for entry in items
        if entry["deadline_at"] is not None
        and datetime.fromisoformat(entry["deadline_at"]) <= current
    ]
    session = db.session()
    try:
        funnel = _funnel_counts(session)
    finally:
        session.close()
    markdown = _render_brief_markdown(current, items, due_items, funnel)
    return {
        "brief_markdown": markdown,
        "brief_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "todo_total": len(items),
        "due_total": len(due_items),
        "funnel": funnel,
        "generated_at": current.isoformat(),
    }


@blueprint.post("/briefs/generate")
@require_auth
def generate_ops_brief_route():
    if g.current_user.role != "admin":
        return error_response("forbidden", "运营简报仅平台管理员可生成。", 403)
    result = compose_ops_brief()
    with db.session() as session, session.begin():
        # projects.events 懒导入（跨包单向边，顶层 import 面最小化）。
        from fde_api.projects.events import record_event

        record_event(
            session,
            g.current_user,
            "ops_brief_generated",
            target=g.current_user,
            changes={
                "todo_total": result["todo_total"],
                "due_total": result["due_total"],
                "funnel": result["funnel"],
                "brief_sha256": result["brief_sha256"],
            },
        )
    return jsonify({"data": result, "error": None}), 200
