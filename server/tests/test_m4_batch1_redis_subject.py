"""多客户 M4 批次 A：Redis 面主体归属核销钉（盘点表维度 3a K3/K4/K5＋K10/K11）。

M0 判定「无主体维度」按 M4 现测**纠正为核销**（机器判定人工纠正先例，不改造）：
- K4/K5（``fde:ai-execution:{id}:state``／``:events``）：``get_execution`` 已按
  ``state.actor_id != actor.id ⇒ 404``（不确认存在性）——本文件钉死跨主体读。
- K3（``fde:ai:action:{identifier}``）：identifier = sha256([user.id, execution_id,
  data]) 含执行者维度，事件账按 ``actor_user_id`` 过滤——本文件钉死 B 不能沿用
  A 的 action 结果（execution_id 相同也各自成账）。
- K10/K11（research import preview/lock/fence）：preview token 绑
  ``(preview_id, project_id)``＋commit 走 ``load_subject_project`` 项目闸——钉死
  非成员持合法 token 不能 commit。
变异验收（字节级还原＋sha256 对账）：
- M1 摘 ``get_execution`` 的 actor 校验 ⇒ K4/K5 钉红；
- M2 摘 K3 identifier 的 user.id 维度＋事件账 actor 过滤 ⇒ K3 钉红。
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.ai.executions import AIExecutionError, get_execution, start_execution
from fde_api.control.access import capabilities_for_level
from fde_api.control.api_actions import execute_api
from fde_api.research.imports import commit_subject_import
from fde_api.research.imports import _serializer as _import_serializer
from fde_api.research.subject_service import ResearchSubjectServiceError
from fde_api.workbench.models import OperationEvent
from test_ai_server_chat_mcp import ai_context, make_project  # noqa: F401

# ─────────────────────────── K4/K5：执行状态与事件流 ───────────────────────────


def _m4_actor(db_session, role: str = "admin") -> object:
    from fde_api.auth.models import User

    user = User(
        username=f"m4-a-{role}-{uuid4().hex[:8]}",
        display_name=f"M4 批次A {role}",
        role=role,
        password_hash="unused",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_execution_state_and_events_cross_actor_not_found(db_session, app):
    """K4/K5：B 读 A 的执行状态/事件流 ⇒ 404（事件流在归属闸之后，同闸覆盖）。"""
    with app.app_context():
        actor_a = _m4_actor(db_session)
        actor_b = _m4_actor(db_session)
        started = start_execution(
            actor=actor_a,
            operation="project_ai_opportunities_discover",
            payload={"project_id": str(uuid4())},
        )
        execution_id = started["id"]
        with pytest.raises(AIExecutionError) as exc:
            get_execution(actor=actor_b, execution_id=execution_id, after=0)
        assert exc.value.status == 404
        assert exc.value.code == "ai_execution_not_found"
        # 阳性对照：本人可读（running 态、事件流可分页）。
        own = get_execution(actor=actor_a, execution_id=execution_id, after=0)
        assert own["id"] == execution_id
        # K5 事件流：本人可读（含 start 时落的首条 stage 事件）、他人 404。
        assert any(e["type"] == "stage_changed" for e in own["events"])


# ─────────────────────────── K3：API-action 锁与事件账 ───────────────────────────


def _invoke(user, operation, parameters, body, *, execution, scope, level="system_operator"):
    return execute_api(
        user=user,
        claims={"execution_id": execution, "project_id": scope},
        allowed=set(capabilities_for_level(level)),
        operation=operation,
        parameters=parameters,
        body=body,
    )


def test_api_action_ledger_is_per_actor_with_same_execution_id(ai_context, db_session):
    """K3：B 提交与 A 完全相同的 (execution_id, data) ⇒ 各自成账，不沿用 A 的结果。"""
    users, _ = ai_context
    actor_a = users["admin"]
    actor_b = _m4_actor(db_session)  # 第二个 admin：与角色无关，只验 user.id 维度
    project = make_project(db_session, actor_a)
    execution = str(uuid4())  # 假设 B 以某种方式得知 A 的 execution_id（UUID 不可枚举不足以作防线）
    args = {"project_id": project.id}
    body = {"version": project.version, "name": "M4 K3 归属钉"}

    result_a = _invoke(actor_a, "projects.update", args, body, execution=execution, scope=project.id)
    assert result_a["status"] == "completed", result_a
    assert result_a["http_status"] == 200

    # 同一 execution_id＋同一 data，换 B 的身份提交。
    result_b = _invoke(actor_b, "projects.update", args, body, execution=execution, scope=project.id)
    # 锁键含 user.id ⇒ action_id 必不同（不是同一条 action 的重放）。
    assert result_b["action_id"] != result_a["action_id"]
    # 事件账按 actor 过滤 ⇒ B 的账里没有 A 的事件，反之亦然。
    events_a = db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == result_a["action_id"])
    ).all()
    events_b = db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == result_b["action_id"])
    ).all()
    assert events_a and events_b
    assert {e.actor_user_id for e in events_a} == {actor_a.id}
    assert {e.actor_user_id for e in events_b} == {actor_b.id}
    # B 的重放仍是 B 自己的账（不会撞到 A 的账）。
    replay_b = _invoke(actor_b, "projects.update", args, body, execution=execution, scope=project.id)
    assert replay_b["action_id"] == result_b["action_id"]


# ─────────────────────── K10/K11：research import preview/锁 ───────────────────────


def test_import_preview_token_cannot_be_committed_by_non_member(app, db_session):
    """K10/K11：非项目成员持合法 preview token commit ⇒ 404（项目闸兜底）。"""
    from fde_api.auth.models import User

    with app.app_context():
        member = User(
            username=f"m4-a-member-{uuid4().hex[:8]}",
            display_name="M4 成员",
            role="project_lead",
            password_hash="unused",
            must_change_password=False,
            is_active=True,
        )
        outsider = User(
            username=f"m4-a-outsider-{uuid4().hex[:8]}",
            display_name="M4 非成员",
            role="project_lead",
            password_hash="unused",
            must_change_password=False,
            is_active=True,
        )
        db_session.add_all([member, outsider])
        db_session.commit()
        project = make_project(db_session, member)

        # 成员侧合法签发的 preview token（形状与 store_subject_import 落库键一致）。
        preview_id = uuid4().hex
        token = _import_serializer().dumps({"preview_id": preview_id, "project_id": project.id})

        with pytest.raises(ResearchSubjectServiceError) as exc:
            commit_subject_import(
                project_id=project.id,
                preview_token=token,
                expected_version=1,
                actor=outsider,
            )
        assert exc.value.status == 404
        assert exc.value.code == "project_not_found"
