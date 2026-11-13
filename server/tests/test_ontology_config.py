"""Ontology 开关配置测试（纯 Settings 校验，不依赖 MySQL）。"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from fde_api.config import Settings

# **kwargs 展开进 pydantic-settings 构造器无法被类型桩精确建模——与其他 Settings 测试同惯例
_BASE: dict[str, str] = {
    "database_url": "mysql+pymysql://u:p@127.0.0.1:3306/x",
    "redis_url": "redis://127.0.0.1:6379/2",
    "jwt_secret": "test-secret-with-at-least-thirty-two-characters",
}


def _make(**extra: object) -> Settings:
    return Settings(env="test", **_BASE, **extra)  # type: ignore[arg-type]


def test_ontology_disabled_by_default() -> None:
    settings = _make()
    assert settings.ontology_enabled is False
    assert settings.ontology_api_key is None


def test_ontology_enabled_requires_auth_material() -> None:
    with pytest.raises(ValidationError, match="FDE_ONTOLOGY"):
        _make(ontology_enabled=True)


def test_ontology_enabled_requires_base_url_and_org() -> None:
    """D10：I5 运行时调用必须带非空 org 上下文；base_url 空为配置错误（契约 §1）。"""
    with pytest.raises(ValidationError, match="FDE_ONTOLOGY"):
        _make(ontology_enabled=True, ontology_org_id="")
    with pytest.raises(ValidationError, match="FDE_ONTOLOGY"):
        _make(ontology_enabled=True, ontology_org_id="org-1", ontology_base_url=" ")


def test_ontology_enabled_with_material_ok() -> None:
    settings = _make(
        ontology_enabled=True,
        ontology_api_key=SecretStr("k"),
        ontology_signing_key=SecretStr("s"),
        ontology_org_id="org-1",
    )
    assert settings.ontology_enabled is True
    assert settings.ontology_org_id == "org-1"
    # 契约 §1 预留字段（M3 起）已声明
    assert settings.ontology_model_endpoint == ""
    assert settings.ontology_gate_dependency == ""
