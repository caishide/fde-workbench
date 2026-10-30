from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask import current_app

from fde_api.ai.kimi import KimiError, KimiFileClient
from fde_api.extensions import db, object_storage
from fde_api.files.models import ProjectFileVersion
from fde_api.guidance.ai_prompt import build_kimi_presurvey_analysis_messages
from fde_api.guidance.ai_schema import GuidanceContractError, LIST_FIELDS, validate_guidance_output
from fde_api.guidance.models import ProjectGuidanceAnalysis
from fde_api.jobs.handlers import register_handler

logger = logging.getLogger(__name__)

# 同一任务内的自动重试上限（不含首次尝试）。契约失败（ai_output_invalid）是
# MiniMax 级模型概率性不守 JSON 合同的已知现象：一次自动重试即可消化绝大多数，
# 上限必须有测试钉住——无上限会在模型持续吐畸形输出时把 worker 拖死。
GUIDANCE_ANALYSIS_RETRY_LIMIT = 1

# 兜底分类：KimiError / GuidanceContractError 之外的未预期异常，保证分析
# 永远不会卡在 analyzing 态（那会让前端无限轮询）。
UNEXPECTED_FAILURE_CODE = "analysis_unexpected_error"


def handle_presurvey_analysis(job) -> None:
    session = db.session()
    try:
        analysis = session.get(ProjectGuidanceAnalysis, job.target_id)
        if analysis is None or analysis.analysis_state in {"ready", "cancelled"}:
            return
        analysis.analysis_state = "extracting"
        session.commit()
        version = session.get(ProjectFileVersion, analysis.source_file_version_id)
        if version is None:
            _fail(session, analysis, "source_missing", "预调研源文件不存在。")
            return
        analysis.analysis_state = "analyzing"
        session.commit()
        settings = current_app.config["SETTINGS"]
        client = KimiFileClient(
            base_url=settings.kimi_base_url,
            api_key=settings.kimi_project_presurvey_api_key,
            model=settings.kimi_project_presurvey_model,
            timeout_seconds=settings.kimi_timeout_seconds,
            local_extract=settings.kimi_local_docx_extract,
            openai_compatible=settings.kimi_openai_compatible,
        )
        source_ref = f"kimi-file:{analysis.source_file_version_id}"
        attempts = 0
        while True:
            attempts += 1
            try:
                # 每次尝试重新开流：上一次尝试已消费/关闭了流。
                with object_storage.current.open_stream(version.storage_key) as stream:
                    payload = client.analyze_docx_json(
                        stream=stream,
                        filename=analysis.source_filename,
                        request_id=job.id,
                        build_messages=lambda content: build_kimi_presurvey_analysis_messages(content, source_ref),
                    )
                draft = validate_guidance_output(payload, source_refs={source_ref})
                break
            except KimiError as error:
                # 只有可重试错误（限流/超时/偶发畸形输出）才消耗重试额度；
                # ai_service_not_configured 这类配置问题重试也不会好。
                if not error.retryable or attempts > GUIDANCE_ANALYSIS_RETRY_LIMIT:
                    _safe_fail(
                        session, job.target_id, error.code,
                        _exhausted_message(error.public_message, attempts),
                    )
                    return
            except GuidanceContractError as error:
                if attempts > GUIDANCE_ANALYSIS_RETRY_LIMIT:
                    logger.warning(
                        "guidance contract violation not recovered (%s at %s)",
                        error.code, error.path,
                    )
                    _safe_fail(
                        session, job.target_id, "ai_output_invalid",
                        _exhausted_message("AI 返回的项目指引格式不正确。", attempts),
                    )
                    return
        analysis.customer_vision = draft["customer_vision"]
        analysis.current_phase_objective = draft["current_phase_objective"]
        analysis.executive_summary = draft["executive_summary"]
        analysis.evidence_json = draft["evidence"]
        for field in LIST_FIELDS:
            setattr(analysis, f"{field}_json", draft[field])
        analysis.ai_model = settings.kimi_project_presurvey_model
        analysis.ai_generated_at = datetime.now(UTC)
        analysis.analysis_state = "ready"
        analysis.failure_code = ""
        analysis.failure_message = ""
        analysis.version += 1
        session.commit()
    except Exception as error:  # noqa: BLE001 - 分析绝不能卡在 analyzing 态
        # 只记录异常类型：异常串可能携带用户文档内容，不进日志。
        logger.warning("presurvey analysis unexpected failure (%s)", type(error).__name__)
        _safe_fail(
            session, job.target_id, UNEXPECTED_FAILURE_CODE,
            "分析过程出现未预期错误，请重试；若持续失败请检查文件后重新发起分析。",
        )
    finally:
        session.close()


def _exhausted_message(public_message: str, attempts: int) -> str:
    retries = attempts - 1
    if retries <= 0:
        return public_message
    return f"{public_message}（已自动重试 {retries} 次仍失败，请重新发起分析）"


def _safe_fail(session, analysis_id: str, code: str, message: str) -> None:
    session.rollback()
    row = session.get(ProjectGuidanceAnalysis, analysis_id)
    if row is not None:
        _fail(session, row, code, message)


def _fail(session, row: ProjectGuidanceAnalysis, code: str, message: str) -> None:
    row.analysis_state = "failed"
    row.failure_code = code
    row.failure_message = message
    row.version += 1
    session.commit()


def register_presurvey_analysis_handler() -> None:
    register_handler("project.presurvey.analyze", handle_presurvey_analysis)
