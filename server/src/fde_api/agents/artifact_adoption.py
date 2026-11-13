"""产物采纳为方案（goal-crj 采纳流最小补全；自 agents/service.py 拆出）。

背景（80/20 补全）：solutions 域已有**正向**接线——``POST /solutions/{id}/generate-agent``
起 run，completed 即把 ``solution.agent_run_id`` 接线并标 ``generated_by='agent'``
（``solutions/service.py::generate_agent_solution``）。缺的是**反向**入口：run 产物页
把一份产物**采纳为方案**（人点一次，AI 产出的交付物进入方案台账）。

族内先例（人工采纳语义一律"AI 只产候选、人工点确认"，红线同族）：
- ``guidance/service.py::adopt_translator_draft``——翻译草稿 ready → 升格项目指引新版本；
- ``ontology`` change-set 候选 → confirmed（``confirm`` 事务逐项物化）；
- ``workflows/draft_ai``——AI 只出草稿，人工采纳走既有 ``create_definition``→``publish``。

本模块与族内先例同尺：
- **人工触发**（无自动采纳路径）；AI 不自行把产物写进方案台账；
- **can_manage 闸**（与产物复核动作同尺）＋项目存在性闸；
- **幂等**：同一 run 的同一产物重复采纳 ⇒ 复用既有方案（``linked_solution_id`` 已存在
  则直接返回，不重复建方案、不重复计费、不重复落事件）；
- **溯源列族**（E3/V9/V11）：新建方案即 ``generated_by='agent'`` ＋
  ``agent_run_id=<run_id>`` ＋ ``source_json.kind='adopted_artifact'``，
  产物行回写 ``linked_solution_id`` ⇒ solution⇄run⇄artifact 三段可反查；
- **只引用不搬运**（红线 §6.6）：产物原件永不进库/仓库——方案只存**指针**
  （``storage_ref`` ＋ sha256 ＋ 引用计数），原件留在宿主工作区。

拆分缘起：``agents/service.py`` 行数预算 1836（``test_source_size_budgets``），
落库链路的加法一律新开模块——与 ``host_receipt.py`` 拆分同款纪律。
依赖形态：**顶层只依赖 models/extensions**；solutions 侧一律**函数内惰性导入**
（agents⇄solutions 本就互相延迟导入，避免顶层 import 环）。
"""
from __future__ import annotations

from typing import Any, NoReturn

from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.auth.models import User
from fde_api.extensions import db

# 采纳后方案的默认名（人工可改；仅当未指定 name 时的兜底）。
_DEFAULT_NAME = "AI 产物采纳方案"
_NAME_MAX = 160
# 引用计数上限：方案正文里逐条列出被采纳产物（指针＋指纹），超限截断并计数。
_MAX_REFERENCES = 50


