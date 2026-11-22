"""R5 收敛钉：立项异常可按类别排查，敏感异常内容不进入日志。"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import StatementError

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.projects import service
from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion
from fde_api.workbench.seed import GENERIC_TEMPLATE_KEY, seed_workbench

from conftest import INITIAL_PASSWORD


@pytest.fixture
def published_template(db_session):
    seed_workbench(db_session)
    db_session.commit()
    return db_session.scalar(
        select(IndustryTemplateVersion).join(IndustryTemplate).where(
            IndustryTemplateVersion.status == "published",
            IndustryTemplate.template_key == GENERIC_TEMPLATE_KEY,
        )
    )


def test_unexpected_create_project_error_logs_only_exception_type(
    app, db_session, published_template, monkeypatch, caplog
):
    admin = User(
        username=f"r5-cause.{uuid4().hex[:8]}",
        display_name="R5 cause admin",
        role="admin",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    marker = "synthetic-should-not-be-logged"

    def force_unexpected_failure(*args, **kwargs):
        raise StatementError(marker, "SELECT :value", {"value": marker}, RuntimeError(marker))

    monkeypatch.setattr(service, "schedule_tasks", force_unexpected_failure)

    with caplog.at_level(logging.ERROR), pytest.raises(service.ProjectServiceError) as error:
        service.create_project(
            actor=admin,
            input={
                "name": marker,
                "enterprise_code": f"r5-{uuid4().hex[:8]}",
                "template_version_id": published_template.id,
                "leader_user_id": admin.id,
                "planned_start_date": "2026-11-24",
                "module_keys": ["pre_diagnosis"],
                "business_line": "FDE",
            },
        )

    assert error.value.code == "project_creation_failed"
    assert error.value.status == 503
    assert error.value.message == "Unable to create the project at this time."
    records = [record for record in caplog.records if record.name == app.logger.name]
    assert [record.getMessage() for record in records] == ["project_creation_failed (StatementError)"]
    assert records[0].exc_info is None
    assert records[0].stack_info is None
    assert marker not in repr(vars(records[0]))
    assert marker not in caplog.text
    assert "SELECT :value" not in caplog.text
    assert error.value.__suppress_context__
    assert error.value.__cause__ is None
