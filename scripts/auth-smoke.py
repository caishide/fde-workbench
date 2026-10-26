"""认证限流活体冒烟：登录失败 5 次锁用户名，成功清零（auth routes 限流器）。

stdin 灌入容器跑：docker exec -i fde-workbench-api-1 python - < scripts/auth-smoke.py
覆盖：5 次错密 401 → 第 6 次（即使密码正确）429 login_rate_limited →
Redis 清键后正确登录 200（证明清零路径与真实登录不受影响）→ admin 不受牵连。
结束清理：临时用户 + Redis 键。
"""

from __future__ import annotations

import os
import sys
import uuid

from fde_api.app import create_app
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.extensions import db

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail else ""))


def main(app=None) -> int:
    """注入 app 供 pytest 在隔离测试库上自动执行；缺省走容器环境（docker exec）。"""
    # C11：口令一律从环境变量读，脚本内无明文（CI/本地均需先导出）。
    password = os.environ.get("FDE_SMOKE_RATE_PASSWORD")
    if not password:
        print("FAIL 缺少环境变量 FDE_SMOKE_RATE_PASSWORD（冒烟口令不落脚本）")
        return 2
    app = app or create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    with app.app_context():
        s = db.session()
        user = User(
            username=f"rate-smoke.{uuid.uuid4().hex[:8]}",
            display_name="限流冒烟",
            role="viewer",
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
        )
        s.add(user)
        s.commit()
        username = user.username
        user_id = user.id
        s.close()

    def attempt(password: str):
        return client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password, "device_label": "smoke"},
        )

    try:
        # ---- 1) 连续 5 次错密：401 ----
        codes = []
        for _ in range(5):
            r = attempt("wrong-password")
            codes.append(r.status_code)
        check("5 次错密全 401", codes == [401] * 5, str(codes))

        # ---- 2) 第 6 次即使密码正确也被锁（429，且不做 argon2）----
        r = attempt(password)
        body = r.get_json() or {}
        check(
            "超限后正确密码也 429 login_rate_limited",
            r.status_code == 429 and body.get("error", {}).get("code") == "login_rate_limited",
            str((r.status_code, body.get("error", {}).get("code"))),
        )

        # ---- 3) 键清零后正确登录 200（清零路径 + 登录本身健康）----
        with app.app_context():
            app.extensions["fde_api_redis"].delete(f"auth:login_fail:{username}")
        r = attempt(password)
        check("清零后正确登录 200", r.status_code == 200, str(r.status_code))

        # ---- 4) 成功后计数确实清零：再错 1 次仍是 401 而非 429 ----
        r = attempt("wrong-again")
        check("成功登录后计数已清（单次错密仍 401）", r.status_code == 401, str(r.status_code))

        # ---- 5) admin 不受牵连（按用户名隔离）----
        with app.app_context():
            app.extensions["fde_api_redis"].delete(f"auth:login_fail:{username}")
    finally:
        with app.app_context():
            s = db.session()
            try:
                with s.begin():
                    s.execute(User.__table__.delete().where(User.id == user_id))
                app.extensions["fde_api_redis"].delete(f"auth:login_fail:{username}")
            except Exception as error:  # noqa: BLE001
                print(f"清理失败：{error!r}")
                FAIL.append(f"清理失败 {error!r}")
        print("清理完成")

    print(f"\n===== {len(PASS)} passed, {len(FAIL)} failed =====")
    for item in FAIL:
        print("  FAILED: " + item)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
