"""Published B orders pick up existing receipts without rewriting settled amounts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from time import monotonic, sleep

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch.models import DeliveryPackage, DeliverySettlement, DispatchRuleVersion
from fde_api.dispatch.packages import publish_package
from fde_api.dispatch.settlements import record_receipt_settlements
from fde_api.projects.payment_service import PaymentServiceError, update_payment
from fde_api.workbench.models import Payment, Project
from test_dispatch_p0_r2 import _payment
from test_dispatch_p0_r3 import _authorized, _context


def _settlements(session, package_id):
    return list(session.scalars(select(DeliverySettlement).where(
        DeliverySettlement.package_id == package_id,
    ).execution_options(populate_existing=True)))


@pytest.mark.parametrize("locked", [False, True])
def test_publish_backfills_b_receipt_and_preserves_locked_snapshot(client, db_session, settings, locked):
    admin, _, project, _, _, package = _context(db_session, final_amount="20000")
    payment = _payment(db_session, project, "G4", "b", amount="9000")
    _payment(db_session, project, "G8", "b", received=False)
    assert record_receipt_settlements(db_session, actor=admin, project=project, payment=payment) == 0
    db_session.commit()
    api = _authorized(client, settings, admin)
    url = f"/api/v1/dispatch/packages/{package.id}"

    published = api.post(f"{url}/publish", json={})
    assert published.status_code == 200, published.json
    (row,) = _settlements(db_session, package.id)
    db_session.refresh(package)
    first_snapshot = package.snapshot_hash
    assert first_snapshot is not None
    assert (row.settlement_key, row.base_amount, row.snapshot_hash, row.status) == (
        "G4", Decimal("9000.00"), first_snapshot, "draft",
    )
    row_id = row.id
    if locked:
        row.status = "accrued"
    db_session.commit()

    assert api.post(f"{url}/withdraw", json={}).status_code == 200
    republished = api.post(f"{url}/publish", json={})
    if locked:
        assert republished.status_code == 409, republished.json
        assert republished.json["error"]["code"] == "allocation_mirror_protected"
        expected_snapshot = first_snapshot
    else:
        assert republished.status_code == 200, republished.json
        db_session.refresh(package)
        expected_snapshot = package.snapshot_hash
        assert expected_snapshot != first_snapshot
    (row,) = _settlements(db_session, package.id)
    assert (row.id, row.snapshot_hash, row.base_amount) == (row_id, expected_snapshot, Decimal("9000.00"))
    assert db_session.get(DeliveryPackage, package.id, populate_existing=True).snapshot_hash == expected_snapshot


def test_b_package_estimate_uses_five_seat_rule(client, db_session, settings):
    admin, _, project, _, _, package = _context(db_session, final_amount="20000")
    _payment(db_session, project, "G4", "b", received=False)
    version = db_session.scalar(select(DispatchRuleVersion).where(DispatchRuleVersion.status == "active"))
    assert version is not None and version.version_no == 100
    db_session.commit()

    response = _authorized(client, settings, admin).post(f"/api/v1/dispatch/packages/{package.id}/publish", json={})
    assert response.status_code == 200, response.json
    assert response.json["data"]["delivery_seat_amount"] == 7000


def test_receipt_amount_change_refuses_accrued_legacy_row(client, db_session, settings):
    admin, _, project, _, _, package = _context(db_session, final_amount="20000")
    _payment(db_session, project, "G4", "b", amount="9000")
    db_session.commit()
    _authorized(client, settings, admin).post(f"/api/v1/dispatch/packages/{package.id}/publish", json={})
    (row,) = _settlements(db_session, package.id)
    row.status = "accrued"  # 无五席明细的存量形态：计提后金额即锁定事实。
    db_session.commit()

    with pytest.raises(PaymentServiceError) as error:
        update_payment(actor=admin, project_id=project.id, milestone_key="G4", payload={
            "received_amount": 12000, "received_at": "2026-11-01",
        })
    assert error.value.code == "allocation_mirror_protected"
    db_session.rollback()
    (current,) = _settlements(db_session, package.id)
    assert (current.base_amount, current.status) == (Decimal("9000.00"), "accrued")


@pytest.mark.parametrize("publish_first", [False, True])
def test_publish_and_receipt_agree_across_transactions(app, db_session, engine, publish_first):
    admin, _, project, _, _, package = _context(db_session)
    payment = _payment(db_session, project, "G4", "b", received=False)
    admin_id, project_id, package_id, payment_id = admin.id, project.id, package.id, payment.id
    db_session.commit()

    def run_second():
        with app.app_context(), Session(engine) as session, session.begin():
            actor = session.get(User, admin_id)
            if publish_first:
                update_payment(actor=actor, project_id=project_id, milestone_key="G4", payload={
                    "received_amount": 9000, "received_at": "2026-10-31",
                })
            else:
                publish_package(session, actor=actor, package_id=package_id)

    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as first:
        with first.begin():
            actor = first.get(User, admin_id)
            if publish_first:
                publish_package(first, actor=actor, package_id=package_id)
            else:
                first.scalar(select(Project.id).where(Project.id == project_id).with_for_update(key_share=True))
                receipt = first.get(Payment, payment_id)
                receipt.received_at = date(2026, 10, 31)
                receipt.received_amount = Decimal("9000")
                assert record_receipt_settlements(
                    first, actor=actor, project=first.get(Project, project_id), payment=receipt,
                ) == 0
            holder_pid = first.scalar(text("SELECT pg_backend_pid()"))
            future = pool.submit(run_second)
            deadline = monotonic() + 8
            while monotonic() < deadline and not future.done():
                first.execute(text("SELECT pg_stat_clear_snapshot()"))
                if first.scalar(text("""
                    SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                                   WHERE :pid = ANY(pg_blocking_pids(pg_stat_activity.pid)))
                """), {"pid": holder_pid}):
                    break
                sleep(0.05)
            else:
                pytest.fail("第二个事务未等待项目或交付包锁")
        future.result(timeout=10)

    (row,) = _settlements(db_session, package_id)
    db_session.refresh(package)
    assert (row.base_amount, row.snapshot_hash, row.status) == (Decimal("9000"), package.snapshot_hash, "draft")
