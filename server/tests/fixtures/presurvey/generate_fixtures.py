"""程序化生成预调研 DOCX 对抗样本（G4：解析器加固的畸形输入面）。

每个样本对应一类真实世界会出现的畸形 DOCX；测试用它们钉住两层解析的
行为契约：guidance.docx_extract.extract_docx（预调研块抽取）与
documents.qa.extract_docx_xml_text（本地全文提取，KimiFileClient
local_extract 路径）。契约要点：

- 畸形样本绝不令进程崩溃，一律落进可分类的失败（PresurveyParseError /
  KimiError("kimi_file_extract_failed")）或正常产出块；
- 空内容（空文档/空表格）必须失败为「没有可分析的文字内容」而不是静默成功；
- 合并单元格在全文提取里去重（python-docx 会按格位重复同一单元格）；
- 批注（word/comments.xml）不进入提取文本；
- 引用不存在样式的段落照样可提取（样式解析失败不阻塞文本）；
- 嵌套表格的文本在全文提取里可见（递归遍历）；
- 超长段落不截断、不崩溃。

用法：
    python tests/fixtures/presurvey/generate_fixtures.py [输出目录]

不传目录时输出到脚本同目录的 adversarial/ 下（供人工检视）；
测试通过 pytest session fixture 调 build_all() 在临时目录构建同款样本，
二进制不入 git。
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject

# (文件名, 说明) —— 顺序即测试参数化顺序，保持稳定。
FIXTURE_SPECS: tuple[tuple[str, str], ...] = (
    ("empty-document.docx", "空文档：无任何文字内容"),
    ("empty-table.docx", "空表格：只有空单元格"),
    ("merged-cells.docx", "合并单元格：表头整行合并"),
    ("comments.docx", "批注：正文带 word/comments.xml 批注"),
    ("invalid-style.docx", "异常样式：段落引用不存在的样式 id"),
    ("missing-sections.docx", "缺失章节：只有标题与一行客户名"),
    ("huge-paragraph.docx", "超长段落：单个段落约 10 万字"),
    ("nested-tables.docx", "嵌套表格：单元格内再套表"),
    ("corrupt-zip.docx", "非 ZIP 字节流：根本不是 OOXML"),
)

MERGED_HEADER_TEXT = "合并表头：客户预调研信息汇总"
NESTED_CELL_A = "嵌套表单元格甲"
NESTED_CELL_B = "嵌套表单元格乙"
OUTER_CELL_TEXT = "外层表格单元格"
INVALID_STYLE_TEXT = "引用不存在样式的段落"
HUGE_PARAGRAPH_UNIT = "超长段落压力测试单位文本。"
HUGE_PARAGRAPH_REPEATS = 10_000


def build_all(out_dir: Path) -> dict[str, Path]:
    """按 FIXTURE_SPECS 生成全部对抗样本，返回 文件名 → 路径。"""
    builders: dict[str, Callable[[], bytes]] = {
        "empty-document.docx": _build_empty_document,
        "empty-table.docx": _build_empty_table,
        "merged-cells.docx": _build_merged_cells,
        "comments.docx": _build_comments,
        "invalid-style.docx": _build_invalid_style,
        "missing-sections.docx": _build_missing_sections,
        "huge-paragraph.docx": _build_huge_paragraph,
        "nested-tables.docx": _build_nested_tables,
        "corrupt-zip.docx": _build_corrupt_zip,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, _note in FIXTURE_SPECS:
        target = out_dir / name
        target.write_bytes(builders[name]())
        paths[name] = target
    return paths


def _docx_bytes(document: DocumentObject) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_empty_document() -> bytes:
    return _docx_bytes(Document())


def _build_empty_table() -> bytes:
    document = Document()
    document.add_table(rows=2, cols=2)
    return _docx_bytes(document)


def _build_merged_cells() -> bytes:
    document = Document()
    table = document.add_table(rows=3, cols=3)
    header = table.rows[0].cells[0].merge(table.rows[0].cells[2])
    header.text = MERGED_HEADER_TEXT
    for row_index, label in enumerate(("客户背景", "当前痛点"), 1):
        table.rows[row_index].cells[0].text = label
        table.rows[row_index].cells[1].text = f"{label}补充说明"
        table.rows[row_index].cells[2].text = f"{label}证据"
    return _docx_bytes(document)


def _build_comments() -> bytes:
    document = Document()
    paragraph = document.add_paragraph("带批注的正文段落，批注内容不应进入提取文本。")
    document.add_comment(
        paragraph.runs,
        text="内部批注：此段数据待客户确认",
        author="tester",
        initials="ts",
    )
    return _docx_bytes(document)


def _build_invalid_style() -> bytes:
    document = Document()
    document.add_paragraph("正常段落先行。")
    base = _docx_bytes(document)
    injected = (
        "<w:p><w:pPr><w:pStyle w:val=\"NoSuchStyleBogusId\"/></w:pPr>"
        f"<w:r><w:t>{INVALID_STYLE_TEXT}</w:t></w:r></w:p>"
    )
    return _inject_before_sectpr(base, injected)


def _build_missing_sections() -> bytes:
    document = Document()
    document.add_heading("预调研表", level=1)
    document.add_paragraph("客户代号：somwyn")
    return _docx_bytes(document)


def _build_huge_paragraph() -> bytes:
    document = Document()
    document.add_paragraph(HUGE_PARAGRAPH_UNIT * HUGE_PARAGRAPH_REPEATS)
    return _docx_bytes(document)


def _build_nested_tables() -> bytes:
    document = Document()
    outer = document.add_table(rows=2, cols=2)
    nested = outer.cell(0, 0).add_table(rows=1, cols=2)
    nested.cell(0, 0).text = NESTED_CELL_A
    nested.cell(0, 1).text = NESTED_CELL_B
    # 单元格内表格之后必须补一个段落，否则部分阅读器认为结构不完整。
    outer.cell(0, 0).add_paragraph("")
    outer.cell(1, 0).text = OUTER_CELL_TEXT
    outer.cell(1, 1).text = "外层表格另一格"
    return _docx_bytes(document)


def _build_corrupt_zip() -> bytes:
    return "这不是一个 DOCX 文件：字节流根本不是 ZIP 归档。".encode("utf-8")


def _inject_before_sectpr(docx_bytes: bytes, paragraph_xml: str) -> bytes:
    """对 word/document.xml 做最小注入：把 paragraph_xml 插到 sectPr 之前。"""
    source = io.BytesIO(docx_bytes)
    output = io.BytesIO()
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as rebuilt:
        for item in archive.infolist():
            data = archive.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                marker = text.rfind("<w:sectPr")
                if marker < 0:
                    raise ValueError("document.xml has no sectPr to inject before")
                text = text[:marker] + paragraph_xml + text[marker:]
                data = text.encode("utf-8")
            rebuilt.writestr(item, data)
    return output.getvalue()


if __name__ == "__main__":
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "adversarial"
    built = build_all(out)
    for name, path in built.items():
        print(f"{name}  {path.stat().st_size:>9,} bytes")
