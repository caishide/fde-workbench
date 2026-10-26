"""WP03 交付链身份与 QA 回归钉（D1/D2/D6/D7）。

A2 代号化后企业标识全链路只承载 ``enterprise_code``：模板源头、生成表格、
中文别名、QA 空值检测四处必须一致；``research_result`` 导出与其它文档类型
一样要过 ``inspect_generated_docx`` 门。
"""
import io
import zipfile

import pytest

from fde_api.documents.catalog import RESOURCE_TEMPLATES_DIR, load_template_manifest
from fde_api.documents.generator import render_docx
from fde_api.documents.qa import inspect_generated_docx
from fde_api.research.export_service import (
    ResearchExportError,
    _build_docx,
    _research_result_qa,
)

ENTERPRISE_CODE = "星河制造·制造·苏州"

_PLAN_CONTEXT = {
    "project": {
        "name": "星河 PoV",
        "project_code": "FDE-POV-0001",
        "industry_name": "制造业",
        "leader_name": "王工",
        "status": "active",
        "planned_start_date": "2026-08-22",
        "planned_end_date": "2026-09-15",
        "background": "提升交付效率",
        "notes": "每周复盘",
    },
    "enterprise": {"enterprise_code": ENTERPRISE_CODE},
    # 生产路径里 generated_date 由 _build_context 冻结填充；测试给等价静态值
    "generated_date": "2026年08月22日",
    "guidance": [],
    "tasks": [],
}

_NO_TEMPLATE_SESSION = type("S", (), {"scalar": lambda self, _query: None})()


def _render_plan_progress(enterprise: dict) -> bytes:
    template = RESOURCE_TEMPLATES_DIR / "project_plan_progress.docx"
    context = dict(_PLAN_CONTEXT, enterprise=enterprise)
    return render_docx(io.BytesIO(template.read_bytes()), context, {}).getvalue()


def _template_documents():
    return sorted(RESOURCE_TEMPLATES_DIR.glob("*.docx"))


def test_built_templates_carry_enterprise_codename_placeholder_only():
    """D1：17 个模板里不得再出现 enterprise.name——它是永不存在的占位符。"""
    assert len(_template_documents()) >= 17
    for path in _template_documents():
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
        assert "enterprise.name" not in xml, f"{path.name} still references enterprise.name"


def test_plan_progress_renders_codename_and_drops_dead_contact_rows():
    """D1+D2 实质验收：代号成文、企业名称栏非空、三个死行彻底消失。"""
    data = _render_plan_progress({"enterprise_code": ENTERPRISE_CODE})
    manifest = load_template_manifest()["project_plan_progress"]
    qa = inspect_generated_docx(
        io.BytesIO(data),
        manifest["required_sections"],
        required_values=(("enterprise_code", ENTERPRISE_CODE),),
    )
    assert qa.errors == [], [error.code for error in qa.errors]
    assert ENTERPRISE_CODE in qa.text
    assert "企业名称" in qa.text
    # 代号化下没有这些概念：不是填空，是整行不存在
    assert "联系人" not in qa.text
    assert "联系方式" not in qa.text
    assert "企业地址" not in qa.text


def test_qa_rejects_plan_progress_with_empty_enterprise_identity():
    """D6：企业代号渲染为空必须被 QA 拦下，而不是静默出一份空标识文档。"""
    data = _render_plan_progress({})
    manifest = load_template_manifest()["project_plan_progress"]
    qa = inspect_generated_docx(
        io.BytesIO(data),
        manifest["required_sections"],
        required_values=(("enterprise_code", ""),),
    )
    codes = [error.code for error in qa.errors]
    assert "required_value_empty" in codes


def test_research_result_docx_contains_summary_sections_and_passes_qa():
    """D7：无模板兜底路径也要产出四段完整调研结果，且过 QA 门。"""
    project = type("P", (), {"name": "星河 PoV", "enterprise_code": ENTERPRISE_CODE})()
    subject = type("S", (), {"name": "计划员"})()
    forms = [
        {
            "subject_name": "计划员",
            "form_name": "岗位调研",
            "answers": [{"question": "现状与痛点", "value": "排产信息分散"}],
        }
    ]
    summary = {
        "executive_summary": "调研覆盖排产全流程。",
        "key_findings": ["排产依赖手工报表"],
        "recommendations": ["引入自动排产"],
    }
    data = _build_docx(project, subject, forms, summary, session=_NO_TEMPLATE_SESSION)
    _research_result_qa(data, project)

    from docx import Document as load_docx

    text = "\n".join(p.text for p in load_docx(io.BytesIO(data)).paragraphs)
    for section in ("调研摘要", "关键发现", "建议", "调研记录"):
        assert section in text, section
    assert ENTERPRISE_CODE in text


def test_research_result_qa_rejects_missing_enterprise_code():
    project = type("P", (), {"name": "星河 PoV", "enterprise_code": ""})()
    subject = type("S", (), {"name": "计划员"})()
    forms = [
        {
            "subject_name": "计划员",
            "form_name": "岗位调研",
            "answers": [{"question": "现状与痛点", "value": "排产信息分散"}],
        }
    ]
    summary = {
        "executive_summary": "调研覆盖排产全流程。",
        "key_findings": ["排产依赖手工报表"],
        "recommendations": ["引入自动排产"],
    }
    data = _build_docx(project, subject, forms, summary, session=_NO_TEMPLATE_SESSION)
    with pytest.raises(ResearchExportError) as excinfo:
        _research_result_qa(data, project)
    assert excinfo.value.code == "research_result_qa_failed"
    assert "required_value_empty" in str(excinfo.value.message)
