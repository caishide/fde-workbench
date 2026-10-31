"""dispatch 服务层统一错误（对齐 GateServiceError / PaymentServiceError 惯例）。"""

from __future__ import annotations


class DispatchServiceError(Exception):
    """code + message + http_status，路由层原样透传（路由随 P0-1/P1 轮次落位）。"""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
