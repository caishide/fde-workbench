"""政策条目数据（首屏「政策补贴测算」卡的规则底料）。

**引用纪律**（沿本地政策弹药库红线，逐条可溯源）：

1. **原文口径层**（``POLICY_ENTRIES``）只放**政策原文口径** + 官方出处 +
   快照日期；**不改写、不缩写、不外推**。
2. **我方解读层**（``POLICY_INTERPRETATION``）单独放我方对适用对象与享受前提
   的归纳，**必须标注「我方解读」**；引用到对外文案时不得写成政策原文。
3. **本模块不落补贴金额**——弹药库五条均未披露具体补贴额度，任何金额都会是
   编造数字（R-4「未溯源数字 fail-closed」）。测算卡只算**资格与准备度**。

快照日期：``POLICY_SNAPSHOT_DATE``。**停更超 30 天须重核**（弹药库红线）。

来源：本地真相层 ``D:\\test\\FDE\\knowledge\\policy\\政策弹药库-时间轴-2026-10-19.md``
（五条政策均经双层证据核查：官方原文 + 权威媒体交叉）。本仓已按「独立重写 +
来源对照表」落库，政策原文口径不改写。
"""
from __future__ import annotations

from dataclasses import dataclass

POLICY_SNAPSHOT_DATE = "2026-10-19"

# 双层依据的**标签**（单一真身：测算卡与 AI 报告共用，避免两处各写各的）
ORIGINAL_LABEL = "原文口径"
INTERPRETATION_LABEL = "我方解读"

# 弹药库「⚠️ 核查中纠正的两处口径」——引用前必读，防再次写错
POLICY_CORRECTIONS: tuple[str, ...] = (
    "国发11号的 70%：原文是『新一代智能终端、智能体等**应用**普及率超 70%』"
    "——含智能终端、是『应用普及率』。**不得**缩写成『智能体普及率 >70%』。",
    "279号『第十四条』：原文没有『四项工作无一能远程交付』这句话。"
    "第十四条原文是『发展赋能应用服务商』，那五项是服务商侧能力清单。"
    "『这类活没有一样能隔着屏幕干完』是**我方解读**，引用时必须标注。",
)


@dataclass(frozen=True, slots=True)
class PolicyEntry:
    """一条政策（**原文口径层**）。

    ``original_wording`` 只放原文口径；``official_source_url`` 是官方出处；
    ``snapshot_date`` 是本地快照日期（超 30 天须重核）。
    """

    policy_id: str
    title: str
    doc_number: str
    issued_on: str
    original_wording: str
    official_source_url: str
    snapshot_date: str = POLICY_SNAPSHOT_DATE


POLICY_ENTRIES: tuple[PolicyEntry, ...] = (
    PolicyEntry(
        policy_id="gov_work_report_2024_03",
        title="《政府工作报告》「人工智能+」行动首次写入",
        doc_number="—",
        issued_on="2024-03",
        original_wording="「人工智能+」行动首次写入政府工作报告；此后每年持续推进。",
        official_source_url="https://www.gov.cn/",
    ),
    PolicyEntry(
        policy_id="guofa_2025_11",
        title="《国务院关于深入实施「人工智能+」行动的意见》",
        doc_number="国发〔2025〕11号",
        issued_on="2025-08-21",
        original_wording=(
            "「到 2027 年……新一代智能终端、智能体等**应用普及率超 70%**」；"
            "「培育人工智能应用服务商，发展『模型即服务』『智能体即服务』」。"
        ),
        official_source_url="https://www.gov.cn/zhengce/zhengceku/202508/content_7037862.htm",
    ),
    PolicyEntry(
        policy_id="miit_lianke_2025_279",
        title="八部门《「人工智能+制造」专项行动实施意见》",
        doc_number="工信部联科〔2025〕279号",
        issued_on="2025-12-25",
        original_wording=(
            "2027 目标：「打造一批『懂智能、熟行业』的**赋能应用服务商**」；"
            "第十四条「发展赋能应用服务商」：行业模型调优、数据治理、安全保障、"
            "生态伙伴型服务商、优质服务商目录。"
        ),
        official_source_url=(
            "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/202512/"
            "8b6a31547603437db54d6596d33d04c4.pdf"
        ),
    ),
    PolicyEntry(
        policy_id="miit_minister_2026_03_05",
        title="工信部部长「部长通道」公开表述",
        doc_number="—",
        issued_on="2026-03-05",
        original_wording=(
            "「『人工智能+制造』是一个**必答题，不是一个选择题。**」"
            "同场披露：「我国规上制造业企业人工智能技术应用普及率**超 30%**，"
            "这是到去年底的数据」。"
        ),
        official_source_url=(
            "https://www.miit.gov.cn/xwfb/bldhd/art/2026/art_e4b64e4dd78544708df400dd1042bdee.html"
        ),
    ),
    PolicyEntry(
        policy_id="miit_lianyue_2026_343",
        title="六部门《关于开展 2026 年度智能工厂梯度培育行动的通知》"
        "＋《智能工厂梯度培育要素条件(2026年版)》",
        doc_number="工信厅联通装函〔2026〕343号",
        issued_on="2026-07-15",
        original_wording=(
            "卓越级智能工厂「应用人工智能技术场景比例**不低于 30%**」"
            "（2025 年版为 20%，一年抬 10 个点）；领航级不低于 60%。"
        ),
        official_source_url="https://www.miit.gov.cn/",
    ),
)

