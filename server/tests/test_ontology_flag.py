"""开关挂载 parity（WP4⑥ / §13 验收 8）：off 时路由表与 V3.2 一致，on 时挂载。

评审 W-G：挂载双向不钉死则门禁可静默失效（该测试此前缺失）。
sqlite 文件库 + 真实 Settings；不依赖 CI MySQL。
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask
from pydantic import SecretStr

from fde_api.app import create_app
from fde_api.config import Settings

_BASE: dict[str, str] = {
    "redis_url": "redis://127.0.0.1:6379/2",
    "jwt_secret": "test-secret-with-at-least-thirty-two-characters",
}


def _settings(tmp_path: Path, *, enabled: bool) -> Settings:
    base = dict(_BASE)
    base["database_url"] = f"sqlite:///{tmp_path / ('flag-on.db' if enabled else 'flag-off.db')}"
    kwargs: dict[str, object] = {"env": "test", **base}
    if enabled:
        kwargs.update(
            ontology_enabled=True,
            ontology_api_key=SecretStr("k"),
            ontology_signing_key=SecretStr("s"),
            ontology_org_id="org-1",
        )
    return Settings(**kwargs)  # type: ignore[arg-type]


def _ontology_routes(app: Flask) -> set[str]:
    return {str(r) for r in app.url_map.iter_rules() if "ontology-bindings" in str(r)}


def test_flag_off_route_parity(tmp_path: Path) -> None:
    """off（默认）：ontology 蓝图不注册——路由表与 V3.2 完全一致。"""
    app = create_app(_settings(tmp_path, enabled=False))
    assert _ontology_routes(app) == set()
    assert app.config["SETTINGS"].ontology_enabled is False


def test_flag_on_mounts_bindings_api(tmp_path: Path) -> None:
    """on：§5.2 四路径挂载（list/create/upgrade-proposal/approve-upgrade）。"""
    app = create_app(_settings(tmp_path, enabled=True))
    routes = sorted(str(r) for r in app.url_map.iter_rules() if "ontology-bindings" in str(r))
    assert len(routes) == 4, routes
    assert any(r.endswith("/ontology-bindings") for r in routes)
    assert any("upgrade-proposal" in r for r in routes)
    assert any("approve-upgrade" in r for r in routes)
