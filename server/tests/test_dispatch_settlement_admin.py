"""Project-scoped administrator settlement API contracts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from conftest import INITIAL_PASSWORD
from fde_api.commercial.models import CommercialRevenueLedger, RegionalPartner
from fde_api.dispatch.models import DeliverySettlement, DispatchSettlementAllocation
from fde_api.dispatch.settlements import allocate_five_seats_with_lead_attribution, record_receipt_settlements
from fde_api.extensions import db
from fde_api.orgs.models import Org
from fde_api.workbench.models import OperationEvent, Payment, Project
from test_dispatch_p0_r2 import _authorized, _package, _payment, _project, _template, _user


@pytest.fixture
def settlement_case(client, db_session, settings):
    admin = _user("settlement-admin")
    lead = _user("settlement-lead", role="project_lead")
    payee = _user("settlement-payee", role="fde_engineer")
    db_session.add_all([admin, lead, payee])
    db_session.flush()
    db_session.add(RegionalPartner(
        partner_code="test-city-service", region_name="合成测试城市", stage="city_service",
        applicant_user_id=payee.id, stage_changed_at=datetime.now(timezone.utc),
    ))
    project = _project(db_session, _template(db_session), enterprise_code=f"test-{uuid4().hex}", leader=lead)
    package = _package(db_session, project, seat_delivery=payee.id, sow_type="b")
    payment = _payment(db_session, project, "G4", "b")
    record_receipt_settlements(db_session, actor=admin, project=project, payment=payment)
    db_session.commit()
    path = f"/api/v1/admin/dispatch/projects/{project.id}/settlements"
    return _authorized(client, settings, admin), _authorized(client, settings, lead), path, package, payee


def test_lists_project_settlements_for_admin_only(client, settlement_case):
    admin, lead, path, package, _ = settlement_case
    assert client.get(path).status_code == 401
    assert lead.get(path).status_code == 403
    response = admin.get(path)
    assert response.status_code == 200, response.json
    row, = response.json["data"]["settlements"]
    assert (row["package_id"], row["settlement_key"], row["status"], row["base_amount"]) == (
        package.id, "G4", "draft", "10000.00",
    )
    assert row["allocations"] == []


def _current_row(admin, path):
    response = admin.get(path)
    assert response.status_code == 200, response.json
    row, = response.json["data"]["settlements"]
    return row


def _allocation(payee_id, row):
    return {
        "confirm_password": INITIAL_PASSWORD,
        "expected_allocation_snapshot": row["allocation_snapshot"],
        "seat_payees": {"county": payee_id},
        "vacant_reasons": {"province": "no_province_partner"},
    }


def _mark_accrued(session, row_id, project_id):
    # 验收与收款并发顺序由 test_dispatch_p0_r2 及下方真实锁测试验证。
    row = session.get(DeliverySettlement, row_id)
    payment = session.scalar(select(Payment).where(
        Payment.project_id == project_id,
        Payment.milestone_key == row.settlement_key,
    ))
    now = datetime.now(timezone.utc)
    payment.acceptance_passed_at = row.acceptance_passed_at = now
    row.status = "accrued"
    session.commit()
    return payment


@pytest.mark.parametrize("action", ["allocate", "payable", "paid", "input-invoice"])
def test_writes_require_platform_admin_and_current_password(client, db_session, settlement_case, action):
    admin, lead, path, package, _ = settlement_case
    row = _current_row(admin, path)
    url = f"{path}/{row['id']}/{action}"
    assert client.post(url, json={}).status_code == 401
    assert lead.post(url, json={}).status_code == 403
    assert admin.post(url, json={}).status_code == 400
    wrong = admin.post(url, json={"confirm_password": "wrong-password"})
    assert (wrong.status_code, wrong.json["error"]["code"]) == (403, "invalid_password")

    # 原平台 JWT 的 org claim 为 null，后续身份以数据库为准。
    org = Org(name="test-settlement-tenant", org_type="enterprise")
    db_session.add(org)
    db_session.flush()
    admin.user.org_id = org.id
    db_session.commit()
    assert admin.get(path).status_code == 403
    poisoned = admin.post(url, json={"confirm_password": INITIAL_PASSWORD})
    assert (poisoned.status_code, poisoned.json["error"]["code"]) == (403, "forbidden")
    assert db_session.get(DeliverySettlement, row["id"]).status == "draft"
    assert not list(db_session.scalars(select(OperationEvent).where(
        OperationEvent.target_id == package.id,
        OperationEvent.event_type.in_(("five_seat_allocations_recorded", "settlement_payable", "settlement_paid")),
    )))


@pytest.mark.parametrize(("value", "status", "code"), [
    ({}, 428, "allocation_snapshot_required"),
    ({"expected_allocation_snapshot": None}, 400, "invalid_allocation_snapshot"),
    ({"expected_allocation_snapshot": "short"}, 400, "invalid_allocation_snapshot"),
])
def test_allocation_requires_a_valid_confirmation_snapshot(settlement_case, value, status, code):
    admin, _, path, _, payee = settlement_case
    row = _current_row(admin, path)
    payload = _allocation(payee.id, row)
    del payload["expected_allocation_snapshot"]
    response = admin.post(f"{path}/{row['id']}/allocate", json={**payload, **value})
    assert (response.status_code, response.json["error"]["code"]) == (status, code)
    assert _current_row(admin, path) == row


def test_allocation_snapshot_binds_delivery_assignee(db_session, settlement_case):
    admin, lead, path, package, payee = settlement_case
    row = _current_row(admin, path)
    package.seat_delivery = lead.user.id
    db_session.commit()
    response = admin.post(f"{path}/{row['id']}/allocate", json=_allocation(payee.id, row))
    assert (response.status_code, response.json["error"]["code"]) == (409, "allocation_snapshot_conflict")
    current = _current_row(admin, path)
    assert current["base_amount"] == row["base_amount"]
    assert current["delivery_user_id"] == lead.user.id
    assert current["allocations"] == []


def test_allocates_from_linked_receipt_then_records_payment(db_session, settlement_case):
    admin, _, path, package, payee = settlement_case
    shown = _current_row(admin, path)
    row_id = shown["id"]
    url = f"{path}/{row_id}"
    payload = _allocation(payee.id, shown)
    org = Org(name="test-settlement-customer", org_type="enterprise")
    db_session.add(org)
    db_session.flush()
    db_session.get(Project, package.project_id).org_id = org.id
    db_session.commit()

    response = admin.post(f"{url}/allocate", json=payload)
    assert response.status_code == 200, response.json
    row = _current_row(admin, path)
    assert row["status"] == "draft"
    assert row["version_no"] == 100
    assert {item["seat_key"]: (item["amount"], item["reason_code"]) for item in row["allocations"]} == {
        "platform": ("5800.00", None), "lead": ("0.00", "no_sourcer"), "delivery": ("3500.00", None),
        "county": ("700.00", None), "province": ("0.00", "no_province_partner"),
    }
    payment = _mark_accrued(db_session, row_id, package.project_id)
    auth = {"confirm_password": INITIAL_PASSWORD}
    assert admin.post(f"{url}/allocate", json=payload).status_code == 409
    incomplete_invoice = admin.post(f"{url}/payable", json=auth)
    assert (incomplete_invoice.status_code, incomplete_invoice.json["error"]["code"]) == (422, "invoice_required")
    payment.invoice_no = "INV-SYNTHETIC"
    db_session.commit()
    response = admin.post(f"{url}/payable", json=auth)
    assert response.status_code == 200, response.json
    assert response.json["data"]["status"] == "payable"
    response = admin.post(f"{url}/paid", json={**auth, "paid_proof_source_uri": "data:application/pdf;base64,SGVsbG8="})
    assert response.status_code == 400
    paid = {**auth, "paid_proof_source_uri": "fdeops://m1-test/payment-receipt"}
    response = admin.post(f"{url}/paid", json=paid)
    assert response.status_code == 200, response.json
    assert response.json["data"]["status"] == "paid"
    assert admin.post(f"{url}/paid", json=paid).status_code == 409
    db_session.expire_all()
    assert db_session.get(DeliverySettlement, row_id).paid_proof_source_uri == paid["paid_proof_source_uri"]
    cross_org = list(db_session.scalars(select(OperationEvent).where(
        OperationEvent.target_id == package.id,
        OperationEvent.event_type == "cross_org_dispatch_settlement_bookkeeping",
    )))
    assert {event.changes["action"] for event in cross_org} == {"allocate", "payable", "paid"}
    assert all(event.org_id == org.id and "confirm_password" not in event.changes for event in cross_org)


@pytest.mark.parametrize("details", ["missing", "partial", "no_version", "different_versions"])
def test_pilot_payable_requires_complete_common_version(db_session, settlement_case, details):
    admin, _, path, package, payee = settlement_case
    row_id = _current_row(admin, path)["id"]
    url = f"{path}/{row_id}"
    if details != "missing":
        assert admin.post(f"{url}/allocate", json=_allocation(payee.id, _current_row(admin, path))).status_code == 200
        detail = db_session.scalar(select(DispatchSettlementAllocation).where(
            DispatchSettlementAllocation.settlement_id == row_id,
            DispatchSettlementAllocation.seat_key == "province",
        ))
        if details == "partial":
            db_session.delete(detail)
        elif details == "no_version":
            for allocation in db_session.scalars(select(DispatchSettlementAllocation).where(
                DispatchSettlementAllocation.settlement_id == row_id,
            )):
                allocation.rule_version_id = None
        else:
            detail.rule_version_id = None
    payment = _mark_accrued(db_session, row_id, package.project_id)
    payment.invoice_no = "INV-SYNTHETIC"
    db_session.commit()
    response = admin.post(f"{url}/payable", json={"confirm_password": INITIAL_PASSWORD})
    assert (response.status_code, response.json["error"]["code"]) == (409, "versioned_allocation_required")
    assert _current_row(admin, path)["status"] == "accrued"


def test_rejects_wrong_project_and_mismatched_receipt(db_session, settlement_case):
    admin, lead, path, package, payee = settlement_case
    shown = _current_row(admin, path)
    row_id = shown["id"]
    other = _project(db_session, _template(db_session), enterprise_code=f"other-{uuid4().hex}", leader=lead.user)
    other_receipt = _payment(db_session, other, "G4", "b")
    own_receipt = db_session.scalar(select(Payment).where(Payment.project_id == package.project_id))
    own_receipt.received_amount = other_receipt.received_amount + 1
    db_session.commit()
    payload = _allocation(payee.id, shown)
    wrong = admin.post(f"{path.replace(package.project_id, other.id)}/{row_id}/allocate", json=payload)
    assert (wrong.status_code, wrong.json["error"]["code"]) == (404, "settlement_not_found")
    mismatch = admin.post(f"{path}/{row_id}/allocate", json=payload)
    assert (mismatch.status_code, mismatch.json["error"]["code"]) == (409, "settlement_receipt_conflict")
    assert _current_row(admin, path)["allocations"] == []


def test_regional_seats_honor_city_service_and_province_rollout(settlement_case):
    admin, lead, path, _, payee = settlement_case
    row = _current_row(admin, path)
    url = f"{path}/{row['id']}/allocate"
    invalid_city = admin.post(url, json=_allocation(lead.user.id, row))
    assert (invalid_city.status_code, invalid_city.json["error"]["code"]) == (422, "city_service_required")
    blocked_province = admin.post(url, json={
        **_allocation(payee.id, row),
        "seat_payees": {"county": payee.id, "province": payee.id},
        "vacant_reasons": {},
    })
    assert (blocked_province.status_code, blocked_province.json["error"]["code"]) == (409, "regional_agent_not_enabled")
    assert _current_row(admin, path)["allocations"] == []


def test_allocating_already_accepted_receipt_accrues_only_selected_settlement(db_session, settlement_case):
    admin, _, path, package, payee = settlement_case
    row_id = _current_row(admin, path)["id"]
    payment = db_session.scalar(select(Payment).where(Payment.project_id == package.project_id))
    payment.acceptance_passed_at = datetime.now(timezone.utc)
    project = db_session.get(Project, package.project_id)
    other_payment = _payment(db_session, project, "G8", "b")
    other_payment.acceptance_passed_at = payment.acceptance_passed_at
    record_receipt_settlements(db_session, actor=admin.user, project=project, payment=other_payment)
    db_session.commit()
    response = admin.get(path)
    assert response.status_code == 200, response.json
    shown = next(row for row in response.json["data"]["settlements"] if row["id"] == row_id)
    result = admin.post(f"{path}/{row_id}/allocate", json=_allocation(payee.id, shown))
    assert result.status_code == 200, result.json
    assert result.json["data"]["status"] == "accrued"
    rows = admin.get(path).json["data"]["settlements"]
    assert {r["settlement_key"]: r["status"] for r in rows} == {"G4": "accrued", "G8": "draft"}


def test_existing_province_allocation_requires_idempotent_invoice_record(db_session, settlement_case):
    admin, _, path, package, payee = settlement_case
    row_id = _current_row(admin, path)["id"]
    url = f"{path}/{row_id}"
    payment = db_session.scalar(select(Payment).where(Payment.project_id == package.project_id))
    # 合成存量，模拟早期内部原语已经写入非空省级席。新管理面不允许产生这类数据。
    allocate_five_seats_with_lead_attribution(
        db_session, payment, package, actor=admin.user,
        seat_payees={"delivery": payee.id, "county": payee.id, "province": payee.id},
    )
    payment = _mark_accrued(db_session, row_id, package.project_id)
    payment.invoice_no = "SYNTHETIC-OUT"
    db_session.commit()
    confirm = {"confirm_password": INITIAL_PASSWORD}
    assert _current_row(admin, path)["input_invoice_required"] is True
    assert _current_row(admin, path)["input_invoice_recorded"] is False
    denied = admin.post(f"{url}/payable", json=confirm)
    assert (denied.status_code, denied.json["error"]["code"]) == (422, "input_invoice_required")
    invoice = {**confirm, "source_uri": "fdeops://m1-test/invoice", "content_hash": "a" * 64}
    assert admin.post(f"{url}/input-invoice", json={**invoice, "content_hash": "invalid"}).status_code == 400
    recorded = admin.post(f"{url}/input-invoice", json=invoice)
    assert recorded.status_code == 200, recorded.json
    assert recorded.json["data"]["changed"] is True
    duplicate = admin.post(f"{url}/input-invoice", json={**invoice, "content_hash": "A" * 64})
    assert duplicate.status_code == 200
    assert duplicate.json["data"] == {"changed": False, "entry_id": recorded.json["data"]["entry_id"]}
    assert admin.post(f"{url}/input-invoice", json={**invoice, "content_hash": "b" * 64}).status_code == 409
    entries = list(db_session.scalars(select(CommercialRevenueLedger).where(
        CommercialRevenueLedger.delivery_settlement_id == row_id,
    )))
    entry, = entries
    assert (entry.payee_user_id, entry.payment_id, entry.delivery_package_id) == (payee.id, payment.id, package.id)
    assert str(entry.amount) == "4900.00"
    assert _current_row(admin, path)["input_invoice_recorded"] is True
    assert admin.post(f"{url}/payable", json=confirm).status_code == 200


def test_allocation_rechecks_amount_after_waiting_on_project_lock(app, db_session, settlement_case):
    admin, _, path, package, payee = settlement_case
    shown = _current_row(admin, path)
    row_id = shown["id"]
    url = f"{path}/{row_id}/allocate"
    payload = _allocation(payee.id, shown)
    event_query = select(OperationEvent.id).where(OperationEvent.target_id == package.id)
    prior_events = set(db_session.scalars(event_query))

    def allocate():
        worker = app.test_client()
        return worker.post(url, json=payload, headers=admin.headers)

    with ThreadPoolExecutor(max_workers=1) as pool, db.engine.connect() as conn, conn.begin():
        pid = conn.scalar(text("SELECT pg_backend_pid()"))
        conn.execute(select(Project.id).where(Project.id == package.project_id).with_for_update())
        future = pool.submit(allocate)
        end = monotonic() + 10
        while monotonic() < end:
            conn.execute(text("SELECT pg_stat_clear_snapshot()"))
            blocked = conn.scalar(text("""
                SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                               WHERE :pid = ANY(pg_blocking_pids(pg_stat_activity.pid)))
            """), {"pid": pid})
            if blocked:
                break
            sleep(0.05)
        else:
            pytest.fail("分配请求未等待项目行锁")
        # 若分配方先锁了结算行，再来等项目，NOWAIT 会立即失败。
        conn.execute(select(DeliverySettlement.id).where(DeliverySettlement.id == row_id).with_for_update(nowait=True))
        conn.execute(Payment.__table__.update().where(Payment.project_id == package.project_id).values(received_amount=12000))
        conn.execute(DeliverySettlement.__table__.update().where(DeliverySettlement.id == row_id).values(base_amount=12000))
    response = future.result(timeout=10)
    assert (response.status_code, response.json.get("error", {}).get("code")) == (409, "allocation_snapshot_conflict")
    current = _current_row(admin, path)
    assert current["base_amount"] == "12000.00"
    assert current["allocations"] == []
    assert set(db_session.scalars(event_query)) == prior_events
    assert current["allocation_snapshot"] != shown["allocation_snapshot"]

    response = admin.post(url, json={**payload, "expected_allocation_snapshot": current["allocation_snapshot"]})
    assert response.status_code == 200, response.json
    by_seat = {item["seat_key"]: item["amount"] for item in _current_row(admin, path)["allocations"]}
    assert by_seat["delivery"] == "4200.00"
