"""工作台只读选项表路由（WP29/J1）。

GET /api/v1/workbench/options —— 下发业务枚举（价格档位 / 门禁五态 / C 分支 /
SOW / 业务阶段）。只读、无副作用，任何已登录用户可取（选项不含客户信息）。
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from fde_api.auth.decorators import require_auth
from fde_api.workbench.options import options_payload

workbench_blueprint = Blueprint("workbench_options", __name__, url_prefix="/api/v1/workbench")


@workbench_blueprint.get("/options")
@require_auth
def list_options():
    return jsonify({"data": options_payload(), "error": None})
