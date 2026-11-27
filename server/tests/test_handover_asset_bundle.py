"""B1 结项资产闸＋B9-a 结果合同回指（FDU 对照拍板 E-1，2026-11-28）。

验收面（分析文档 B1/B9 落点 + 评审拍板 E-1/E-3）：
- 严格默认（asset_bundle_gate_required=True）：缺 asset_bundle → 428
  asset_bundle_required；缺 result_contract → 428 result_contract_required；
- 形状非法 → 422 invalid_asset_bundle：asset_bundle 键集闭合（S13 既产物
  retrospective/handoff/patterns 三件，缺件/多件皆拒——空包不放行）、
  指针恰含 source_uri(≤500)+sha256(64hex，大写归一)；
- B9-a：result_contract 与 G4 门禁清单项「结果合同页」已 accepted 证据的
  content_hash 比对——在案不命中 → 409 result_contract_mismatch；无 G4 行/
  项未 accepted → 放行（回指留痕可推翻）；
- 兼容期（开关 False）：完全省略键放行＋handover_asset_bundle_skipped
  留痕（missing 列出放行了哪些键）；携带（含非法形状）仍严格校验；
- 事件留痕：handover_package_delivered changes 带 asset_bundle 三键指针与
  result_contract（原件留项目工作目录，库内只有指针+指纹）；
- 件 4 载体（E-1）：_snapshot_payload 键集钉（§2.3 对表修订 +1 键）＋
  workbench_manifest 子键集钉＋装配确定性（纯函数可从行数据重建）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from test_agents_d4_harness import d4_app, d4_client, d4_settings  # noqa: F401  (pytest fixture)
from test_handover_packages import delivery_case  # noqa: F401  (pytest fixture)

from fde_api.dispatch.packages import _snapshot_payload, _workbench_manifest
from fde_api.dispatch.models import DeliveryPackage
from fde_api.handover.models import HandoverPackage
from fde_api.workbench.models import Gate, OperationEvent

RESULT_CONTRACT_SHA = "d" * 64


def _package_project_id(db_session, path: str) -> str:
    package = db_session.get(HandoverPackage, path.rsplit("/", 1)[-1])
    assert package is not None
    return package.project_id


def _seed_g4_result_contract(db_session, project_id: str, *, sha256: str, accepted: bool = True) -> None:
    """直接造 G4 行＋「结果合同页」清单项（正常流程由门禁证据闸写入）。"""
    db_session.add(Gate(
        project_id=project_id,
        gate_key="G4",
        status="passed",
        evidence_checklist=[{
            "label": "结果合同页",
            "claim_status": "accepted" if accepted else "claimed",
            "source_uri": "fdeops/case/结果合同页-v1.md",
            "content_hash": sha256,
            "evidence_id": None,
        }],
    ))
    db_session.commit()


def _bundle(sha_prefix: str = "a") -> dict:
    return {
        "retrospective": {"source_uri": "fdeops/case/复盘-v1.md", "sha256": sha_prefix * 64},
        "handoff": {"source_uri": "fdeops/case/交接-v1.md", "sha256": "b" * 64},
        "patterns": {"source_uri": "openfde/assets/patterns-candidates.md", "sha256": "c" * 64},
    }


def _pointer(uri: str = "fdeops/case/结果合同页-v1.md", sha: str = RESULT_CONTRACT_SHA) -> dict:
    return {"source_uri": uri, "sha256": sha}


def _sealed(delivery_case):
    leader, admin, path = delivery_case
    sealed = leader.post(f"{path}/seal").get_json()["data"]
    return leader, admin, path, sealed


# ---------------------------------------------------------------------------
# 严格默认：428 家族
# ---------------------------------------------------------------------------


def test_strict_missing_both_keys_reports_asset_bundle_first(delivery_case) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 428
    assert response.get_json()["error"]["code"] == "asset_bundle_required"


def test_strict_missing_result_contract_when_g4_evidence_present(delivery_case, db_session) -> None:
    """有源必回指：G4 已 accepted「结果合同页」在案 ⇒ 缺 result_contract → 428。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    _seed_g4_result_contract(db_session, _package_project_id(db_session, path), sha256=RESULT_CONTRACT_SHA)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 428
    assert response.get_json()["error"]["code"] == "result_contract_required"