class ArtifactAdoptionError(Exception):
    """产物采纳失败（稳定错误码；路由面映射 HTTP）。"""

    def __init__(self, code: str, message: str, status: int = 400, *, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.detail = code, message, status, detail


def _error(code: str, message: str, status: int = 400, *, detail: dict[str, Any] | None = None) -> NoReturn:
    raise ArtifactAdoptionError(code, message, status, detail=detail)


def _load_run_artifact(session, run_id: str, artifact_id: str) -> tuple[AgentRun, AgentArtifact]:
    run = session.get(AgentRun, run_id)
    if run is None:
        _error("agent_run_not_found", "智能体 run 不存在。", 404)
    artifact = session.get(AgentArtifact, artifact_id)
    if artifact is None or artifact.run_id != run.id:
        _error("agent_artifact_not_found", "产物不存在或不属于该 run。", 404)
    return run, artifact


def adopt_artifact_as_solution(
    *,
    actor: User,
    run_id: str,
    artifact_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把 run 产物采纳为项目方案（人工动作；can_manage；幂等）。

    失败语义（fail-closed 家族一致，零静默降级）：
    - run/产物不存在或产物不属该 run ⇒ 404（不泄露存在性）；
    - run 未到终态（queued/running/host_running）⇒ 409 ``agent_run_not_terminal``
      （半成品不采纳）；
    - 产物已被别的方案引用 ⇒ 409 ``artifact_already_adopted``；
    - 项目不可见 ⇒ 404；不可管 ⇒ 403（与产物复核动作同尺）；
    - 方案字段非法 ⇒ 400（沿 solutions 域 ``_normalize`` 同款约束）。
    """
    from fde_api.projects.events import record_event
    from fde_api.projects.permissions import project_access
    from fde_api.solutions import models as solution_models
    from fde_api.solutions import service as solutions_service
    from fde_api.workbench.models import Project

    payload = payload or {}
    if not isinstance(payload, dict):
        _error("invalid_request", "请求字段无效。")
    allowed = {"name", "business_category", "opportunity_ids", "target_solution_id"}
    if set(payload) - allowed:
        _error("invalid_request", "请求字段无效。")
    target_solution_id = payload.get("target_solution_id")
    if target_solution_id is not None and (
        not isinstance(target_solution_id, str) or not target_solution_id or len(target_solution_id) > 36
    ):
        _error("invalid_request", "target_solution_id 无效。")

    with db.session() as session, session.begin():
        run, artifact = _load_run_artifact(session, run_id, artifact_id)

        # ① 终态闸：未终态不采纳（半成品不进方案台账）。
        if run.status not in ("completed", "succeeded_but_receipt_invalid"):
            _error(
                "agent_run_not_terminal",
                "该 run 未到终态，暂不能采纳产物。",
                409,
                detail={"run_id": run.id, "status": run.status},
            )
        # ② 幂等闸：已采纳 ⇒ 原样返回既有方案（不重复建、不重复落事件）。
        if artifact.linked_solution_id:
            existing = session.get(solution_models.ProjectSolution, artifact.linked_solution_id)
            if existing is not None:
                return {
                    "solution_id": existing.id,
                    "run_id": run.id,
                    "artifact_id": artifact.id,
                    "adopted": False,
                    "duplicate": True,
                    "solution": solutions_service.serialize_solution(existing, session),
                }
            # 引用指向的方案已不存在（历史脏数据）⇒ 视为未采纳，继续。
        # ③ 重复采纳闸：同一 run 已采纳过其它产物 ⇒ 同 run 只认一份方案
        #    （避免一个 run 产出多份方案的台账歧义）。人工要多次采纳请先归档。
        for sibling in session.query(AgentArtifact).filter(
            AgentArtifact.run_id == run.id, AgentArtifact.linked_solution_id.isnot(None)
        ):
            _error(
                "artifact_already_adopted",
                "该 run 已有产物被采纳为方案，请先归档既有方案再采纳。",
                409,
                detail={
                    "run_id": run.id,
                    "solution_id": sibling.linked_solution_id,
                    "artifact_id": sibling.id,
                },
            )

        # ④ 项目闸：存在性（404，不泄露）＋ can_manage（403，同复核动作尺）。
        project = session.get(Project, run.project_id)
        if project is None:
            _error("project_not_found", "项目不存在。", 404)
        access = project_access(actor, project)
        if access is None:
            _error("project_not_found", "项目不存在或无权访问。", 404)
        if not access.can_manage:
            _error("project_forbidden", "采纳产物需要项目管理权限。", 403)

        # ④' 归入既有方案分支：人工已建方案时把产物挂上去（不新建方案）。
        #     同 run 只认一份方案 ⇒ 既有分支同样受"一 run 一方案"约束。
        if target_solution_id:
            target = session.get(solution_models.ProjectSolution, target_solution_id)
            if target is None or target.project_id != project.id:
                _error("solution_not_found", "目标方案不存在或不属于本项目。", 404)
            if target.status != "active":
                _error("solution_archived", "目标方案已弃用，不能采纳产物。", 409)
            if target.agent_run_id is not None and target.agent_run_id != run.id:
                _error(
                    "solution_agent_run_conflict",
                    "目标方案已绑定其它 run。",
                    409,
                    detail={"solution_id": target.id, "agent_run_id": target.agent_run_id},
                )
            # 溯源列族：归入时补接线（generated_by='agent' 与 agent_run_id）。
            if target.agent_run_id != run.id:
                target.agent_run_id = run.id
                target.generated_by = "agent"
                record_event(session, actor, "solution_agent_wired", project, {
                    "solution_id": target.id,
                    "agent_run_id": run.id,
                    "agent_id": run.agent_id,
                    "source": "adopted_artifact",
                })
            artifact.linked_solution_id = target.id
            session.flush()
            project.version += 1
            record_event(session, actor, "agent_artifact_adopted_as_solution", project, {
                "solution_id": target.id,
                "run_id": run.id,
                "artifact_id": artifact.id,
                "agent_id": run.agent_id,
                "mode": "link_existing",
            })
            return {
                "solution_id": target.id,
                "run_id": run.id,
                "artifact_id": artifact.id,
                "adopted": True,
                "duplicate": False,
                "solution": solutions_service.serialize_solution(target, session),
            }

        # ⑤ 方案字段：沿 solutions 域同款约束（name 必填/长度上限）。
        name = payload.get("name")
        if name is None:
            name = f"{_DEFAULT_NAME}·{artifact.kind}"
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > _NAME_MAX:
            _error("invalid_request", f"name 必须为非空文本，且不能超过 {_NAME_MAX} 字。")
        name = name.strip()
        business_category = payload.get("business_category")
        if business_category is not None and business_category not in solutions_service.BUSINESS_CATEGORIES:
            _error("invalid_request", "业务阶段无效。")
        opportunity_ids = payload.get("opportunity_ids")
        if opportunity_ids is not None:
            if (
                not isinstance(opportunity_ids, list)
                or len(opportunity_ids) > 100
                or any(not isinstance(key, str) or not key or len(key) > 36 for key in opportunity_ids)
                or len(set(opportunity_ids)) != len(opportunity_ids)
            ):
                _error("invalid_opportunities", "机会 id 列表无效（最多 100 个且不能重复）。")

        # ⑥ 建方案：正文只存**指针＋指纹**（红线 §6.6——原件永不进库/仓库）。
        #    方案状态 active：终审进度由 solution_review_checkpoints 承载
        #    （不靠 solution.status——该列 CHECK 仅允许 active/archived），
        #    采纳只是"落台账"，终审拍板仍走既有 signoff 人工动作。
        references = [
            {
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "storage_ref": artifact.storage_ref,
                "sha256": artifact.sha256,
            }
        ]
        source_json = {
            "kind": "adopted_artifact",
            "run_id": run.id,
            "agent_id": run.agent_id,
            "execution_provider": run.execution_provider,
            "capability_used": run.capability_used,
            "artifact_id": artifact.id,
            "storage_ref": artifact.storage_ref,
            "sha256": artifact.sha256,
            "references": references[:_MAX_REFERENCES],
            "references_truncated": len(references) > _MAX_REFERENCES,
        }
        design_markdown = (
            "# AI 产物采纳（待完善）\n\n"
            f"本方案由 run `{run.id}` 的产物采纳生成，原件不在服务端（红线 §6.6）。\n\n"
            f"- 产物指纹：`{artifact.sha256}`\n"
            f"- 产物指针：`{artifact.storage_ref}`\n\n"
            "请人工补全方案正文（设计/交付物/验收/数据系统/排期/风险），再走终审拍板。\n"
        )
        solution = solution_models.ProjectSolution(
            project_id=project.id,
            owner_user_id=actor.id,
            name=name,
            design_markdown=design_markdown,
            deliverables="",
            acceptance_criteria="",
            data_systems="",
            schedule="",
            risks_dependencies="",
            business_category=business_category,
            status="active",
            generated_by="agent",
            agent_run_id=run.id,
            source_json=source_json,
        )
        session.add(solution)
        session.flush()
        if opportunity_ids:
            # 同 solutions 域 create_solution 同款：机会须属本项目且未弃用
            # （_selected_opportunities 内部校验并报错）。
            opportunities = solutions_service._selected_opportunities(session, project.id, opportunity_ids)
            solutions_service._set_opportunities(solution, opportunities)

        # ⑦ 产物回写引用（同一事务内 ⇒ 不会出现"建了方案但没回链"的中间态）。
        artifact.linked_solution_id = solution.id
        session.flush()
        project.version += 1
        record_event(session, actor, "agent_artifact_adopted_as_solution", project, {
            "solution_id": solution.id,
            "run_id": run.id,
            "artifact_id": artifact.id,
            "agent_id": run.agent_id,
        })
        return {
            "solution_id": solution.id,
            "run_id": run.id,
            "artifact_id": artifact.id,
            "adopted": True,
            "duplicate": False,
            "solution": solutions_service.serialize_solution(solution, session),
        }
