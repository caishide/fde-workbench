"""WP29/J1：业务枚举选项表下发端点。

缺陷基线：桌面端把业务枚举硬编码在渲染层（价格档位、门禁五态、C 分支、SOW、
业务阶段），口径变更要改前端代码，且各页面各写一份容易漂移。本轮把选项表
下沉服务端下发，前端消费 + 保留本地兜底。

断言覆盖：
- 端点可用且需要登录（未登录 401）
- 五类选项齐全，且 value 沿用既有存库值（不改字段契约）
- 门禁五态齐全（口径不得扩张）
- 业务阶段 value 仍是历史存库的中文标签（旧数据兼容）
"""

import pytest

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from conftest import INITIAL_PASSWORD


@pytest.fixture
def auth_client(app, db_session, settings):
    user = User(
        username="options.reader",
        display_name="选项表读取者",
        role="viewer",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = issue_access_token(user, settings)
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_options_endpoint_requires_auth(app):
    response = app.test_client().get("/api/v1/workbench/options")

    assert response.status_code == 401


def test_options_endpoint_returns_all_option_groups(auth_client):
    client, headers = auth_client

    response = client.get("/api/v1/workbench/options", headers=headers)

    assert response.status_code == 200
    data = response.json["data"]
    for group in (
        "price_tiers",
        "gate_statuses",
        "c_handling_options",
        "sow_options",
        "business_categories",
    ):
        assert group in data, f"缺少选项组 {group}"
        assert isinstance(data[group], list)
        assert len(data[group]) > 0, f"选项组 {group} 为空（前端兜底会掩盖口径缺失）"


def test_gate_statuses_keep_five_state_vocabulary(auth_client):
    """门禁五态是口径边界：不得增删状态。"""
    client, headers = auth_client

    response = client.get("/api/v1/workbench/options", headers=headers)

    values = [item["value"] for item in response.json["data"]["gate_statuses"]]
    assert sorted(values) == sorted(
        ["pending", "evidence", "passed", "conditional_pass", "failed"]
    )


def test_option_values_keep_existing_contract(auth_client):
    """value 沿用既有存库值：前端提交的还是同一个字符串（不改字段契约）。"""
    client, headers = auth_client

    data = client.get("/api/v1/workbench/options", headers=headers).json["data"]

    assert [item["value"] for item in data["price_tiers"]] == [
        "light",
        "standard",
        "flagship",
    ]
    assert [item["value"] for item in data["c_handling_options"]] == [
        "scope_cut",
        "split_phases",
        "external_collab",
        "ticket_deal",
    ]
    assert [item["value"] for item in data["sow_options"]] == ["b", "c", "a", "d"]


def test_business_categories_keep_legacy_chinese_values(auth_client):
    """业务阶段 value 仍是历史存库的中文标签（旧数据兼容，不做数据迁移）。"""
    client, headers = auth_client

    data = client.get("/api/v1/workbench/options", headers=headers).json["data"]

    values = [item["value"] for item in data["business_categories"]]
    assert values == [
        "商务合约",
        "预调研",
        "调研",
        "PoV验证",
        "生产部署",
        "培训预交接",
    ]
    # 同时给出稳定 key —— 前端按 key 引用，显示标签仍可独立调整
    keys = [item["key"] for item in data["business_categories"]]
    assert keys == [
        "contract",
        "presurvey",
        "research",
        "pov",
        "deployment",
        "handover",
    ]
