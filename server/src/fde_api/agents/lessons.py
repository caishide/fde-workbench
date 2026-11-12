# -*- coding: utf-8 -*-
"""agent 上下文知识片段（lessons）装载与选择（L 线 L3 轮，2026-11-12）。

设计稿 §2.3 方案 A：静态「经验条目」层起步——``server/seeds/lessons.json``
（条目＝{id, capability_tags, text, source_ref, sha256}），接线点
``agents/service.py::_render_context``（原硬编码空元组＝管道铺好、水源没接）。

**内容纪律**（设计稿 §2.3，静态钉机械承载）：条目只含抽象打法/判据，
**零案例答案、零客户资料、零未溯源数字**；来源＝SOP 现行产品已蒸馏资产
＋诊断案例集展示面提炼（展示面仅限已带「示例案例」角标的公开口径，
判卷基准侧永不进）；逐条登记 source_ref 指针。静态钉
``server/tests/test_lessons_wiring.py`` 钉住 schema 闭集、sha256 一致
（改 text 必留 diff）、答案字段词汇零命中、能力域闭集。

**运行时软失败**：生产 run 面对种子缺文件/形状坏一律回落空片段（渲染面
本就呈现「未检索到知识片段」）——种子质量问题由 CI 静态钉拦截，不在
run 路径上炸客户可见面。选择本身是纯函数（可独立测试）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# server/src/fde_api/agents/lessons.py → parents[3] = server → server/seeds/
SEEDS_PATH = Path(__file__).resolve().parents[3] / "seeds" / "lessons.json"

REQUIRED_ENTRY_KEYS = frozenset({"id", "capability_tags", "text", "source_ref", "sha256"})
OPTIONAL_ENTRY_KEYS = frozenset({"industries"})


@lru_cache(maxsize=8)
def _load_entries_cached(path_str: str, mtime_ns: int) -> tuple[dict[str, Any], ...]:
    raw = json.loads(Path(path_str).read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise SystemExit(f"lessons 种子形状非法（缺 entries 数组）：{path_str}")
    return tuple(entries)


def load_entries(path: Path | None = None) -> tuple[dict[str, Any], ...]:
    """装载种子条目（形状校验 fail-closed；供 CI 静态钉与测试直接调用）。"""
    seed_path = Path(path) if path is not None else SEEDS_PATH
    if not seed_path.is_file():
        raise SystemExit(f"lessons 种子不在场：{seed_path}")
    entries = _load_entries_cached(str(seed_path.resolve()), seed_path.stat().st_mtime_ns)
    for entry in entries:
        if not isinstance(entry, dict) or not REQUIRED_ENTRY_KEYS.issubset(entry):
            raise SystemExit("lessons 条目缺必填键（id/capability_tags/text/source_ref/sha256）")
        unknown = set(entry) - REQUIRED_ENTRY_KEYS - OPTIONAL_ENTRY_KEYS
        if unknown:
            raise SystemExit(f"lessons 条目未知键（schema 闭集）：{sorted(unknown)}")
    return entries


def select_lessons(
    entries: Any,
    *,
    capability_tier: str,
    project_industry: str | None = None,
    top_k: int = 3,
    max_chars: int = 400,
) -> list[dict[str, str]]:
    """按能力腿＋项目行业过滤取前 K 条，单条截断（纯函数）。

    - 能力腿过滤：条目 ``capability_tags`` 须包含当前 agent 的
      ``capability_tier``——不同能力腿的 agent 只看到与己相关的经验；
    - 行业过滤：条目声明 ``industries`` 时仅注入匹配行业（缺省＝通用条目）；
    - ``top_k``／``max_chars``：上下文膨胀上限（配置位，默认进 Settings）。
    """
    picked: list[dict[str, str]] = []
    for entry in entries:
        tags = entry.get("capability_tags") or []
        if capability_tier not in tags:
            continue
        industries = entry.get("industries") or []
        if industries and project_industry not in industries:
            continue
        text = str(entry.get("text") or "")
        picked.append({"id": str(entry.get("id") or ""), "text": text[:max_chars]})
        if len(picked) >= top_k:
            break
    return picked


def knowledge_snippets_for(*, project: Any, agent: Any, settings: Any) -> tuple[dict[str, str], ...]:
    """``_render_context`` 接线入口：返回可注入 ``render_masked_context`` 的片段。

    任何装载/读取异常都回落空元组（运行时软失败——CI 静态钉保证种子质量，
    run 路径不为种子问题炸客户可见面）；渲染面既有禁区词＋模式遮蔽闸对
    注入文本二次把关（``render_masked_context`` 内 ``_clean``），零新脱敏面。
    """
    if not bool(getattr(settings, "fde_agent_lessons_enabled", False)):
        return ()
    try:
        entries = load_entries()
    except (Exception, SystemExit):
        # SystemExit 是 BaseException 直系——load_entries 的 fail-closed 异常
        # 也必须被软失败接住（种子缺文件/形状坏都不炸 run 路径）。
        return ()
    industry: str | None = None
    snapshot = getattr(project, "template_snapshot", None)
    if isinstance(snapshot, dict):
        industry = snapshot.get("industry_name") or None
    picked = select_lessons(
        entries,
        capability_tier=str(getattr(agent, "capability_tier", "") or ""),
        project_industry=industry,
        top_k=int(getattr(settings, "fde_agent_lessons_top_k", 3)),
        max_chars=int(getattr(settings, "fde_agent_lessons_max_chars", 400)),
    )
    return tuple(picked)
