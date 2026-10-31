"""撮合仿真器（goal-r9）：回放只读性、漏斗/指标数学、同种子可复现、参数封闭。

前置：module_catalog 由 conftest seed_reference_data 灌入（含 pre_diagnosis）。
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import delete, select

from fde_api.dispatch.models import (
    DeliveryPackage,
    DispatchOffer,
    DispatchRuleVersion,
    FdeProfile,
)
from fde_api.dispatch.simulator import DEFAULT_ASSUMPTIONS, replay_scoring, run_simulation
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    ModuleCatalog,
    OperationEvent,
    Project,
    ProjectModule,
    Quote,
)
from fde_api.solutions.models import ProjectSolution
from fde_api.auth.models import User

from conftest import SERVER_ROOT

_SIM_TABLES = (
    OperationEvent,
    DispatchOffer,
    DeliveryPackage,
    FdeProfile,
    DispatchRuleVersion,
    ProjectModule,
    Quote,
    ProjectSolution,
    Project,
    IndustryTemplateVersion,
    IndustryTemplate,
    User,
)
# 注意：module_catalog 不进清表集合——module_catalog fixture 灌的引用种子
# 要跨两次 run_simulation 存活（确定性用例）。


@pytest.fixture
def module_catalog(db_session):
    """每用例清表会连带清 module_catalog——仿真前重灌引用种子（同 conftest）。"""
    if str(SERVER_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVER_ROOT))
    from load_seeds import _upsert_module_catalog

    _upsert_module_catalog(db_session)
    db_session.commit()
    return db_session.scalar(
        select(ModuleCatalog)
        .where(ModuleCatalog.is_active.is_(True))
        .order_by(ModuleCatalog.sort_order)
        .limit(1)
    )


def _wipe_sim_tables(db_session) -> None:
    for model in _SIM_TABLES:
        db_session.execute(delete(model))
    db_session.commit()


def test_simulation_rejects_unknown_params(db_session):
    with pytest.raises(ValueError) as err:
        run_simulation(db_session, scenarios=1, params={"nope": 1})
    assert "nope" in str(err.value)


def test_run_simulation_funnel_and_metric_math(db_session, module_catalog):
    """漏斗守恒 + 指标数学自洽（H2 分母=已交付；H3=工时占比/毛利）。"""
    report = run_simulation(db_session, scenarios=12, seed=42)
    funnel = report["funnel"]
    assert funnel["demands"] == 12
    assert (
        funnel["engine_accepted"] + funnel["scenario_c_manual"] + funnel["unfilled"]
        == 12
    )
    h2 = report["h2"]
    if h2["delivered_count"]:
        expected = round(h2["first_pass_count"] / h2["delivered_count"], 4)
        assert h2["g9_first_pass_rate"] == expected
    assert isinstance(h2["gate_pass"], bool)
    assert h2["random_assignment_baseline"] is not None
    h3 = report["h3"]
    total = h3["total_hours_total"]
    if total:
        assert h3["platform_hours_share"] == round(h3["platform_hours_total"] / total, 4)
    assert isinstance(h3["gate_pass"], bool)
    # 诚实纪律：假设表全量回显、口径标注 simulation
    assert report["assumptions"] == DEFAULT_ASSUMPTIONS
    assert "simulation" in report["meta"]["discipline"]
    # 全部需求都挂在派单线项目上（P2-4 H3 语义）
    lines = db_session.scalars(
        select(Project.business_line).where(Project.project_code.like("SIM-%"))
    ).all()
    assert lines and set(lines) == {"FDE_DISPATCH"}


def test_replay_scoring_is_readonly(db_session, module_catalog):
    """回放前后 offer 数不变、包状态不变（只读回放的判定证据）。"""
    run_simulation(db_session, scenarios=6, seed=7)
    offers_before = len(db_session.scalars(select(DispatchOffer)).all())
    statuses_before = sorted(
        db_session.scalars(select(DeliveryPackage.dispatch_status)).all()
    )
    replay = replay_scoring(db_session)
    offers_after = len(db_session.scalars(select(DispatchOffer)).all())
    statuses_after = sorted(
        db_session.scalars(select(DeliveryPackage.dispatch_status)).all()
    )
    assert offers_after == offers_before
    assert statuses_after == statuses_before
    assert replay["summary"]["replayed"] == 6
    assert replay["mode"] == "replay"
    assert set(replay["summary"]["scenario_counts"]) == {"A", "B", "C"}
    for row in replay["packages"]:
        assert row["package_code"].startswith("PKG-")


def test_run_simulation_deterministic(db_session, module_catalog):
    """同种子两次运行（中间清表）报告逐字段一致。"""
    first = run_simulation(db_session, scenarios=8, seed=99)
    _wipe_sim_tables(db_session)
    second = run_simulation(db_session, scenarios=8, seed=99)
    assert first == second
