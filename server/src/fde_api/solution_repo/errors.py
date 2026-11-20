"""solution_repo 错误面（AF3-WP1）：14 码闭集 + 域错误类型。

闭集纪律沿 AE1 ``ActionExecutionError`` 同款（Q8 口径）：不运行时扩码——
闭集外码在构造层即拒；错误面本身不得成为扩码通道。AF3 契约件随 WP2/WP3
冻结时对本表对齐（20 号 §3：WP0 契约位先钉、随任务集冻结扩登）。
"""
from __future__ import annotations

# code → HTTP 状态。403 面＝越权/保护路径（安全拒绝）；422 面＝请求形状或
# 仓状态不满足；409 面＝状态冲突；500 面＝Git 执行层诚实失败（不冒充成功）。
ERROR_STATUS: dict[str, int] = {
    "validation_failed": 422,
    "not_found": 404,
    "permission_revoked": 403,
    "tool_not_allowed": 403,            # git_boundary 闭集外 / human_only 面（S-AF3-10）
    "protected_path_rejected": 403,     # 四拒（S-AF3-01/02/03）——读取面同拒（.git/config 可泄露配置）
    "path_escape_rejected": 422,        # S-AF3-04
    "outside_allow_roots": 422,         # S-AF3-07
    "symlink_escape_rejected": 422,     # S-AF3-05
    "oversize_patch": 422,              # S-AF3-06（WP2 接线时经本码出信封）
    "dirty_tree_conflict": 409,         # S-AF3-08：不进他人 dirty tree
    "binding_exists": 409,              # 同 org+repo+branch 重复绑定
    "base_mismatch": 409,               # AF3-WP2：plan.base_commit != 应用时刻 HEAD（修改源内容后旧批准失效）
    "idempotency_mismatch": 409,        # AF3-WP2：同 patch_id 重放但 plan 内容指纹不一致（AE1 同构）
    "acceptance_tests_intact_violation": 403,  # AF3-WP3：基线验收测试被 Patch 修改/删除（05 §2.1 T4「验收测试不能被 Agent 删除」）
    "git_operation_failed": 500,        # Git 执行层失败（结构化拒绝信息随 details）
}


class SolutionRepoError(Exception):
    """域错误（同 ``ActionExecutionError`` 形；缺省 status 取闭集注册表）。"""

    def __init__(self, code: str, message: str, status: int | None = None, details: dict | None = None):
        if code not in ERROR_STATUS:
            raise ValueError(f"AF3 solution_repo 错误码闭集外：{code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status if status is not None else ERROR_STATUS[code]
        self.details = details
