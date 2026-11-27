"""B2 随包走的交付工位（FDU 对照 B2；评审 Wildcard 席②「存公式不存指针」）。

件 4 载体 ``workbench_manifest`` 的装配公式四键钉：
- sop_node_keys：sop_nodes.segment ∈ (交付段, 交付后段) − 包前段 {S3, S4}
  （16 键种子由 conftest 迁移后灌入 ⇒ 闭集断言 S5–S13 九键）；
- industry_template_refs：industry_name == required_industry ∧ status=active；
- eval_suite_refs：套件 scenario_ids_json 与该行业场景集有交集（两跳）；
- hq_card_keys：恒空（四卡 pending_owner_approval 不装配，M2 拍板）。
漂移语义＝真身现算：同一公式对同一库态确定性重建，真身漂移输出即变
（换手重建与发布冻结 hash 失配当场炸出来）。读面＝白名单对表扩项
``workbench_manifest``（routes._whitelist_payload 单点现算传入）。
"""

from __future__ import annotations

from uuid import uuid4

from fde_api.dispatch.access import serialize_package_whitelist
from fde_api.dispatch.packages import _snapshot_payload, _workbench_manifest
from fde_api.dispatch.routes import _whitelist_payload
from fde_api.simulation.models import RegressionSuite, SimulationScenario
from fde_api.workbench.models import IndustryTemplate, SopNode

from test_dispatch_p0_r3 import _context

# 种子灌入的（交付段 ∪ 交付后段）− 包前段 {S3, S4}＝S5–S13 九键；
# sorted 字典序：同前缀 S1x 数字段先于个位段。
_EXPECTED_SOP_KEYS = ["S10", "S11", "S12", "S13", "S5", "S6", "S7", "S8", "S9"]


def _industry_template(db_session, *, key: str, industry: str, status: str = "active"):
    row = IndustryTemplate(
        template_key=key, name=f"B2 {key}", industry_name=industry, status=status
    )
    db_session.add(row)
    return row


def _scenario(db_session, *, key: str, industry: str):
    row = SimulationScenario(
        scenario_key=key, name=f"B2 场景 {key}", industry=industry
    )
    db_session.add(row)
    return row


def test_manifest_sop_keys_seed_closed_set(db_session):
    """公式①：种子 16 键下交付工位＝S5–S13 九键（S3/S4 包前段排除、横切线排除）。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    manifest = _workbench_manifest(db_session, package)
    assert manifest["sop_node_keys"] == _EXPECTED_SOP_KEYS


def test_manifest_sop_formula_is_segment_driven(db_session):
    """公式①活性：不手抄键清单——新交付段节点自动入列，横切线永不入列。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    probe = f"S9X{uuid4().hex[:4]}"
    # A4 纪律：sop_nodes 每条带出处指针（source_uri NOT NULL）——探测行同款。
    db_session.add(
        SopNode(
            node_key=probe,
            name="B2 探测节点",
            segment="交付段",
            source_uri="test://b2-manifest/probe",
            content_hash="a" * 64,
        )
    )
    db_session.add(
        SopNode(
            node_key=f"S9Y{uuid4().hex[:4]}",
            name="B2 横切探测",
            segment="横切线",
            source_uri="test://b2-manifest/probe-cross",
            content_hash="b" * 64,
        )
    )
    db_session.flush()
    keys = _workbench_manifest(db_session, package)["sop_node_keys"]
    assert probe in keys
    assert keys == sorted(_EXPECTED_SOP_KEYS + [probe])


def test_manifest_industry_templates_active_only(db_session):
    """公式②：行业模板只取 required_industry 的 active 行（template_key 排序）。

    注：_context 自种一行 r3-tpl-*（制造业 active）——公式应把它一并入列，
    期望按性质断言（inactive/异行业排除＋排序），不依赖 _context 内部细节。
    """
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    active_a = _industry_template(db_session, key=f"b2-a-{uuid4().hex[:6]}", industry="制造业")
    active_b = _industry_template(db_session, key=f"b2-b-{uuid4().hex[:6]}", industry="制造业")
    _industry_template(
        db_session, key=f"b2-i-{uuid4().hex[:6]}", industry="制造业", status="inactive"
    )
    _industry_template(db_session, key=f"b2-o-{uuid4().hex[:6]}", industry="外贸出口")
    db_session.flush()
    refs = _workbench_manifest(db_session, package)["industry_template_refs"]
    assert refs == sorted(refs)
    assert active_a.template_key in refs
    assert active_b.template_key in refs
    assert not any(key.startswith("b2-i-") for key in refs)
    assert not any(key.startswith("b2-o-") for key in refs)


