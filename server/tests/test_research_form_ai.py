from fde_api.ai.research_form_service import _normalize_generated_form, _valid_generated_form


def generated_form():
    return {
        "form_key": "production_lead_interview",
        "name": "生产部门负责人访谈",
        "description": "了解生产计划、质量异常和数据现状。",
        "subject_type": "department",
        "module_key": "pre_diagnosis",
        "sections": [
            {
                "section_key": "business_context",
                "name": "业务现状",
                "description": "",
                "fields": [
                    {
                        "field_key": "current_process",
                        "name": "当前流程",
                        "help_text": "请描述当前的业务流程。",
                        "type": "long_text",
                        "is_required": True,
                        "options": {},
                    }
                ],
            }
        ],
    }


def test_generated_research_form_must_be_editable_and_non_duplicate():
    value = generated_form()

    assert _valid_generated_form(value, ["pre_diagnosis"], set()) is True
    assert _valid_generated_form(value, ["pre_diagnosis"], {value["form_key"]}) is False


def test_generated_research_form_rejects_unknown_module_and_extra_fields():
    value = generated_form()
    value["module_key"] = "unknown"
    assert _valid_generated_form(value, ["pre_diagnosis"], set()) is False

    value = generated_form()
    value["unexpected"] = "not allowed"
    assert _valid_generated_form(value, ["pre_diagnosis"], set()) is False


def test_generated_research_form_normalizes_common_model_format_drift():
    value = generated_form()
    value["form_key"] = "Production Lead Interview"
    value["subject_type"] = "project"
    value["unexpected"] = "ignored"
    value["sections"][0].pop("description")
    field = value["sections"][0]["fields"][0]
    field.pop("help_text")
    field["is_required"] = "true"
    field["unexpected"] = "ignored"

    normalized = _normalize_generated_form(
        {"research_form": value},
        required_subject_type="department",
    )

    assert normalized is not None
    assert normalized["form_key"] == "production_lead_interview"
    assert normalized["subject_type"] == "department"
    assert normalized["sections"][0]["description"] == ""
    assert normalized["sections"][0]["fields"][0]["help_text"] == ""
    assert normalized["sections"][0]["fields"][0]["is_required"] is True
    assert _valid_generated_form(normalized, ["pre_diagnosis"], set(), required_subject_type="department") is True


def _drifting_form():
    """复刻 r31 线上失败样本：table 列用 column_key、choice 用 value/label 对象。"""
    value = generated_form()
    value["sections"][0]["fields"].append({
        "field_key": "process_map",
        "name": "流程环节",
        "help_text": "列出关键流程。",
        "type": "table",
        "is_required": True,
        "options": {
            "columns": [
                {"column_key": "process_stage", "name": "流程环节", "required": True},
                {"column_key": "owner", "name": "责任人", "required": False},
            ]
        },
    })
    value["sections"][0]["fields"].append({
        "field_key": "priority_types",
        "name": "优先问题类型",
        "help_text": "选择优先问题。",
        "type": "multi_choice",
        "is_required": True,
        "options": {
            "choices": [
                {"value": "quality", "label": "质量缺陷"},
                {"value": "downtime", "label": "设备停机"},
            ]
        },
    })
    return value


def test_generated_research_form_normalizes_table_column_keys():
    """r31：AI 用 column_key，定义 schema 要 key——不归一即 invalid_table_columns。"""
    normalized = _normalize_generated_form(_drifting_form())

    assert normalized is not None
    table_field = next(
        field
        for field in normalized["sections"][0]["fields"]
        if field["type"] == "table"
    )
    columns = table_field["options"]["columns"]
    assert [column["key"] for column in columns] == ["process_stage", "owner"]
    assert [column["name"] for column in columns] == ["流程环节", "责任人"]
    assert all("column_key" not in column for column in columns)
    assert _valid_generated_form(normalized, ["pre_diagnosis"], set()) is True


def test_generated_research_form_normalizes_choice_objects_to_strings():
    """r31：AI 用 {value,label}，定义 schema 要纯字符串 choices。"""
    normalized = _normalize_generated_form(_drifting_form())

    assert normalized is not None
    choice_field = next(
        field
        for field in normalized["sections"][0]["fields"]
        if field["type"] == "multi_choice"
    )
    assert choice_field["options"]["choices"] == ["quality", "downtime"]
    assert _valid_generated_form(normalized, ["pre_diagnosis"], set()) is True


def test_generated_research_form_deduplicates_choice_values():
    """重复 choices 会被定义 schema 判非法——归一时顺手去重。"""
    value = _drifting_form()
    value["sections"][0]["fields"][-1]["options"]["choices"] = [
        {"value": "quality", "label": "质量缺陷"},
        {"value": "quality", "label": "质量缺陷（重复）"},
    ]

    normalized = _normalize_generated_form(value)

    assert normalized is not None
    choice_field = next(
        field
        for field in normalized["sections"][0]["fields"]
        if field["type"] == "multi_choice"
    )
    assert choice_field["options"]["choices"] == ["quality"]
    assert _valid_generated_form(normalized, ["pre_diagnosis"], set()) is True


def test_generated_research_form_drops_choice_default_not_in_choices():
    """default_value 不在 choices 里会被判非法——归一时移除。"""
    value = _drifting_form()
    value["sections"][0]["fields"][-1]["options"]["default_value"] = ["unknown_type"]

    normalized = _normalize_generated_form(value)

    assert normalized is not None
    choice_field = next(
        field
        for field in normalized["sections"][0]["fields"]
        if field["type"] == "multi_choice"
    )
    assert "default_value" not in choice_field["options"]
    assert _valid_generated_form(normalized, ["pre_diagnosis"], set()) is True
