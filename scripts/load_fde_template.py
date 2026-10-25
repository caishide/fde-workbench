"""P5 种子：灌「标准 FDE 项目」行业模板（Template→Module→Task→Dependency 四层）。

容器内运行：docker exec -i fde-workbench-api-1 python - < scripts/load_fde_template.py

口径（设计 §7 / SOP v2.4.6 映射表 v1.3，全部数据驱动，不硬编码节点清单）：
- 14 节点任务 = sop_nodes.json 里 segment != 横切线 的全部节点
  （S0-B、S1、S2 / S3–S9 / S10–S13；横切线 S0 获客基建、S7.5 范围蔓延是常开纪律，
   不占顺序节点——映射表抽取约定）。
- 三段模块挂 module_catalog 既有四段键（sop_presale / sop_delivery / sop_post_delivery）。
- 依赖边来自节点 next_node_keys ∩ 选中集，外加三条主链衔接边（种子 next_node/
  gate_note 原文有出处，keys 抽取器没落）：
    S8→S10（S8.next_node="S10（proceed）"）
    S9→S8 （S9.gate_note="并入G8前执行"）
    S12→S13（S12.next_node="S13 或循环回 S6"——循环不建模）
- task_key = node_key 稳定键（小写、-/. → _：S0-B→s0_b），与
  projects/service._annotate_sop_tasks 同规——派生时自动补 sop_node/gate 挂点（9 门）。
- duration_days=1 为占位（SOP 无逐节点工时口径，不发明），派生后按实际排期调整。

幂等：模板名「标准 FDE 项目」已存在则跳过（不重复灌）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from fde_api.app import create_app
from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.templates.service import (
    TemplateServiceError,
    create_template,
    publish_template_version,
)
from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion

SEED_DIR = Path(__file__).parent.parent / "seeds"
TEMPLATE_NAME = "标准 FDE 项目"

# 三条主链衔接边（出处见模块 docstring；两端都在选中集才生效）
SUPPLEMENT_EDGES = (("S8", "S10"), ("S9", "S8"), ("S12", "S13"))


def _stable_key(node_key: str) -> str:
    return node_key.lower().replace("-", "_").replace(".", "_")


def _build_modules(nodes: list[dict]) -> list[dict]:
    selected = {n["node_key"]: n for n in nodes if n.get("segment") != "横切线"}
    if len(selected) != 14:
        raise SystemExit(
            f"FAIL 期望 14 个非横切节点（S0-B + S1–S13），实际 {len(selected)}："
            + "、".join(sorted(selected))
        )

    def node_edges(node_key: str) -> list[str]:
        """task 的 dependency_keys = 前驱集：谁 next 指向我 + 补充衔接边。"""
        preds = [
            _stable_key(pred_key)
            for pred_key, pred in selected.items()
            if node_key in (pred.get("next_node_keys") or [])
        ]
        for pred, succ in SUPPLEMENT_EDGES:
            if succ == node_key and pred in selected:
                preds.append(_stable_key(pred))
        return sorted(set(preds))

    segment_modules = [
        ("sop_presale", "售前段", 10),
        ("sop_delivery", "交付段", 20),
        ("sop_post_delivery", "交付后段", 30),
    ]
    modules: list[dict] = []
    order = 0
    for module_key, label, sort_order in segment_modules:
        tasks = []
        for node_key, node in sorted(selected.items()):
            if node.get("segment") != label:
                continue
            order += 1
            gate = node.get("gate_key")
            description = (
                f"SOP 节点 {node_key}：{node['name']}。"
                f"触发：{node.get('trigger') or '—'}。"
                f"产出：{node.get('artifact') or '—'}。"
                f"门禁：{gate or '无'}。"
                f"出处：{node['source_uri']}。"
                "工期为占位 1 天（SOP 无逐节点工时口径），派生后按实际排期调整。"
            )
            tasks.append(
                {
                    "task_key": _stable_key(node_key),
                    "name": f"{node_key} {node['name']}",
                    "description": description,
                    "duration_days": 1,
                    "default_assignee_role": "project_lead",
                    "sort_order": order,
                    "dependency_keys": node_edges(node_key),
                }
            )
        if not tasks:
            raise SystemExit(f"FAIL 段 {label} 无节点")
        modules.append(
            {
                "module_key": module_key,
                "name": f"{label}（SOP）",
                "description": f"SOP v2.4.6 {label}节点任务（映射表 v1.3 程序化）",
                "sort_order": sort_order,
                "tasks": tasks,
            }
        )
    return modules


def main() -> int:
    app = create_app()
    with app.app_context():
        session = db.session()
        try:
            admin = session.scalars(
                select(User).where(User.role == "admin", User.is_active.is_(True))
            ).first()
            if admin is None:
                print("FAIL 找不到可用 admin 用户", file=sys.stderr)
                return 1

            existing = session.scalars(
                select(IndustryTemplate).where(IndustryTemplate.name == TEMPLATE_NAME)
            ).first()
            if existing is not None:
                published = session.scalar(
                    select(IndustryTemplateVersion).where(
                        IndustryTemplateVersion.template_id == existing.id,
                        IndustryTemplateVersion.status == "published",
                    )
                )
                if published is not None:
                    print(
                        f"SKIP 模板「{TEMPLATE_NAME}」已存在（published {published.id}）"
                    )
                    return 0
                # 上次发布失败留下的草稿不许永久卡死（create_template 已独立提交）：
                # 重试发布最新版本，而不是 exit 0 掩盖问题。
                draft = session.scalars(
                    select(IndustryTemplateVersion)
                    .where(IndustryTemplateVersion.template_id == existing.id)
                    .order_by(IndustryTemplateVersion.version.desc())
                    .limit(1)
                ).first()
                if draft is None:
                    print("FAIL 模板存在但没有任何版本", file=sys.stderr)
                    return 1
                publish_template_version(
                    actor=admin, version_id=draft.id, expected_version=draft.version
                )
                print(f"OK 补发布成功：{TEMPLATE_NAME} version_id={draft.id}")
                return 0

            payload = json.loads(
                (SEED_DIR / "sop_nodes.json").read_text(encoding="utf-8")
            )
            modules = _build_modules(payload["nodes"])
            task_count = sum(len(m["tasks"]) for m in modules)
            edge_count = sum(len(t["dependency_keys"]) for m in modules for t in m["tasks"])
            print(f"模块 {len(modules)} / 任务 {task_count} / 依赖边 {edge_count}")

            version = create_template(
                actor=admin,
                name=TEMPLATE_NAME,
                industry_name="FDE",
                description=(
                    "SOP v2.4.6 双轨主线 14 节点模板（S0-B + S1–S13；横切线 S0/S7.5 "
                    "常开不占节点）。派生后任务自动挂 SOP 节点与 9 门门禁挂点，"
                    "门禁清单由门禁引擎懒实例化。"
                ),
                modules=modules,
            )
            publish_template_version(
                actor=admin, version_id=version.id, expected_version=version.version
            )
            print(f"OK 模板已发布：{TEMPLATE_NAME} version_id={version.id}")
            return 0
        except TemplateServiceError as error:
            print(f"FAIL 模板服务错误：{error.code} {error.message}", file=sys.stderr)
            return 1
        finally:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