def test_strict_missing_result_contract_without_g4_source_passes(delivery_case, db_session) -> None:
    """无源可指（未走试点门禁线）⇒ 省略 result_contract 放行（delivered 事件 null 留痕）。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
    }
    assert admin.post(f"{path}/deliver", json=payload).status_code == 200
    (delivered,) = db_session.query(OperationEvent).filter_by(
        event_type="handover_package_delivered"
    ).all()
    assert delivered.changes["result_contract"] is None
    assert delivered.changes["asset_bundle"]["retrospective"]["sha256"] == "a" * 64


# ---------------------------------------------------------------------------
# 形状非法：422 invalid_asset_bundle（空包不放行）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("broken_bundle", [
    {},  # 空包：宁拒登不制造形式合规
    {"retrospective": _pointer(), "handoff": _pointer()},  # 缺 patterns
    {**_bundle(), "extra": _pointer()},  # 多件（键集闭合）
    "not-a-dict",  # 非 dict
    [_pointer(), _pointer(), _pointer()],  # 数组
])
def test_malformed_bundle_shape_422(delivery_case, broken_bundle) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": broken_bundle,
        "result_contract": _pointer(),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 422, response.get_json()
    assert response.get_json()["error"]["code"] == "invalid_asset_bundle"


@pytest.mark.parametrize("broken_pointer", [
    {"source_uri": "fdeops/x.md"},  # 缺 sha256
    {"sha256": "a" * 64},  # 缺 source_uri
    {"source_uri": "fdeops/x.md", "sha256": "a" * 64, "extra": 1},  # 多键
    {"source_uri": "", "sha256": "a" * 64},  # 空 uri
    {"source_uri": "fdeops/" + "x" * 500, "sha256": "a" * 64},  # uri 超长（>500）
    {"source_uri": "fdeops/x.md", "sha256": "a" * 63},  # 短指纹
    {"source_uri": "fdeops/x.md", "sha256": "g" * 64},  # 非十六进制
    {"source_uri": "fdeops/x.md", "sha256": 123},  # 非字符串
])
def test_malformed_pointer_shape_422(delivery_case, broken_pointer) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": {key: broken_pointer for key in ("retrospective", "handoff", "patterns")},
        "result_contract": _pointer(),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 422, response.get_json()
    assert response.get_json()["error"]["code"] == "invalid_asset_bundle"


def test_uppercase_sha256_normalized_and_event_carries_bundle(
    delivery_case, db_session
) -> None:
    """大写指纹归一为小写；delivered 事件 changes 携带三件指针＋result_contract。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    bundle = _bundle()
    bundle["retrospective"]["sha256"] = "A" * 64
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": bundle,
        "result_contract": _pointer(),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 200, response.get_json()
    (event,) = db_session.query(OperationEvent).filter_by(
        event_type="handover_package_delivered"
    ).all()
    assert event.changes["asset_bundle"]["retrospective"]["sha256"] == "a" * 64
    assert event.changes["asset_bundle"]["handoff"]["sha256"] == "b" * 64
    assert event.changes["result_contract"]["sha256"] == RESULT_CONTRACT_SHA
    # 兼容留痕零出现（键全部在场且合法）
    assert db_session.query(OperationEvent).filter_by(
        event_type="handover_asset_bundle_skipped"
    ).count() == 0


# ---------------------------------------------------------------------------
# B9-a：G4「结果合同页」回指比对
# ---------------------------------------------------------------------------


def test_result_contract_mismatch_against_accepted_g4_evidence(delivery_case, db_session) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    _seed_g4_result_contract(db_session, _package_project_id(db_session, path), sha256="9" * 64)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
        "result_contract": _pointer(sha=RESULT_CONTRACT_SHA),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "result_contract_mismatch"


def test_result_contract_match_passes(delivery_case, db_session) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    _seed_g4_result_contract(db_session, _package_project_id(db_session, path), sha256=RESULT_CONTRACT_SHA)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
        "result_contract": _pointer(),
    }
    assert admin.post(f"{path}/deliver", json=payload).status_code == 200


