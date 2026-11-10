"""诊断问卷定义（固定问卷 v0）——从首批 6 张案例卡的标准答案**反推**得出。

槽位清单源自诊断评测线的必备事实槽位分析（该分析在真相层维护，**不进本仓**
——评测集污染隔离纪律，生成器可见面不引用评测集路径）；反推口径：
**不问这些槽位，诊断必失分**（每一槽位都支撑某张案例卡的标准答案条目）。

纪律：

- **总题量 ≤ 30 / 填写 ≤ 10 分钟**（市场调研基准：问卷漏斗完成率 60–80%，失败
  主因是题过多与过早索要联系方式）。
- **首屏 = 测算卡 5 题**（纯规则、零 AI、零成本）——P-1 的钩子位；**联系方式
  不前置**（互惠顺序：先给真值，再开口要联系方式）。
- **条件显隐**：依赖槽位无值时不问（少一题少一次流失）。
- **允许留空**：留空的槽位在报告里标「待澄清」，**不得由模型编造补齐**。
"""
from __future__ import annotations

from dataclasses import dataclass

QUESTIONNAIRE_VERSION = "diag-questionnaire-v0"

FAMILY_ENTERPRISE = "企业画像"
FAMILY_BUSINESS = "业务链路"
FAMILY_SYSTEM = "数据与系统"
FAMILY_POLICY = "政策与申报"
FAMILY_CONTEXT = "补充"

INDUSTRIES: tuple[str, ...] = (
    "制造与工业",
    "零售与消费",
    "企业运营与其他",
    "交通运输与物流",
    "科技与软件",
    "金融与保险",
    "医疗与生命科学",
    "专业服务",
    "建筑与工程服务",
    "其他",
)

SCALE_TIERS: tuple[str, ...] = ("20人以下", "20–99人", "100–499人", "500–999人", "1000人以上")

QUALIFICATIONS: tuple[str, ...] = (
    "高新技术企业",
    "专精特新中小企业",
    "规上工业企业",
    "行业准入或生产资质",
    "暂无",
)

DECLARATION_HISTORY: tuple[str, ...] = (
    "从未申报过",
    "申报过但未通过",
    "申报并通过",
    "不清楚",
)

DIGITALIZATION_STATE: tuple[str, ...] = (
    "已有在推进的数字化改造",
    "做过但停滞",
    "打算做",
    "完全没有",
    "不清楚",
)

PAIN_STAGES: tuple[str, ...] = (
    "获客与销售",
    "报价与方案",
    "生产与交付",
    "财务与内部流程",
    "客服与售后",
    "经营决策与数据",
    "其他",
)

DECISION_MAKERS: tuple[str, ...] = (
    "老板",
    "总经理或副总",
    "部门负责人",
    "生产负责人",
    "财务负责人",
    "采购负责人",
    "尚不确定",
)

DELIVERY_MODES: tuple[str, ...] = (
    "离散制造",
    "流程制造",
    "项目制交付",
    "门店零售",
    "服务型",
    "其他",
)

SYSTEM_OPTIONS: tuple[str, ...] = (
    "ERP",
    "OA",
    "CRM",
    "财务软件",
    "生产或 MES",
    "电商平台",
    "自建系统",
    "几乎没有系统",
    "其他",
)

INTEGRATION_STATES: tuple[str, ...] = (
    "各系统数据互通",
    "部分互通",
    "互不相通",
    "只有一个系统",
    "不清楚",
)

DATA_QUALITY_STATES: tuple[str, ...] = (
    "数据实时且有人维护",
    "数据大致准确但靠人工核对",
    "数据经常过期或缺字段",
    "说不清",
    "没有可用数据",
)

PRIORITIES: tuple[str, ...] = (
    "拿到政策补贴",
    "提升获客与销售效率",
    "降本增效（人工与流程）",
    "满足合规与交付要求",
    "解决某个具体痛点",
    "说不清",
)


@dataclass(frozen=True, slots=True)
class Slot:
    """一个问卷槽位。"""

    key: str
    label: str
    kind: str  # single | multi | text | long_text
    family: str
    required: bool = False
    options: tuple[str, ...] = ()
    max_chars: int = 0
    show_if: tuple[str, ...] = ()  # 依赖槽位：任一有值即显示
    hint: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "family": self.family,
            "required": self.required,
        }
        if self.options:
            payload["options"] = list(self.options)
        if self.max_chars:
            payload["max_chars"] = self.max_chars
        if self.show_if:
            payload["show_if"] = list(self.show_if)
        if self.hint:
            payload["hint"] = self.hint
        return payload


