# goal-r6 · 派单引擎轮次报告（2026-10-31）

> 第六轮，输入：goal-r5 报告 + 设计文档 §6.6/§7.5/§8.4 + 代码实测。
> 本轮 Goal（阶段 1，P1 收官）：**P1-6 报价归属 + P1-7 留存策略（调度挂载）+ disputes 表（§8.1 第 8 张）+ T+30 自动对账——完成后 §8.4 P1 七项全过、§8.1 八表齐。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | B8·P1-6 报价归属 | `Quote` 加 `owner_user_id`，归属过滤用例（§8.4 P1-6） | 列不存在；报价无归属维度 | **P1** | 一列 + 创建即落 owner + 过滤断言 |
| 2 | B6·P1-7 留存策略 | 撮合流水/评分 3 年、涉税 10 年；归档任务走既有 jobs 框架（§8.4 P1-7 / §6.2 / B11） | 零实现；超时释放（r4）也无调度挂载 | **P1** | `dispatch/maintenance.py`（报告只读扫描 + 24h 节流 + outbox 投递 + handler 注册） |
| 3 | B1·disputes 表 | §8.1 第 8 张（§6.6 四层仲裁 + §7.5 T+30 草稿） | 表零存在；E5 对账零实现 | **P1** | 表 + `dispatch/disputes.py`（L0 自动草稿幂等 + L1 打开/裁决） |
| 4 | E5·T+30 对账 | 应计 vs 实收逐包比对，差异>±¥1 自动 dispute 草稿（§7.5） | 零实现 | **P1（E5 前半）** | `run_l0_reconciliation` + 维护作业挂载 |
| 5 | H5 口径 | AGENTS.md=实测 | 本轮后 86 表 / 14 revision / head `b2c4d6e8f1a3` / 路由 226 / ENTRIES 66 | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A1 报价（owner 列纯增量，quote_service 全量回归 ✓）；A3 收款（T+30 对账只读 Payment，零写路径 ✓）；A5 门禁（零触碰，回归 ✓）。

