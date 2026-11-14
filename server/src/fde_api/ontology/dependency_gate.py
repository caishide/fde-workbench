"""S-16 双层枚举解析 + S-12 防降级旁路锁（M5-WP2④；独立新模块，零 ``ontology/service.py`` 增写）。

S-16（集成契约 §0/§3，冻结契约 v1.3.0-m5）：
- 全局环境闸 ``FDE_ONTOLOGY_GATE_DEPENDENCY = strong | weak | per_gate``（默认 ``per_gate``）；
- **仅在 ``per_gate`` 下**读取单门禁 ``ontology_dependency = required | optional | none``；
- ``strong``：本体不可用一律挂起；``weak``：原规则运行 + 标注未校验；
- 非法全局值 fail-closed 取 ``strong``（宁严勿松：不可用即挂起）。

S-12（任务书红线 12 / 工作令 §1 条 4）：
门禁基线建档后，任何**下调**依赖等级或放宽阈值的操作强制走项目 Owner
**异人**审批并记 ``audit_events``，且熔断（本体降级）窗口期内严禁下调生效
或追溯放行已挂起门禁。本模块只提供纯判定函数；审批留痕由调用方落
``projects.events.record_event``（audit_events 通道）。
"""

from __future__ import annotations

# S-16 双层枚举（外层全局闸 / 内层单门禁等级）
GLOBAL_GATES = ("strong", "weak", "per_gate")
GATE_DEPENDENCY_LEVELS = ("required", "optional", "none")
DEFAULT_GLOBAL_GATE = "per_gate"  # 集成契约 §0 配置表默认值

# 等级严格序：数值越大越严格；下调 = 放松 = 严格度变小
_LEVEL_STRICTNESS = {"none": 0, "optional": 1, "required": 2}


def resolve_ontology_dependency(
    global_gate: str | None,
    template_default: str | None,
    gate_row_value: str | None,
) -> str:
    """解析门禁的生效本体依赖等级（双层枚举，S-16）。

    - ``global_gate="strong"/"weak"``：直接生效（内层值不可达，防旁路）；
    - ``global_gate="per_gate"``（或 None = 契约默认）：读单门禁行值，
      行值缺省回退模板默认，模板也缺省取 ``optional``（本体辅助档）；
    - 非法全局值：fail-closed ``strong``。

    行值/模板全缺省取 ``optional`` 而非 ``required`` 的理由（升级兼容性）：
    M4 及之前的存量 ``gates`` 行与本版迁移前全部无 ``ontology_dependency``
    值（NULL）——若保守兜底 required，升级瞬间所有未建档门禁即被「本体
    不可用 → 挂起」钳制，属行为爆炸；optional 的本体辅助语义（可用则校验
    标注、不可用降级放行）是唯一平滑口径。要硬钳制的门禁应显式建档
    ``required``（显式可见降级原则）。
    """
    gate = (global_gate or "").strip()
    if not gate:
        gate = DEFAULT_GLOBAL_GATE
    if gate not in GLOBAL_GATES:
        return "strong"
    if gate in ("strong", "weak"):
        return gate
    # per_gate：才允许内层等级发声
    row = (gate_row_value or "").strip()
    if row in GATE_DEPENDENCY_LEVELS:
        return row
    tpl = (template_default or "").strip()
    if tpl in GATE_DEPENDENCY_LEVELS:
        return tpl
    return "optional"


def is_downgrade(current: str, proposed: str) -> bool:
    """判定依赖等级变更是否为「下调」（放松方向，S-12 审批锁触发条件）。

    非法等级一律 False（视为无效变更而非下调——无效变更由调用方按
    422 拒绝，不走审批通道）。
    """
    old = _LEVEL_STRICTNESS.get((current or "").strip())
    new = _LEVEL_STRICTNESS.get((proposed or "").strip())
    if old is None or new is None:
        return False
    return new < old


def can_activate_downgrade(
    *,
    proposer: str,
    approver: str,
    degraded: bool,
    approver_is_owner: bool = True,
) -> bool:
    """S-12 生效闸：下调审批满足「Owner 异人批准 + 非本体降级窗口」才可生效。

    - 同人自批（approver == proposer）一律拒绝（I4 同源职责分离）；
    - ``degraded=True``（client 熔断 open/half_open，本体不可用窗口）内
      严禁下调生效或追溯放行已挂起门禁——宁可挂起，不带病降级；
    - 审批人须为项目 Owner（``approver_is_owner`` 由调用方按
      ``ProjectMember``/``User.role`` 判定后传入，默认从严 True）。
    """
    if degraded:
        return False
    if not proposer or not approver or proposer == approver:
        return False
    return approver_is_owner
