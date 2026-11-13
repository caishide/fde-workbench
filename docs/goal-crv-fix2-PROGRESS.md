# goal-crv-fix2 进度台账（剩余修复批次总循环）

- **工作树**：`D:/test/fde-wt-crv2`
- **任务书**：`docs/goal-crv-fix2-剩余批次总循环-任务书.md`
- **基线参照**：`docs/audit/全面代码审查报告-2026-11-13.md`（v1.0，基点 `35ffbea`）＋`docs/goal-crv-BLOCKED.md` §5 拍板

| 轮次 | 批次 | 覆盖范围 | 状态 | PR / SHA | 变异红→绿记录 |
|---|---|---|---|---|---|
| r1 | 批 A | `QR-001` / `QR-002` / `QR-003` / `QR-004` + `QR-018` | 已合并 | `#444` / `a8a2c25c` | 7 组全红→字节级还原核 sha256→25 passed |
| r2 | 批 C | `QR-041` / `QR-042` / `QR-043` / `QR-044` | 已合并 | `#451` / `f4cb5e9f` | 7 组全红→字节级还原核 sha256→4 passed + 168 邻域绿 |
| r3 | 批 D | `QR-055` / `QR-056`+`059` / `QR-057` / `QR-067` + 单步迁移 `d4b8e1f6a9c3` | 已验待合并 | 待填 | 5 组全红→字节级还原核 sha256→4 passed + 300 邻域绿 |
| r4 | 批 E | `QR-071` / `QR-072` + `QR-073`/宿主通道核销 | 待开工 | - | - |
| r5 | 批 G | `QR-133` / `QR-134` | 待开工 | - | - |
| r6 | 批 R7 | `QR-109` / `QR-110` / `QR-111` / `QR-112` / `QR-113` + 便携版 | 待开工 | - | - |
| r7 | 收口与部署 | 总报告销号节 + `BLOCKED`/`PROGRESS` + `AGENTS` bullet + 活体部署三验 | 待开工 | - | - |

---

## r1 批 A（权限·身份·项目闸，零迁移零新路由）

- **合并记录**：PR `#444` → squash `a8a2c25c`（4 个必需 CI job 全绿）。
- **修复明细**：
  1. `QR-001`（`server/src/fde_api/auth/routes.py::_login_fail_key`）：登录失败计数与清零键改调 `normalize_username(username)`（NFKC + strip + lower），大小写/全角/首尾空白变体共享同一限流桶。
  2. `QR-002`（`server/src/fde_api/auth/service.py::change_password` + `registration/service.py`）：`change_password` 在旧密验证后补 `_registration_state_gate(current_user)`，拦截 `suspended` / `rejected` / `pending_email` 改密换发新令牌对；`suspend_registration` 与 `review_registration(decision="reject")` 递增 `user.auth_version += 1` 使存量 15min JWT 立即 401 失效，同时保留 `/auth/refresh` 返回 `403 account_suspended` / `registration_rejected` 契约。
  3. `QR-003`（`server/src/fde_api/control/api_actions.py::_authorized`）：新增 `_target_project_id` 兼容 `agents.run_start` 的 `body.project_id`，将 `_require_run_start_scope_binding` 并入 `_authorized` 单点（propose 与 confirm 双侧必经），消除路径无 `{project_id}` 致先 403 死代码。
  4. `QR-004` + `QR-018`（`server/src/fde_api/projects/service.py::update_project` + `projects/quote_service.py::create_quote`）：PATCH `enterprise_code` 发生实质变更时复跑 `ensure_enterprise_channel`（H2 池内企业 / G4 商机保护期均拦 422）；`create_quote` 改为先 `for_update=True` 锁定并 `populate_existing` 重读 `Project` 后再跑 `ensure_enterprise_channel`；`projects/service.py` 1943 行 ≤ 1946 热点上限。
- **测试与变异证据**：NEW `server/tests/test_crv_batch_a.py`（9 例）+ `test_ai_run_proposal.py`（16 例）；7 组变异全红→还原 `sha256` 全绿。

---

## r2 批 C（公网写面与个保法留存期，零迁移零新路由）

