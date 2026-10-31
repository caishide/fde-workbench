"""撮合评分原语（设计 §4.3/§4.4/§4.7，P1-2）。

纯函数、无 DB 依赖——权重/映射分全部经参数注入（active 规则版本快照，
§4.3「唯一来源是版本表，不硬编码」；调用方从 dispatch.rules 取）。

负面清单对应关系（§5.2/规则表 A-6，测试逐条反例钉死）：
- #1 软画像：本模块零画像输入（只有 level 标量 + 申报标签 + 静态城市）；
- #2 历史接单量/响应率：函数签名无历史参数（结构性地进不了排序）；
- #3 位置轨迹：地理输入只有 home_city / client_city 两个静态申报字段；
- #4 地理连续加权：geo 只有分档（geo_tier 0–3 / 加权维度仅 100/50/0 三档）。
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

LEVEL_RANKS = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


def level_rank(level: str | None) -> int:
    return LEVEL_RANKS.get(level or "", 0)


def level_score(level: str | None, rule: Mapping[str, Any]) -> int:
    """等级映射分（§4.3：L1=40…L4=100 等距 20，取值进版本快照）。"""
    mapping = rule.get("level_score_map") or {}
    return int(mapping.get(level, 0))


def industry_score(
    industry_tags: list[Any] | None, required_industry: str | None
) -> int:
    """行业匹配分（§4.3：精确命中 100 / 大类 60 / 未命中 0）。

    大类（business_category）映射随行业模板库 A7 落位——一期只有精确档
    （goal-r5 留注⑭：required_industry 为空时发布侧已放行 A3，此处恒 100
    只发生在 required 为空的包，排序中性）。
    """
    if not required_industry:
        return 100
    tags = {str(tag) for tag in (industry_tags or [])}
    return 100 if required_industry in tags else 0


def sla_score() -> int:
    """服务时限可达性（§4.3：满足 100 / 可协商 50 / 不满足 0）。

    fde_profiles 无档期/SLA 承诺字段（goal-r5 留注⑫）——一期统一按
    「可协商=50」，对所有候选同值 → 排序影响中性；档期字段随 P2 落位后
    接真实判定。
    """
    return 50


def geo_score(tier: int) -> int:
    """地理分（§4.3 远程型专用维度：同城 100 / 同省 50 / 其他 0）。"""
    return {0: 100, 1: 50}.get(tier, 0)


def geo_tier(
    home_city: str | None,
    client_city: str | None,
    city_index: Mapping[str, tuple[str | None, str | None]],
) -> int:
    """地理分档（§4.7，一期城市级、双静态数据源）：
    0 同城（字符串精确相等）/ 1 同省 / 2 同都市圈跨省 / 3 全国（其余）。
    city_index: city → (province, metro_group)，来自 dispatch_cities.json。"""
    if not home_city or not client_city:
        return 3
    if home_city == client_city:
        return 0
    home = city_index.get(home_city)
    client = city_index.get(client_city)
    home_province = home[0] if home else None
    client_province = client[0] if client else None
    if home_province and home_province == client_province:
        return 1
    home_metro = home[1] if home else None
    client_metro = client[1] if client else None
    if home_metro and home_metro == client_metro:
        return 2
    return 3


def weighted_score(
    *,
    level: str | None,
    industry_tags: list[Any] | None,
    tier: int,
    rule: Mapping[str, Any],
) -> int:
    """Stage B 加权总分（§4.3：等级 40 / 行业 30 / 时限 20 / 地理 10）。
    权重取值来自版本快照；sla 统一 50（留注⑫）。"""
    weights = rule.get("stage_b_weights") or {}
    industry = industry_score(industry_tags, rule.get("_required_industry"))
    total = (
        level_score(level, rule) * int(weights.get("level", 0))
        + industry * int(weights.get("industry", 0))
        + sla_score() * int(weights.get("sla", 0))
        + geo_score(tier) * int(weights.get("geo_remote", 0))
    )
    return total // 100


def tie_break_seed(package_id: str, dispatch_round: int, version_no: int) -> int:
    """可复现随机种子（§4.3 tie-break ②：seed=hash(package_id, round, version_no)
    ——替代已废弃的「距今时效」公平目标，负面清单 #2 的合规实现）。"""
    digest = hashlib.sha256(
        f"{package_id}:{dispatch_round}:{version_no}".encode("utf-8")
    ).hexdigest()
    return int(digest[:8], 16)


def sort_key_onsite(
    *, tier: int, level: str | None, industry: int, sla: int
) -> tuple[int, int, int, int]:
    """到场型字典序（§4.4 场景 A）：(geo_tier, -level_rank, -industry, -sla)。
    差旅实报实销是真金白银，地理一级键不可被能力分稀释（负面清单 #4 反例的
    结构保证：tier 是字典序分量不是加权项）。"""
    return (tier, -level_rank(level), -industry, -sla)


def sort_key_remote(
    *, weighted: int, in_fence: bool, seed: int, candidate_key: str
) -> tuple[int, int, int, int]:
    """远程型加权序（§4.4 场景 B）：(-weighted, not in_fence, rng, 稳定尾键)。
    尾键用候选 id 的稳定散列保证同种子下全序确定（Python sort 稳定性已够，
    尾键只为跨进程可复现）。"""
    candidate_hash = int(hashlib.sha256(candidate_key.encode("utf-8")).hexdigest()[:8], 16)
    return (-weighted, 0 if in_fence else 1, seed % 100000, candidate_hash)


def in_fence(home_city: str | None, client_city: str | None, fence_km: int) -> bool:
    """围栏内优先（§4.3 tie-break ①；一期城市级：同城即视为围栏内）。
    geo_fence_km 的 km 语义二期坐标级才生效（§4.7 一期日志口径）。"""
    return bool(home_city and client_city and home_city == client_city)


__all__ = [
    "LEVEL_RANKS",
    "geo_score",
    "geo_tier",
    "in_fence",
    "industry_score",
    "level_rank",
    "level_score",
    "sla_score",
    "sort_key_onsite",
    "sort_key_remote",
    "tie_break_seed",
    "weighted_score",
]
