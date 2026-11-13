# goal-crv-fix2 进度台账（剩余修复批次总循环）

- **工作树**：`D:/test/fde-wt-crv2`
- **任务书**：`docs/goal-crv-fix2-剩余批次总循环-任务书.md`
- **基线参照**：`docs/audit/全面代码审查报告-2026-11-13.md`（v1.0，基点 `35ffbea`）＋`docs/goal-crv-BLOCKED.md` §5 拍板

| 轮次 | 批次 | 覆盖范围 | 状态 | PR / SHA | 变异红→绿记录 |
|---|---|---|---|---|---|
| r1 | 批 A | `QR-001` / `QR-002` / `QR-003` / `QR-004` + `QR-018` | 已验待合并 | 待填 | 7 组全红→字节级还原核 sha256→25 passed |
| r2 | 批 C | `QR-041` / `QR-042` / `QR-043` / `QR-044` | 待开工 | - | - |
| r3 | 批 D | `QR-055` / `QR-056`+`059` / `QR-057` / `QR-067` + 单步迁移 | 待开工 | - | - |
| r4 | 批 E | `QR-071` / `QR-072` + `QR-073`/宿主通道核销 | 待开工 | - | - |
| r5 | 批 G | `QR-133` / `QR-134` | 待开工 | - | - |
| r6 | 批 R7 | `QR-109` / `QR-110` / `QR-111` / `QR-112` / `QR-113` + 便携版 | 待开工 | - | - |
| r7 | 收口与部署 | 总报告销号节 + `BLOCKED`/`PROGRESS` + `AGENTS` bullet + 活体部署三验 | 待开工 | - | - |

---

## r1 批 A（权限·身份·项目闸，零迁移零新路由）

- **修复明细**：
  1. `QR-001`（`server/src/fde_api/auth/routes.py::_login_fail_key`）：登录失败计数与清零键改调 `normalize_username(username)`（NFKC + strip + lower），大小写/全角/首尾空白变体共享同一限流桶。
  2. `QR-002`（`server/src/fde_api/auth/service.py::change_password` + `registration/service.py`）：`change_password` 在旧密验证后补 `_registration_state_gate(current_user)`，拦截 `suspended` / `rejected` / `pending_email` 改密换发新令牌对；`suspend_registration` 与 `review_registration(decision="reject")` 递增 `user.auth_version += 1` 使存量 15min JWT 立即 401 失效，同时保留 `/auth/refresh` 返回 `403 account_suspended` / `registration_rejected` 契约。
  3. `QR-003`（`server/src/fde_api/control/api_actions.py::_authorized`）：新增 `_target_project_id` 兼容 `agents.run_start` 的 `body.project_id`，将 `_require_run_start_scope_binding` 并入 `_authorized` 单点（propose 与 confirm 双侧必经），消除路径无 `{project_id}` 致先 403 死代码。
  4. `QR-004` + `QR-018`（`server/src/fde_api/projects/service.py::update_project` + `projects/quote_service.py::create_quote`）：PATCH `enterprise_code` 发生实质变更时复跑 `ensure_enterprise_channel`（H2 池内企业 / G4 商机保护期均拦 422）；`create_quote` 改为先 `for_update=True` 锁定并 `populate_existing` 重读 `Project` 后再跑 `ensure_enterprise_channel`；`projects/service.py` 1943 行 ≤ 1946 热点上限。
- **测试与变异证据**：
  - NEW `server/tests/test_crv_batch_a.py`（9 例）+ `test_ai_run_proposal.py` 源钉更新（16 例）+ 邻域回归全绿。
  - 变异七连（`try/finally` 字节还原核对 `sha256`）：
    - `M1_QR001_auth_routes_raw_username`：2 failed → 还原 `sha256=75872a1eef72`
    - `M2_QR002_change_password_drop_state_gate`：3 failed → 还原 `sha256=30aec1935011`
    - `M2b_QR002_suspend_drop_auth_version_bump`：1 failed → 还原 `sha256=7bcbe5bd1c63`
    - `M3a_QR003_target_project_id_ignore_agents_body`：1 failed → 还原 `sha256=bb426fdf90b6`
    - `M3b_QR003_drop_scope_binding_gate`：1 failed → 还原 `sha256=bb426fdf90b6`
    - `M4_QR004_projects_patch_drop_channel_guard`：1 failed → 还原 `sha256=61176abf42c5`
    - `M5_QR018_quote_drop_for_update_lock`：1 failed → 还原 `sha256=af0e0e2dbeb2`
    - 还原终验：`25 passed`；`ruff` 0 告警；`check-python-types.py` `277 occurrences / 102 distinct` 零新增。
