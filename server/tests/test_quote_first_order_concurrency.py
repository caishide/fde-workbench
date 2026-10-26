"""WP05/B3：首单并发闸门回归钉。

首单身份靠「当前没有任何 finalized 报价」判定。判定与随后的写入之间若没有
锁，两个并发事务能同时读到 finalized_count=0，双双按「首单」放行——首单的
「必须回校」义务与三条硬约束就都被绕过去了。

本测试用真实 PostgreSQL 并发（两个独立连接、真实事务、真 advisory lock），
不以顺序调用代替：

1. 对照组：只有一张违反首单硬约束③（realistic > 120 h）的报价时，finalize
   必须按「首单」被拒（409 first_order_constraint）——证明约束本身有效且可观测。
2. 并发组：一个并发事务持有同一把 advisory lock 并随后提交一张 finalized
   报价；本事务的 finalize 必须被锁阻塞，待锁释放后读到 finalized_count=1，
   于是按非首单口径放行（allowance 用 anchor_mode 的 40%，而不是首单的 50%）。
   没有锁时它会读到 0 → 被判首单 → 409。
3. 无死锁：两个事务都正常结束，无重复副作用（finalized 报价数正确）。
"""
import threading
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.projects.quote_service import QuoteServiceError, finalize_quote
from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion, Project, Quote


LOCK_KEY = "fde_quote_first_order"


def _seed_project(session: Session) -> tuple[Project, User]:
    leader = User(
        username=f"quote.lead.{uuid4().hex[:8]}",
        display_name="报价负责人",
        role="admin",
        password_hash=hash_password("InitialPass!234"),
        must_change_password=False,
        is_active=True,
    )
    session.add(leader)
    session.flush()
    template = IndustryTemplate(name="报价模板", industry_name="制造")
    version = IndustryTemplateVersion(
        template=template,
        name=template.name,
        industry_name=template.industry_name,
        description="",
        version_number=1,
        status="published",
        published_by=leader,
    )
    session.add_all([template, version])
    session.flush()
    project = Project(
        project_code=f"QTE-{uuid4().hex[:8]}",
        name="报价并发项目",
        enterprise_code=f"报价企业·制造·{uuid4().hex[:8]}",
        leader=leader,
        source_template_version=version,
        template_snapshot={},
        research_snapshot={},
        planned_start_date=date(2026, 8, 22),
    )
    session.add(project)
    session.commit()
    return project, leader


def _make_quote(
    session: Session,
    project: Project,
    leader: User,
    *,
    hours: str,
    anchor_mode: str = "steady",
) -> Quote:
    """建一张待成交回填的报价（actual_hours 已回校，绕开「首单必须先回校」）。

    直接构造 ORM 行：报价公式的分支/锚点约束与本用例无关，本用例只关心
    「首单判定」这一段。
    """
    quote = Quote(
        project_id=project.id,
        quote_key=f"Q-{uuid4().hex[:6]}",
        status="draft",
        tier="light",
        ideal_hours=Decimal(hours),
        realistic_hours=Decimal(hours),
        actual_hours=Decimal(hours),
        integration_factor=Decimal("1.00"),
        data_factor=Decimal("1.00"),
        compliance_factor=Decimal("1.00"),
        buffer_factor=Decimal("1.00"),
        hourly_rate=150,
        cash_cost=100000,
        margin_factor=Decimal("0.25"),
        b_layer_score=0,
        b_layer_factor=Decimal("1.00"),
        anchor_mode=anchor_mode,
        labor_cost=Decimal("100000"),
        total_cost=Decimal("100000"),
        formula_price=Decimal("200000"),
        anchor_low=200000,
        anchor_high=300000,
        branch="A",
    )
    session.add(quote)
    session.commit()
    return quote


def _finalize(url: str, project_id: str, quote_key: str, actor_id: str):
    """在独立连接里跑一次 finalize，返回 (状态, 载荷)。"""
    from fde_api.app import create_app
    from fde_api.config import Settings
    from fde_api.extensions import db

    app = create_app(Settings(database_url=url, env="test"))
    with app.app_context():
        session = db.session()
        try:
            with session.begin():
                actor = session.get(User, actor_id)
                try:
                    data = finalize_quote(
                        actor=actor,
                        project_id=project_id,
                        quote_key=quote_key,
                        payload={"final_amount": "250000"},
                    )
                    return ("ok", data)
                except QuoteServiceError as error:
                    return ("error", error.code)
        finally:
            session.close()


def test_first_order_constraint_applies_when_no_finalized_quote_exists(
    db_session, test_settings
):
    """对照组：首单硬约束③必须真实拦截（否则并发测试无意义）。"""
    project, leader = _seed_project(db_session)
    violating = _make_quote(db_session, project, leader, hours="150")

    status, payload = _finalize(
        test_settings.database_url, project.id, violating.quote_key, leader.id
    )
    assert status == "error"
    assert payload == "first_order_constraint"

    db_session.refresh(violating)
    assert violating.status == "draft"
    assert violating.final_amount is None


