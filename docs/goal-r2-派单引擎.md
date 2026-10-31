# goal-r2 · 派单引擎轮次报告（2026-10-31）

> 第二轮，输入：goal-r1 报告 + 设计文档 v1.0 补齐版 + BP v3.0 + 代码实测。
> 本轮 Goal（阶段 1，依 §8.3 依赖序取簇②）：**表建设簇 P0-3（fde_profiles 档案+等级证据链）、P0-8（dispatch_rule_versions）、P0-4（Payment.acceptance_passed_at + delivery_settlements 分成落库）、P0-7（system_configuration 派单常数只读节），四项各落可判定用例。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | B1·P0-3 供给池档案 | `fde_profiles`（一人一档、level 标量、四域分、标签/城市/产能）+ `fde_level_evidence`（§3.2/§3.3，判据=L1/L2 晋级证据链用例） | 两表零存在（r1 末 78 表无此二者）；等级核验逻辑全库零匹配 | **P0** | 两表 + `dispatch/profiles.py` 判据复算与晋级核验 |
| 2 | B1·P0-8 规则版本表 | `dispatch_rule_versions`（版本快照、发布/生效、旧 offer 永指当时版本；§6.2/规则表 B9） | 表零存在；Stage B 权重/席位份额无版本化载体 | **P0** | 表 + `dispatch/rules.py`（30 天公示窗 + 到点生效） |
| 3 | B2/B5·P0-4 分成落库 | `Payment` 只加 `acceptance_passed_at`；`delivery_settlements` 状态机 draft→accrued→payable→paid→disputed + 四席位 35/5/20/40 + 累计预扣（§7.2/§7.4，判据=7 里程碑×四席位+预扣） | Payment 无验收列（`workbench/models.py:716` 区段）；结算表零存在；实收回填无结算联动 | **P0** | Payment 一列 + 结算表 + `dispatch/settlements.py` + 双钩子（收款回填/G8 过门） |
| 4 | B3·P0-7 配置项 | §6.2 时间常数唯一权威表进 `system_configuration`，锁定不可运行时改（§8.3 P0-7 判据=配置只读断言） | `system_configuration.py:35` PUBLIC_FIELDS 无任何派单常数；时间常数散落风险为零（尚无实现引用）但**无集中权威源** | **P0** | `DISPATCH_CONSTANTS` 只读节（MappingProxyType）+ GET 暴露 + PUT 可写集精确等值校验天然拒改 |
| 5 | H5 口径漂移 | AGENTS.md 口径=实测 | AGENTS.md 写 78 表 / 10 revision / head `d2f6b4c8a1e9`（r1 后口径）；本轮后实测 82 表 / 11 revision / head `e3a7c5d9f2b8` | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A3 收款 7 里程碑 + 催款读时现算（`payment_service.py` 头注与 `:45`——本轮只加列与联动钩子，催款逻辑零改动，`test_payments_api.py` 全绿 ✓）；A2 报价三档（`test_quotes_api.py` 全绿 ✓）；A6 SOP 15 节点（`test_sop_api.py` 全绿 ✓，均在全量回归中）。

**实施中的三处留注（冲突裁决顺序=代码实测事实优先，均已消化）**：
- **留注③（复购判据 × enterprise_code 唯一约束）**：设计 §3.3「客户复购」要求**同一 enterprise_code 下 ≥2 个项目**，但 `projects.enterprise_code` 带全局唯一约束（`uq_projects_enterprise_code`，P1 代号化迁移引入）——判据在原 schema 下**不可表达**。处理：随本迁移把唯一约束放宽为普通索引（代号红线不动：仍只存代号不存明文；唯一性交还录入侧约定），`_enterprise_code` 服务层格式校验（三段两枚「·」）保留。若拍板要求恢复唯一，需另立企业主体表（P2-5 组织实体暂缓范围）承载复购关系。
- **留注④（「独立交付」席位口径）**：§3.3 操作定义写「delivery_settlements 中本人占据 seat_lead 或 seat_delivery 席位」，但该表四席位是**商务席位** platform/region/city/delivery（§7.2），不存在 seat_lead；seat_lead/seat_delivery 是 `delivery_packages` 的**执行席位**（§2.4）。判据按 delivery_packages 执行席位实现（`dispatch_status='accepted'` 也在该表），语义与 §2.4 一致。
- **留注⑤（冷启动「该城」口径）**：交付包本身无城市字段（城市随 P0-1 发布服务 + `dispatch_cities.json` 落位），本轮冷启动序号以**交付席位 FDE 档案 home_city** 为代理口径，包侧城市落地后切换。

