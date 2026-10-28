"""WP30/J3：交付审计专用表（document_delivery_records）。

缺陷基线（5d82de1）：交付审计只落通用 operation_events，没有专用表与查询路由，
无法按「交付」维度检索。本轮加专用表 + 迁移 + 查询路由。

三条权限断言（不许「不止 happy path」这种不可证伪表述）：
  1. 普通用户（viewer / 非 project_lead）调用交付审计查询 → 403
  2. 跨项目访问 → 403/404（拿不到别的项目的交付记录）
  3. 同一 version 重复签发 → 审计记录幂等不重复
外加：签发确实写专用表（version_id + sha256 + 操作人 + 时间）。
"""
from uuid import uuid4

from sqlalchemy import func, select

from fde_api.documents.models import DocumentDeliveryRecord
from test_document_versions_api import (
    _docx_bytes,
    _manual_upload,
    _seed_document,
    authorized_client_factory,
    engineer_client,
    leader_client,
)


def _other_project(db_session, leader):
    """建一个「由另一位 project_lead 领导」的项目（跨项目访问断言用）。

    关键：leader 换成另一个 project_lead —— 这样请求方的系统角色
    （project_lead）能过路由门禁，被拒的只能是**项目范围**，
    断言测的才是跨项目边界而不是角色门禁。
    """
    from datetime import date

    from fde_api.auth.models import User
    from fde_api.auth.passwords import hash_password
    from fde_api.workbench.models import Project

    other_leader = User(
        username=f"other-lead.{uuid4().hex[:8]}",
        display_name="别的项目负责人",
        role="project_lead",
        password_hash=hash_password("Other-Lead-Pass!1"),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(other_leader)
    db_session.flush()

    project = Project(
        project_code=f"OTH-{uuid4().hex[:8]}",
        name="别的项目",
        enterprise_code="别家客户·制造·北京",
        sop_phase="S3",
        business_line="FDE",
        background="",
        notes="",
        status="draft",
        planned_start_date=date(2026, 1, 1),
        leader_user_id=other_leader.id,
        template_snapshot={},
        research_snapshot={},
    )
    db_session.add(project)
    db_session.commit()
    return project


def _confirmed_version(leader, member, project_id, document):
    """上传一版并确认（确认需要 project_lead），返回 version dict。"""
    upload = _manual_upload(
        member, project_id, document.id, document.version, _docx_bytes(text="交付版本")
    )
    assert upload.status_code == 201, upload.get_data(as_text=True)
    version = upload.json["data"]
    confirmed = leader.post(
        f"/api/v1/projects/{project_id}/documents/{version['id']}/confirm",
        json={"version": version["document_version"]},
    )
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)
    return version


def test_delivery_record_is_written_when_signing_download_url(
    db_session, leader_client, engineer_client
):
    """签发下载 URL 落专用表：version_id + sha256 + 操作人 + 时间齐全。"""
    engineer = engineer_client.user
    seeded = _seed_document(db_session, leader_client.user, engineer)
    project_id = seeded["project"].id
    document = seeded["document"]
    version = _confirmed_version(
        leader_client, engineer_client, project_id, document
    )

    response = engineer_client.get(
        f"/api/v1/projects/{project_id}/documents/{version['id']}/download-url"
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    record = db_session.scalar(
        select(DocumentDeliveryRecord).where(
            DocumentDeliveryRecord.version_id == version["id"]
        )
    )
    assert record is not None, "签发下载 URL 未落交付审计专用表"
    assert record.project_id == project_id
    assert record.document_id == document.id
    assert record.version_number == version["version_number"]
    assert record.sha256
    assert record.actor_user_id == engineer.id
    assert record.delivered_at is not None


def test_repeated_signing_keeps_delivery_record_idempotent(
    db_session, leader_client, engineer_client
):
    """断言 3：同一 version 重复签发 → 审计记录幂等不重复。"""
    engineer = engineer_client.user
    seeded = _seed_document(db_session, leader_client.user, engineer)
    project_id = seeded["project"].id
    document = seeded["document"]
    version = _confirmed_version(
        leader_client, engineer_client, project_id, document
    )

    for _ in range(3):
        response = engineer_client.get(
            f"/api/v1/projects/{project_id}/documents/{version['id']}/download-url"
        )
        assert response.status_code == 200

    count = db_session.scalar(
        select(func.count())
        .select_from(DocumentDeliveryRecord)
        .where(DocumentDeliveryRecord.version_id == version["id"])
    )
    assert count == 1, f"重复签发产生 {count} 条审计记录（应幂等为 1 条）"


def test_delivery_records_route_rejects_viewer(
    db_session, leader_client, engineer_client, authorized_client_factory
):
    """断言 1：项目成员中的低角色（fde_engineer）调用交付审计查询 → 403。

    注意：这里用的是**项目成员**（工程师），不是非成员——非成员会被
    project_access 挡在项目范围那一层，测不到角色门禁本身。
    """
    seeded = _seed_document(db_session, leader_client.user, engineer_client.user)
    project_id = seeded["project"].id

    response = engineer_client.get(
        f"/api/v1/projects/{project_id}/documents/delivery-records"
    )

    assert response.status_code == 403, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "forbidden"

    # 非成员（viewer，且不是项目成员）同样 403
    viewer_client = authorized_client_factory("viewer")
    viewer_response = viewer_client.get(
        f"/api/v1/projects/{project_id}/documents/delivery-records"
    )
    assert viewer_response.status_code == 403


def test_delivery_records_route_rejects_cross_project_access(
    db_session, leader_client, engineer_client
):
    """断言 2：跨项目访问 → 403/404，拿不到别的项目的交付记录。"""
    first = _seed_document(db_session, leader_client.user, engineer_client.user)
    # 第二个项目：_seed_document 的 enterprise_code 写死（唯一约束），这里手工建
    # 一个不同代号的空项目当作「别人的项目」。
    second = _other_project(db_session, leader_client.user)

    version = _confirmed_version(
        leader_client, engineer_client, first["project"].id, first["document"]
    )
    assert engineer_client.get(
        f"/api/v1/projects/{first['project'].id}/documents/{version['id']}/download-url"
    ).status_code == 200

    response = leader_client.get(
        f"/api/v1/projects/{second.id}/documents/delivery-records"
    )

    assert response.status_code in (403, 404)
    body = response.get_data(as_text=True)
    assert version["id"] not in body


def test_delivery_records_route_lists_project_records(
    db_session, leader_client, engineer_client
):
    """project_lead 可按项目查交付记录（本次交付事实可见）。"""
    engineer = engineer_client.user
    seeded = _seed_document(db_session, leader_client.user, engineer)
    project_id = seeded["project"].id
    version = _confirmed_version(
        leader_client, engineer_client, project_id, seeded["document"]
    )
    assert engineer_client.get(
        f"/api/v1/projects/{project_id}/documents/{version['id']}/download-url"
    ).status_code == 200

    response = leader_client.get(
        f"/api/v1/projects/{project_id}/documents/delivery-records"
    )

    assert response.status_code == 200
    items = response.json["data"]["items"]
    assert any(item["version_id"] == version["id"] for item in items)
    assert all("enterprise_name" not in item for item in items)
