"""用独立 PostgreSQL 事务验证跨项目累计预扣。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from queue import Queue
from time import monotonic, sleep

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch.models import DeliverySettlement
from fde_api.dispatch.settlements import accrue_settlements_for_project
from test_f_line_t6_tax_invoice_reconciliation import _allocate, _ctx, _payees_map


_ACCEPTED_AT = datetime(2026, 1, 15, tzinfo=timezone.utc)


def _ready(context, delivery_id, *, accepted_at=_ACCEPTED_AT):
    actor, package, row, payment, _ = context
    package.seat_delivery = row.seat_delivery_user_id = delivery_id
    payment.acceptance_passed_at = accepted_at
    row.created_at = accepted_at
    return actor.id, package.project_id, row.id


def _accrue(session, target):
    actor_id, project_id, _ = target
    actor = session.get(User, actor_id)
    assert accrue_settlements_for_project(session, actor=actor, project_id=project_id) == 1


def _start_accrual(engine, target, pid):
    with Session(engine) as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '15s'"))
        pid.put(session.scalar(text("SELECT pg_backend_pid()")))
        _accrue(session, target)


def _controlled_overlap(engine, first, second, *, commit=True):
    """首笔完成计提但暂不提交。第二笔必须等待首笔所在的真实 PG 后端。"""
    worker_pid = Queue()
    with Session(engine) as holder, ThreadPoolExecutor(max_workers=1) as executor:
        with holder.begin():
            holder_pid = holder.scalar(text("SELECT pg_backend_pid()"))
            _accrue(holder, first)
            worker = executor.submit(_start_accrual, engine, second, worker_pid)
            waiting_pid = worker_pid.get(timeout=10)
            with engine.connect() as observer:
                deadline = monotonic() + 5
                while monotonic() < deadline and not worker.done():
                    blockers = observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": waiting_pid}
                    )
                    if holder_pid in blockers:
                        break
                    sleep(0.01)
                else:
                    blockers = []
            if not commit:
                holder.rollback()
        worker.result(timeout=15)
    return holder_pid in blockers


def _taxes(session, *targets):
    session.expire_all()
    return [session.get(DeliverySettlement, target[2]).withholding_tax for target in targets]


@pytest.mark.parametrize("commit", [True, False])
def test_withholding_waits_for_other_project_then_reads_committed_tax(db_session, engine, commit):
    one = _ctx(db_session, received="100000", milestone="G3")
    two = _ctx(db_session, received="100000", milestone="G3")
    first = _ready(one, one[4]["delivery"])
    second = _ready(two, one[4]["delivery"])
    db_session.commit()

    blocked = _controlled_overlap(engine, first, second, commit=commit)
    # 每笔交付收入 40,000 元。首笔 810 元，两笔累计跨档后应预扣 3,380 元。
    assert _taxes(db_session, first, second) == (
        [Decimal("810"), Decimal("2570")] if commit else [Decimal("0"), Decimal("810")]
    )
    assert blocked, "第二项目未等待首笔事务结束"


def test_withholding_year_follows_acceptance_across_new_year(db_session, engine):
    one = _ctx(db_session, received="100000", milestone="G3")
    two = _ctx(db_session, received="100000", milestone="G3")
    three = _ctx(db_session, received="100000", milestone="G3")
    delivery = one[4]["delivery"]
    previous_year = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
    january = datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc)
    first = _ready(one, delivery, accepted_at=january)
    february = datetime(2026, 2, 1, 0, 1, tzinfo=timezone.utc)
    second = _ready(two, delivery, accepted_at=february)
    previous = _ready(three, delivery, accepted_at=previous_year)
    one[2].created_at = previous_year  # 上年建草稿，本年验收。
    db_session.commit()

    assert not _controlled_overlap(engine, previous, first)
    db_session.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
    _accrue(db_session, second)
    # 本年两笔跨月，累计税额 2,880 元，减去首笔 810 元。
    assert _taxes(db_session, previous, first, second) == [
        Decimal("810"), Decimal("810"), Decimal("2070"),
    ]


def test_withholding_serializes_other_personal_seats(db_session, engine):
    one = _ctx(db_session, received="100000", milestone="G3")
    two = _ctx(db_session, received="100000", milestone="G3")
    alice, bob = one[4]["delivery"], two[4]["delivery"]
    first = _ready(one, alice)
    second = _ready(two, bob)
    _allocate(db_session, one, _payees_map(one[4]["lead"], alice, bob, one[4]["province"]))
    _allocate(db_session, two, _payees_map(two[4]["lead"], bob, alice, two[4]["province"]))
    db_session.commit()

    blocked = _controlled_overlap(engine, first, second)
    # 第一笔市县席位给 Bob 增加 7,000 元，第二笔应按 42,000 元计税。
    assert _taxes(db_session, first, second) == [Decimal("690"), Decimal("858")]
    assert blocked, "第二项目应等待同年其他个人席位收入入账"
