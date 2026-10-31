# goal-r3 · 派单引擎轮次报告（2026-10-31）

> 第三轮，输入：goal-r2 报告 + 设计文档 v1.0 补齐版 + 代码实测。
> 本轮 Goal（阶段 1，簇②收尾）：**P0-1 交付包服务层（§2.3 canonical_json 快照冻结 + §2.5 八态机）与 P0-2 package_access 第三语义 + §9.5 隔离基线四条全部落可判定用例——至此 §8.3 P0 8 项全部落地。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | B6·P0-1 服务层 | 发布后改 solution/quote 不回写快照；8 态全迁移用例（§8.3 P0-1 判据 / §2.3/§2.5） | 表与约束 r1 已落，但**零服务逻辑**：无 create/publish/withdraw 函数、snapshot_hash 恒空、状态列不可迁 | **P0** | `dispatch/packages.py`（canonical_json/发布冻结/状态机/§9.3 交接） |
| 2 | B1/B6·P0-2 | `package_access` 第三语义 + 跨主体 100% 拒绝基线（§8.3 P0-2 判据 / §9.2/§9.5） | 表零存在；无 dispatch 路由；非成员对派单域零可见性机制 | **P0** | 表 + `dispatch/access.py` + `dispatch/routes.py` + §9.5 四条基线 |
| 3 | B3 白名单第二处 | `system_configuration.py` PUBLIC_FIELDS（§8 B3 列 2 处之一） | r2 已按「只读节不进可写集」实现（留注：设计原文写「加进 PUBLIC_FIELDS」与「锁定不可运行时改」矛盾，r2 采只读节口径并已验证） | 已闭（r2） | 无新增动作，报告复核确认 |
| 4 | C5/C8 部分 | 时间常数唯一引用源；package_code 生成规则（§6.2/§2.2） | response_window_hours 创建包时引用 DISPATCH_CONSTANTS ✓；package_code 无生成规则 | P0 收尾 | `PKG-{项目码尾段}-{轮次}` 规则落位 |
| 5 | H5 口径 | AGENTS.md=实测 | 本轮后 83 表 / 12 revision / head `f4b8c2d6e3a1` / 路由 218 / ENTRIES 60 | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A3 收款（`update_payment` 本轮零改动，r2 钩子回归 12 例全绿 ✓）；A5 门禁（decide_gate 本轮零改动，r1 双 403 钉子全绿 ✓）；A8 台账与桥（`scripts/bridge-poll.mjs` 未触碰 ✓）。

