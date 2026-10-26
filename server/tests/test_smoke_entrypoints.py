"""B6/C11：三个 smoke 脚本的 pytest 自动入口。

- 自动执行：把脚本 main() 指向**隔离测试库**的 app（conftest 的
  resolve_test_database_url 已断言库名必须 *_test），合成数据 + 随机口令，
  绝不触碰开发/生产库。
- 口令外置（C11）：脚本内无明文口令，运行时从环境变量读取；本套件为每次
  运行生成随机口令注入。
- 手工模式保留：docker exec 场景先 export 对应 FDE_SMOKE_*_PASSWORD 即可。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest

from fde_api.app import create_app

from conftest import seed_reference_data

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

_LOADED: dict[str, ModuleType] = {}


def _load_script(stem: str) -> ModuleType:
    """按路径加载 scripts/ 下的冒烟脚本（文件名含连字符，不能常规 import）。"""
    if stem not in _LOADED:
        path = SCRIPTS_DIR / f"{stem}.py"
        spec = importlib.util.spec_from_file_location(f"fde_smoke_{stem.replace('-', '_')}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _LOADED[stem] = module
    return _LOADED[stem]


def _random_password() -> str:
    return f"Smoke!{uuid4().hex[:16]}A9"


@pytest.fixture
def smoke_app(settings):
    """隔离测试库上的 app（settings 来自 conftest，库名断言 *_test）。"""
    application = create_app(settings)
    application.config.update(TESTING=True)
    return application


def test_smoke_scripts_contain_no_plaintext_passwords():
    """C11 回归钉：口令明文不许回流脚本。"""
    for name in ("auth-smoke.py", "gate-engine-smoke.py", "commercial-smoke.py"):
        text = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        assert "Smoke!2026" not in text, name
        assert "FDE_SMOKE_" in text, f"{name} 缺少环境变量口令入口"


def test_smoke_scripts_refuse_to_run_without_password(monkeypatch):
    """缺环境变量时显式拒绝（exit 2），不允许悄悄用内置默认口令。"""
    monkeypatch.delenv("FDE_SMOKE_RATE_PASSWORD", raising=False)
    auth_smoke = _load_script("auth-smoke")
    assert auth_smoke.main() == 2


def test_auth_rate_limit_smoke_against_isolated_test_db(
    smoke_app, monkeypatch, settings
):
    monkeypatch.setenv("FDE_SMOKE_RATE_PASSWORD", _random_password())
    auth_smoke = _load_script("auth-smoke")
    assert auth_smoke.main(app=smoke_app) == 0


def test_gate_engine_smoke_against_isolated_test_db(
    smoke_app, monkeypatch, settings
):
    monkeypatch.setenv("FDE_SMOKE_GATE_PASSWORD", _random_password())
    gate_smoke = _load_script("gate-engine-smoke")
    # 先行 db_session 测试的 teardown 会清空 module_catalog；建项目校验需要它
    seed_reference_data(settings.database_url)
    assert gate_smoke.main(app=smoke_app, settings=settings) == 0


def test_commercial_smoke_against_isolated_test_db(
    smoke_app, monkeypatch, settings
):
    monkeypatch.setenv("FDE_SMOKE_COMMERCIAL_PASSWORD", _random_password())
    commercial_smoke = _load_script("commercial-smoke")
    # 同 gate 冒烟：module_catalog 先行测试后已被清，先重灌（幂等）
    seed_reference_data(settings.database_url)
    # 冒烟依赖「标准 FDE 项目」模板（P5 派生源）且 loader 需要一个 admin；
    # 隔离测试库先补齐这两样（幂等），再跑冒烟。
    from fde_api.auth.models import User
    from fde_api.auth.passwords import hash_password
    from fde_api.extensions import db

    with smoke_app.app_context():
        session = db.session()
        try:
            session.add(
                User(
                    username=f"smoke-seed-admin.{uuid4().hex[:8]}",
                    display_name="冒烟种子",
                    role="admin",
                    password_hash=hash_password(_random_password()),
                    must_change_password=False,
                    is_active=True,
                )
            )
            session.commit()
        finally:
            session.close()
    _load_script("load_fde_template").main(app=smoke_app)
    assert commercial_smoke.main(app=smoke_app, settings=settings) == 0
