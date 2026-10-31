# goal-r4 · 派单引擎轮次报告（2026-10-31）

> 第四轮，输入：goal-r3 报告 + 设计文档 §6/§12 + 代码实测。
> 本轮 Goal（阶段 1，P1 首批）：**P1-1 offer_service（§6.3 乐观锁并发接单 409 判据 + §6.7 拒单权 + §6.4 开闸评估）+ P1-3 蓝图↔目录一致性测试 + P1-5 seeds 三处，各落可判定用例。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | C12·P1-1 offer 服务 | `dispatch/offer_service.py`（乐观锁）；并发接单 409 stale_version 用例（§8.4 P1-1 / §6.3） | `dispatch_offers` 表 r1 已落但零服务逻辑：offer 只能测试直插；无接单/拒单/超时释放；`stale_version` 对 offer 无覆盖 | **P1（核心能力）** | offer_service 全套 + 路由 4 条 + 目录 +4 |
| 2 | C11·拒单权 | 每日 ≥4 次无条件拒单、不惩罚、原因只进档案不进分值（§6.7 / 规则表 A-6 #6） | 无拒单入口（拒单概念零代码） | **P1** | `decline_offer`（永不因配额拒绝拒单）+ 原因枚举守卫 + 5 连拒用例 |
| 3 | C9·抢单开闸 | 三条件（供给>需求 / 拒单率<40% / 备案+权重公示）城市级开关（§6.4） | 全库零实现；无城市白名单数据源 | **P1** | `dispatch/cities.py`（§12 种子加载 + 三条件可解释评估）+ `claim_package` 403 降级态 |
| 4 | B4·P1-5 seeds | gates.json 扩 `applicable_industries` + `dispatch_cities.json` + `acceptance_metrics.json`，种子加载幂等用例（§8.4 P1-5） | seeds/ 仅 3 个文件；派单两类种子不存在；gates.json 无行业适用域字段 | **P1** | 三处落地 + 幂等/结构用例 |
| 5 | B8·P1-3 一致性 | 蓝图清单与 api_catalog 一致性测试（§8.4 P1-3 判据） | 目录 54→60（r3）后**无任何一致性校验**——目录条目指向不存在路由或新路由脱册均不可发现 | **P1** | 双向一致性测试（ENTRIES→url_map 逐条可解析；dispatch 路由→ENTRIES 逐条在册） |
| 6 | H5 口径 | AGENTS.md=实测 | 本轮后路由 224 / ENTRIES 64（表 83、12 revision 不变——本轮零迁移） | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A5 门禁（gates.json 扩字段后 `_gate_templates` 读取与 `template_hash` 审计链不变——历史迁移 `f7a2c9e4b1d3` 的回填哈希常量是冻结历史值，见下「哈希钉子辨析」；`test_gate_template_hash_migration_backfills_existing_gate_rows` 全绿 ✓）；A1 报价（`_published_package` 复用 Quote 直插口径，`test_quotes_api` 全量回归 ✓）；A3 收款（本轮零触碰 ✓）。

**哈希钉子辨析（防后续轮误改）**：`GATES_JSON_SHA256`（test_migrations.py）是 **f7a2c9e4b1d3 迁移时刻的 gates.json 文件哈希（历史回填值）**，不随后续种子演进漂移——本轮 gates.json 加字段后文件哈希变为 `661d6304…`，该常量**保持旧值**并在注释中钉明语义；gate 行实例化时的实时哈希由 `gate_service._gates_file_hash()` 现算（审计语义=「该行从哪版模板实例化」）。

