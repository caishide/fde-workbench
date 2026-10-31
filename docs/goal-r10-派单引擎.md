# goal-r10 · 派单引擎轮：C7 混合模式自动转换 job

- 日期：2026-10-31
- 分支：`feat/dispatch-r10-c7-job`（自 fork/main `1337863`，goal-r9 之后）
- 输入：goal-r9 报告/台账二十一节登记的工程侧最后剩余项——C7 混合模式自动转换 job（assign 24h 超时→转 claim，挂 dispatch.maintenance 节流框架）
- 迁移：**零迁移**（head 仍 `c5d7e9f1a3b7`；无新路由，ENTRIES 不变）

## 一、差距清单

| 能力项 | 目标口径（出处） | 现状（代码证据，轮前） | 定级 | 对应行动 |
|---|---|---|---|---|
| C7 双轨+混合模式 | 设计 §6.1：混合（**大多数单走这个**）=「先 `assign` 指派，响应窗内无人接 → 转 `claim`」，前置=同 claim（§6.4 三条件+城市开关） | `dispatch_mode` 仅在 `create_package` 落定（packages.py:170）后**全仓无任何转换路径**（grep `dispatch_mode =` 仅 create/无翻转）；assign 死亡（expired/rejected）后只能人工重派——混合模式名存实亡；r9 报告/台账二十一节登记为最后剩余工程项 | P2（§八条件 1 C 组第 7 项的明示缺口） | `convert_stale_assign_to_claim` 挂 dispatch.maintenance（goal-r10） |
| C8 时间常数唯一权威 | §6.2：响应窗 24h 只引用 `response_window_hours` | 现状已合规（expire_stale_offers 按包上 `response_window_hours` 判死） | 守护 | 转换**零新增时间常数**（判死上游执行，转换跟随 maintenance 24h 节流），代码与报告双明示 |
| F1 降级态 | §11：降级不降红线、替代动作留痕 | claim 开闸=r4 `claim_gate_status` 三条件+种子开关（cities.py:91）；未开闸时 claim 403 claim_closed 已有 | 守护 | 城市未开闸 → 转换**安全空转**（包保持原状，人工路径不变），跳过明细随作业结果上报 |

存量防回退抽查（A 组）：projects/quotes 全量套件在后台全量内绿（零改动模块回归）。

## 二、行动说明

**`server/src/fde_api/dispatch/maintenance.py` 新增 `convert_stale_assign_to_claim(session, *, now=None)`**，并挂入 `run_maintenance`（排在 `expire_stale_offers` 之后——同一节拍内「响应窗判死 → 开闸转 claim」，判定与转换延迟 ≤ 一个维护周期）：

- **扫描口径**：`dispatch_mode='assign'` 且 `dispatch_status in ('expired','rejected')`——超时（响应窗内无人接）与全拒（都属「无人接」）双入口；
- **闸门前置**：逐包取客户城（企业代号第三段，与 `claim_package` 同口径）→ `claim_gate_status`（§6.4 三条件+城市开关）不过 → **跳过**（reason=claim_gate_closed / city_unknown），包保持原状；
- **转换动作**：`dispatch_mode` 翻转 `'claim'` + `publish_package`（§2.3 非 draft 重发：round+1、新 package_code、新 snapshot_hash、§4.7 扩圈半径自动推进；actor=复用 `offer_service.actor_system` 的系统留痕身份）+ `record_event('dispatch_c7_converted')` 留痕（city/round/规则引用）；
- **幂等**：mode 翻转后不再命中扫描（天然只转一次，第二轮空转零扫描成本）；
- **单包隔离**：逐包 `session.begin_nested()`（SAVEPOINT）——前置缺失（如报价被改非 finalized）只回滚该包并计 `convert_failed:<code>`，不炸整批维护事务；失败后 `session.expire(package)` 回读库内权威态防内存残留误提交；
- **安全空转**：城市未开闸是常态降级态（§12 种子全关）——不逐包刷事件（避免每日噪音），跳过明细进作业结果载荷；
- **时间常数**：零新增——24h 判死由上游 `expire_stale_offers` 按包 `response_window_hours`（§6.2 唯一权威）执行，重发节流复用 maintenance 24h。

