"""立项模板「模块须带任务行」契约（2026-11-25，CI 偶发红根因轮）。

背景（2026-11-25 实测定位，非猜测）：
  `seed_workbench` 会发布四个模板版本——通用模板（每模块带任务行）＋三个行业模板
  （零售连锁／餐饮连锁／制造业，**每模块 0 任务行**：``seed_industry_templates``
  按设计只建模块与调研表，不建任务行）。
  用行业模板建项目时，``create_project`` 的 ``_set_module_dates`` 会因
  ``tasks_by_module_id[module.id]`` 取不到模块而抛 KeyError，被兜底
  ``except Exception`` 吞成 **503 project_creation_failed**；``from None``
  又抹掉原始 traceback ⇒ 调用方只看到一句不可读的 503。

本文件钉两件事：
  ① 产品侧：这类输入是「模板形状不满足立项前提」的可判定错误 ⇒ 必须 400
     ``template_module_without_tasks``，且**不得**再落成 503；
  ② 测试侧：``published_template`` 夹具必须钉住唯一模板（``GENERIC_TEMPLATE_KEY``）——
     无序选取是 CI 偶发红的直接来源（``test_crv_batch_a.py::test_qr018_...``）。
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.projects.service import ProjectServiceError, create_project
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    ModuleCatalog,
    TemplateModule,
    TemplateTask,
)
from fde_api.workbench.seed import GENERIC_TEMPLATE_KEY, seed_workbench

_TESTS_DIR = Path(__file__).resolve().parent


def _admin(db_session) -> User:
    user = User(
        username=f"tpl.{uuid4().hex[:8]}",
        display_name="Template Admin",
        role="admin",
        password_hash=hash_password("Template-Pass-101"),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _published_versions(db_session) -> list[tuple[IndustryTemplateVersion, int]]:
    """每个 published 版本 → 它的任务行总数（0 ＝ 只建了模块与调研表）。"""
    rows: list[tuple[IndustryTemplateVersion, int]] = []
    for version in db_session.scalars(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    ):
        modules = list(db_session.scalars(
            select(TemplateModule).where(TemplateModule.template_version_id == version.id)
        ))
        task_rows = sum(
            len(list(db_session.scalars(
                select(TemplateTask).where(TemplateTask.template_module_id == module.id)
            )))
            for module in modules
        )
        rows.append((version, task_rows))
    return rows


def _create_project(actor: User, version_id: str):
    return create_project(
        actor=actor,
        input={
            "name": "模板任务契约",
            "enterprise_code": f"tpl-{uuid4().hex[:8]}",
            "template_version_id": version_id,
            "leader_user_id": actor.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
            "business_line": "FDE",
        },
    )


# ---------------------------------------------------------------- ① 产品侧


def test_industry_template_without_tasks_is_rejected_as_400(db_session):
    """无任务行的模板（行业模板）建项目 ⇒ 400 template_module_without_tasks，不是 503。"""
    seed_workbench(db_session)
    db_session.commit()
    rows = _published_versions(db_session)
    without_tasks = [version for version, task_rows in rows if task_rows == 0]
    assert without_tasks, "前置条件：seed_workbench 应发布至少一个 0 任务行的行业模板"

    admin = _admin(db_session)
    with pytest.raises(ProjectServiceError) as error:
        _create_project(admin, without_tasks[0].id)

    assert error.value.code == "template_module_without_tasks", error.value.code
    assert error.value.status == 400, error.value.status
    # 关键：不得再落成兜底 503（那会把输入形状问题伪装成服务端故障）
    assert error.value.status != 503
    assert error.value.code != "project_creation_failed"


def test_rejection_message_names_the_offending_module(db_session):
    """错误消息须指名无任务的模块键，便于调用方定位（不是一句不可读的通用文案）。"""
    seed_workbench(db_session)
    db_session.commit()
    rows = _published_versions(db_session)
    without_tasks = [version for version, task_rows in rows if task_rows == 0]
    admin = _admin(db_session)
    with pytest.raises(ProjectServiceError) as error:
        _create_project(admin, without_tasks[0].id)
    assert "pre_diagnosis" in error.value.message, error.value.message


def test_generic_template_project_creation_still_succeeds(db_session):
    """通用模板（有任务行）建项目不受影响——零回归。"""
    seed_workbench(db_session)
    db_session.commit()
    generic = db_session.scalar(
        select(IndustryTemplateVersion)
        .join(IndustryTemplate)
        .where(
            IndustryTemplateVersion.status == "published",
            IndustryTemplate.template_key == GENERIC_TEMPLATE_KEY,
        )
    )
    assert generic is not None
    admin = _admin(db_session)
    created = _create_project(admin, generic.id)
    assert created["id"]


def test_rejection_leaves_no_project_row(db_session):
    """被 400 拒绝时不得留下半棵项目树（事务整体回滚）。"""
    from fde_api.workbench.models import Project as WorkbenchProject
    from fde_api.workbench.models import ProjectModule, ProjectTask

    seed_workbench(db_session)
    db_session.commit()
    rows = _published_versions(db_session)
    without_tasks = [version for version, task_rows in rows if task_rows == 0]
    admin = _admin(db_session)
    with pytest.raises(ProjectServiceError):
        _create_project(admin, without_tasks[0].id)
    db_session.rollback()
    for model in (WorkbenchProject, ProjectModule, ProjectTask):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0, model.__name__


# ---------------------------------------------------------------- ② 测试侧


def _published_template_fixtures() -> list[tuple[str, int]]:
    """扫出全仓 `published_template` 夹具定义（文件＋行号）。"""
    found: list[tuple[str, int]] = []
    for path in sorted(_TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "published_template":
                found.append((path.name, node.lineno))
    return found


def test_published_template_fixtures_pin_a_unique_template():
    """每个 `published_template` 夹具都必须按 template_key 钉住唯一模板。

    无序选取（只按 status=="published"）会让「库里有几个 published 版本」变成隐式随机变量：
    命中行业模板（0 任务行）时建项目落成 503，命中通用模板时成功 ⇒ 同一断言偶红偶绿。

    判定走 **AST 层**（查函数体内的 ``ast.Attribute(attr="template_key")`` 节点），
    不用文本匹配——夹具的 docstring 里若出现「template_key」字样，纯文本 grep 会把
    「已回退成无序选取」的夹具误判为合格（本次变异验证实测踩过：M3 曾因此幸存）。
    """
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "published_template"):
                continue
            # 只看函数体（docstring 是首个 Expr 节点，其内容不参与判定）
            body_nodes = list(ast.walk(node))
            pins_by_key = any(
                isinstance(child, ast.Attribute) and child.attr == "template_key"
                for child in body_nodes
            )
            if not pins_by_key:
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "这些 published_template 夹具未钉住 template_key（无序选取＝隐式随机变量）："
        + ", ".join(offenders)
    )


def test_published_template_fixture_exists_at_all():
    """防扫描本身失效（夹具被改名/删除时本钉须红）。"""
    found = _published_template_fixtures()
    assert len(found) >= 8, f"夹具清单只剩 {len(found)} 个（扫描范围被缩小）：{found}"
