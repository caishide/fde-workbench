from __future__ import annotations

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.jobs.handlers import register_handler
from fde_api.research.export_service import ResearchExportError, export_research_result
from fde_api.research.models import ProjectResearchExport


def handle_research_export(job) -> None:
    session = db.session()
    export = session.get(ProjectResearchExport, job.target_id)
    if export is None or export.status in {"succeeded", "failed"}:
        session.close()
        return
    export.status = "generating"
    export.failure_code = ""
    export.failure_message = ""
    actor_id, project_id, form_id = export.requested_by_user_id, export.project_id, export.form_id
    session.commit()
    session.close()

    try:
        actor_session = db.session()
        actor = actor_session.get(User, actor_id)
        actor_session.close()
        if actor is None:
            _fail(job.target_id, "requester_missing", "发起导出的用户不存在。")
            return
        result = export_research_result(actor=actor, project_id=project_id, form_id=form_id)
        result_session = db.session()
        row = result_session.get(ProjectResearchExport, job.target_id)
        if row is not None:
            row.status = "succeeded"
            row.project_file_id = result["file_id"]
            row.file_version_id = result["version_id"]
            row.version_number = result["version_number"]
            row.display_name = result["display_name"]
            result_session.commit()
        result_session.close()
    except ResearchExportError as error:
        _fail(job.target_id, error.code, error.message)
    except Exception:  # noqa: BLE001 - persist a safe Chinese task result
        _fail(job.target_id, "research_export_failed", "调研结果生成失败，请稍后重试。")


def _fail(export_id: str, code: str, message: str) -> None:
    session = db.session()
    try:
        row = session.get(ProjectResearchExport, export_id)
        if row is not None:
            row.status = "failed"
            row.failure_code = code
            row.failure_message = message
            session.commit()
    finally:
        session.close()


def register_research_export_handler() -> None:
    register_handler("research.export", handle_research_export)


def fail_export_on_worker_loss(session, job) -> None:
    """Close out an export whose worker died mid-flight.

    The export row sits in ``generating`` until somebody finishes it; a dead
    worker leaves it there and the UI polls for a file that never arrives.
    """
    row = session.get(ProjectResearchExport, job.target_id)
    if row is None or row.status in {"succeeded", "failed"}:
        return
    row.status = "failed"
    row.failure_code = "export_worker_lost"
    row.failure_message = "导出进程中断（后台任务进程退出），请重试。"


def register_research_export_failure_handler() -> None:
    from fde_api.jobs.handlers import register_job_failure_handler

    register_job_failure_handler("research.export", fail_export_on_worker_loss)