- **合并记录**：PR `#451` → squash `f4cb5e9f`（4 个必需 CI job 全绿）。
- **修复明细**：
  1. `QR-041`（#1A，`server/src/fde_api/guidance/redaction.py::redact_text_detailed` + `diagnostics/service.py::capture_lead` + `diagnostics/claim_service.py::reveal_claimed_lead_contact`）：新增 `mask_pii: bool = True` 开关（默认仍掩码手机号/邮箱/固话），仅留资 `contact` 传 `mask_pii=False` 保留联系方式明文（企业名代号化与凭据 422 拦截恒在位）；受控读函数仅允许 `admin` 或已接受认领单本人读取并写 `diagnostic_lead_contact_revealed` 审计事件（事件 `changes` 零明文联系方式）。
  2. `QR-042`（#2A，`server/src/fde_api/diagnostics/service.py::_enforce_retention` + `claim_service.py` + `diagnostics/jobs.py`）：30 天 `expires_at` 读写懒检查——未认领且 `expires_at <= now` 的会话立即转 `expired` 并匿名化清空 `answers`/`assessment`/`report`/`lead_contact`/`subject_fingerprint`/`region_name`/`share_token_sha256`；续写返 `409 session_closed`、分享返 `404`、线索池排除、认领与裁定返 `409 lead_expired`、worker 跳过 AI 调用；已 `claimed` 会话保全。
  3. `QR-043`（`server/src/fde_api/registration/routes.py` + `commercial/routes.py`）：四入口注册、重发验证邮件与 legacy 企业注册三处将 `_ensure_surface_open` 移至限流器前，部署闸关闭时即使超限或 Redis 故障也恒返 **404 `not_found`**。
  4. `QR-044`（`server/src/fde_api/diagnostics/claim_service.py::get_claim` + `lead_routes.py`）：补 `ensure_enabled()` 与 `admin` / `claimant_user_id == actor.id` 归属校验，越权一律返 **404 `claim_not_found`**。
- **测试与变异证据**：NEW `server/tests/test_crv_batch_c.py`（4 组）+ 既有 168 例绿；7 组变异全红→还原 `sha256` 全绿。

---

## r3 批 D（资金商业面＋单步 Alembic 迁移 `d4b8e1f6a9c3`）

- **修复明细**：
  1. `QR-055`（`server/src/fde_api/commercial/models.py` + `commercial/service.py::activate_seat`）：`CommercialEntitlement` 增加 `CheckConstraint("seat_status <> 'active' OR seat_expires_at IS NOT NULL", name="ck_commercial_entitlements_active_requires_expiry")`，`activate_seat` 服务层必填 `expires_at`（缺失返 `400 invalid_request`）；换代 9 份商业/多租户测试夹具补显式 `expires_at`。
  2. `QR-056` + `QR-059`（`server/src/fde_api/commercial/attribution_service.py::record_settlement` + `commercial/models.py`）：对 `CommercialRevenueLedger` 加 `with_for_update()` 锁；`entry.delivery_package_id` 或 `row.matched_delivery_package_id` 缺失或不等一律返 `409 ledger_package_mismatch`（对齐 `regional_service.py`）；同一笔 `project_share` 科目行不可被多条商机重复引用结算（服务层返 `409 ledger_already_settled` + DB 部分唯一索引 `uq_commercial_opportunities_settled_ledger` 兜底）。
  3. `QR-057`（`server/src/fde_api/commercial/models.py` + `conftest.py`）：`CommercialRoleAssignment.source_uri` 由 `String(255)` 扩为 `String(500)`（对齐服务层 `_URI_MAX = 500`），并在 `conftest.py` `cleanup_models` 补列 `CommercialRoleAssignment` 防止 RESTRICT 清理冲突。
  4. `QR-067`（#3A，`server/src/fde_api/commercial/admin_routes.py`）：`/fee-configs`、`/split-rules`、`/opportunity-rules`、`/regional-sale-gate` 四个 GET 治理读面接入 `is_platform_operator` 门禁（非平台管理操作者返 `403 commercial_admin_required`）。
  5. **单步迁移与口径同步**：新增唯一迁移 `server/migrations/versions/d4b8e1f6a9c3_commercial_batch_d_hardening.py`（接 `c8e2a6f0b9d4`，`74→75` 单头），同步 `server/tests/test_migrations.py::HEAD_REVISION` 与 `len(known) == 75`、`docs/audit/v3-workbench-inventory.json`（`check_archify_diagram_freshness.py` PASS）。
- **测试与变异证据**：
  - NEW `server/tests/test_crv_batch_d.py`（4 组）+ `test_migrations.py`（28 例）+ 商业/多租户 17 套件（272 例）= **304 passed** 全绿。
  - 变异五连（`try/finally` 字节还原核对 `sha256`）：
    - `M1_QR055_service_expires_at_required`：red=True → 还原 `sha256=bab938618d97b9d4`
    - `M2_QR056_packageless_ledger_check`：red=True → 还原 `sha256=864bf3fbbd2a820b`
    - `M3_QR059_duplicate_ledger_settlement_check`：red=True → 还原 `sha256=864bf3fbbd2a820b`
    - `M4_QR057_migration_column_width_revert`：red=True → 还原 `sha256=41ad63b871bc363a`
    - `M5_QR067_platform_operator_read_gate`：red=True → 还原 `sha256=9eb8dffe7cf0ca70`
    - 还原终验：`4 passed`；`ruff` 0 告警；`check-python-types.py` `277 occurrences / 102 distinct` 零新增。