def test_manifest_eval_suites_two_hop(db_session):
    """公式③：套件经 scenario_ids_json 两跳挂到行业场景集——命中/异行业不命中/混合命中。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    mfg = _scenario(db_session, key=f"B2-MFG-{uuid4().hex[:4]}", industry="制造业")
    other = _scenario(db_session, key=f"B2-OTH-{uuid4().hex[:4]}", industry="外贸出口")
    db_session.flush()
    db_session.add_all(
        [
            RegressionSuite(
                name=f"b2-hit-{uuid4().hex[:6]}",
                scenario_ids_json=[mfg.id],
            ),
            RegressionSuite(
                name=f"b2-miss-{uuid4().hex[:6]}",
                scenario_ids_json=[other.id],
            ),
            RegressionSuite(
                name=f"b2-mixed-{uuid4().hex[:6]}",
                scenario_ids_json=[other.id, mfg.id],
            ),
        ]
    )
    db_session.flush()
    manifest = _workbench_manifest(db_session, package)
    refs = manifest["eval_suite_refs"]
    assert len(refs) == 2
    assert all(name.startswith(("b2-hit-", "b2-mixed-")) for name in refs)
    assert refs == sorted(refs)


def test_manifest_industry_none_yields_empty_refs(db_session):
    """公式②③：required_industry 缺失 ⇒ 模板/评测集两键空，SOP 段键不受影响。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    package.required_industry = None
    db_session.flush()
    manifest = _workbench_manifest(db_session, package)
    assert manifest["industry_template_refs"] == []
    assert manifest["eval_suite_refs"] == []
    assert manifest["sop_node_keys"] == _EXPECTED_SOP_KEYS


def test_manifest_hq_cards_pending_not_assembled(db_session):
    """公式④：岗位卡恒空——四卡 pending_owner_approval 不装配（M2 拍板）。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    assert _workbench_manifest(db_session, package)["hq_card_keys"] == []


def test_manifest_deterministic_and_modules_sorted(db_session):
    """同一库态确定性重建；行上乱序 required_modules 出清单必排序。"""
    _admin, _fde, _project, _solution, _quote, package = _context(db_session)
    package.required_modules = ["m2", "m1", "m3"]
    db_session.flush()
    first = _workbench_manifest(db_session, package)
    second = _workbench_manifest(db_session, package)
    assert first == second
    assert first["required_modules"] == ["m1", "m2", "m3"]


def test_snapshot_payload_covers_manifest(db_session):
    """hash 覆盖证明：payload 的 workbench_manifest 与公式输出同源——
    真身漂移改变 payload ⇒ 冻结 hash 失配（漂移可见性的机制链）。"""
    _admin, _fde, _project, solution, quote, package = _context(db_session)
    from datetime import datetime, timezone

    payload = _snapshot_payload(
        db_session,
        package,
        solution,
        _project,
        quote,
        published_at=datetime.now(timezone.utc),
    )
    assert payload["workbench_manifest"] == _workbench_manifest(db_session, package)


def test_whitelist_includes_workbench_manifest(db_session):
    """读面对表扩项：白名单带 workbench_manifest 且与公式输出一致。"""
    admin, fde, project, solution, _quote, package = _context(db_session)
    view = serialize_package_whitelist(
        package,
        solution=solution,
        project=project,
        workbench_manifest=_workbench_manifest(db_session, package),
    )
    assert view["workbench_manifest"] == _workbench_manifest(db_session, package)
    assert view["workbench_manifest"]["sop_node_keys"] == _EXPECTED_SOP_KEYS


def test_whitelist_payload_route_helper_wires_manifest(db_session):
    """routes._whitelist_payload 单点接线：白名单读面自动携带现算清单。"""
    admin, _fde, _project, solution, _quote, package = _context(db_session)
    view = _whitelist_payload(db_session, package)
    assert view["workbench_manifest"] == _workbench_manifest(db_session, package)
    assert view["scope_summary"] == solution.name  # 白名单原字段零回归
