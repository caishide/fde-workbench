"""智能体凭据管理面（E11 实施轮，2026-11-13）。

## 为什么有这个模块

事实盘点发现：`agent_credentials` 表（`agents/models.py:223-236`）**没有任何
HTTP 路由**——全 `server/src` 搜 `AgentCredential(` 只命中模型定义、`service.py`
读取、`agents/seeds.py` 写 `credential_ref`；唯一创建点是脚本
`scripts/simulation/sandbox_real_e2e.py:106`。后果是：

- 种子 agent（`server/seeds/agents.json`）的 `credential_ref` **全为 null**；
- `agents/service.py:219`（`_unavailability`）先判 `credential_missing`
  ⇒ run 发起直接 **409 `agent_unavailable`**，**连执行链都进不去**；
- 裸机不可复现（只有跑过一次本地脚本才有凭据行）。

本模块提供**正规管理入口**：平台管理操作者（`is_platform_operator`：平台身份
＋ system_operator AI 档）可写入/列出/删除凭据行。

## 不可放宽的边界

1. **只存密文，绝不回显**：明文只在写入瞬间进 Fernet，落库的是密文；
   任何序列化路径只出 `credential_configured: bool`，不出密文、更不出明文。
2. **凭据名只登记不外发**：凭据名会进沙箱 env（`FDE_AGENT_<NAME>`），因此
   名字只允许字母数字与下划线，且长度有界（防 env 注入与超长）。
3. **平台管理面只认平台身份**（沿 M3b 批次 ①-a 单一判定 `is_platform_operator`）：
   企业身份即使被显式授予 `system_operator` AI 档也不得写凭据。
4. **不代发起 run**：本模块只管凭据行，绝不触碰 run 发起路径（H4）。
5. **不留明文痕迹**：不写日志、不进 operation_events 明文字段。

加密先例沿用 `control/model_preferences.py::_cipher`（同款 Fernet 密钥派生：
`FDE_MODEL_CREDENTIAL_KEY`，缺省派生自 `jwt_secret`）。
"""
from __future__ import annotations

import re
from typing import Any

from cryptography.fernet import Fernet
from flask import current_app
from sqlalchemy import select

from fde_api.agents.models import AgentCredential
from fde_api.auth.models import User
from fde_api.control.access import is_platform_operator
from fde_api.errors import error_response
from fde_api.extensions import db

# 凭据名允许字符：字母数字与下划线（会进 env 名 `FDE_AGENT_<NAME>`）。
CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,120}$")

# 明文长度上限（防超大 payload 与意外塞入大文件）。
PLAINTEXT_MAX_CHARS = 8000


class CredentialsError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _cipher() -> Fernet:
    """Fernet 构造（与 `control/model_preferences.py::_cipher` 同款密钥派生）。"""
    import os
    from hashlib import sha256
    from base64 import urlsafe_b64encode

    key = current_app.config.get("MODEL_CREDENTIAL_KEY") or os.environ.get(
        "FDE_MODEL_CREDENTIAL_KEY", ""
    )
    if not key:
        key = urlsafe_b64encode(sha256(current_app.config["SETTINGS"].jwt_secret.encode()).digest())
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as error:
        raise CredentialsError(
            "credential_storage_unavailable", "服务端尚未配置凭据加密，暂不能保存凭据。", 503
        ) from error


def _require_platform_operator(user: User) -> None:
    """平台管理面只认平台身份 ＋ system_operator AI 档（M3b 批次 ①-a 单一判定）。"""
    if not is_platform_operator(user):
        raise CredentialsError("forbidden", "当前账号无权配置智能体凭据。", 403)


def _validate_name(raw: Any) -> str:
    if not isinstance(raw, str):
        raise CredentialsError("invalid_credential", "凭据名必须是字符串。", 400)
    name = raw.strip()
    if not CREDENTIAL_NAME_PATTERN.match(name):
        raise CredentialsError(
            "invalid_credential",
            "凭据名只允许字母、数字与下划线，长度 1–120。",
            400,
        )
    return name


def _validate_plaintext(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise CredentialsError("invalid_credential", "凭据明文不能为空。", 400)
    if len(raw) > PLAINTEXT_MAX_CHARS:
        raise CredentialsError(
            "invalid_credential", f"凭据明文过长（上限 {PLAINTEXT_MAX_CHARS} 字符）。", 400
        )
    return raw


def serialize_credential(item: AgentCredential) -> dict[str, Any]:
    """序列化：**只出「有没有配」与名字，绝不出密文/明文**。"""
    return {
        "id": item.id,
        "name": item.name,
        "credential_configured": bool(item.credential_ciphertext),
        "created_by_user_id": item.created_by_user_id,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


def list_credentials(*, actor: User) -> list[dict[str, Any]]:
    _require_platform_operator(actor)
    session = db.session()
    try:
        rows = session.scalars(
            select(AgentCredential).order_by(AgentCredential.name)
        ).all()
        return [serialize_credential(row) for row in rows]
    finally:
        session.close()


def save_credential(*, actor: User, payload: dict[str, Any]) -> dict[str, Any]:
    """写入/覆盖一条凭据（同名即更新，明文只在本次请求内存中出现）。"""
    _require_platform_operator(actor)
    allowed = {"name", "credential", "id"}
    if not payload or set(payload) - allowed:
        raise CredentialsError("invalid_credential", "凭据参数无效。", 400)
    name = _validate_name(payload.get("name"))
    plaintext = _validate_plaintext(payload.get("credential"))

    ciphertext = _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")

    session = db.session()
    try:
        item = session.scalar(select(AgentCredential).where(AgentCredential.name == name))
        if item is None:
            item = AgentCredential(
                name=name,
                credential_ciphertext=ciphertext,
                created_by_user_id=actor.id,
            )
            session.add(item)
        else:
            item.credential_ciphertext = ciphertext
            item.created_by_user_id = actor.id
        session.commit()
        return serialize_credential(item)
    finally:
        session.close()


def delete_credential(*, actor: User, name: str) -> dict[str, Any]:
    """删除一条凭据（不返回密文）。"""
    _require_platform_operator(actor)
    key = _validate_name(name)
    session = db.session()
    try:
        item = session.scalar(select(AgentCredential).where(AgentCredential.name == key))
        if item is None:
            raise CredentialsError("credential_not_found", "凭据不存在。", 404)
        session.delete(item)
        session.commit()
        return {"deleted": key}
    finally:
        session.close()


def error_response_for(error: CredentialsError):
    return error_response(error.code, error.message, error.status, None)


__all__ = [
    "CREDENTIAL_NAME_PATTERN",
    "CredentialsError",
    "delete_credential",
    "error_response_for",
    "list_credentials",
    "save_credential",
    "serialize_credential",
]
