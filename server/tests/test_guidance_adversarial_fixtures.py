# G4：对抗 DOCX 样本驱动两层解析的行为契约。
#
# 样本由 tests/fixtures/presurvey/generate_fixtures.py 程序化生成（session 级
# 构建到临时目录，二进制不入 git）。每个用例钉住「畸形输入绝不崩溃、失败
# 必须可分类」的底线：
#   - extract_docx（guidance 链）→ PresurveyParseError 或正常块；
#   - extract_docx_xml_text（本地全文）→ 文本或原始异常（分类由 Kimi 层负责）；
#   - KimiFileClient._extract_docx_locally（local_extract 路径）→ KimiError，
#     携带 kimi_file_extract_failed 且 retryable=True。
import importlib.util
import io
from pathlib import Path

import pytest

from fde_api.ai.kimi import KimiError, KimiFileClient
from fde_api.documents.qa import extract_docx_xml_text
from fde_api.guidance.docx_extract import PresurveyParseError, extract_docx

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "presurvey"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "presurvey_generate_fixtures", _FIXTURES_DIR / "generate_fixtures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def adversarial(tmp_path_factory):
    generator = _load_generator()
    paths = generator.build_all(tmp_path_factory.mktemp("adversarial-docx"))
    return generator, paths


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


def test_fixture_catalog_matches_specs(adversarial):
    generator, paths = adversarial
    assert tuple(paths) == tuple(name for name, _ in generator.FIXTURE_SPECS)
    assert len(paths) >= 8


@pytest.mark.parametrize("name", ["empty-document.docx", "empty-table.docx"])
def test_empty_content_fails_as_unanalyzable_in_all_layers(adversarial, name):
    _, paths = adversarial
    data = _bytes(paths[name])

    with pytest.raises(PresurveyParseError, match="没有可分析的文字内容"):
        extract_docx(io.BytesIO(data))

    # 全文提取层返回空串（不负责分类），分类发生在 Kimi 本地提取层。
    assert extract_docx_xml_text(io.BytesIO(data)) == ""

    with pytest.raises(KimiError) as kimi:
        KimiFileClient._extract_docx_locally(io.BytesIO(data), name)
    assert kimi.value.code == "kimi_file_extract_failed"
    assert kimi.value.retryable is True


def test_corrupt_zip_is_classified_not_crashing(adversarial):
    _, paths = adversarial
    data = _bytes(paths["corrupt-zip.docx"])

    with pytest.raises(PresurveyParseError, match="无法读取"):
        extract_docx(io.BytesIO(data))

    with pytest.raises(KimiError) as kimi:
        KimiFileClient._extract_docx_locally(io.BytesIO(data), "corrupt-zip.docx")
    assert kimi.value.code == "kimi_file_extract_failed"
    assert kimi.value.retryable is True


def test_merged_cells_dedupe_in_full_text_and_stable_refs_in_blocks(adversarial):
    generator, paths = adversarial
    data = _bytes(paths["merged-cells.docx"])

    result = extract_docx(io.BytesIO(data))
    header_blocks = [b for b in result.blocks if b.text == generator.MERGED_HEADER_TEXT]
    # python-docx 按格位重复同一合并单元格；块抽取按格位生成稳定引用
    #（table-1-row-1-cell-1..3），重复 3 次是钉住的现状而非缺陷。
    assert len(header_blocks) == 3
    assert {b.source_ref for b in header_blocks} == {
        "table-1-row-1-cell-1", "table-1-row-1-cell-2", "table-1-row-1-cell-3",
    }

    text = extract_docx_xml_text(io.BytesIO(data))
    # 全文提取按 _tc 身份去重，合并表头只出现一次。
    assert text.count(generator.MERGED_HEADER_TEXT) == 1


def test_comments_never_leak_into_extraction(adversarial):
    generator, paths = adversarial
    data = _bytes(paths["comments.docx"])

    blocks = extract_docx(io.BytesIO(data)).blocks
    assert len(blocks) == 1
    assert "带批注的正文段落" in blocks[0].text

    text = extract_docx_xml_text(io.BytesIO(data))
    assert "带批注的正文段落" in text
    assert "内部批注" not in text


def test_invalid_style_reference_does_not_block_extraction(adversarial):
    generator, paths = adversarial
    data = _bytes(paths["invalid-style.docx"])

    assert generator.INVALID_STYLE_TEXT in extract_docx_xml_text(io.BytesIO(data))
    blocks = extract_docx(io.BytesIO(data)).blocks
    assert any(generator.INVALID_STYLE_TEXT in b.text for b in blocks)


def test_missing_sections_still_extract_for_model_side_judgment(adversarial):
    # 章节缺失是语义问题：解析层只负责把文字交给模型，open_questions 是
    # 模型的职责——这里钉住「解析不替模型做章节校验」的边界。
    generator, paths = adversarial
    data = _bytes(paths["missing-sections.docx"])

    blocks = extract_docx(io.BytesIO(data)).blocks
    assert len(blocks) == 2
    assert blocks[0].source_ref == "paragraph-1"


def test_huge_paragraph_is_extracted_whole(adversarial):
    generator, paths = adversarial
    data = _bytes(paths["huge-paragraph.docx"])

    blocks = extract_docx(io.BytesIO(data)).blocks
    assert len(blocks) == 1
    assert blocks[0].text == generator.HUGE_PARAGRAPH_UNIT * generator.HUGE_PARAGRAPH_REPEATS

    full = extract_docx_xml_text(io.BytesIO(data))
    assert len(full) == len(generator.HUGE_PARAGRAPH_UNIT) * generator.HUGE_PARAGRAPH_REPEATS


def test_nested_tables_recurse_in_full_text_top_level_in_blocks(adversarial):
    generator, paths = adversarial
    data = _bytes(paths["nested-tables.docx"])

    text = extract_docx_xml_text(io.BytesIO(data))
    assert generator.NESTED_CELL_A in text
    assert generator.NESTED_CELL_B in text
    assert generator.OUTER_CELL_TEXT in text

    # 块抽取只走顶层表格格位文本，嵌套表文本不在其产物里——钉住两层差异，
    # 改动任何一层都必须显式更新这里的预期。
    blocks = extract_docx(io.BytesIO(data)).blocks
    assert any(generator.OUTER_CELL_TEXT in b.text for b in blocks)
    assert not any(generator.NESTED_CELL_A in b.text for b in blocks)


def test_every_fixture_survives_block_extraction_without_unexpected_error(adversarial):
    """兜底矩阵：9 个样本过一遍块抽取，只允许 PresurveyParseError 或成功。"""
    _, paths = adversarial
    outcomes = {}
    for name, path in paths.items():
        try:
            blocks = extract_docx(io.BytesIO(path.read_bytes()))
            outcomes[name] = ("ok", len(blocks.blocks))
        except PresurveyParseError:
            outcomes[name] = ("classified", 0)
    classified = {n for n, (kind, _) in outcomes.items() if kind == "classified"}
    assert classified == {"empty-document.docx", "empty-table.docx", "corrupt-zip.docx"}