**实施中的留注（默认口径施工）**：
- **留注⑨（开闸条件 3 代理）**：§6.4 条件 3「算法备案完成且权重版本已公示」——备案编号无承载模型，以「存在 published/active 规则版本」为代理；备案未定期间（附录 B-①）条件 3 恒不满足 → claim 全城关闭 = §11.1 降级态，与种子 `claim_enabled=false` 双保险。备案编号公示随 §5.1 落位后收紧。
- **留注⑩（claim 评估窗）**：§6.2 抢单评估窗 3–5s 的收集期裁决属 P1-2 撮合核心——本轮 claim 入口只做登记（开闸判定 + offer 创建），裁决/中签排序随 P1-2。
- **留注⑪（acceptance_metrics schema）**：设计只给文件名未给 schema——字段集（key/target/comparator/gate/unit/scope）为工程侧最小决定，内容=BP §11 闸门指标投影（覆盖率 0.60 / G9 一次通过率 0.70 / 平台工时 ≤0.25 / 毛利 ≥0.70 / 结算 T+15 / 拒单配额下限 4），收口报告列待签字。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p1-offer-seeds`，零迁移 + 10 个文件）：

1. `dispatch/offer_service.py`（P1-1）：
   - `create_assign_offers`（平台侧指派：包 published→offered 迁移 + 按 Top-N 建 offer 行 + 同轮重复 409 `offer_exists` + `match_breakdown={mode:'assign', ranked_position}`）；
   - `accept_offer`（**§6.3 乐观锁显式版本比对先行** → 角色校验（本人或平台侧）→ 状态校验 → **时限校验**（claim=15 分钟确认窗 / assign=包响应窗，§6.2 常数引用）→ 包行 FOR UPDATE 串行化 → 同轮互斥（已有 accepted → 409 `offer_already_accepted`）→ offer accepted + version+=1 → 包 accept 迁移 → 同轮其余 offered 自动 expired）；
   - `decline_offer`（§6.7：候选人本人拒单；原因枚举 档期冲突/能力不匹配/距离/其他 只进 OperationEvent 留痕不进任何分值；**配额只降不升——本函数永不因拒单次数拒绝拒单**（负面清单 A-6 #6 防护）→ 本轮全 offer 终结且无接受者 → 包 rejected（重派入口））；
   - `expire_stale_offers`（超时批量释放：过时限 offered → expired；包无活 offer → expired 迁移；系统动作挂 admin 留痕）；
   - `claim_package`（C9：城市归属=企业代号第三段 → `claim_gate_status` 三条件 + 种子开关 → 未开 403 `claim_closed`（可解释明细进 message）→ 开则登记 claim offer）；
   - `accept_offer_and_handover`（API 入口：主事务后 §9.3 交接复用 `handover_accepted_member`）。
2. `dispatch/packages.py`：抽出 `handover_accepted_member`（leader 为 actor、幂等、stale_version 重试——r3 逻辑原样，offer_service 共用）。
3. `dispatch/cities.py`（P1-5 + C9）：`load_dispatch_cities` / `load_acceptance_metrics`（lru_cache 只读加载=幂等）；`claim_gate_status`（供给=active 档案计数、需求=近 90 天 published 包（客户城=代号第三段）、拒单率=近 90 天 declined÷offered、公示=规则版本存在——**全部条件输出明细**（§5.2 释明义务））。
4. `seeds/dispatch_cities.json`（§12 schema 逐字段，6 城建议名单，`claim_enabled` 全 false）+ `seeds/acceptance_metrics.json`（留注⑪）+ `seeds/gates.json` 加 `applicable_industries`（null=全行业通用，meta.conventions 记录演进）。
5. `dispatch/routes.py` +4：POST packages/{id}/offers（平台侧）/ offers/{id}/accept（乐观锁 version 必填）/ offers/{id}/decline / packages/{id}/claim；`api_catalog.py` ENTRIES 60→64。
6. 测试 `tests/test_dispatch_p1_r4.py` 14 用例（见第三节）。

**影响面与回滚**：零迁移、纯增量（2 新模块 + 1 拆函数 + 4 路由 + 3 种子）；既有行为变化仅一处=同轮他端接单后，持旧版本的重复接单从状态 409 变为**乐观锁 409 先行**（§6.3 语义正确化）。回滚=revert PR（种子文件与路由随 revert 消失，无数据迁移）。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.4 P1-1 判据「并发接单 409 stale_version」 | ✅ `test_accept_offer_optimistic_lock_409`（显式旧版本比对 409 先于状态校验——版本检查是第一道闸） |
| §6.3 同轮互斥 | ✅ `test_concurrent_accept_single_winner`（他端已 accepted → 409 `offer_already_accepted`，包行锁串行化）+ `test_accept_releases_sibling_offers`（先到者胜 + 落选者自动 expired + seat_delivery 落位） |
| §6.2 确认窗 | ✅ `test_claim_confirm_window_15min`（claim 16 分钟后接单 → 409 `offer_window_expired`）+ `test_expire_stale_offers_releases_package`（assign 25h 超时 → offer expired + 包 expired） |
| §6.7 拒单权（负面清单 #6 防护） | ✅ `test_decline_quota_never_blocks`（**5 连拒全部成功**、每轮重发→拒→包 rejected 重派入口；原因枚举两种走法）+ `test_decline_reason_enum_guard`（非法原因 400） |
| §6.4/C9 开闸 | ✅ `test_claim_closed_by_default_seed_switch`（种子全 false → 403 `claim_closed`，§11.1 降级态）+ `test_claim_gate_opens_when_conditions_met`（双供给档案 + active 规则版本 + monkeypatch 城市开关 → claim 放行，`claim_gate_status` 三条件全 True 明细断言） |
| §8.4 P1-5 判据「种子加载幂等」 | ✅ `test_seeds_load_idempotent_and_valid`（lru_cache 同对象幂等 + §12 六城逐字段 + claim_enabled 全 false + 指标键集与 G9 0.70 阈值）+ `test_gates_seed_has_applicable_industries` |
| §8.4 P1-3 判据「一致性测试」 | ✅ `test_catalog_entries_resolve_in_url_map`（64 条 ENTRIES 逐条在 url_map 可解析——目录漂移即红）+ `test_dispatch_routes_all_in_catalog`（dispatch 10 路由逐条在册——脱册即红；werkzeug `<param>` ↔ 目录 `{param}` 记法归一） |
| 派单回归 | ✅ r1/r2/r3 全部 38 用例 + 门禁 5 用例全绿（gates.json 扩字段后零回归） |
| 全量 | 见口径表 |
| 迁移 | 本轮零迁移（head 仍 `f4b8c2d6e3a1`） |

**口径数字重测（H5）**：

| 口径 | 附录 A 快照 | 本轮实测 | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **83**（零新表） | §8.1 进度维持 7/8（余 disputes） |
| 迁移 revision | 9 | **12**（零新迁移） | 不变 |
| 蓝图路由 | 212 | **224**（+4 offer/claim 路由） | 正向漂移 |
| api_catalog ENTRIES | 54 | **64**（+4） | 与路由对应，一致性测试双向钉死 |
| 服务端 pytest | — | **1386 passed + 6 skipped**（+14 r4 用例） | — |
| 桌面 vitest | — | 654（零改动） | — |

**失败与未完成项（如实）**：① r4 用例首轮 3 失败——同轮互斥测试的期望错误（sibling 已被释放为 expired，乐观锁/状态闸先行返回 `stale_version`/`invalid_offer_state` 均为正确行为；拆成互斥守卫 + 释放路径两用例后各归其位）、开闸测试供给=需求不满足严格不等式（补第二个苏州档案）、目录归一测试缺 werkzeug→目录记法转换；② 测试期间发生一次**测试库 advisory lock 堵塞**（残留 pytest 进程 idle in transaction 持锁）——按既有配方 `pg_terminate_backend` 清锁后重跑，非代码问题（记忆库已有同类案例）；③ mypy 3 处新错误（Optional isoformat ×2、Optional 包行 ×1）当场修复。

## 四、下一轮建议

1. **goal-r5 = P1-2 撮合核心（L 级主战役，整轮主攻）**：`dispatch/matching.py`（Stage A 五资格门：等级/模块/行业/负载=产能÷单均工时/到场型围栏）+ `dispatch/scoring.py`（Stage B 权重从 `active_rule_snapshot` 取 + tie-break 可复现随机 + 围栏内优先）+ 场景裁决（到场=字典序 geo_tier→能力→行业→时效；远程=加权；无候选=不自动派）+ `match_breakdown` §4.8 schema 对被派方展示 + **负面清单 7 条每条一个反例用例**（=开池闸③）。静态依赖已全部齐备。
2. **P1-4 options 枚举**（S 档可搭车 goal-r5）；`disputes` 表（第 8 张）随 E5 T+30 对账轮。
3. **风险**：① 负载计算依赖 `fde_profiles.monthly_capacity_hours/avg_delivery_hours` 真实数据（种子档案为测试口径）；② 扩圈链（§4.7）需要城市/都市圈静态数据源——`dispatch_cities.json` 已含 metro_group，扩圈半径序列与包侧城市切换（r2 留注⑤）在 P1-2 一并收口；③ claim 评估窗裁决（留注⑩）是 P1-2 范围内最难的部分（3–5s 收集窗 + 排序键裁决 + 确认窗联动）。
4. **待拍板（附录 B）**：无新增阻塞；留注⑨⑩⑪ 并入收口报告待签字清单。
5. **文档修订建议（附录 A 时效）**：路由 224 / ENTRIES 64；A-⑥ 乐观锁口径可再补「dispatch_offers 沿用 32 模型泛化模式」实测句；种子清单从 3 个变 5 个。
