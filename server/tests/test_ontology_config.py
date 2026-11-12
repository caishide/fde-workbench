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


def test_ontology_enabled_with_material_ok() -> None:
    settings = _make(
        ontology_enabled=True, ontology_api_key=SecretStr("k"), ontology_signing_key=SecretStr("s")
    )
    assert settings.ontology_enabled is True