def test_concurrent_finalize_waits_for_first_order_lock_and_then_passes(
    db_session, test_settings
):
    """并发组：并发事务持锁时 finalize 被阻塞；锁释放后按非首单口径放行。"""
    url = test_settings.database_url
    project, leader = _seed_project(db_session)
    # steady 锚点：若被判首单，allowance 取冷启动 50%；非首单取 40%。
    violating = _make_quote(db_session, project, leader, hours="150", anchor_mode="steady")

    holder_ready = threading.Event()
    holder_done = threading.Event()
    holder_error: list[BaseException] = []

    def holder() -> None:
        """模拟并发的首单事务：持同一把 advisory lock，插入一张 finalized 报价后提交。"""
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(f"SELECT pg_advisory_xact_lock(hashtext('{LOCK_KEY}'))")
                )
                holder_ready.set()
                # 给主线程留出「finalize 必然被锁阻塞」的观察窗口
                if not holder_done.wait(timeout=15):
                    raise AssertionError("holder was not released in time")
                connection.execute(
                    text(
                        "INSERT INTO quotes (id, project_id, quote_key, tier, status, "
                        "ideal_hours, integration_factor, data_factor, "
                        "compliance_factor, buffer_factor, hourly_rate, cash_cost, "
                        "margin_factor, b_layer_score, b_layer_factor, anchor_mode, "
                        "realistic_hours, labor_cost, total_cost, formula_price, "
                        "anchor_low, anchor_high, branch, ticket_note, deviation_reason, "
                        "field_claims, version) "
                        "VALUES (:id, :project_id, 'Q-CONCURRENT', 'light', 'finalized', "
                        "40, 1.00, 1.00, 1.00, 1.00, 150, 100000, 0.25, 0, 1.00, "
                        "'cold_start', 40, 100000, 100000, 200000, 200000, 300000, "
                        "'A', '', '', '{}'::json, 1)"
                    ),
                    {"id": str(uuid4()), "project_id": project.id},
                )
        except BaseException as exc:  # noqa: BLE001 - 交由主线程断言
            holder_error.append(exc)
        finally:
            engine.dispose()
            holder_done.set()

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert holder_ready.wait(timeout=15), "holder did not acquire the advisory lock"

    outcome: list[tuple[str, object]] = []

    def worker() -> None:
        outcome.append(
            _finalize(url, project.id, violating.quote_key, leader.id)
        )

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    # 并发证明：finalize 必须被 advisory lock 阻塞（尚未完成）
    worker_thread.join(timeout=3)
    assert worker_thread.is_alive(), (
        "finalize did not block on the first-order advisory lock — the TOCTOU window is open"
    )

    holder_done.set()
    worker_thread.join(timeout=30)
    thread.join(timeout=30)

    assert not holder_error, holder_error
    assert outcome, "finalize did not return"
    status, payload = outcome[0]
    assert status == "ok", payload

    # 关键判据：它按非首单口径放行——allowance 用 anchor_mode 的 40%，
    # 而不是首单的冷启动 50%。若读不到并发事务提交的 finalized 行，
    # 就会被判首单并被硬约束③拒绝。
    db_session.expire_all()
    refreshed = db_session.get(Quote, violating.id)
    assert refreshed.status == "finalized"
    # (250000 − 100000) × 40% = 60000
    assert refreshed.allowance_cap == Decimal("60000.00")


def test_no_deadlock_and_single_finalized_effect_under_concurrency(
    db_session, test_settings
):
    """无死锁/无重复副作用：并发两笔成交回填后，finalized 报价数与事件一致。"""
    url = test_settings.database_url
    project, leader = _seed_project(db_session)
    first = _make_quote(db_session, project, leader, hours="40", anchor_mode="cold_start")
    second = _make_quote(db_session, project, leader, hours="40", anchor_mode="cold_start")

    barrier = threading.Barrier(2, timeout=20)
    outcome: list[tuple[str, object]] = []
    errors: list[BaseException] = []

    def worker(quote_key: str) -> None:
        try:
            barrier.wait(timeout=20)
            outcome.append(_finalize(url, project.id, quote_key, leader.id))
        except BaseException as exc:  # noqa: BLE001 - 汇总到主线程断言
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(first.quote_key,)),
        threading.Thread(target=worker, args=(second.quote_key,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=40)

    assert not errors, errors
    assert len(outcome) == 2, outcome
    # 两笔都能成交（第二笔按非首单口径），且都不应崩溃
    assert all(status in {"ok", "error"} for status, _ in outcome), outcome

    with create_engine(url).connect() as connection:
        finalized = connection.execute(
            text("SELECT count(*) FROM quotes WHERE status = 'finalized'")
        ).scalar_one()
    assert finalized == 2, finalized