@pytest.mark.parametrize("accepted", [False])
def test_result_contract_claimed_g4_passes_with_trace_note(delivery_case, db_session, accepted) -> None:
    """G4 在案但「结果合同页」未 accepted（claimed）⇒ 指纹集为空 ⇒ 放行。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    _seed_g4_result_contract(
        db_session, _package_project_id(db_session, path), sha256="9" * 64, accepted=accepted
    )
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
        "result_contract": _pointer(sha=RESULT_CONTRACT_SHA),
    }
    assert admin.post(f"{path}/deliver", json=payload).status_code == 200


# ---------------------------------------------------------------------------
# 兼容期：开关 False → 完全省略放行＋留痕；携带仍严格
# ---------------------------------------------------------------------------


def test_compat_allows_absent_keys_and_traces_missing(delivery_case, d4_app, db_session, monkeypatch) -> None:
    _leader, admin, path, sealed = _sealed(delivery_case)
    monkeypatch.setattr(d4_app.config["SETTINGS"], "asset_bundle_gate_required", False)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
    }
    assert admin.post(f"{path}/deliver", json=payload).status_code == 200
    (skipped,) = db_session.query(OperationEvent).filter_by(
        event_type="handover_asset_bundle_skipped"
    ).all()
    # 本项目无 G4 在案证据：result_contract 属「无源可指」放行（不属兼容放行），
    # missing 只登记 asset_bundle（兼容语义只覆盖开关管辖的省略键）。
    assert skipped.changes["missing"] == ["asset_bundle"]
    (delivered,) = db_session.query(OperationEvent).filter_by(
        event_type="handover_package_delivered"
    ).all()
    # 兼容期省略时 delivered 事件两键为 None——复盘读数据此区分「带了」与「放行」。
    assert delivered.changes["asset_bundle"] is None
    assert delivered.changes["result_contract"] is None


def test_compat_traces_result_contract_only_when_g4_source_present(
    delivery_case, d4_app, db_session, monkeypatch
) -> None:
    """有源＋开关关＋省略 result_contract ⇒ 兼容放行且 missing 登记 result_contract。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    monkeypatch.setattr(d4_app.config["SETTINGS"], "asset_bundle_gate_required", False)
    _seed_g4_result_contract(db_session, _package_project_id(db_session, path), sha256=RESULT_CONTRACT_SHA)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": _bundle(),
    }
    assert admin.post(f"{path}/deliver", json=payload).status_code == 200
    (skipped,) = db_session.query(OperationEvent).filter_by(
        event_type="handover_asset_bundle_skipped"
    ).all()
    assert skipped.changes["missing"] == ["result_contract"]


def test_compat_carried_keys_still_strict(delivery_case, d4_app, monkeypatch) -> None:
    """开关只放行**完全省略**的旧请求：携带坏形状照旧 422（ux-p0 兼容语义）。"""
    _leader, admin, path, sealed = _sealed(delivery_case)
    monkeypatch.setattr(d4_app.config["SETTINGS"], "asset_bundle_gate_required", False)
    payload = {
        "expected_manifest_sha256": sealed["manifest_sha256"],
        "expected_unsealed_count": sealed["unsealed_count"],
        "asset_bundle": {"retrospective": _pointer()},  # 缺两件
        "result_contract": _pointer(),
    }
    response = admin.post(f"{path}/deliver", json=payload)
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_asset_bundle"


# ---------------------------------------------------------------------------
# 件 4 载体（E-1）：快照键集钉＋装配确定性
# ---------------------------------------------------------------------------


def test_snapshot_payload_key_set_pinned() -> None:
    """§2.3 快照字段清单键集钉（此前无测试硬钉——E-1 对表修订同时补闸）。

    27 键闭集 = 既有 26 键 + workbench_manifest（拍板 E-1 对表修订记录）。
    任何再增删必须先改本钉并同步修订 packages.py docstring 的对表记录。
    """
    from datetime import UTC, datetime

    from fde_api.solutions.models import ProjectSolution
    from fde_api.workbench.models import Project, Quote

    payload = _snapshot_payload(
        DeliveryPackage(), ProjectSolution(), Project(), Quote(),
        published_at=datetime(2026, 11, 28, tzinfo=UTC),
    )
    assert frozenset(payload.keys()) == frozenset({
        "package_id", "solution_id", "solution_version", "project_id", "name",
        "business_category", "design_markdown", "deliverables", "acceptance_criteria",
        "data_systems", "schedule", "risks_dependencies", "quote_id", "quote_version",
        "quote_tier", "quote_low", "quote_high", "b_layer_score", "required_modules",
        "required_industry", "onsite_required", "seat_lead", "seat_delivery",
        "seat_consult", "seat_qa", "published_at", "workbench_manifest",
    })
    manifest = payload["workbench_manifest"]
    assert set(manifest.keys()) == {
        "required_modules", "required_industry", "sop_node_keys",
        "industry_template_refs", "eval_suite_refs", "hq_card_keys",
    }


def test_workbench_manifest_deterministic_rebuild() -> None:
    """纯函数装配：同一行数据两次装配逐位一致（换手可从行重建同一清单）。"""
    left = DeliveryPackage()
    left.required_modules = ["m3", "m1"]
    left.required_industry = "manufacturing"
    right = DeliveryPackage()
    right.required_modules = ["m1", "m3"]
    right.required_industry = "manufacturing"
    assert _workbench_manifest(left) == _workbench_manifest(right)
    assert _workbench_manifest(left) == {
        "required_modules": ["m1", "m3"],
        "required_industry": "manufacturing",
        "sop_node_keys": [],
        "industry_template_refs": [],
        "eval_suite_refs": [],
        "hq_card_keys": [],
    }


def test_snapshot_payload_consumes_workbench_manifest() -> None:
    """E-1 载体在位静态钉：_snapshot_payload 实际消费装配函数（防回退脱钩）。"""
    import inspect

    source = inspect.getsource(_snapshot_payload)
    assert '"workbench_manifest": _workbench_manifest(package)' in source
