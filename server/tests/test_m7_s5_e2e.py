"""M7：S5 场景端到端（多客户工作平台 M7 轮；leader 任务书 §1.1 S5）。

S5 场景原文（leader 任务书 :36）：
**区域伙伴注册 → 报备企业线索 → 企业确认归属 → 保护期 → 撮合**

本文件钉住五件事：

1. **S5 全链走通**（区域伙伴申请 → 报备 → 企业确认 → 平台确认归属 →
   保护期 → 售前 → 撮合），逐步状态迁移与引用落库；
2. **售卖闸关闭态下区域伙伴无法进入售卖流**：推进到正式区域合作商
   （``formal_partner``＝对外收费签约的开始）⇒ 409
   ``regional_sale_gate_closed`——这是 leader 任务书 §7 M7 验收明文
   「售卖开关关闭态下区域伙伴无法进入售卖流」；
3. **客户名单硬约束贯穿 S5**（M7 A 组）：企业确认前，区域服务商读不到
   客户识别字段；企业确认后可见（双方按授权可见）；
4. **保护期规则位未配置 ⇒ fail-closed**（409 ``rule_not_configured``）——
   规则数值本期未定数（不预写默认值）；
5. **GAP-11 反例**：企业后续自行注册**不转移**归属（结构性保证）。

> ⚠ **席位口径声明（必须显式标注）**
>
> S5 第一步「报备」有硬依赖：``submit_opportunity`` → ``_require_sourcer_seat``
> 要求**席位 active**（``commercial_entitlements.seat_status='active'``）或
> 科目层存在有效 ``seat_fee`` 行，否则 fail-closed 403
> ``opportunity_reporter_seat_required``。
>
> 席位 active 的**唯一来源**是 G3 ``activate_seat``（首单扣费后激活）。
> 而 §17-1 拍板「席位计费在有真实外部交付者前不激活」，且**工程侧零门控**。
>
> 因此本文件**复用既有测试夹具 ``_activate_seat``**（**测试态激活**）：
> **席位为测试态激活、非商用态、不触发真实计费**。
> 本文件**不改动** ``activate_seat`` 路径、**不加**全局门控、
> **不改** G4 拉单资格判定式。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

from fde_api.commercial.models import (
    OPPORTUNITY_RULE_KEYS,
    CommercialOpportunity,
)

from conftest import INITIAL_PASSWORD
from test_commercial_opportunity_attribution import (  # noqa: F401  (pytest fixture)
    _activate_seat,
    admin_client,
    authorized_client_factory,
    leader_client,
)

SERVER_ROOT = Path(__file__).resolve().parent.parent
REGIONAL_SERVICE = (
    SERVER_ROOT / "src" / "fde_api" / "commercial" / "regional_service.py"
)

PARTNER_CODE = "s5 伙伴·集成·广州"
ENTERPRISE_CODE = "s5 企业·制造·广州"


def _pwd() -> str:
    return INITIAL_PASSWORD


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _opp_url(opportunity_id: str = "") -> str:
    base = "/api/v1/commercial/opportunities"
    return f"{base}/{opportunity_id}" if opportunity_id else base


def _admin_opp_url(opportunity_id: str, action: str = "") -> str:
    base = f"/api/v1/admin/commercial/opportunities/{opportunity_id}"
    return f"{base}/{action}" if action else base


def _partners_url() -> str:
    return "/api/v1/commercial/regional-partners"


def _admin_partner_url(partner_id: str, action: str = "") -> str:
    base = f"/api/v1/admin/commercial/regional-partners/{partner_id}"
    return f"{base}/{action}" if action else base


def _rules_url() -> str:
    return "/api/v1/admin/commercial/opportunity-rules"


def _tiers_url() -> str:
    return "/api/v1/commercial/regional-partner-tiers"


def _apply_partner(client, partner_code: str = PARTNER_CODE, region: str = "广州"):
    """① 区域伙伴注册（城市观察伙伴；免费；当事人自证）。"""
    response = client.post(
        _partners_url(),
        json={"partner_code": partner_code, "region_name": region},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.json["data"]["partner"]


def _report(client, enterprise_code: str = ENTERPRISE_CODE, title: str = "s5 企业线索"):
    """② 报备企业线索（当事人自证动作；需席位已缴）。"""
    response = client.post(
        _opp_url(),
        json={
            "enterprise_code": enterprise_code,
            "title": title,
            "source_uri": f"fdeops://s5/leads/{uuid4().hex[:8]}.md",
            "content_hash": _sha(f"s5-lead-{uuid4().hex}"),
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.json["data"]["opportunity"]


def _enterprise_confirm(admin_client, opportunity_id: str):
    return admin_client.post(
        _admin_opp_url(opportunity_id, "enterprise-confirm"),
        json={
            "confirmation_uri": f"fdeops://s5/confirmations/{opportunity_id}.pdf",
            "confirmation_hash": _sha(f"s5-confirm-{opportunity_id}"),
            "confirm_password": _pwd(),
        },
    )


def _confirm_attribution(admin_client, opportunity_id: str, owner_user_id: str):
    return admin_client.post(
        _admin_opp_url(opportunity_id, "attribution"),
        json={
            "owner_user_id": owner_user_id,
            "attribution_uri": f"fdeops://s5/attribution/{opportunity_id}.pdf",
            "attribution_hash": _sha(f"s5-attr-{opportunity_id}"),
            "confirm_password": _pwd(),
        },
    )


def _configure_rule(admin_client, key: str, value):
    return admin_client.post(
        f"{_rules_url()}/{key}",
        json={
            "value": value,
            "source_uri": f"fdeops://s5/rules/{key}.md",
            "content_hash": _sha(f"s5-rule-{key}-{uuid4().hex[:6]}"),
            "confirm_password": _pwd(),
        },
    )


def _promote(admin_client, partner_id: str, to_stage: str, **extra):
    payload = {
        "to_stage": to_stage,
        "source_uri": f"fdeops://s5/promotions/{partner_id}-{to_stage}.md",
        "content_hash": _sha(f"s5-promote-{partner_id}-{to_stage}"),
        "confirm_password": _pwd(),
    }
    payload.update(extra)
    return admin_client.post(
        _admin_partner_url(partner_id, "promote"), json=payload
    )


# ---------------------------------------------------------------------------
# 1. S5 全链端到端（区域伙伴注册 → 报备 → 企业确认 → 保护期 → 撮合）
# ---------------------------------------------------------------------------


def test_s5_e2e_partner_registers_reports_confirms_protects_and_matches(
    admin_client, authorized_client_factory, db_session
) -> None:
    """S5 全链走通（**席位为测试态激活、非商用态、不触发真实计费**）。

    链路：区域伙伴注册 → 报备企业线索 → 企业确认有真实需求 → 平台确认归属
    → 设定保护期 → 售前 → 撮合交付者。

    **规则数值本期未定数**：保护期长度须先配置 ``protection_period_days``
    （否则 409 ``rule_not_configured``，**不回落默认值**）。
    """
    # ── ① 区域伙伴注册（城市观察伙伴；免费自证）──
    partner_client = authorized_client_factory("fde_engineer")
    partner_id = partner_client.user.id
    partner = _apply_partner(partner_client)
    assert partner["stage"] == "city_observer"
    assert partner["stage_note"], "阶段注记必须透出"

    # 席位：**测试态激活**（非商用态，不触发真实计费）
    _activate_seat(admin_client, admin_client.user.id, partner_id)

    # ── ② 报备企业线索 ──
    opportunity = _report(partner_client)
    opportunity_id = opportunity["id"]
    assert opportunity["status"] == "submitted"
    assert opportunity["protection"]["status"] == "unconfigured"

    # ── ③ 企业确认有真实需求（平台代录书面答复；admin＋密码确认）──
    confirmed = _enterprise_confirm(admin_client, opportunity_id)
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)
    confirmed_body = confirmed.json["data"]["opportunity"]
    assert confirmed_body["status"] == "enterprise_confirmed"
    assert confirmed_body["enterprise_confirmation"]["confirmed_at"] is not None

    # ── ④ 平台确认商机归属（关键流转；admin＋密码确认）──
    attributed = _confirm_attribution(admin_client, opportunity_id, partner_id)
    assert attributed.status_code == 200, attributed.get_data(as_text=True)
    attributed_body = attributed.json["data"]["opportunity"]
    assert attributed_body["status"] == "attribution_confirmed"
    assert attributed_body["attribution"]["owner_user_id"] == partner_id

    # ── ⑤ 设定保护期（规则位未配置 ⇒ fail-closed，不回落默认值）──
    blocked = admin_client.post(
        _admin_opp_url(opportunity_id, "protection"), json={"confirm_password": _pwd()}
    )
    assert blocked.status_code == 409, blocked.get_data(as_text=True)
    assert blocked.json["error"]["code"] == "rule_not_configured"

    configured = _configure_rule(admin_client, "protection_period_days", 30)
    assert configured.status_code == 200, configured.get_data(as_text=True)
    protected = admin_client.post(
        _admin_opp_url(opportunity_id, "protection"), json={"confirm_password": _pwd()}
    )
    assert protected.status_code == 200, protected.get_data(as_text=True)
    protected_body = protected.json["data"]["opportunity"]
    assert protected_body["protection"]["status"] == "active"
    assert protected_body["protection"]["effective_status"] == "active"
    assert protected_body["protection"]["days_remaining"] == 30

    # ── ⑥ 售前与客户关系 ──
    presales = admin_client.post(
        _admin_opp_url(opportunity_id, "presales"), json={"confirm_password": _pwd()}
    )
    assert presales.status_code == 200, presales.get_data(as_text=True)
    assert presales.json["data"]["opportunity"]["status"] == "presales"

    # ── ⑦ 撮合交付者（引用既有 dispatch 交付包，不建第二套撮合）──
    package = _delivery_package(db_session, partner_id)
    matched = admin_client.post(
        _admin_opp_url(opportunity_id, "match"),
        json={"delivery_package_id": package.id, "confirm_password": _pwd()},
    )
    assert matched.status_code == 200, matched.get_data(as_text=True)
    matched_body = matched.json["data"]["opportunity"]
    assert matched_body["status"] == "matched"
    assert matched_body["matched_delivery_package_id"] == package.id


def _delivery_package(db_session, leader_user_id: str):
    """同企业代号下的交付包（复用既有 dispatch 结构，不建第二套撮合）。"""
    from fde_api.dispatch.models import DeliveryPackage
    from fde_api.solutions.models import ProjectSolution
    from fde_api.workbench.models import (
        IndustryTemplate,
        IndustryTemplateVersion,
        Project,
    )

    template = IndustryTemplate(
        template_key=f"s5-tpl-{uuid4().hex[:8]}", name="s5 模板", industry_name="制造业"
    )
    version = IndustryTemplateVersion(
        template=template,
        name="s5 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"S5-{uuid4().hex[:6].upper()}",
        name="s5 交付项目",
        enterprise_code=ENTERPRISE_CODE,
        business_line="FDE_DISPATCH",
        planned_start_date="2026-10-31",
        leader_user_id=leader_user_id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([template, version, project])
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id, name="s5 方案", schedule="", owner_user_id=leader_user_id
    )
    db_session.add(solution)
    db_session.flush()
    package = DeliveryPackage(
        id=uuid4().hex,
        solution_id=solution.id,
        project_id=project.id,
        package_code=f"PKG-S5-{uuid4().hex[:8].upper()}",
        dispatch_status="published",
        seat_lead=leader_user_id,
    )
    db_session.add(package)
    db_session.commit()
    return package


# ---------------------------------------------------------------------------
# 2. 售卖开关关闭态下区域伙伴无法进入售卖流（M7 验收明文）
# ---------------------------------------------------------------------------


def test_s5_sale_gate_closed_blocks_formal_partner_entry(
    admin_client, authorized_client_factory
) -> None:
    """**售卖闸关闭态**下推进正式区域合作商 ⇒ 409 ``regional_sale_gate_closed``。

    leader 任务书 §7 M7 验收：「售卖开关关闭态下区域伙伴无法进入售卖流」。
    ``formal_partner``＝对外收费签约的开始——被 ``require_sale_gate_open``
    闸住（fail-closed，不回落、不绕行）。

    **本用例不登记任何合规条件证据、不开启售卖闸**（本期四条件槽全空）。
    """
    partner_client = authorized_client_factory("fde_engineer")
    partner = _apply_partner(partner_client, f"s5 伙伴·售卖闸·{uuid4().hex[:6]}")

    # 城市观察 → 城市服务（书面依据齐备即可，**不触售卖闸**）
    to_service = _promote(admin_client, partner["id"], "city_service")
    assert to_service.status_code == 200, to_service.get_data(as_text=True)
    assert to_service.json["data"]["partner"]["stage"] == "city_service"

    # 城市服务 → 正式区域合作商 ⇒ 售卖闸关 ⇒ 409
    to_formal = _promote(
        admin_client, partner["id"], "formal_partner", tier_code="T1"
    )
    assert to_formal.status_code == 409, to_formal.get_data(as_text=True)
    assert to_formal.json["error"]["code"] == "regional_sale_gate_closed"


def test_s5_sale_gate_read_face_still_closed_and_catalog_visible(
    admin_client, authorized_client_factory
) -> None:
    """售卖闸关闭态：档位目录**仍可见**（既有行为，不是漏洞）＋闸状态透出。

    **口径**：目录可见 ≠ 可签约——「无法进入售卖流」由
    ``require_sale_gate_open`` 闸住，不靠隐藏目录。本用例把这条边界显式
    钉住，避免后续被误读成闸失效。
    """
    partner_client = authorized_client_factory("fde_engineer")

    tiers = partner_client.get(_tiers_url())
    assert tiers.status_code == 200, tiers.get_data(as_text=True)
    assert tiers.json["data"]["sale_gate_status"] == "closed"
    assert {row["tier_code"] for row in tiers.json["data"]["tiers"]} == {
        "T1",
        "T2",
        "T3",
    }

    gate = admin_client.get("/api/v1/admin/commercial/regional-sale-gate")
    assert gate.status_code == 200, gate.get_data(as_text=True)
    assert gate.json["data"]["status"] == "closed"
    assert all(
        info["registered"] is False for info in gate.json["data"]["conditions"].values()
    ), "本期合规条件槽全空（登记≠开启）"


def test_s5_no_code_path_signs_while_gate_closed():
    """**结构性钉**：正式档写点唯一且在过闸函数内（源码扫描）。

    「本期无任何对外收费签约路径」的可执行形态：``regional_service.py`` 里把
    ``stage`` 赋成 ``formal_partner`` 的位置唯一，且该函数体先调用
    ``require_sale_gate_open``。
    """
    source = REGIONAL_SERVICE.read_text(encoding="utf-8")
    writes = [
        m.start() for m in re.finditer(r"\.stage\s*=\s*to_stage", source)
    ]
    assert len(writes) == 1, "formal_partner 阶段写点必须唯一"
    gate_call = source.find("require_sale_gate_open(session)")
    assert 0 <= gate_call < writes[0], "写点之前必须先过售卖闸"
    assert "regional_sale_gate_closed" in source


# ---------------------------------------------------------------------------
# 3. 客户名单硬约束贯穿 S5（M7 A 组）
# ---------------------------------------------------------------------------


def test_s5_customer_list_masked_before_enterprise_confirmation(
    admin_client, authorized_client_factory
) -> None:
    """S5 中：企业确认前，区域服务商读不到客户识别字段（M7 A 组）。

    平台托管 ⇒ 企业确认前客户代号属平台托管事实；区域服务商不得取得
    客户名单。遮蔽字段（非删除）＋ 显式 ``customer_identity_visible=False``。
    """
    partner_client = authorized_client_factory("fde_engineer")
    partner_id = partner_client.user.id
    _apply_partner(partner_client, f"s5 伙伴·名单·{uuid4().hex[:6]}")
    _activate_seat(admin_client, admin_client.user.id, partner_id)
    opportunity = _report(partner_client)

    listed = partner_client.get(_opp_url())
    assert listed.status_code == 200, listed.get_data(as_text=True)
    row = next(
        item
        for item in listed.json["data"]["opportunities"]
        if item["id"] == opportunity["id"]
    )
    assert row["enterprise_code"] is None, "企业确认前客户识别字段必须被遮蔽"
    assert row["customer_identity_visible"] is False

    # 平台托管方（admin）仍全量可见（**托管方例外**）
    platform = admin_client.get(_opp_url(opportunity["id"]))
    assert platform.status_code == 200, platform.get_data(as_text=True)
    platform_row = platform.json["data"]["opportunity"]
    assert platform_row["enterprise_code"] == ENTERPRISE_CODE
    assert platform_row["customer_identity_visible"] is True


def test_s5_customer_list_visible_after_enterprise_confirmation(
    admin_client, authorized_client_factory
) -> None:
    """S5 中：企业确认后 ⇒ 双方按授权可见（客户识别字段恢复）。"""
    partner_client = authorized_client_factory("fde_engineer")
    partner_id = partner_client.user.id
    _apply_partner(partner_client, f"s5 伙伴·授权·{uuid4().hex[:6]}")
    _activate_seat(admin_client, admin_client.user.id, partner_id)
    opportunity = _report(partner_client)
    confirmed = _enterprise_confirm(admin_client, opportunity["id"])
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)

    listed = partner_client.get(_opp_url())
    assert listed.status_code == 200, listed.get_data(as_text=True)
    row = next(
        item
        for item in listed.json["data"]["opportunities"]
        if item["id"] == opportunity["id"]
    )
    assert row["enterprise_code"] == ENTERPRISE_CODE, "企业确认后按授权可见"
    assert row["customer_identity_visible"] is True


# ---------------------------------------------------------------------------
# 4. GAP-11 反例（S5 内嵌：企业自行注册不转移归属）
# ---------------------------------------------------------------------------


def test_s5_attribution_not_transferred_when_enterprise_registers_directly(
    admin_client, leader_client, authorized_client_factory, db_session
) -> None:
    """**反例**（GAP-11）：企业后续自行注册 ⇒ 商机归属**逐项不变**。

    企业侧立项路径**无任何写路径**可触碰商机行（结构性保证）。
    """
    partner_client = authorized_client_factory("fde_engineer")
    partner_id = partner_client.user.id
    _apply_partner(partner_client, f"s5 伙伴·反例·{uuid4().hex[:6]}")
    _activate_seat(admin_client, admin_client.user.id, partner_id)
    opportunity = _report(partner_client)
    _enterprise_confirm(admin_client, opportunity["id"])
    _confirm_attribution(admin_client, opportunity["id"], partner_id)

    before = admin_client.get(_opp_url(opportunity["id"])).json["data"]["opportunity"]
    assert before["attribution"]["owner_user_id"] == partner_id
    assert before["enterprise_registered"] is False

    # 企业自行注册（直签立项）——归属不得易主
    created = _create_direct_project(admin_client, leader_client, db_session)
    assert created.status_code == 201, created.get_data(as_text=True)

    after = admin_client.get(_opp_url(opportunity["id"])).json["data"]["opportunity"]
    assert after["attribution"]["owner_user_id"] == partner_id
    assert after["attribution"]["confirmed_at"] == before["attribution"]["confirmed_at"]
    assert after["status"] == before["status"]
    assert after["protection"]["status"] == before["protection"]["status"]
    # 派生事实：企业确已自助注册（反例**非空洞**）
    assert after["enterprise_registered"] is True


def _create_direct_project(
    admin_client, leader_client, db_session, enterprise_code: str = ENTERPRISE_CODE
):
    """企业**直签立项**（business_line 缺省＝FDE）——「企业自行注册」真实路径。"""
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    db_session.commit()
    return admin_client.post(
        "/api/v1/projects",
        json={
            "name": "企业自行注册的项目",
            "enterprise_code": enterprise_code,
            "planned_start_date": "2026-11-01",
            "leader_user_id": leader_client.user.id,
            "creation_source": "manual",
            "module_keys": ["pre_diagnosis"],
            "project_snapshot": {
                "industry_name": "通用",
                "description": "企业自行注册",
                "modules": [
                    {
                        "module_key": "pre_diagnosis",
                        "name": "预诊断",
                        "description": "确认范围",
                        "tasks": [
                            {
                                "task_key": "manual_scope",
                                "name": "确认项目范围",
                                "description": "整理输入和验收口径",
                                "duration_days": 2,
                                "default_assignee_role": "project_lead",
                                "dependency_keys": [],
                                "sort_order": 0,
                            }
                        ],
                    }
                ],
            },
        },
    )


# ---------------------------------------------------------------------------
# 5. 规则数值本期不定数（S5 链路侧的数值零落数核对）
# ---------------------------------------------------------------------------


def test_s5_opportunity_rule_slots_remain_unset_by_default(
    admin_client, db_session
) -> None:
    """S5 链路使用的规则位**缺省 unset**——**数值本期不定数**。

    本用例只核对**缺省态**（未配置的规则位一律 fail-closed）；
    S5 用例中显式配置 ``protection_period_days`` 属**测试态**动作，
    配置后该槽为 ``configured``——本用例在新库/未配置态下核对缺省。
    """
    response = admin_client.get(_rules_url())
    assert response.status_code == 200, response.get_data(as_text=True)
    rules = {row["key"]: row for row in response.json["data"]["rules"]}
    assert set(rules) == set(OPPORTUNITY_RULE_KEYS)
    for key, row in rules.items():
        if key == "protection_period_days":
            # 本轮 S5 用例可能已配置（测试态）——数值不由代码预写
            continue
        assert row["status"] == "unset", key
        assert row["days"] is None, key
        assert row["criteria"] is None, key


def test_s5_no_hardcoded_business_numbers_in_opportunity_service():
    """**数值零落数哨兵**：商机服务层不出现预写的业务数值常量。

    「规则数值本期不定数，不落硬编码默认值」——源码扫描哨兵。
    """
    source = (
        SERVER_ROOT / "src" / "fde_api" / "commercial" / "attribution_service.py"
    ).read_text(encoding="utf-8")
    # 保护期长度等规则数值不得以字面量出现在服务层
    assert "protection_period_days = " not in source
    assert "protection_days=30" not in source
    assert "protection_period_days\": 30" not in source
