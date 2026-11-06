# T-A2 代号化自动替换层（企业名）语义钉子。
#
# 拍板 6①（分层失败语义）：替换器机械性故障（词典缺文件/坏 JSON/正则编译
# 失败）→ fail-closed 硬阻断入库；疑似企业名但词典未收录（「技术公司」类
# 通用词）→ 放行但进待复核清单，confirm 前必须复核（ack 显式留痕）。
# 拍板 6②（词典形态）：仓库内种子文件，CI 扫库与入库替换读同一份——
# 本文件用 subprocess 钉死「提取器输出 == 种子 replacements 键」。
#
# 词典内容纪律（红线级）：种子文件只存检测词表+合成条目；真实企业名映射
# 只经 FDE_ENTERPRISE_DICT / 约定本地覆盖文件注入，永不进 git。本文件测试
# 数据只用合成 fixture（.github/ci-assets/synthetic-leads-blacklist.txt 同族），
# 真实客户资料不可作测试素材。
from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from fde_api.auth.models import User
from fde_api.extensions import object_storage
from fde_api.guidance import jobs as guidance_jobs
from fde_api.guidance.ai_schema import LIST_FIELDS
from fde_api.guidance.enterprise_vocab import (
    OVERRIDE_ENV,
    EnterpriseDictionaryError,
    load_dictionary,
)
from fde_api.guidance.jobs import handle_presurvey_analysis
from fde_api.guidance.models import ProjectGuidanceAnalysis
from fde_api.guidance.redaction import (
    SensitiveCredentialDetected,
    collect_redaction_review,
    redact_guidance_draft,
)
from fde_api.guidance.service import (
    GuidanceServiceError,
    confirm_analysis,
    get_analysis,
)
from fde_api.jobs.models import BackgroundJob
from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion, OperationEvent, Project

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_BLACKLIST = REPO_ROOT / ".github" / "ci-assets" / "synthetic-leads-blacklist.txt"
EXTRACTOR = REPO_ROOT / "scripts" / "extract_company_names.py"

# 合成条目（与种子文件一致——种子内容变更时本文件同步，双向漂移即红）
SYNTHETIC_NAME = "合成测试集团"


@pytest.fixture(autouse=True)
def _seed_only_dictionary(monkeypatch, tmp_path):
    """把词典环境钉成 seed-only：本地覆盖文件/env 不参与（显式传参的用例除外）。"""
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    monkeypatch.setattr(
        "fde_api.guidance.enterprise_vocab.LOCAL_OVERRIDE_PATH",
        tmp_path / "does-not-exist.local.json",
    )


