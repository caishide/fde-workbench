"""多客户 M3（隔离）测试共用工厂——双 org 夹具的单一出处。

被 ``test_org_scope_entry.py``（M3a 入口钉）与
``test_cross_tenant_isolation.py``（M3c 越权套件）复用，避免两处各写一套
夹具导致语义漂移。

**代号纪律**（红线 2）：org 名与项目代号一律代号化随机串，不含任何客户
真实信息；密码用测试常量，不进日志不进 git。
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.orgs.models import ORG_TYPE_ENTERPRISE, Org
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    Project,
    ProjectMember,
)

from conftest import INITIAL_PASSWORD


def make_enterprise_org(db_session, *, creator: User | None = None) -> Org:
    """建一个企业 org（代号化名，全局唯一）。"""
    org = Org(
        org_type=ORG_TYPE_ENTERPRISE,
        name=f"隔离用例企业·制造·{uuid4().hex[:8]}",
        created_by_user_id=creator.id if creator is not None else None,
    )
    db_session.add(org)
    db_session.commit()
    return org


def make_user(db_session, role: str = "viewer", *, org_id: str | None = None) -> User:
    """建一个账号；``org_id=None`` 即**平台身份**（§11-8 拍板语义）。"""
    user = User(
        username=f"m3.{role}.{uuid4().hex}",
        display_name=f"隔离用例{role}",
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
        org_id=org_id,
    )
    db_session.add(user)
    db_session.commit()
    return user


def make_project(
    db_session, leader: User, *, code: str, org_id: str | None = None
) -> Project:
    """建一个项目；``org_id`` **显式**给定（归属戳不覆盖显式值，M1 契约）。"""
    industry_template = IndustryTemplate(name="隔离用例模板", industry_name="制造")
    template_version = IndustryTemplateVersion(
        template=industry_template,
        name=industry_template.name,
        industry_name=industry_template.industry_name,
        description="",
        version_number=1,
        status="published",
        published_by=leader,
    )
    project = Project(
        project_code=code,
        name="隔离用例项目",
        enterprise_code=f"隔离用例企业·制造·{code}",
        leader=leader,
        source_template_version=template_version,
        template_snapshot={},
        research_snapshot={},
        planned_start_date=date(2026, 8, 22),
        org_id=org_id,
    )
    db_session.add(project)
    db_session.flush()
    db_session.commit()
    return project


def add_member(
    db_session, project: Project, user: User, *, role: str = "member"
) -> ProjectMember:
    """把账号加进项目成员（跨企业成员关系＝M3 越权套件的关键场景）。"""
    member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
    db_session.add(member)
    db_session.commit()
    return member
