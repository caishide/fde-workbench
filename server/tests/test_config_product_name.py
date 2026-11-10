"""CR-046：FDE_PRODUCT_NAME env 覆写链路钉（validation_alias 单点）。

回归背景：无 alias 时 pydantic-settings 的 env_prefix 把生效键拼成
FDE_FDE_PRODUCT_NAME（全树零记载的死键），README/.env.example/AGENTS 六处
承诺的 FDE_PRODUCT_NAME 覆写通道静默失效——本文件把「env→Settings 生效」
钉成测试事实。
"""
from __future__ import annotations

from fde_api.config import DEFAULT_PRODUCT_NAME, Settings


def _make_settings() -> Settings:
    # _env_file=None＋显式 redis_url/jwt_secret：CI 无 .env 也能构造
    # （test_config 同款必填面）。type: ignore＝pydantic mypy 插件把
    # validation_alias 字段合成进 __init__ 形参面，具名调用被误报缺参
    # （字段实有 Field 默认值，运行时零影响）——官方闸实测。
    return Settings(  # type: ignore[call-arg]  # pydantic-plugin alias synthesis
        _env_file=None,
        env="test",
        database_url="postgresql+psycopg://fde:pw@127.0.0.1:15432/fde_workbench_test",
        redis_url="redis://127.0.0.1:16379/2",
        jwt_secret="test-secret-with-at-least-thirty-two-characters",
    )


def test_env_override_changes_product_name(monkeypatch) -> None:
    monkeypatch.setenv("FDE_PRODUCT_NAME", "覆写产品名XYZ")
    settings = _make_settings()
    assert settings.fde_product_name == "覆写产品名XYZ"


def test_without_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.delenv("FDE_PRODUCT_NAME", raising=False)
    monkeypatch.delenv("FDE_FDE_PRODUCT_NAME", raising=False)
    settings = _make_settings()
    assert settings.fde_product_name == DEFAULT_PRODUCT_NAME


def test_legacy_double_prefix_key_is_dead(monkeypatch) -> None:
    """历史事故键 FDE_FDE_PRODUCT_NAME 不再生效（validation_alias 接管后）。"""
    monkeypatch.setenv("FDE_FDE_PRODUCT_NAME", "FROM_DOUBLE_KEY")
    monkeypatch.delenv("FDE_PRODUCT_NAME", raising=False)
    settings = _make_settings()
    assert settings.fde_product_name == DEFAULT_PRODUCT_NAME


def test_short_key_wins_over_double_key(monkeypatch) -> None:
    monkeypatch.setenv("FDE_PRODUCT_NAME", "FROM_SHORT_KEY")
    monkeypatch.setenv("FDE_FDE_PRODUCT_NAME", "FROM_DOUBLE_KEY")
    settings = _make_settings()
    assert settings.fde_product_name == "FROM_SHORT_KEY"
