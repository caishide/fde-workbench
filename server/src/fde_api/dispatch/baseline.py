"""F 线 T2：五席位分账「上线前初始基线」版本常量（ADR-011 §3，2026-11-11）。

迁移种入 ``dispatch_rule_versions`` 一行 ``status='active'`` 的初始基线
（docs/commercialization/rules/five-seat-split-rules.md §10 豁免边界：
「初始基线」不是「对存量规则的变更」，§6.2 公示窗不适用——**不是永久
豁免，也没有豁免分支**，上线后任何改值仍必须走 create_rule_version +
30 天公示）。

机器可读块三方逐位一致闸（test_dispatch_five_seat_baseline.py）：本模块
常量 ↔ 迁移内联字面量 ↔ 规则文件 JSON 块 ``rule_versioning.initial_baseline``。

快照形状裁决（两处细节都是刻意的）：

- 五席位比例落 ``five_seat`` 块（``platform_share_percent`` + ``pool_shares``，
  字段名与 ``allocate_five_seats::_five_seat_shares`` 读法一致）——这就是
  「seat_shares 表达平台 30% + 池内 30/50/10/10」的唯一正确形状；平台份额
  与池内份数是**两个 100**（基数 100% vs 池内百份制），不能摊平进一个键。
- **不含**旧四席位 ``seat_shares``（35/5/20/40）/冷启动键：旧口径是待迁移
  口径，不得写进新层基线行（规则文件锚点表）。旧消费方
  ``seat_shares_for`` 对缺键回退 ``DISPATCH_CONSTANTS``，行为与基线前逐位
  一致；``stage_b_weights``/``level_score_map`` 随基线落快照（与常量同值）
  ——基线 active 后撮合按快照打分，落这两节才能不静默空权重。
"""

from __future__ import annotations
from typing import Any

# 初始基线版本号：占保留段 100。1–99 留给上线后人工版本序列
# （create_rule_version 语义上的「第一版」），迁移种子不与任何人工版本
# 竞争编号；三方闸把该值钉在规则文件 initial_baseline.version_no。
FIVE_SEAT_BASELINE_VERSION_NO = 100

# 基线快照（唯一权威形状；迁移内联字面量与此逐位一致，三方闸钉死）。
FIVE_SEAT_BASELINE_SNAPSHOT: dict[str, Any] = {
    "snapshot_kind": "initial_baseline",
    "five_seat": {
        "platform_share_percent": 30,
        "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "province": 10},
    },
    # Stage B 权重与等级映射分：与 DISPATCH_CONSTANTS 同值（撮合快照必备
    # 节）；字面量随迁移冻结，与常量的逐位一致由机器闸断言。
    "stage_b_weights": {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10},
    "level_score_map": {"L1": 40, "L2": 60, "L3": 80, "L4": 100},
}
