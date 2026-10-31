from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.files.models import ProjectFileVersion
from fde_api.guidance.ai_schema import LIST_FIELDS
from fde_api.guidance.models import (
    INTERVIEW_MODES,
    PresurveyIntake,
    ProjectGuidanceAnalysis,
    ProjectPresurveySource,
)
from fde_api.jobs.outbox import enqueue_outbox
from fde_api.projects.events import record_event
from fde_api.projects.permissions import project_access
from fde_api.workbench.models import Gate, Project


class GuidanceServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def set_presurvey_source(*, actor: User, project_id: str, file_version_id: str) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _project(session, actor, project_id, manage=True)
            _require_s3_gate(session, project.id)
            version = session.scalar(select(ProjectFileVersion).options(selectinload(ProjectFileVersion.project_file)).where(ProjectFileVersion.id == file_version_id))
            _valid_source(version, project.id)
            source = session.get(ProjectPresurveySource, project.id)
            if source is None:
                source = ProjectPresurveySource(project_id=project.id, project_file_id=version.file_id, current_file_version_id=version.id)
                session.add(source)
            else:
                source.project_file_id = version.file_id
                source.current_file_version_id = version.id
                source.version += 1
            session.flush()
            return _source_dict(source)
    finally:
        session.close()


def create_analysis(*, actor: User, project_id: str, source_file_version_id: str | None = None) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _project(session, actor, project_id, manage=True)
            _require_s3_gate(session, project.id)
            source = session.get(ProjectPresurveySource, project.id)
            version_id = source_file_version_id or (source.current_file_version_id if source else None)
            if not version_id:
                raise GuidanceServiceError("presurvey_source_required", "请先在文件库选择一份预调研 DOCX。", 400)
            version = session.scalar(select(ProjectFileVersion).options(selectinload(ProjectFileVersion.project_file)).where(ProjectFileVersion.id == version_id))
            _valid_source(version, project.id)
            number = int(session.scalar(select(func.coalesce(func.max(ProjectGuidanceAnalysis.version_number), 0)).where(ProjectGuidanceAnalysis.project_id == project.id)) or 0) + 1
            analysis = ProjectGuidanceAnalysis(
                project_id=project.id, version_number=number, source_file_id=version.file_id,
                source_file_version_id=version.id, source_filename=version.original_filename,
                source_sha256=version.sha256, status="draft", analysis_state="queued",
                created_by_user_id=actor.id,
            )
            session.add(analysis)
            session.flush()
            enqueue_outbox(session, "project.presurvey.analyze", analysis.id, {"project_id": project.id})
            return serialize_analysis(analysis, source)
    finally:
        session.close()


def list_analyses(*, actor: User, project_id: str) -> list[dict[str, Any]]:
    session = db.session()
    try:
        _project(session, actor, project_id)
        source = session.get(ProjectPresurveySource, project_id)
        rows = session.scalars(select(ProjectGuidanceAnalysis).where(ProjectGuidanceAnalysis.project_id == project_id).order_by(ProjectGuidanceAnalysis.version_number.desc())).all()
        return [serialize_analysis(row, source) for row in rows]
    finally:
        session.close()


def get_analysis(*, actor: User, project_id: str, analysis_id: str) -> dict[str, Any]:
    session = db.session()
    try:
        _project(session, actor, project_id)
        row = session.get(ProjectGuidanceAnalysis, analysis_id)
        if row is None or row.project_id != project_id:
            raise GuidanceServiceError("guidance_not_found", "项目指引版本不存在。", 404)
        return serialize_analysis(row, session.get(ProjectPresurveySource, project_id))
    finally:
        session.close()