# ── 首屏 5 题（测算卡输入；纯规则、零 AI） ─────────────────────────────
FIRST_SCREEN_SLOTS: tuple[Slot, ...] = (
    Slot(
        key="org.industry",
        label="你所在的行业是？",
        kind="single",
        family=FAMILY_ENTERPRISE,
        required=True,
        options=INDUSTRIES,
    ),
    Slot(
        key="org.scale",
        label="企业大约多少人？",
        kind="single",
        family=FAMILY_ENTERPRISE,
        required=True,
        options=SCALE_TIERS,
    ),
    Slot(
        key="pol.qualification",
        label="目前已具备哪些资质？（可多选）",
        kind="multi",
        family=FAMILY_POLICY,
        options=QUALIFICATIONS,
    ),
    Slot(
        key="pol.declaration_history",
        label="以前申报过政策项目或补贴吗？",
        kind="single",
        family=FAMILY_POLICY,
        options=DECLARATION_HISTORY,
    ),
    Slot(
        key="pol.digitalization_project",
        label="现在有没有在推进的数字化改造？",
        kind="single",
        family=FAMILY_POLICY,
        required=True,
        options=DIGITALIZATION_STATE,
    ),
)

# ── 续填槽位（诊断问卷输入；≤25 题） ────────────────────────────────────
DIAGNOSTIC_SLOTS: tuple[Slot, ...] = (
    Slot(
        key="org.main_business",
        label="主营业务是什么？",
        kind="text",
        family=FAMILY_ENTERPRISE,
        max_chars=120,
    ),
    Slot(
        key="org.delivery_mode",
        label="主要交付形态是？",
        kind="single",
        family=FAMILY_ENTERPRISE,
        options=DELIVERY_MODES,
    ),
    Slot(
        key="biz.current_process",
        label="这件事现在是怎么做的？（谁做、用什么、多久一次）",
        kind="long_text",
        family=FAMILY_BUSINESS,
        max_chars=600,
        hint="用自己的话写，不用工整——口语、简写、只写一半都可以。",
    ),
    Slot(
        key="biz.pain_stage",
        label="最卡的是哪个环节？",
        kind="single",
        family=FAMILY_BUSINESS,
        options=PAIN_STAGES,
    ),
    Slot(
        key="biz.decision_maker",
        label="这件事最后谁拍板？",
        kind="single",
        family=FAMILY_BUSINESS,
        options=DECISION_MAKERS,
    ),
    Slot(
        key="biz.cycle_time",
        label="现在这一轮大概要多久？",
        kind="text",
        family=FAMILY_BUSINESS,
        max_chars=80,
    ),
    Slot(
        key="biz.volume",
        label="大概的量是多少？（如每月多少单、多少张单据、多少家门店）",
        kind="text",
        family=FAMILY_BUSINESS,
        max_chars=80,
        hint="说不准可以留空——留空我们标「待澄清」，不会替你编。",
    ),
    Slot(
        key="sys.systems",
        label="现在在用哪些系统？（可多选）",
        kind="multi",
        family=FAMILY_SYSTEM,
        options=SYSTEM_OPTIONS,
    ),
    Slot(
        key="sys.integration_status",
        label="这些系统之间数据通不通？",
        kind="single",
        family=FAMILY_SYSTEM,
        options=INTEGRATION_STATES,
        show_if=("sys.systems",),
    ),
    Slot(
        key="sys.data_assets",
        label="业务数据、文档或知识现在放在哪里？",
        kind="text",
        family=FAMILY_SYSTEM,
        max_chars=200,
    ),
    Slot(
        key="sys.data_quality",
        label="这些数据可信吗？",
        kind="single",
        family=FAMILY_SYSTEM,
        options=DATA_QUALITY_STATES,
        show_if=("sys.data_assets",),
    ),
    Slot(
        key="pol.pain_priority",
        label="这次你最想解决什么？",
        kind="single",
        family=FAMILY_POLICY,
        options=PRIORITIES,
    ),
    Slot(
        key="ctx.free_text",
        label="用你自己的话说说，现在最难的是什么？",
        kind="long_text",
        family=FAMILY_CONTEXT,
        max_chars=600,
        hint="越具体越有用——例如「报价要问老工程师，一单两三天」。",
    ),
)

ALL_SLOTS: tuple[Slot, ...] = FIRST_SCREEN_SLOTS + DIAGNOSTIC_SLOTS
SLOT_BY_KEY: dict[str, Slot] = {slot.key: slot for slot in ALL_SLOTS}

# 留资时才问的联系方式（**不进问卷**，不进首屏）
CONTACT_SLOT_KEY = "ctx.contact"

MAX_SLOT_CHARS = 600
MAX_ANSWER_CHARS = 800
MAX_CONTACT_CHARS = 200


def questionnaire_payload() -> dict[str, object]:
    """对外问卷定义（公开只读；不含答案键）。"""
    return {
        "version": QUESTIONNAIRE_VERSION,
        "first_screen": [slot.to_dict() for slot in FIRST_SCREEN_SLOTS],
        "diagnostic": [slot.to_dict() for slot in DIAGNOSTIC_SLOTS],
        "total_questions": len(ALL_SLOTS),
        "notes": [
            "首屏 5 题出政策补贴测算卡（纯规则、零 AI、零成本），免注册即时可见。",
            "联系方式不在问卷里问——完整报告解锁时才收。",
            "留空的槽位会在报告里标「待澄清」，不会被编造补齐。",
        ],
    }
