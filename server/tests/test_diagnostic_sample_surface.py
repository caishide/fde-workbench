"""工具内示例报告展示面（获客诊断 T-13′）的**机械闸**。

背景：评测集污染隔离（任务书 R-6／P-8）把「网站案例页与工具内示例报告
可消费展示素材」定为**受约束的例外**——展示面是例外，但四道约束必须
**机械可判**，不能靠人自觉：

- **S1 角标在场**：示例报告固定带角标「示例案例 · 据公开案例整理」／
  「脱敏真实交付 · 代号化」（文案与任务书 R-6 逐字一致）；
- **S2 不冒充实测**：示例页声明「非实时诊断结果」，报告底部写「示例整理
  日期」而不是「生成于」；
- **S3 无分数无评级无金额**（R-1／R-4）：示例报告正文不含评分形态
  （``x/100``）与评分词；出现的百分比**只有政策引文原文口径**；
- **S4 检索面隔离**：示例产物在桌面端，生成器检索面
  （``server/src/fde_api/diagnostics`` ＋ ``server/seeds``）**零引用**
  ——展示内容永不进生成器提示词／few-shot／知识库／检索索引。

本钉把「受约束」从流程纪律变成可执行断言：任一条被违反即红。
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SERVER_DIR = TESTS_DIR.parent
REPO_ROOT = SERVER_DIR.parent

DIAGNOSTICS_DIR = REPO_ROOT / "desktop" / "src" / "renderer" / "src" / "diagnostics"
SAMPLE_MODULE = DIAGNOSTICS_DIR / "sampleReport.ts"
SAMPLE_PAGE = DIAGNOSTICS_DIR / "PublicDiagnosticSamplePage.tsx"
SAMPLE_ROUTE_PAGE = DIAGNOSTICS_DIR / "PublicDiagnosticPage.tsx"

# 生成器检索面（展示内容永不进这里）
GENERATOR_SURFACE = (
    SERVER_DIR / "src" / "fde_api" / "diagnostics",
    SERVER_DIR / "seeds",
)

# 任务书 R-6 固定的角标文案
BADGE_PUBLIC_CASE = "示例案例 · 据公开案例整理"
BADGE_INTERNAL_DELIVERY = "脱敏真实交付 · 代号化"

# 评分形态与评分词（R-1：无分数无评级；R-4：未溯源数字 fail-closed）
SCORE_PATTERN = re.compile(r"\d+\s*/\s*100")
SCORE_WORDS = ("评分", "得分", "评级")
# 金额形态（补贴金额一律不落——政策原文未披露额度，任何金额都是编造）
AMOUNT_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:万元|亿元|元)")
# 政策引文里允许出现的口径比例（343 号：不低于 30%／领航级 60%／2025 版 20%）
ALLOWED_PERCENTS = {"20%", "30%", "60%"}

# 展示产物在生成器检索面里不得出现的引用标记
FORBIDDEN_SURFACE_TOKENS = (
    "sampleReport",
    "PublicDiagnosticSamplePage",
    "diag-sample",
    "desktop/src",
    "desktop\\src",
)

_SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".json", ".txt", ".yml", ".yaml"}
_SKIP_DIR_NAMES = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """去掉块注释与行注释，只留**内容**。

    「不写『生成于』」这类规则说明写在注释里，检查时必须只看内容——
    否则纪律说明本身会被当成违规。``://`` 不当作行注释（政策引文 URL）。
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines = []
    for line in text.splitlines():
        cut = len(line)
        index = 0
        while True:
            found = line.find("//", index)
            if found < 0:
                break
            if found > 0 and line[found - 1] == ":":
                index = found + 2
                continue
            cut = found
            break
        lines.append(line[:cut])
    return "\n".join(lines)


def _iter_surface_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return out