def update_analysis(*, actor: User, project_id: str, analysis_id: str, expected_version: int, changes: Mapping[str, Any]) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            _project(session, actor, project_id, manage=True)
            row = session.get(ProjectGuidanceAnalysis, analysis_id, with_for_update=True)
            if row is None or row.project_id != project_id:
                raise GuidanceServiceError("guidance_not_found", "项目指引版本不存在。", 404)
            if row.status != "draft" or row.analysis_state != "ready":
                raise GuidanceServiceError("guidance_not_editable", "只有分析完成的草稿可以修改。", 409)
            if row.version != expected_version:
                raise GuidanceServiceError("stale_version", "项目指引已被他人更新，请刷新后重试。", 409)
            for field in ("customer_vision", "current_phase_objective", "executive_summary"):
                if field in changes:
                    value = changes[field]
                    if not isinstance(value, str) or not value.strip():
                        raise GuidanceServiceError("invalid_guidance", f"{field} 不能为空。", 400)
                    setattr(row, field, value.strip())
            for field in LIST_FIELDS:
                if field in changes:
                    value = changes[field]
                    if not isinstance(value, list):
                        raise GuidanceServiceError("invalid_guidance", f"{field} 格式不正确。", 400)
                    setattr(row, f"{field}_json", value)
            row.version += 1
            session.flush()
            return serialize_analysis(row, session.get(ProjectPresurveySource, project_id))
    finally:
        session.close()


def create_manual_revision(*, actor: User, project_id: str, analysis_id: str, expected_version: int) -> dict[str, Any]:
    """Create an editable revision without overwriting a confirmed guidance version."""
    session = db.session()
    try:
        with session.begin():
            project = _project(session, actor, project_id, manage=True)
            source_row = session.get(ProjectGuidanceAnalysis, analysis_id, with_for_update=True)
            if source_row is None or source_row.project_id != project.id:
                raise GuidanceServiceError("guidance_not_found", "项目指引版本不存在。", 404)
            if source_row.analysis_state != "ready":
                raise GuidanceServiceError("guidance_not_ready", "项目指引尚未分析完成，暂时不能编辑。", 409)
            if source_row.version != expected_version:
                raise GuidanceServiceError("stale_version", "项目指引已被更新，请刷新后重试。", 409)
            if source_row.status == "draft":
                return serialize_analysis(source_row, session.get(ProjectPresurveySource, project.id))

            number = int(session.scalar(
                select(func.coalesce(func.max(ProjectGuidanceAnalysis.version_number), 0))
                .where(ProjectGuidanceAnalysis.project_id == project.id)
            ) or 0) + 1
            revision = ProjectGuidanceAnalysis(
                project_id=project.id,
                version_number=number,
                source_file_id=source_row.source_file_id,
                source_file_version_id=source_row.source_file_version_id,
                source_filename=source_row.source_filename,
                source_sha256=source_row.source_sha256,
                status="draft",
                analysis_state="ready",
                customer_vision=source_row.customer_vision,
                current_phase_objective=source_row.current_phase_objective,
                executive_summary=source_row.executive_summary,
                evidence_json=deepcopy(source_row.evidence_json),
                ai_model=source_row.ai_model,
                ai_generated_at=source_row.ai_generated_at,
                created_by_user_id=actor.id,
            )
            for field in LIST_FIELDS:
                setattr(revision, f"{field}_json", deepcopy(getattr(source_row, f"{field}_json")))
            session.add(revision)
            session.flush()
            return serialize_analysis(revision, session.get(ProjectPresurveySource, project.id))
    finally:
        session.close()