**实施中的三处留注（默认口径施工，不停工）**：
- **留注⑥（onsite 派生 + 席位金额物化）**：① `onsite_required` 按 schedule 文本关键词（现场/到场/驻场/驻点）启发式派生——§4.6 只说「从 schedule 派生」，规则化随 P1-2 场景引擎收口；② 交付包 API 禁 join quotes（§9.2 纪律①），「交付方席位 40% 金额」显示义务因此必须落库物化——新增 `delivery_packages.delivery_seat_amount` 列，发布时按当时报价（final_amount，未回填回落 quote_high）×40% 冻结。
- **留注⑦（候选视图与快照的时差）**：`serialize_package_whitelist` 的文本字段读 solution 实时值，而 `snapshot_hash` 冻结发布时刻——发布后改 solution 且未撤回时，候选视图文本与仲裁哈希所锚定的版本存在时差。§2.3 规则 1 本意是「发布后不回写、要改先撤回」，时差窗口=违规操作窗口；完整冻结内容服务（发布时同时落 export_sow 快照）随 P1 轮补，降级路径 §11.1 已有 export_sow 线下传递。
- **留注⑧（§9.3 交接执行人）**：接单人本人在交接前无 `can_manage`，`add_project_member` 的 actor 取**项目管理位 leader**（发布侧）执行——零新增鉴权路径的口径不变（复用同一服务与同一权限判定）。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p0-package-service`，1 个迁移 + 10 个文件）：

1. `dispatch/models.py`：`PackageAccess`（`Unique(package_id, user_id, role)` + role Check lead/seller/delivery/audit + granted_at/revoked_at/granted_by——§9.2 粒度与可撤销）；`DeliveryPackage.delivery_seat_amount` Numeric(12,2)（留注⑥②）。
2. `dispatch/packages.py`（P0-1 服务层）：
   - `canonical_json`/`compute_snapshot_hash`：§2.3 规则逐条（键字典序、ensure_ascii=False、紧凑分隔、Decimal→str、None→null、required_modules 先排序）；
   - `create_package`（draft：方案 active + 同项目报价 + 平台侧角色 + PK=方案 id + `PKG-{项目码尾段}-{轮次:02d}` 编码 + 模块/行业/onsite 派生落库 + `response_window_hours` 引用 §6.2 常数）；
   - `publish_package`（发布前置=报价 finalized（422）；非 draft 来源（withdrawn/rejected/expired）= round+1 + 新编码 + 新哈希（§2.3 规则 1/3 版本对）；哈希一次冻结；席位金额物化；对候选授 `delivery` 只读（§9.2 发布即授权）；留痕 `delivery_package_published` 含哈希与候选数）；
   - `transition_package`（§2.5 八态机通用迁移表 TRANSITIONS + 每迁移留痕；`withdraw` 带「本轮进行中 offer」防御守卫 409）；
   - `accept_package`（accept 迁移 + §9.3 交接：leader 为 actor 调 `add_project_member(member)`，stale_version 重读重试一次，重复成员幂等）。
3. `dispatch/access.py`（P0-2）：`grant/revoke/has/require_package_access`（admin 平台域放行；无授权 **404 不泄露存在性**）+ `list_accessible_package_ids`（admin 全量 / 其余授权去重）+ `serialize_package_whitelist`（§9.2 白名单 12 项 + 交付方席位金额 + 状态面；**显式 schema，禁 `__dict__` 直出**——纪律②）。
4. `dispatch/routes.py`（6 路由）：list/detail（守卫前置——纪律③）、create/publish/withdraw（平台侧 403 守卫）、accept（平台侧或**被指派人本人 + delivery 授权**双门槛；冒名接单 403）。响应体全部走白名单 schema。
5. `app.py` 注册 dispatch 蓝图；`control/api_catalog.py` ENTRIES +6（54→60）。
6. 迁移 `f4b8c2d6e3a1`（down_revision `e3a7c5d9f2b8`）：package_access 表 + delivery_seat_amount 列；`tests/conftest.py` 清理序补 PackageAccess（先于包）；`test_migrations.py` HEAD 常量。
7. 测试 `tests/test_dispatch_p0_r3.py` 15 用例（见第三节）。

**影响面与回滚**：纯增量（1 表 + 1 列 + 1 蓝图 + 2 服务模块）；既有路径零改动（r2 钩子与 r1 门禁逻辑未触碰）。回滚 = `alembic downgrade e3a7c5d9f2b8` + revert PR（dispatch 蓝图 404 即回滚完成）。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.3 P0-1 判据「发布后改 solution/quote 不回写快照」 | ✅ `test_snapshot_frozen_after_publish`（哈希与席位金额双冻结断言 + 「用现在的数据重算必然≠冻结值」可证伪断言） |
| §8.3 P0-1 判据「8 态状态机全迁移」 | ✅ `test_eight_state_machine_full_walk`（主路径 draft→published→offered→assigned→accepted；拒绝→重发 round+1 新码新哈希；offered→expired→人工重发；published→withdrawn→重发；非法迁移 409）+ `test_withdraw_blocked_while_offer_in_flight`（防御守卫） |
| §2.3 canonical_json 规则 | ✅ `test_canonical_json_rules`（中文字面量、Decimal→str、null、键序逐字符比对） |
| 发布前置 | ✅ `test_publish_requires_finalized_quote`（422 + 状态停留 draft）+ `test_publish_grants_candidate_read_access` |
| §8.3 P0-2 判据「跨主体访问 100% 拒绝」（§9.5 基线①） | ✅ `test_cross_principal_access_denied`（4 路由 × 陌生人参数化：403/404，列表空） |
| §9.5 基线② 响应体字段断言 | ✅ `test_package_response_field_whitelist`（键集精确等值；报价/收款/真名片段零出现；席位金额=20000×40%=8000；client_city=代号第三段） |
| §9.5 基线③ 静态检查 | ✅ `test_static_isolation_rules`（access.py/routes.py 源级禁 Quote/Payment/Contract 引用；全 dispatch 包禁裸 `session.query(`） |
| §9.5 基线④ 渗透用例 | ✅ `test_penetration_cases`（冒名接单 403；快照篡改无入口——包无 PUT/PATCH → 405；撤销后重放 404、显式 re-grant 才复活） |
| §9.3 接单交接 | ✅ `test_accept_handover_adds_project_member` + `test_platform_user_can_publish_and_candidate_accepts`（候选人本人经 API 接单全链路 + ProjectMember(member) 落库） |
| 全量 `npm run test:server` | ✅ **1372 passed / 6 skipped / 0 failed**（14:19；含迁移链全量 up/down + `alembic check`） |
| `npm run test:desktop` / `typecheck` | ✅ typecheck 零错误；vitest 首跑 653/654（1 例 navigation 重定向时序 flake，与本轮零改动的桌面端无关——单文件复跑 42/42、全量复跑 **654/654** 双确认） |

**口径数字重测（H5，本轮后 vs 设计文档附录 A 快照）**：

| 口径 | 附录 A 快照 | 本轮实测（改动后） | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **83**（82+package_access） | §8.1「新增 8 张」进度 **7/8**（余 disputes） |
| 迁移 revision | 9 / head `a9c3f1d8e2b4` | **12 / head `f4b8c2d6e3a1`** | 派单迁移第 3 个，接链正确 |
| 蓝图路由 | 212 | **218**（+6 dispatch 路由） | 首次正向漂移（新 API），P1-3 一致性测试随后 |
| api_catalog ENTRIES | 54 | **60**（+6） | 与新路由一一对应 |
| 服务端 pytest | — | **1372 passed + 6 skipped**（+15 派单 r3 用例） | — |
| 桌面 vitest | — | 654（零改动） | — |

**镜像与正式库**：合并后 main 重建镜像 + recreate + `alembic upgrade head`（红线纪律），结果补记于 PR。

**失败与未完成项（如实）**：r3 用例首轮 3 失败——① routes 空候选列表校验把 `()` 判非 list（publish 400 早于角色守卫）；② offer_in_flight 测试场景构造错误（offered 态先被状态机拦，属测试错非代码错，改为 published+本轮 offer 的防御场景）；③ §9.3 交接以接单人为 actor 调 get_project → 403（发现真缺陷：交接执行人应为 leader，已修复并加留注⑧）。修复后 33/33 派单用例与全量绿。

## 四、下一轮建议

1. **P0 收官判据复核轮（goal-r4 建议主攻 P1-1 + P1-3）**：P0-1/P0-2 的服务与基线已全绿，但 §8.8 开池闸③「负面清单 7 条防护测试」依赖 P1-2 撮合核心（规则表 A-6 反例用例）。建议 goal-r4 = **P1-1 offer_service**（乐观锁 409 stale_version 并发接单用例，§6.3）+ **P1-3 蓝图注册一致性测试**（现成 6 路由即素材）+ P1-5 seeds 三处（gates.json 扩 + dispatch_cities.json + acceptance_metrics.json，冷启动城市口径切换的依赖）。
2. **goal-r5 = P1-2 撮合核心（L 级主战役）**：Stage A 五资格门 + 场景裁决 + Stage B 权重（active_rule_snapshot 已就绪）+ match_breakdown（§4.8 schema）+ 负面清单 7 条反例——静态依赖全部齐备。
3. **风险**：① 候选视图与快照时差（留注⑦）在 P1-2 前建议先补「发布时落 export_sow 快照」；② `disputes` 表（§8.1 第 8 张）随 T+30 对账（E5）落位；③ offer_service 的并发用例需要双会话真并发或线程内 flush 序构造（本仓无分布式锁，乐观锁模式已有先例）。
4. **待拍板（附录 B）**：无新增阻塞；留注⑥⑦⑧与 r2 的③④⑤一并列入收口报告待签字清单。
5. **文档修订建议（附录 A 时效）**：表 83 / 12 revision / head `f4b8c2d6e3a1` / 路由 218 / ENTRIES 60；§8.1 表数进度 7/8；B3 白名单「两处」中 PUBLIC_FIELDS 处按 r2 只读节口径改写表述。
