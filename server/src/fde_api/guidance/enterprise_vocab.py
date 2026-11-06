"""T-A2 企业名词典单点：检测词表与替换条目的唯一定义处。

拍板 6②（2026-11-06）：词典为仓库内种子文件（``server/seeds/enterprise_redaction.json``），
CI 扫库（``scripts/check-pseudonymization.sh`` 经 ``scripts/extract_company_names.py``
调用本模块）与入库替换（``guidance/redaction.py``）读同一个文件、同一份正则——
「替换器词典 == CI 词典」由 pytest 逐条钉死，不再是文字承诺。

词典内容纪律（红线级）：本仓种子文件只允许存放**检测词表**（后缀词/长度界，与
原 check-pseudonymization.sh 内联 perl 正则逐位等价）与**合成示例条目**
（与 ``.github/ci-assets/synthetic-leads-blacklist.txt`` 同族）；真实企业名→代号
的映射经 ``FDE_ENTERPRISE_DICT`` 指向的本地覆盖文件注入（与 ``FDE_LEADS_MD``
同一注入模型，约定路径 ``server/seeds/enterprise_redaction.local.json`` 已
gitignore）——真实姓名永不进 git 历史与远端（AGENTS.md 红线上位）。

本模块刻意保持纯标准库零 fde_api 依赖，使 CI 脚本无需安装服务端依赖即可复用
同一份模式定义。机械性故障（缺文件/坏 JSON/形状非法/正则编译失败/替换值自撞
检测模式）一律抛 :class:`EnterpriseDictionaryError`——按拍板 6① 由调用方
fail-closed 硬阻断，绝不静默降级。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# 与原 check-pseudonymization.sh 内联 perl 正则逐位等价的码位区间（按码位匹配，
# 与 locale 完全无关——perl 时代的可移植性结论原样继承）。
_CJK_RANGE = "\\u4e00-\\u9fa5"

_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds"
SEED_PATH = _SEEDS_DIR / "enterprise_redaction.json"
# 真名条目唯一合法入口：gitignored 本地覆盖文件（env 显式指定优先）。
LOCAL_OVERRIDE_PATH = _SEEDS_DIR / "enterprise_redaction.local.json"
OVERRIDE_ENV = "FDE_ENTERPRISE_DICT"


class EnterpriseDictionaryError(Exception):
    """词典机械性故障——拍板 6① fail-closed：调用方必须硬阻断，不许静默降级。"""


@dataclass(frozen=True)
class EnterpriseDictionary:
    """加载完毕的词典：编译好的检测模式 + 收录条目（名称→替换值）。

    ``detect``/``replace`` 是仅有的两个行为面：入库替换层只消费 ``replace``
    （收录→代号），读面与确认闸只消费 ``detect``（疑似→待复核清单）。
    """

    pattern: re.Pattern[str]
    replacements: Mapping[str, str]
    suffixes: tuple[str, ...]
    min_length: int
    max_length: int

    def detect(self, text: str) -> list[tuple[str, int, int]]:
        """非重叠扫描出全部「疑似企业名」片段（match, start, end）。"""
        return [(item.group(0), item.start(), item.end()) for item in self.pattern.finditer(text)]

    def replace(self, text: str) -> tuple[str, list[str]]:
        """把收录条目确定性替换为其代号；返回（新文本, 命中的收录名）。

        长名优先（防「甲公司」遮蔽「甲公司集团」）；未收录的模式命中一律
        **不替换**（拍板 6①：疑似放行，交给待复核清单）。
        """
        replaced: list[str] = []
        for name in sorted(self.replacements, key=len, reverse=True):
            value = self.replacements[name]
            if name and name in text:
                text = text.replace(name, value)
                replaced.append(name)
        return text, replaced


def load_dictionary(
    *, seed_path: Path | None = None, override_path: Path | None = None
) -> EnterpriseDictionary:
    """加载词典：种子文件（必在）+ 本地覆盖（可选，键级合并、覆盖方优先）。

    覆盖文件解析序：显式参数 > 环境变量 ``FDE_ENTERPRISE_DICT`` > 约定路径
    （存在才并入）。mtime 参与 lru_cache 键——文件变更即自动失效，无需手动清缓存。
    """
    seed = Path(seed_path) if seed_path is not None else SEED_PATH
    override = _resolve_override(override_path)
    try:
        seed_stat = seed.stat()
        override_stat = override.stat() if override is not None else None
    except OSError as error:
        raise EnterpriseDictionaryError(f"企业名词典文件不可访问：{error}") from error
    return _load_cached(
        str(seed),
        seed_stat.st_mtime_ns,
        str(override) if override is not None else "",
        override_stat.st_mtime_ns if override_stat is not None else None,
    )


def _resolve_override(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    from_env = os.environ.get(OVERRIDE_ENV, "").strip()
    if from_env:
        return Path(from_env)
    if LOCAL_OVERRIDE_PATH.is_file():
        return LOCAL_OVERRIDE_PATH
    return None


@lru_cache(maxsize=8)
def _load_cached(
    seed_key: str, _seed_mtime: int, override_key: str, _override_mtime: int | None
) -> EnterpriseDictionary:
    payload = _read_mapping(Path(seed_key), label="企业名词典种子")
    detection = payload.get("detection")
    if not isinstance(detection, dict):
        raise EnterpriseDictionaryError("企业名词典种子缺少 detection 对象")
    suffixes = detection.get("suffixes")
    min_length = detection.get("min_length")
    max_length = detection.get("max_length")
    if (
        not isinstance(suffixes, list)
        or not suffixes
        or not all(isinstance(word, str) and word for word in suffixes)
    ):
        raise EnterpriseDictionaryError("detection.suffixes 必须是非空字符串列表")
    if not isinstance(min_length, int) or not isinstance(max_length, int) or min_length < 1 or max_length < min_length:
        raise EnterpriseDictionaryError("detection 长度界非法（需 1 <= min_length <= max_length）")
    replacements = payload.get("replacements")
    if not isinstance(replacements, dict) or not all(
        isinstance(name, str) and name and isinstance(value, str) and value
        for name, value in replacements.items()
    ):
        raise EnterpriseDictionaryError("replacements 必须是「非空名称→非空替换值」映射")
    if override_key:
        override_payload = _read_mapping(Path(override_key), label="企业名词典本地覆盖")
        override_items = override_payload.get("replacements")
        if not isinstance(override_items, dict) or not all(
            isinstance(name, str) and name and isinstance(value, str) and value
            for name, value in override_items.items()
        ):
            raise EnterpriseDictionaryError("本地覆盖 replacements 必须是「非空名称→非空替换值」映射")
        replacements = {**replacements, **override_items}
    try:
        pattern = re.compile(
            f"[{_CJK_RANGE}]{{{min_length},{max_length}}}(?:{'|'.join(re.escape(word) for word in suffixes)})"
        )
    except re.error as error:
        raise EnterpriseDictionaryError(f"检测正则编译失败：{error}") from error
    # 自洽律：替换值不得再命中检测模式——否则替换后的文本会被待复核清单
    # 反复标记，替换层与检测层互相打架。违背即词典故障，fail-closed。
    offenders = sorted(name for name, value in replacements.items() if pattern.search(value))
    if offenders:
        raise EnterpriseDictionaryError(f"替换值命中检测模式（会替换后被复标）：{offenders[0]}")
    return EnterpriseDictionary(
        pattern=pattern,
        replacements=dict(replacements),
        suffixes=tuple(suffixes),
        min_length=min_length,
        max_length=max_length,
    )


def _read_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise EnterpriseDictionaryError(f"{label}不可读：{path}") from error
    except ValueError as error:
        raise EnterpriseDictionaryError(f"{label}不是合法 JSON：{path}") from error
    if not isinstance(payload, dict):
        raise EnterpriseDictionaryError(f"{label}顶层必须是对象：{path}")
    return payload