def test_s1_sample_badges_are_pinned_verbatim() -> None:
    """S1：两枚角标常量的文案与任务书 R-6 逐字一致，且真的被示例数据与页面用上。"""
    module = _read(SAMPLE_MODULE)
    assert 'export const SAMPLE_BADGE_PUBLIC_CASE = "%s"' % BADGE_PUBLIC_CASE in module, (
        "示例模块缺角标常量「%s」" % BADGE_PUBLIC_CASE
    )
    assert 'export const SAMPLE_BADGE_INTERNAL_DELIVERY = "%s"' % BADGE_INTERNAL_DELIVERY in module, (
        "示例模块缺角标常量「%s」" % BADGE_INTERNAL_DELIVERY
    )
    assert "badge: SAMPLE_BADGE_PUBLIC_CASE" in module, "没有示例案例带「示例案例」角标"
    assert "badge: SAMPLE_BADGE_INTERNAL_DELIVERY" in module, "没有示例案例带「脱敏真实交付」角标"
    page = _read(SAMPLE_PAGE)
    assert "diag-sample-badge" in page, "示例页未渲染角标位"
    assert "activeCase.badge" in page, "示例页未把当前案例的角标渲染出来"


def test_s2_sample_is_not_presented_as_a_live_diagnosis() -> None:
    """S2：示例页声明「非实时诊断结果」；示例正文不写「生成于」。"""
    page = _strip_comments(_read(SAMPLE_PAGE))
    assert "非实时诊断结果" in page, "示例页缺「非实时诊断结果」声明"
    module = _strip_comments(_read(SAMPLE_MODULE))
    assert "生成于" not in module, "示例报告正文不得写成「生成于」"
    assert "生成于" not in page, "示例页不得写成「生成于」"


def test_s3_sample_report_carries_no_score_no_rating_no_amount() -> None:
    """S3：示例报告正文无分数形态、无评分词、无金额；百分比只有政策引文口径。"""
    body = _strip_comments(_read(SAMPLE_MODULE))
    assert SCORE_PATTERN.search(body) is None, "示例报告出现评分形态（x/100）"
    for word in SCORE_WORDS:
        assert word not in body, "示例报告出现评分词「%s」" % word
    assert AMOUNT_PATTERN.search(body) is None, "示例报告出现金额形态"
    percents = {hit.replace(" ", "") for hit in re.findall(r"\d{1,3}\s*%", body)}
    assert percents <= ALLOWED_PERCENTS, (
        "示例报告出现非政策引文口径的百分比：%s" % sorted(percents - ALLOWED_PERCENTS)
    )


def test_s4_generator_surface_never_references_sample_artifacts() -> None:
    """S4：生成器检索面（diagnostics 包 ＋ seeds）零引用展示产物。"""
    violations: list[str] = []
    for root in GENERATOR_SURFACE:
        if not root.is_dir():
            continue
        for path in _iter_surface_files(root):
            text = _read(path)
            for token in FORBIDDEN_SURFACE_TOKENS:
                if token in text:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    violations.append("%s: %s" % (rel, token))
    assert violations == [], f"生成器检索面引用了展示产物：{violations}"


def test_s5_sample_route_is_public_and_read_only() -> None:
    """S5：示例路由是公开面（未登录可达），且首屏入口指向它。

    路由必须**双向**接线：解析（``parseHashRoute``）与序列化（``routeHash``）
    两处都在，否则从首屏点进去或刷新页面都会掉路由——只查「出现过一次」
    是无判别力的写法。
    """
    route_file = REPO_ROOT / "desktop" / "src" / "renderer" / "src" / "routing" / "useHashRoute.ts"
    routes = _read(route_file)
    assert '"public-diagnostics-sample"' in routes, "示例路由 kind 未进路由表"
    assert 'case "public-diagnostics-sample"' in routes, "示例路由未进 routeHash 序列化分支"
    assert routes.count("#diagnostics/sample") >= 2, (
        "示例路由只在解析或序列化一侧接线（出现 %d 次）" % routes.count("#diagnostics/sample")
    )
    app = _read(REPO_ROOT / "desktop" / "src" / "renderer" / "src" / "App.tsx")
    assert "PublicDiagnosticSamplePage" in app, "示例页未接线到应用路由"
    intro = _read(SAMPLE_ROUTE_PAGE)
    assert '#diagnostics/sample' in intro, "访客首屏缺「查看示例报告」入口"