**实施中的留注（默认口径施工）**：
- **留注⑰（留存=只读报告）**：3 年/10 年是「至少保留」下限；超期对象由维护作业盘点并留痕（bounded 样本），实际删档/转冷存储是人工合规审批动作——任务不自动删数据。
- **留注⑱（L2 双签）**：§6.6 L2 双人复核的「双签记录」需要双人工作流载体，二期落位；当前 L2 打开/裁决走同一人工入口，双签留痕字段已在 disputes（handled_by + OperationEvent 双事件）可承载。
- **留注⑲（T+30 触达频率）**：§7.5 说「月度 jobs」——实现为 24h 节流的维护作业（对账本身幂等、只产差异草稿），月度节奏由运营按草稿量复盘；如需硬性月度窗口，P2 在调度层加 cron 月度参数。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p1-closeout`，1 个迁移 + 8 个文件）：

1. 迁移 `b2c4d6e8f1a3`（down_revision `a7f3c1e9d5b2`）：`quotes.owner_user_id`（FK SET NULL + 索引）+ `disputes` 表（layer/status Check、package FK RESTRICT、l0_report_source_uri 指针、snapshot_hash、48h SLA 字段、opened/handled_by）。
2. `workbench/models.py`：Quote.owner_user_id + `Index("ix_quotes_owner")`（alembic check 元数据等价要求模型/迁移一致——CI 首跑即抓出模型缺索引声明，已补）。
3. `dispatch/models.py`：Dispute 模型。
4. `projects/quote_service.py`：create_quote 落 `owner_user_id=actor.id`（P1-6）。
5. `dispatch/disputes.py`：`open_dispute`（人工 L1/L2；L1 ¥50,000 上限 422 `amount_above_l1`；48h SLA 起；snapshot 锚定）、`resolve_dispute`（100% 人工——非平台侧 403；resolution 必填；事件留痕）、`run_l0_reconciliation`（逐包逐键结算应计 vs 实收，差异>±¥1 → L0 草稿，幂等：同包同键已有 draft/open 跳过）。
6. `dispatch/maintenance.py`：`retention_scan`（3 年/10 年超期盘点，报告只读+事件留痕，留注⑰）、`maintenance_due`（24h 节流，DB 侧 max(updated_at)）、`run_maintenance`（超时释放+留存+对账一体）、handler 注册（沿 research.export guard 模式）。
7. `cli.py` scheduler 主循环：维护到期检查 → `enqueue_outbox("dispatch.maintenance", daily-token)`（topic 即 job_type，ensure_background_job 天然去重）。
8. `jobs/handlers.py`：`dispatch.maintenance` 注册（guard 模式）。
9. 测试 `tests/test_dispatch_p1_r6.py` 8 例；conftest 清理序补 Dispute；HEAD_REVISION 常量。

**影响面与回滚**：1 列 + 1 表 + 1 作业类型；既有路径唯一变化=create_quote 多写 owner（nullable 无破坏）。回滚=`alembic downgrade a7f3c1e9d5b2` + revert PR。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.4 P1-6 判据「报价归属过滤」 | ✅ `test_quote_owner_set_on_create_and_filtered`（创建即落 owner + 按 owner 过滤正反例） |
| §8.4 P1-7 判据「归档任务调度用例」 | ✅ `test_maintenance_due_throttle_and_handler`（无记录→到期；succeeded 后 24h 内不投；handler 注册断言）+ `test_maintenance_handler_runs_end_to_end`（worker handler 端到端跑超时释放）+ `test_retention_scan_report_only`（3 年/10 年超期盘点 + 只读断言 + 事件留痕） |
| §7.5 E5「T+30 差异>±1 自动草稿」 | ✅ `test_t30_reconciliation_creates_l0_draft`（差 500 → L0 草稿、金额符号=实收−应计、幂等重跑零新增、差 0.5 ≤±1 不建） |
| §6.6 人工仲裁 | ✅ `test_dispute_open_l1_sla_and_cap`（48h SLA 窗口断言、L1 金额上限 422、L0 禁人工打开、snapshot 锚定）+ `test_dispute_resolve_human_only`（fde_engineer 裁决 403、admin 裁决落 handled_by/resolved_at/事件） |
| 回归 | ✅ r1–r5 派单 67 例 + 迁移链 15 例 + 门禁 5 例 = **87 例全绿**；ruff/mypy 全树无新错 |
| 全量 | CI 门禁出具 |
| 迁移 | 测试库随套件 up/down 往返 + `alembic check` 元数据等价（首跑抓出 Quote 模型缺索引声明——模型/迁移一致性纪律生效，已补） |

**口径数字重测（H5，rebase 后基线=goal-d1 合并态）**：

| 口径 | 附录 A 快照 | 本轮实测 | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **86**（84+disputes） | **§8.1 八表齐（8/8）** |
| 迁移 revision | 9 | **14** / head `b2c4d6e8f1a3` | 接链正确 |
| 蓝图路由 | 212 | **226**（零新路由） | 不变 |
| api_catalog ENTRIES | 54 | **66** | 不变 |
| 服务端 pytest | — | **CI 出具（1427+，含 +8 r6 用例）** | — |
| 桌面 vitest | — | 654（零改动） | — |

**失败与未完成项（如实）**：r6 用例首轮 4 失败——① `background_jobs` 终态是 `succeeded` 非 `completed`（CheckConstraint）；② create_quote 自管独立 session，fixture 数据需先 commit（同 r2 g8 教训）；③ maintenance_due 读 server_default 未回填的 updated_at（改 DB 侧 `func.max`）；④ T+30 差异符号（实收−应计=−500 是正确语义）+ rule version_no 同测试内撞号。另 CI 侧（预判）：alembic check 要求模型声明 `ix_quotes_owner`（迁移建了模型没声明）——本地全树 mypy/alembic check 预演已补。

## 四、下一轮建议

1. **P1 全过声明（待收口复核）**：§8.4 七项 = P1-1✅(r4) P1-2✅(r5) P1-3✅(r4) P1-4✅(r5) P1-5✅(r4) P1-6✅(本轮) P1-7✅(本轮)；§8.1 八表齐。**§八终止条件 2 的 P0+P1 全过——剩余=P2 批次 + 开池闸④覆盖率 + 附录 B 拍板项 + 收口报告。**
2. **goal-r7 = P2 批次（S 档为主）**：P2-1 桌面端 dispatch 页面簇（派单池/交付包详情/能力档案/权重配置/产能看板——基础设施复用，桌面端首个派单触点）/ P2-2 Project.status 枚举扩展 / P2-3 business_line 'FDE_DISPATCH' / P2-6 dispatch_cities 扩字段；P2-4 私单封堵（L）单独立项。
3. **goal-r8 = 收口轮**：§8.8 闸④商业模块覆盖率 ≥60%（分子分母出具）+ H1–H3 指标仿真/内测口径 + 附录 B 待签字清单汇总 + 终止条件 5 的附录 A 修订建议提交 + 最终收口报告（逐项证据指针）。
4. **待拍板（附录 B）**：无新增阻塞；留注⑰⑱⑲并入待签字清单。
5. **文档修订建议（附录 A）**：表 86 / 14 revision / head `b2c4d6e8f1a3`；A-③④⑤⑥ 全部需按最新实测重写（建议收口轮统一出修订稿）。