**实施留注**：首版用 `session.rollback()` 做单包失败隔离——在 handler 的 `session.begin()` 单事务里这会炸掉整批（expire 结果全回滚）；改为 SAVEPOINT 语义后才符合「单包失败不阻断整批」。

**影响面与回滚**：纯 maintenance 侧新增，存量请求路径零触碰（assign/claim/撮合/结算全不动）；revert 单提交即回滚，无迁移无数据回填。

## 三、验证结论

- **本轮新用例**（`test_dispatch_p2_r10_c7.py`，8 例，专用测试库 `fde_r10_test` 全绿）：
  1. 超时死亡 + 开闸城 → 转 claim（mode/round=2/published）+ `dispatch_c7_converted` 留痕 + **交付方 claim_package 实抢成功**（全链路闭环）；
  2. 城市未开闸（种子默认）→ 安全空转：包保持 expired+assign，skipped=claim_gate_closed；
  3. 幂等：第二次运行 converted=0 且 skipped=0（mode 翻转后不命中）；
  4. 全拒（rejected）+ 开闸城 → 同样转换（拒单率以 4 条历史 accepted offer 稀释至 2/6≈33%<40%——**顺带验证了 §6.4 条件②真实生效**：全拒 100% 时闸门确实关着）；
  5. 企业代号缺城市段 → skipped=city_unknown；
  6. 在途指派（offered 未超时）不转换——24h 只由上游判死；
  7. 单包失败（报价非 finalized）→ SAVEPOINT 回滚，健康包照转，broken 包保持 expired+assign（无内存残留）；
  8. `run_maintenance` 同节拍：result 带 `c7_conversion`，判死+转换一次完成（offered → published/claim/round2）。
- **静态**：ruff 全绿；mypy 基线 OK no-new（baseline 289/current 288）。
- **全量**：服务端 `run-server-tests.mjs tests -q` 在专用库 **1456 通过 / 6 跳过**（较 r9 +8）；桌面 660（零改动回归）+ typecheck exit 0。
- **失败记录（不粉饰）**：①首跑 8 fail 全红——共享测试库被并行会话占用（advisory lock 排队 7 分钟后撞其 downgrade/upgrade 窗口，已知 stamp 争夺形态），切专用库 `fde_r10_test` 后环境性失败消除；②测试夹具两处笔误（`_assign_package` 多行调用漏传 fixture 参数、测试签名漏声明）由断言即时暴露即改；③全拒用例首版被 §6.4 条件②正确拦截（拒单率 100%）——这正是闸门真实生效的证据，以稀释夹具修正而非放松断言。
- **H5 口径数字（本轮实测）**：业务表 **85**（不变）/ 迁移 **15 revision / head `c5d7e9f1a3b7`**（零迁移）/ 蓝图路由 **228**（不变）/ ENTRIES **68**（不变）/ 服务端 pytest **1456+6** / 桌面 vitest **660**。与设计文档附录 A 快照的偏差已由 r8/r9 修订建议覆盖（表数口径 85 不含 alembic_version）。

## 四、下一轮建议

1. **C7 之后的工程侧登记项已清零**——§8.3 P0 8 项、§8.4 P1 7 项、§8.5 P2（除 P2-5 文档标注暂缓、P2-2 待拍板无目标值不发明）全部落地。能力基准 A–H 内**无需新工程立项的项已尽**。
2. **剩余输入全部外部**：B-① 备案结论（→开闸链路真实启用）/ B-③ 税率表法务确认（→常量替换）/ B-④ 城市名单拍板（→种子更新+开闸）/ P2-2 状态集 / 仿真器假设表的真实内测数据校准 / 便携版重打包（桌面交付纪律，r7 三页已进 main 后未重打包）。
3. **建议下一轮做终止复核轮（r11）**：按 §八 八项逐条重测证据指针（含 H5 口径、四道闸、负面清单 7 反例、附录 B 降级态达标表述），出具更新版收口报告——若全部成立则循环满足终止判定；任何一项不成立即成为 r12 输入。
4. **风险**：C7 转换依赖 `claim_gate_status` 的种子开关与三条件——B-① 备案未拍板前生产城市不会开闸，转换在生产环境天然处于降级空转（符合 §11 预期，非缺陷）；仿真器 H2/H3 数字仍为假设表口径。