def _write_seed(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _minimal_seed(**overrides) -> dict:
    payload: dict = {
        "version": 1,
        "detection": {"min_length": 2, "max_length": 15, "suffixes": ["公司", "集团", "厂"]},
        "replacements": {
            "甲公司集团": "示例客户·行业·城市",
            "甲公司": "示例·行业·城市",
            "乙厂": "示例客户二·行业·城市",
        },
    }
    payload.update(overrides)
    return payload


# ---------- A. 词典单点 ----------


def test_seed_dictionary_loads_and_covers_ci_fixture():
    dictionary = load_dictionary()
    fixture_names = {
        line.strip()
        for line in FIXTURE_BLACKLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert fixture_names, "合成黑名单 fixture 不能为空"
    assert fixture_names == set(dictionary.replacements), "种子 replacements 键必须与 CI fixture 逐条一致"
    for name in fixture_names:
        assert dictionary.detect(name), f"检测模式必须抓得到 fixture 名：{name}"


def test_extractor_script_matches_seed_keys():
    seed_keys = sorted(load_dictionary().replacements)
    result = subprocess.run(
        [sys.executable, str(EXTRACTOR), str(FIXTURE_BLACKLIST)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == seed_keys, "提取器（CI 侧）输出必须与种子词典键逐条一致"


def test_replace_longest_name_wins(tmp_path):
    seed = _write_seed(tmp_path, _minimal_seed())
    dictionary = load_dictionary(seed_path=seed)
    text, hits = dictionary.replace("甲公司集团与甲公司并列")
    assert text == "示例客户·行业·城市与示例·行业·城市并列"
    assert hits == ["甲公司集团", "甲公司"]  # 长名优先，命中顺序稳定


def test_local_override_merges_and_wins(tmp_path):
    seed = _write_seed(tmp_path, _minimal_seed())
    override = tmp_path / "override.json"
    override.write_text(
        json.dumps({"replacements": {"甲公司集团": "覆盖代号·行业·城市", "丙公司": "新增代号·行业·城市"}},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    dictionary = load_dictionary(seed_path=seed, override_path=override)
    assert dictionary.replacements["甲公司集团"] == "覆盖代号·行业·城市"  # 键冲突覆盖方赢
    assert dictionary.replacements["乙厂"] == "示例客户二·行业·城市"  # 种子条目保留
    assert "丙公司" in dictionary.replacements  # 覆盖新增条目并入
    text, _hits = dictionary.replace("甲公司集团与丙公司")
    assert text == "覆盖代号·行业·城市与新增代号·行业·城市"


def test_dictionary_mechanical_failures_fail_closed(tmp_path):
    with pytest.raises(EnterpriseDictionaryError):
        load_dictionary(seed_path=tmp_path / "missing.json")  # 缺文件
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(EnterpriseDictionaryError):
        load_dictionary(seed_path=corrupt)  # 坏 JSON
    bad_shape = _write_seed(tmp_path, _minimal_seed(detection={"min_length": 5, "max_length": 2, "suffixes": ["公司"]}))
    with pytest.raises(EnterpriseDictionaryError):
        load_dictionary(seed_path=bad_shape)  # 长度界非法
    self_matching = _write_seed(tmp_path, _minimal_seed(
        replacements={"甲公司": "某示例公司"}  # 替换值自身命中检测模式 → 替换后被复标
    ))
    with pytest.raises(EnterpriseDictionaryError):
        load_dictionary(seed_path=self_matching)


def test_replace_output_leaves_no_enrolled_residue():
    dictionary = load_dictionary()
    text, hits = dictionary.replace("黑名单示例控股公司、合成测试集团与虚拟演武厂来访")
    assert hits == ["黑名单示例控股公司", "合成测试集团", "虚拟演武厂"]
    assert not dictionary.detect(text), "收录名替换后不得再被检测模式命中（自洽律）"


# ---------- B. 脱敏串联层 ----------


def _draft(**overrides) -> dict:
    ref = overrides.pop("ref", "kimi-file:x")
    item = {"text": SYNTHETIC_NAME + "产线老旧", "classification": "customer_stated",
            "source_refs": [ref], "confirmed": False}
    payload: dict = {
        "customer_vision": SYNTHETIC_NAME + "希望数字化转型，联系 13800138000",
        "current_phase_objective": "三个月内完成试点上线",
        "executive_summary": "某技术公司提出需求",
        "evidence": {ref: SYNTHETIC_NAME + "的现状"},
        **{field: [dict(item)] for field in LIST_FIELDS},
    }
    payload.update(overrides)
    return payload


def test_draft_chain_replaces_enrolled_and_masks_pii():
    draft = _draft()
    out = redact_guidance_draft(draft)
    assert out["customer_vision"].startswith("示例客户乙·软件·上海")
    assert "13800138000" not in out["customer_vision"]
    assert out["evidence"] == {"kimi-file:x": "示例客户乙·软件·上海的现状"}
    assert out["key_business_problems"][0]["text"] == "示例客户乙·软件·上海产线老旧"
    assert draft["customer_vision"] != out["customer_vision"]  # 非变异：入参不改


def test_unenrolled_suspected_not_replaced_but_surfaced():
    out = redact_guidance_draft(_draft())
    assert "某技术公司" in out["executive_summary"]  # 放行：通用词不被替换
    review = collect_redaction_review(out)
    assert {"field": "executive_summary", "match": "某技术公司"} in review


def test_review_covers_evidence_and_list_items():
    review = collect_redaction_review(_draft())
    locations = {hit["field"] for hit in review}
    assert "executive_summary" in locations
    assert "evidence.kimi-file:x" in locations
    assert "key_business_problems[0].text" in locations


def test_redact_text_still_raises_on_credentials():
    with pytest.raises(SensitiveCredentialDetected):
        redact_guidance_draft(_draft(customer_vision="密钥 sk-abcdefghijklmnop1234"))


# ---------- C. analyze 链落库前置（job 级） ----------


def _seed_analysis(db_session, *, data: bytes):
    leader = User(
        username=f"ta2.lead.{uuid4().hex}", display_name="T-A2 负责人",
        role="project_lead", password_hash="x", must_change_password=False, is_active=True,
    )
    template = IndustryTemplate(name="T-A2 模板", industry_name="制造")
    template_version = IndustryTemplateVersion(
        template=template, name=template.name, industry_name=template.industry_name,
        description="", version_number=1, status="published", published_by=leader,
    )
    project_id, file_id, version_id = uuid4().hex, uuid4().hex, uuid4().hex
    project = Project(
        id=project_id, project_code=f"FDE-TA2-{uuid4().hex[:8]}", name="代号化链路项目",
        enterprise_code="星河制造·制造·苏州", leader=leader, source_template_version=template_version,
        template_snapshot={}, planned_start_date=date(2026, 8, 22),
    )
    from fde_api.files.models import ProjectFile, ProjectFileVersion

    project_file = ProjectFile(
        id=file_id, project=project, category="attachment",
        display_name="预调研表", description="", created_by=leader,
    )
    version = ProjectFileVersion(
        id=version_id, project_file=project_file, version_number=1,
        source="upload", original_filename="预调研表.docx", safe_filename="presurvey.docx",
        extension="docx", mime_type="", bucket="local",
        storage_key=f"projects/{project_id}/presurvey/presurvey.docx",
        size_bytes=len(data), etag="", sha256="", uploaded_by=leader,
        status="available", scan_status="clean", preview_status="none",
    )
    analysis = ProjectGuidanceAnalysis(
        id=uuid4().hex, project_id=project_id, version_number=1,
        source_file_id=file_id, source_file_version_id=version_id,
        source_filename="预调研表.docx", source_sha256="",
        status="draft", analysis_state="queued", created_by_user_id=leader.id,
    )
    job = BackgroundJob(job_type="project.presurvey.analyze", target_id=analysis.id, status="pending")
    db_session.add_all([leader, template, template_version, project, project_file, version])
    db_session.flush()
    db_session.add_all([analysis, job])
    db_session.commit()
    object_storage.current.put_stream(version.storage_key, io.BytesIO(data), "application/octet-stream", {})
    return analysis, job, version, leader


def _valid_payload(source_ref: str) -> dict:
    return _draft(
        ref=source_ref,
        customer_vision=SYNTHETIC_NAME + "希望数字化转型，联系 13800138000",
        executive_summary="某技术公司提出需求",
        evidence={source_ref: SYNTHETIC_NAME + "的现状"},
    )


def test_job_redacts_before_persist(app, db_session, monkeypatch):
    analysis, job, version, _leader = _seed_analysis(db_session, data=b"fake docx")
    source_ref = f"kimi-file:{version.id}"

    def payload(ref: str, _content: bytes) -> dict:
        assert ref == source_ref
        return _valid_payload(ref)

    captured: dict = {}

    class _FakeKimiClient:
        def __init__(self, **_kwargs):
            pass

        def analyze_docx_json(self, *, stream, filename, request_id, build_messages):
            captured["content"] = stream.read()
            return payload(source_ref, captured["content"])

    monkeypatch.setattr(guidance_jobs, "KimiFileClient", _FakeKimiClient)

    with app.app_context():
        handle_presurvey_analysis(job)

    db_session.refresh(analysis)
    assert (analysis.analysis_state, analysis.failure_code, analysis.failure_message) == ("ready", "", "")
    assert analysis.customer_vision == "示例客户乙·软件·上海希望数字化转型，联系 [手机号已脱敏]"
    assert analysis.evidence_json == {source_ref: "示例客户乙·软件·上海的现状"}
    assert SYNTHETIC_NAME not in json.dumps(analysis.evidence_json, ensure_ascii=False)


def test_job_credential_echo_fails_cleanly(app, db_session, monkeypatch):
    analysis, job, version, _leader = _seed_analysis(db_session, data=b"fake docx")
    source_ref = f"kimi-file:{version.id}"
    payload = _valid_payload(source_ref)
    payload["evidence"] = {source_ref: "密码: abcd1234efgh5678"}

    class _FakeKimiClient:
        def __init__(self, **_kwargs):
            pass

        def analyze_docx_json(self, *, stream, filename, request_id, build_messages):
            stream.read()
            return payload

    monkeypatch.setattr(guidance_jobs, "KimiFileClient", _FakeKimiClient)

    with app.app_context():
        handle_presurvey_analysis(job)

    db_session.refresh(analysis)
    assert analysis.analysis_state == "failed"
    assert analysis.failure_code == "sensitive_content_detected"
    assert "abcd1234efgh5678" not in (analysis.evidence_json or {})


def test_job_dictionary_failure_fails_closed(app, db_session, monkeypatch):
    analysis, job, version, _leader = _seed_analysis(db_session, data=b"fake docx")
    payload = _valid_payload(f"kimi-file:{version.id}")

    class _FakeKimiClient:
        def __init__(self, **_kwargs):
            pass

        def analyze_docx_json(self, *, stream, filename, request_id, build_messages):
            stream.read()
            return payload

    monkeypatch.setattr(guidance_jobs, "KimiFileClient", _FakeKimiClient)

    def _broken_loader():
        raise EnterpriseDictionaryError("词典不可读（测试注入）")

    monkeypatch.setattr("fde_api.guidance.redaction.load_dictionary", _broken_loader)

    with app.app_context():
        handle_presurvey_analysis(job)

    db_session.refresh(analysis)
    assert analysis.analysis_state == "failed"
    assert analysis.failure_code == "redaction_failed"
    assert analysis.customer_vision == ""  # 零字段落库


# ---------- D. 待复核清单读面与 confirm 复核闸 ----------


def _seed_ready_analysis(db_session, *, executive_summary: str):
    analysis, _job, _version, leader = _seed_analysis(db_session, data=b"fake docx")
    analysis.analysis_state = "ready"
    analysis.executive_summary = executive_summary
    db_session.commit()
    return analysis, leader


def test_serialize_surfaces_review_list(app, db_session):
    analysis, leader = _seed_ready_analysis(db_session, executive_summary="某技术公司提出需求")
    with app.app_context():
        data = get_analysis(actor=leader, project_id=analysis.project_id, analysis_id=analysis.id)
    assert {"field": "executive_summary", "match": "某技术公司"} in data["redaction_review"]


def test_confirm_blocks_without_ack_then_allows_with_ack(app, db_session):
    analysis, leader = _seed_ready_analysis(db_session, executive_summary="某技术公司提出需求")
    with app.app_context():
        with pytest.raises(GuidanceServiceError) as error:
            confirm_analysis(actor=leader, project_id=analysis.project_id, analysis_id=analysis.id, expected_version=analysis.version)
        assert error.value.code == "redaction_review_required"
        assert error.value.status == 409

        confirmed = confirm_analysis(
            actor=leader, project_id=analysis.project_id, analysis_id=analysis.id,
            expected_version=analysis.version, redaction_reviewed=True,
        )
    assert confirmed["status"] == "confirmed"
    db_session.refresh(analysis)
    assert analysis.status == "confirmed"
    event = (
        db_session.query(OperationEvent)
        .filter(OperationEvent.project_id == analysis.project_id)
        .filter(OperationEvent.event_type == "guidance_analysis_confirmed")
        .order_by(OperationEvent.occurred_at.desc())
        .first()
    )
    assert event is not None
    assert event.changes["redaction_reviewed"] is True
    assert event.changes["redaction_review_hits"] >= 1


def test_confirm_clean_analysis_needs_no_ack(app, db_session):
    analysis, leader = _seed_ready_analysis(db_session, executive_summary="围绕试点验证再复制")
    with app.app_context():
        confirmed = confirm_analysis(
            actor=leader, project_id=analysis.project_id, analysis_id=analysis.id,
            expected_version=analysis.version,
        )
    assert confirmed["status"] == "confirmed"