POLICY_BY_ID: dict[str, PolicyEntry] = {entry.policy_id: entry for entry in POLICY_ENTRIES}


@dataclass(frozen=True, slots=True)
class PolicyInterpretation:
    """我方解读层（**非政策原文**）。

    适用对象与享受前提是我方对政策原文的归纳，用于规则判定；对外文案引用时
    **必须标注「我方解读」**。

    ``preparation_requirements`` 只放**享受前提**（可判定的条件）；
    ``verification_steps`` 放「向谁确认」类动作（不是前提，是下一步）。
    """

    policy_id: str
    label: str
    applicable_industries: tuple[str, ...]
    requires_qualifications: tuple[str, ...]
    preparation_requirements: tuple[str, ...]
    verification_steps: tuple[str, ...] = ()
    note: str = ""


POLICY_INTERPRETATION: tuple[PolicyInterpretation, ...] = (
    PolicyInterpretation(
        policy_id="miit_lianyue_2026_343",
        label="智能工厂梯度培育",
        applicable_industries=("制造与工业",),
        requires_qualifications=("规上工业企业",),
        preparation_requirements=(
            "AI 技术应用场景比例达标（卓越级不低于 30%／领航级不低于 60%，2026 年版）",
        ),
        verification_steps=(
            "向本地工信主管部门确认梯度培育申报口径、时间窗与所需材料",
        ),
        note="要素条件的完整清单以 2026 年版原文为准，本卡不代为列举。",
    ),
    PolicyInterpretation(
        policy_id="miit_lianke_2025_279",
        label="「人工智能+制造」行动",
        applicable_industries=("制造与工业",),
        requires_qualifications=(),
        preparation_requirements=(
            "服务商侧需具备行业模型调优与数据治理能力（279 号第十四条列举的服务商能力）",
        ),
    ),
    PolicyInterpretation(
        policy_id="guofa_2025_11",
        label="「人工智能+」行动",
        applicable_industries=(),
        requires_qualifications=(),
        preparation_requirements=(
            "应用普及率口径含智能终端与智能体（国发11号原文口径）",
        ),
    ),
    PolicyInterpretation(
        policy_id="miit_minister_2026_03_05",
        label="规上制造业 AI 应用普及率现状基线",
        applicable_industries=("制造与工业",),
        requires_qualifications=("规上工业企业",),
        preparation_requirements=(
            "规上制造业企业 AI 技术应用普及率已超 30%（部长通道披露口径，截至其发言时点）",
        ),
    ),
)

INTERPRETATION_BY_POLICY_ID: dict[str, PolicyInterpretation] = {
    item.policy_id: item for item in POLICY_INTERPRETATION
}
