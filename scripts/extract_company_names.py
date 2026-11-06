"""T-A2：企业名黑名单提取 Python 单点（check-pseudonymization.sh 调用）。

「CI 扫库正则 == 入库替换词典」的落法：模式定义不再内联在 bash/perl 里，而是
统一来自 ``fde_api.guidance.enterprise_vocab``（读同一份
``server/seeds/enterprise_redaction.json``）——本脚本只负责「读文本 → 套同一
模式 → 去重排序输出」。替换器词典与 CI 词典的逐条一致性由
``server/tests/test_enterprise_redaction.py`` 钉死。

stdout：每行一个企业名（已去重已排序）；
机械性故障（词典不可用/文本不可读）：stderr 说明 + exit 2——绝不静默输出空。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "src"))

from fde_api.guidance.enterprise_vocab import (  # noqa: E402
    EnterpriseDictionaryError,
    load_dictionary,
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: extract_company_names.py <text-file>", file=sys.stderr)
        return 2
    try:
        dictionary = load_dictionary()
        raw = Path(argv[1]).read_text(encoding="utf-8-sig")
    except (EnterpriseDictionaryError, OSError) as error:
        print(f"FAIL 企业名提取失败：{error}", file=sys.stderr)
        return 2
    for name in sorted({match for match, _start, _end in dictionary.detect(raw)}):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