def confirm_analysis(*, actor: User, project_id: str, analysis_id: str, expected_version: int) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _project(session, actor, project_id, manage=True)
            row = session.get(ProjectGuidanceAnalysis, analysis_id, with_for_update=True)
            if row is None or row.project_id != project_id:
                raise GuidanceServiceError("guidance_not_found", "项目指引版本不存在。", 404)
            if row.analysis_state != "ready" or row.status != "draft":
                raise GuidanceServiceError("guidance_not_confirmable", "只有分析完成的草稿可以确认。", 409)
            if row.version != expected_version:
                raise GuidanceServiceError("stale_version", "项目指引已被更新，请刷新后重试。", 409)
            for old in session.scalars(select(ProjectGuidanceAnalysis).where(ProjectGuidanceAnalysis.project_id == project_id, ProjectGuidanceAnalysis.status == "confirmed")).all():
                old.status = "superseded"
                old.version += 1
            row.status = "confirmed"
            row.reviewed_by_user_id = actor.id
            row.reviewed_at = datetime.now(UTC)
            row.version += 1
            source = session.get(ProjectPresurveySource, project_id)
            old_version_id = source.current_file_version_id if source else None
            if source is None:
                source = ProjectPresurveySource(
                    project_id=project_id, project_file_id=row.source_file_id,
                    current_file_version_id=row.source_file_version_id,
                )
                session.add(source)
            else:
                source.project_file_id = row.source_file_id
                source.current_file_version_id = row.source_file_version_id
                source.version += 1
            if old_version_id and old_version_id != row.source_file_version_id:
                old_version = session.get(ProjectFileVersion, old_version_id)
                if old_version is not None and old_version.status == "available":
                    old_version.status = "deprecated"
                    old_version.deprecated_by_user_id = actor.id
                    old_version.deprecated_at = datetime.now(UTC)
                    old_version.deprecation_reason = "预调研表新版本已确认"
            # goal-d2 P0 指标①埋点：售前「独立完成录入+确认」的确认侧事件
            # （录入侧为 presurvey_intake_saved）。纯增量审计，不影响返回值。
            record_event(session, actor, "guidance_analysis_confirmed", project, {
                "analysis_id": row.id, "version_number": row.version_number,
                "source_file_version_id": row.source_file_version_id,
            })
            session.flush()
            return serialize_analysis(row, source)
    finally:
        session.close()


def current_guidance(*, actor: User, project_id: str) -> dict[str, Any] | None:
    session = db.session()
    try:
        _project(session, actor, project_id)
        source = session.get(ProjectPresurveySource, project_id)
        row = session.scalar(select(ProjectGuidanceAnalysis).where(ProjectGuidanceAnalysis.project_id == project_id, ProjectGuidanceAnalysis.status == "confirmed").order_by(ProjectGuidanceAnalysis.version_number.desc()).limit(1))
        return serialize_analysis(row, source) if row else None
    finally:
        session.close()


def serialize_analysis(row: ProjectGuidanceAnalysis, source: ProjectPresurveySource | None = None) -> dict[str, Any]:
    data = {
        "id": row.id, "project_id": row.project_id, "version_number": row.version_number,
        "source_file_id": row.source_file_id, "source_file_version_id": row.source_file_version_id,
        "source_filename": row.source_filename, "status": row.status, "analysis_state": row.analysis_state,
        "customer_vision": row.customer_vision, "current_phase_objective": row.current_phase_objective,
        "executive_summary": row.executive_summary, "evidence": row.evidence_json,
        "ai_model": row.ai_model, "failure_code": row.failure_code, "failure_message": row.failure_message,
        "reviewed_by_user_id": row.reviewed_by_user_id, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "version": row.version,
    }
    for field in LIST_FIELDS:
        data[field] = getattr(row, f"{field}_json")
    data["source_is_stale"] = source is None or source.current_file_version_id != row.source_file_version_id
    return data


def _source_dict(source: ProjectPresurveySource) -> dict[str, Any]:
    return {"project_id": source.project_id, "project_file_id": source.project_file_id, "current_file_version_id": source.current_file_version_id, "version": source.version}


def get_presurvey_intake(*, actor: User, project_id: str) -> dict[str, Any]:
    session = db.session()
    try:
        _project(session, actor, project_id)
        return _intake_dict(session.get(PresurveyIntake, project_id))
    finally:
        session.close()