**另两处按默认口径施工、标注待确认（附录 B 纪律，不停工）**：① §7.1 冷启动 5pp 拆分（平台 40% = 35%+5%，自城市合伙人扣 20%→15%）按建议口径实现并常量化；② §7.4 预扣率表按税务总局 2025 年第 16 号公告居民个人累计预扣口径落 `WITHHOLDING_BRACKETS` 常量（集中一处便于法务确认后一次替换，`dispatch/settlements.py` 顶部注明）。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p0-tables-cluster`，1 个迁移 + 9 个文件）：

1. `dispatch/models.py` 扩四模型（§8.2 全部 DDL 级约束）：
   - `FdeProfile`（PK=user_id 一人一档；level Check L1–L4 可空=未定级；四域分各 0–5 Check；标签 JSON；home_city/geo_fence_km=25/产能双列；status pending/active/suspended；`level_evidence_id` 指向证据链）；
   - `FdeLevelEvidence`（from/to_level Check；verified_by FK RESTRICT + verified_at；evidence_summary JSON=核验时刻客观计数快照；source_uri+source_sha256 NOT NULL=指针+指纹红线）；
   - `DispatchRuleVersion`（version_no Unique ≥1；status draft/published/active/retired；rule_snapshot JSON NOT NULL；published/effective/retired_at + published_by）；
   - `DeliverySettlement`（Unique(package_id, settlement_key)；base_amount Numeric(12,2)=实收基数；商务四席位 user FK SET NULL + 四金额列；withholding_tax；status 5 态 Check；acceptance_passed_at 冗余；paid_proof_source_uri 指针）。
2. `dispatch/profiles.py`（P0-3 服务层）：`evaluate_level_criteria` 把 §3.3 L1–L4 判据落成可复算查询（独立交付=执行席位+accepted+G8 passed；L1 加 Quote finalized；L2 加复购（同 enterprise_code ≥2 项目各 finalized+四值法 measured/accepted）+带教 ≥1；L3 加 ≥2 单 branch='B' 且 b_layer_score≥7 + 带教 L1/L2 ≥2；L4 加 ≥3 单 sow_type='c' 全额实收（Σ实收≥Σ计划）+ 带教 L3 ≥3；四域短板下限+场景工程/业务认知阈值），返回未满足项清单与客观计数快照；`promote_user` 判据全过才写证据链+更新档案+`fde_level_promoted` 审计事件（User 目标），核验人须平台侧（admin/project_lead——§3.3「双签/双人」是运营流程约束，服务层只强制下限，升级留痕随 disputes 轮补）；`create_profile` 注册入池（pending 不占名额）。
3. `dispatch/settlements.py`（P0-4 服务层）：`seat_shares_for`（active 版本快照优先→回退 `DISPATCH_CONSTANTS`；冷启动=同城前 N 单走 40/5/15/40）；`split_four_seats`（Decimal 分、平台吸收舍入尾差、Σ四席位=基数）；`compute_withholding`（§7.4 累计预扣法：累计收入−20% 费用−5000×月份数→累进率表→速算→减累计已预扣，下限 0；累计口径=本自然年 accrued/payable/paid 席位行）；`record_receipt_settlements`（实收回填钩子：按包 upsert draft，无包纯 no-op）；`accrue_settlements_for_project`（实收+验收双满足→accrued+冗余 acceptance_passed_at+计提预扣，按里程碑键序可复算）；`mark_payable`（发票前置 422）/`mark_paid`（凭证指针）/`mark_disputed`（争议入口）；事件全部走 delivery_package 目标（P0-6 白名单复用，零新注册）。
4. `dispatch/rules.py`（P0-8 服务层）：`create_rule_version`（快照必备节校验；**30 天公示窗强制**：effective_at ≥ published_at+30d 否则 422；admin-only）；`activate_due_versions`（到点 published→active、原 active→retired，至多一个 active）；`active_rule_snapshot`（快照优先源）。`default_rule_snapshot` 首版=DISPATCH_CONSTANTS 投影。
5. `workbench/models.py`：`Payment.acceptance_passed_at`（UTCDateTime 可空，G8 过门联动打标；**唯一约束不动、催款读时现算零改动**）；`Project.enterprise_code` 唯一约束→普通索引（留注③）。
6. `projects/payment_service.py`：`update_payment` 实收回填分支挂 `record_receipt_settlements` 钩子（无包项目零感知）；新增 `mark_acceptance_passed`（G8 已过门项目的已实收未打标行补时刻→推进计提；晚到尾款补口：收款回填时若 G8 已 passed 亦调用，幂等）。
7. `projects/gate_service.py`：`decide_gate` G8 pass 分支挂 `mark_acceptance_passed`（与既有 g8_stop 联动并列；结果载荷加 `acceptance_marked` 计数）。
8. `system_configuration.py`：`DISPATCH_CONSTANTS`（§6.2 时间常数 9 项 + top_n + Stage B 权重 + 等级映射分 + 席位份额/冷启动 + 新人保护 + 拒单权）——**不进 PUBLIC_FIELDS**（PUT 可写集），GET 以只读 `dispatch_constants` 节暴露；实现代码只准 import 此处（C8 反散落硬编码的锚点）。
9. 迁移 `e3a7c5d9f2b8`（down_revision `d2f6b4c8a1e9`）：四表 + payments 一列 + enterprise_code 约束放宽；测试 `test_dispatch_p0_r2.py`（12 用例）、`test_migrations.py` HEAD 常量、`tests/conftest.py` 清理序（派单六模型按 FK 安全序插入，先结算/offer 后包，先于 solutions/projects/users）。

**席位口径复述（r1 报告 §二延续）**：`delivery_packages` 四席位=执行席位；`delivery_settlements` 四席位=商务席位 platform/region/city/delivery——本轮两者都已落库，仍不同名不同义，禁混用。

**影响面与回滚**：增量为主（4 表 + 1 列 + 3 服务模块 + 2 只读常量节）；两处行为变化=① enterprise_code 不再拒绝同码二启项目（正是复购所需）；② G8 过门响应多 `acceptance_marked` 键、实收回填多结算联动（无包项目 no-op）。回滚=`alembic downgrade d2f6b4c8a1e9`（丢四表与一列、恢复唯一约束——若已有同码复购数据则需先清理）+ revert PR。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.3 P0-3 判据「L1/L2 晋级证据链」 | ✅ `test_l1_promotion_evidence_chain`（证据链落库+档案更新+`fde_level_promoted` 审计事件）/ `test_l2_promotion_requires_repurchase_and_mentee`（缺带教 422 `level_evidence_insufficient` 且 deficits 指明缺口→补齐后 L2，evidence_summary 含独立交付数/复购/带教计数）/ `test_l1_promotion_rejected_without_delivered_fact`（拆事实→422）/ `test_promotion_verifier_must_be_platform_side`（403） |
| §8.3 P0-4 判据「7 里程碑×四席位+预扣」 | ✅ `test_seven_milestones_four_seats_and_cumulative_withholding`（SOW a/b/c/d 全部 7 条里程碑：四席位 3500/500/2000/4000、Σ=基数、§7.4 累计预扣链 0→42→96×5、总预扣 522 可复算） |
| §7.2 状态机 | ✅ `test_settlement_state_machine_invoice_proof_dispute`（accrued→无发票 422 `invoice_required`→登记发票→payable→paid 落凭证指针→重复 paid 409；draft→disputed→再 payable 409） |
| §7.1 冷启动 | ✅ `test_cold_start_shares_first_three_city_orders`（同城前 3 单 40/5/15/40，第 4 单回 35/5/20/40；split Σ=基数） |
| §7.4 边界 | ✅ `test_withholding_zero_for_small_first_settlement`（首笔小额应纳税所得额≤0→预扣 0 不为负） |
| P0-4 全链路（API） | ✅ `test_g8_pass_marks_acceptance_and_accrues_settlements`（实收回填→draft→G8 过门（P0-5 双主体：admin 提交/leader 拍板）→`acceptance_marked`={1,1}→accrued→**晚到尾款**回填即补打标+计提 42） |
| §8.3 P0-7 判据「配置只读断言」 | ✅ `test_dispatch_constants_readonly_via_configuration_api`（GET 只读节全值断言（§6.2 常数+席位+权重）；values 键集=PUBLIC_FIELDS 精确等值且与派单常数零交集；PUT 夹带 `response_window_hours`→400 `invalid_configuration`；源级 MappingProxyType 改值抛 TypeError） |
| §8.3 P0-8 判据「版本切换后旧 offer 仍指旧版权本」 | ✅ `test_rule_version_switch_keeps_old_offer_on_old_version`（v1 active→offer 记 v1→v2 发布 31 天后到点生效、v1 retired→旧 offer `match_breakdown.rule_version` 仍=v1 不回写）+ `test_rule_version_notice_window_and_role_guard`（29 天→422 `notice_window_required`；project_lead→403；未到生效日不激活；到点 v1 active） |
| 迁移链 | ✅ 测试库随套件反复 up/down（含 `alembic check` 元数据等价测试与 roundtrip）；11 revision / head `e3a7c5d9f2b8` |
| 全量 `npm run test:server` | ✅ **1357 passed / 6 skipped / 0 failed**（9:17；含迁移链全量 up/down 往返与 `alembic check` 元数据等价） |
| `npm run test:desktop` / `npm run typecheck` | ✅ vitest **654/654**、typecheck 零错误（桌面端本轮零改动） |

**口径数字重测（H5，本轮后 vs 设计文档附录 A 快照）**：

| 口径 | 附录 A 快照（2026-10-31） | 本轮实测（改动后） | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **82**（78+r2 四表） | §8.1「新增 8 张」进度 6/8（余 package_access、disputes） |
| 迁移 revision | 9 / head `a9c3f1d8e2b4` | **11 / head `e3a7c5d9f2b8`** | 派单迁移第 2/6–8 个，接链正确 |
| 蓝图路由 | 212 | **212**（本轮零新路由，routes 随 P1-3） | 无漂移 |
| api_catalog ENTRIES | 54 | 54 | 无漂移 |
| 服务端 pytest | —（附录 A 未列） | **1357 passed + 6 skipped**（+12 派单 r2 用例） | — |
| `stale_version` 引用 | 19 文件 42 处 | 本轮不新增引用（新表新列，无存量引用点） | 下轮顺测 |

**镜像与正式库**：合并后于本地 main 重建镜像 + 容器 recreate + `alembic upgrade head`（红线纪律），结果补记于 PR 与本节（见文末补记）。

**失败与未完成项（如实）**：首轮 r2 用例出现 **6 失败 + 1 错误**，逐一定位修复：① Payment 直插缺 `content_hash`（NOT NULL）——补测试助手；② `projects.enterprise_code` 全局唯一约束使复购判据不可表达（真差距，非测试问题）——按留注③放宽约束；③ `activate_due_versions` 漏 flush（refresh 回读旧值）；④ 计提顺序缺陷——`compute_withholding` 内 SELECT 触发 autoflush 把本行双计入累计口径（G3 得 42 应为 0），改为**先算后改**；⑤ g8 用例企业代号不符三段两枚「·」格式校验（400）；⑥ conftest 每用例清理未含派单表，提交型用例遗留行撞 `delivery_packages_solution_id_fkey` RESTRICT——清理序补六模型。另：测试迭代期间测试库曾滞留半套用迁移对象，手工 stamp 回 `d2f6b4c8a1e9` 重建（一次性，无生产影响）。

## 四、下一轮建议

1. **优先（簇②收尾 → P1 主战役起步）**：P0-1 `delivery_packages` **服务层**（§2.3 快照 canonical_json 冻结 + 发布/撤回/8 态迁移用例 + package_code 生成规则；表与结算钩子已就位，快照哈希冻结判据是「快照不可变用例」的最后一环）→ P0-2 `package_access`（§9.2 跨主体只读授权第三语义 + **§9.5 隔离基线四条测试**——开池四道闸之三从这里起建）。
2. **P1-2 撮合核心（L 级主战役）预备**：Stage A 五资格门需要 `fde_profiles.status='active'` 与产能列就位（本轮已落）；`required_level` 推导（§4.5）依赖 Quote 系数（已就位）；Stage B 权重从 `active_rule_snapshot` 取（本轮已落）——撮合主战役的静态依赖全部齐备，建议 goal-r4 整轮主攻。
3. **风险**：① 商务席位中 platform/region/city 的**人的归属**尚未建模（当前三席位 user 可空、金额照拆）——区域代理/城市合伙人实体随 P2；② 冷启动城市口径是代理实现（留注⑤），P0-1 落 dispatch_cities.json 时切换并回归本用例；③ 税率表按 2025-16 号公告口径落常量，**需法务确认**（附录 C）；④ 复购约束放宽后，录入侧需自觉遵守「同企业复购才同码」约定（无 DDL 强制）。
4. **待拍板（附录 B）**：B-②资金托管/开票主体默认口径继续按「平台统一收款开票+四席位内部分账」施工（payable 发票前置已实现）；B-①备案未定期间 claim 相关常数已进只读节但开关随 P1-3。
5. **文档修订建议（附录 A 时效）**：连续两轮重大漂移（表 76→82、迁移 9→11、head 两跳），建议设计文档修订附录 A：A-③ 表数 82、A-⑤ 11 revision / head `e3a7c5d9f2b8`；并把本轮留注③④⑤（enterprise_code 唯一约束、独立交付席位载体、冷启动城市口径）补进附录 A 冲突清单作为已闭环项。
