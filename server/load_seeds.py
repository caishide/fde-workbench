"""P1 种子加载器（容器内运行：docker exec fde-workbench-api-1 python load_seeds.py）。

灌两样：
  1. sop_nodes ← seeds/sop_nodes.json（16 条，SOP v2.4.6 + 映射表 v1.3 快照）
  2. module_catalog 四条固定 SOP 段模块（§3.1 ProjectModule 对齐：售前/交付/交付后/横切）

不灌（留给后续阶段，防止抢跑）：
  - seeds/gates.json          → P3 门禁引擎在项目实例化 Gate 行时作为模板
  - seeds/payment_milestones.json → P4 收款模块

幂等：按 node_key / module_key upsert，重复运行安全；不删除库里多余行
（防误删人工数据）。种子是投影不是真相（A1），SOP 发版后重跑本脚本即可刷新。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from fde_api.app import create_app
from fde_api.extensions import db
from fde_api.workbench.models import ModuleCatalog, SopNode

SEED_DIR = Path(__file__).parent / "seeds"

# module_catalog 四段固定模块（module_key 前缀 sop_ 区分于上游通用模块）
SEGMENT_MODULES = [
    (
        "sop_presale",
        "售前段",
        "S0–S2：获客基建、线索筛选、免费初诊（G1/G2；真相在 leads.md/Twenty）",
        10,
    ),
    (
        "sop_delivery",
        "交付段",
        "S3–S9：深度诊断、提案签约、启动建档、Discover/Design、POC、五开关自查（G3–G8）",
        20,
    ),
    (
        "sop_post_delivery",
        "交付后段",
        "S10–S13：生产集成上线、售后陪跑、续约扩张、结项交接（G9；S13 value+receipts 闸门）",
        30,
    ),
    (
        "sop_cross_cut",
        "横切线",
        "S0-B 冷启动主动获客 / S7.5 范围蔓延应对等常开纪律",
        40,
    ),
]


def _upsert_sop_nodes(session) -> tuple[int, int]:
    payload = json.loads(
        (SEED_DIR / "sop_nodes.json").read_text(encoding="utf-8")
    )
    rows = payload["nodes"]
    existing = {
        node.node_key: node for node in session.scalars(select(SopNode))
    }
    created = 0
    for row in rows:
        fields = {
            "node_key": row["node_key"],
            "name": row["name"],
            "segment": row["segment"],
            "gate_key": row.get("gate_key"),
            "gate_note": row.get("gate_note"),
            "trigger": row.get("trigger") or "",
            "human_action": row.get("human_action") or "",
            # S7.5 无 ②/③ 小节出处 → ai_action=None，不发明
            "ai_action": row.get("ai_action"),
            "artifact": row.get("artifact") or "",
            "evidence_location": row.get("evidence_location") or "",
            "record_track": row.get("record_track") or [],
            "signer_role": row.get("signer_role"),
            "fail_exit": row.get("fail_exit") or "",
            "next_node": row.get("next_node") or "",
            "next_node_keys": row.get("next_node_keys") or [],
            "contract_payment_auth": row.get("contract_payment_auth"),
            # A4 出处指针：种子的 source_sha256 → 表列 content_hash
            "source_uri": row["source_uri"],
            "content_hash": row["source_sha256"],
            "human_ai_source_uri": row.get("human_ai_source_uri"),
            "human_ai_content_hash": row.get("human_ai_source_sha256"),
        }
        node = existing.get(row["node_key"])
        if node is None:
            session.add(SopNode(**fields))
            created += 1
        else:
            for key, value in fields.items():
                setattr(node, key, value)
    return len(rows), created


def _upsert_module_catalog(session) -> tuple[int, int]:
    existing = {
        item.module_key: item
        for item in session.scalars(select(ModuleCatalog))
    }
    created = 0
    for module_key, name, description, sort_order in SEGMENT_MODULES:
        row = existing.get(module_key)
        if row is None:
            session.add(
                ModuleCatalog(
                    module_key=module_key,
                    name=name,
                    description=description,
                    sort_order=sort_order,
                    is_active=True,
                )
            )
            created += 1
        else:
            row.name = name
            row.description = description
            row.sort_order = sort_order
            row.is_active = True
    return len(SEGMENT_MODULES), created


def main() -> int:
    app = create_app()
    with app.app_context():
        session = db.session()
        try:
            with session.begin():
                total_nodes, new_nodes = _upsert_sop_nodes(session)
                total_modules, new_modules = _upsert_module_catalog(session)
            print(
                f"sop_nodes: {new_nodes} 新增 / {total_nodes} 总计（期望 16）"
            )
            print(
                f"module_catalog: {new_modules} 新增 / {total_modules} 总计（期望 4）"
            )
            if total_nodes != 16:
                print(f"FAIL sop_nodes 期望 16 条，实际 {total_nodes}", file=sys.stderr)
                return 1
            if total_modules != 4:
                print(
                    f"FAIL module_catalog 期望 4 条，实际 {total_modules}",
                    file=sys.stderr,
                )
                return 1
            print("OK 种子灌入完成")
            return 0
        finally:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
