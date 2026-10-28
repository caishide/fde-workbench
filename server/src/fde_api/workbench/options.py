"""工作台业务枚举选项表（WP29/J1）。

为什么要下发：桌面端此前把业务枚举硬编码在渲染层（价格档位、门禁五态标签、
C 分支处理方式、SOW 类型、业务阶段）。口径一变就得改前端代码，且各页面各写
一份容易漂移。本模块把选项表放服务端下发，前端消费并保留本地兜底（见
desktop/src/renderer/src/workbench/options.ts）。

口径纪律：这里只做「选项表下发 + 展示标签」，**不改任何字段契约、不新增业务
字段**——value 一律沿用既有存库值（如 tier="standard"、status="conditional_pass"），
前端提交的还是同一个字符串。
"""

from __future__ import annotations

from typing import Any

# 价格档位：value 沿用报价卡的 tier 键（报价卡公式与系数集合一字不动）
PRICE_TIERS: list[dict[str, str]] = [
    {"value": "light", "label": "轻量（25h / 现金 ¥1,500）"},
    {"value": "standard", "label": "标准（50h / 现金 ¥5,000）"},
    {"value": "flagship", "label": "旗舰（80h / 现金 ¥9,000）"},
]

# 门禁五态（pending/evidence/passed/conditional_pass/failed）+ 徽标样式
GATE_STATUSES: list[dict[str, str]] = [
    {"value": "pending", "label": "待证据", "tone": "muted"},
    {"value": "evidence", "label": "待核验", "tone": "warning"},
    {"value": "passed", "label": "已过门", "tone": "success"},
    {"value": "conditional_pass", "label": "有条件通过", "tone": "warning"},
    {"value": "failed", "label": "未过门", "tone": "danger"},
]

# C 分支处理方式（服务端对未知值返回 400，前端不再各自硬编码）
C_HANDLING_OPTIONS: list[dict[str, str]] = [
    {"value": "scope_cut", "label": "① 缩范围"},
    {"value": "split_phases", "label": "② 拆分期"},
    {"value": "external_collab", "label": "③ 外部协作"},
    {"value": "ticket_deal", "label": "④ 门票单（记亏损与补回路径）"},
]

# SOW 类型
SOW_OPTIONS: list[dict[str, str]] = [
    {"value": "b", "label": "B 试点（50/50）"},
    {"value": "c", "label": "C 集成（40/40/20）"},
    {"value": "a", "label": "A 诊断（预付）"},
    {"value": "d", "label": "D 陪跑（月付预付）"},
]

# 业务阶段：value 沿用历史存库的**中文标签**（旧数据兼容，不改契约）；
# key 是稳定标识，供前端按 key 引用而不依赖中文文案。
BUSINESS_CATEGORIES: list[dict[str, str]] = [
    {"key": "contract", "value": "商务合约", "label": "商务合约"},
    {"key": "presurvey", "value": "预调研", "label": "预调研"},
    {"key": "research", "value": "调研", "label": "调研"},
    {"key": "pov", "value": "PoV验证", "label": "PoV验证"},
    {"key": "deployment", "value": "生产部署", "label": "生产部署"},
    {"key": "handover", "value": "培训预交接", "label": "培训预交接"},
]


def options_payload() -> dict[str, Any]:
    """整包选项表（前端一次拉取，本地兜底见 options.ts）。"""
    return {
        "price_tiers": PRICE_TIERS,
        "gate_statuses": GATE_STATUSES,
        "c_handling_options": C_HANDLING_OPTIONS,
        "sow_options": SOW_OPTIONS,
        "business_categories": BUSINESS_CATEGORIES,
    }