def save_presurvey_intake(*, actor: User, project_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _project(session, actor, project_id, manage=True)
            fields = _validated_intake_fields(changes)
            row = session.get(PresurveyIntake, project.id)
            if row is None:
                row = PresurveyIntake(project_id=project.id, updated_by_user_id=actor.id, **fields)
                session.add(row)
            else:
                for key, value in fields.items():
                    setattr(row, key, value)
                row.updated_by_user_id = actor.id
            session.flush()
            record_event(session, actor, "presurvey_intake_saved", project, {"fields": sorted(fields)})
            return _intake_dict(row)
    finally:
        session.close()


def _require_s3_gate(session, project_id: str) -> None:
    """G3 诊断开工门前置闸（PRD F1 / 决议 D16）：DOCX 分析链路仅限 S3 之后。

    G3 的证据清单即 SOW-A 签署 + A 款预付到账 + 数据授权书四项勾选
    （seeds/gates.json，SOP 原文），status=passed 表示三件套已人工核验；
    G3 的 decision 语义只有 pass/fail，无 conditional_pass。轻量录入卡
    （presurvey_intakes）不受此闸——S1–S2 即可填（PRD D16）。
    """
    gate = session.scalar(select(Gate).where(Gate.project_id == project_id, Gate.gate_key == "G3"))
    if gate is None or gate.status != "passed":
        raise GuidanceServiceError(
            "presurvey_s3_gate_open",
            "需先通过 G3 诊断开工门（SOW-A 签署、A 款到账、数据授权书四项勾选），才能上传预调研文件或发起 AI 分析。",
            409,
        )


_INTAKE_TEXT_LIMITS: dict[str, int] = {
    "industry": 80, "scale": 80, "region": 80,
    "customer_vision": 2000, "phase_objective": 2000, "notes": 2000,
}


def _validated_intake_fields(changes: Mapping[str, Any]) -> dict[str, Any]:
    text_limits = _INTAKE_TEXT_LIMITS
    allowed = set(text_limits) | {"interview_mode", "interviewee_roles"}
    unknown = set(changes) - allowed
    if unknown:
        raise GuidanceServiceError("unknown_field", f"不支持的录入卡字段：{sorted(unknown)}。", 400)
    fields: dict[str, Any] = {}
    for name, limit in text_limits.items():
        if name not in changes:
            continue
        value = changes[name]
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise GuidanceServiceError("invalid_request", f"{name} 必须是不超过 {limit} 字的文本。", 400)
        fields[name] = value.strip()
    if "interview_mode" in changes:
        mode = changes["interview_mode"]
        if mode not in INTERVIEW_MODES:
            raise GuidanceServiceError("invalid_request", "interview_mode 仅支持 onsite/remote/hybrid。", 400)
        fields["interview_mode"] = mode
    if "interviewee_roles" in changes:
        roles = changes["interviewee_roles"]
        if not isinstance(roles, list) or len(roles) > 20 or any(
            not isinstance(role, str) or not role.strip() or len(role.strip()) > 80 for role in roles
        ):
            raise GuidanceServiceError("invalid_request", "interviewee_roles 必须是不超过 20 条、每条 80 字以内的文本数组。", 400)
        fields["interviewee_roles"] = [role.strip() for role in roles]
    if not fields:
        raise GuidanceServiceError("invalid_request", "没有可保存的录入卡字段。", 400)
    return fields


def _intake_dict(row: PresurveyIntake | None) -> dict[str, Any]:
    if row is None:
        return {
            "industry": "", "scale": "", "region": "", "interview_mode": "onsite",
            "interviewee_roles": [], "customer_vision": "", "phase_objective": "", "notes": "",
            "updated_by_user_id": None, "updated_at": None,
        }
    return {
        "industry": row.industry, "scale": row.scale, "region": row.region,
        "interview_mode": row.interview_mode, "interviewee_roles": row.interviewee_roles,
        "customer_vision": row.customer_vision, "phase_objective": row.phase_objective,
        "notes": row.notes, "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _project(session, actor: User, project_id: str, *, manage: bool = False) -> Project:
    project = session.scalar(select(Project).options(selectinload(Project.members)).where(Project.id == project_id))
    access = project_access(actor, project) if project else None
    if project is None or access is None or not access.can_view:
        raise GuidanceServiceError("project_not_found", "项目不存在或无权访问。", 404)
    if manage and not access.can_manage:
        raise GuidanceServiceError("forbidden", "只有项目负责人或管理员可以执行此操作。", 403)
    return project


def _valid_source(version: ProjectFileVersion | None, project_id: str) -> None:
    if version is None or version.project_file.project_id != project_id:
        raise GuidanceServiceError("presurvey_file_not_found", "预调研文件版本不存在。", 404)
    if version.source == "preview" or version.extension.lower() != ".docx" or version.status != "available" or version.scan_status not in {"clean", "not_required"}:
        raise GuidanceServiceError("presurvey_file_unavailable", "请选择已完成安全检查的 DOCX 文件。", 400)
