"""WP23/G6：集成桥读接口角色门禁。

缺陷基线（5d82de1）：GET /engagements 只 @require_auth，任意已登录用户（含 viewer）
可枚举全部 engagement 代号 + 关联项目的 project_name / enterprise_code，而同文件
DELETE /engagements/<slug> 与 POST /reconcile 都要求 project_lead —— 读比写松。

修复口径：读接口与写接口同级收敛 require_minimum_role("project_lead")
（最小权限；member-visible 口径需产品确认，不在本轮实施）。
断言覆盖：viewer / fde_engineer → 403 且响应不含 enterprise_code；
project_lead / admin → 200。
"""

import pytest
from conftest import INITIAL_PASSWORD

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token


@pytest.fixture
def role_clients(app, db_session, settings):
    """按角色创建已认证测试客户端（密码已过强制修改关）。"""

    def create(role: str):
        user = User(
            username=f"bridge-gate.{role.replace('_', '-')}",
            display_name=role,
            role=role,
            password_hash=hash_password(INITIAL_PASSWORD),
            must_change_password=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        token = issue_access_token(user, settings)
        return app.test_client(), {"Authorization": f"Bearer {token}"}

    return create


@pytest.mark.parametrize("role", ["viewer", "fde_engineer"])
def test_bridge_engagements_denies_below_project_lead(role_clients, role):
    """低角色读全量集成桥视图必须 403，且响应体不带任何 enterprise_code。"""
    client, headers = role_clients(role)

    response = client.get("/api/v1/bridge/engagements", headers=headers)

    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"
    assert "enterprise_code" not in response.get_data(as_text=True)
    assert response.json["data"] is None


def test_bridge_engagements_allows_project_lead(role_clients):
    """project_lead 是读集成桥视图的最低角色（与 DELETE/reconcile 同级）。"""
    client, headers = role_clients("project_lead")

    response = client.get("/api/v1/bridge/engagements", headers=headers)

    assert response.status_code == 200
    assert isinstance(response.json["data"]["engagements"], list)


def test_bridge_engagements_allows_admin(role_clients):
    client, headers = role_clients("admin")

    assert client.get("/api/v1/bridge/engagements", headers=headers).status_code == 200


@pytest.mark.parametrize("role", ["viewer", "fde_engineer"])
def test_bridge_status_denies_below_project_lead(role_clients, role):
    """/status 暴露运行错误详情与 slug 集合，与 engagements 同级收敛。"""
    client, headers = role_clients(role)

    response = client.get("/api/v1/bridge/status", headers=headers)

    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"
    assert (response.json.get("data") or {}).get("runs") is None


def test_bridge_status_allows_project_lead(role_clients):
    client, headers = role_clients("project_lead")

    response = client.get("/api/v1/bridge/status", headers=headers)

    assert response.status_code == 200
    assert isinstance(response.json["data"]["runs"], list)
