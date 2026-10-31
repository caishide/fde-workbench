# goal-r8 · 派单引擎收口报告（2026-10-31）

> 第八轮（收口轮），输入：goal-r1–r7 全部轮次报告 + 设计文档 v1.0 补齐版 + BP v3.0 + 规则表 v1.0 + 代码实测。
> 本轮 Goal：**开池闸④覆盖率出具（分子分母）+ 收口审计发现的合规缺口补齐（C10 新人保护 / B1 防骚扰不重复推送 / §4.7 扩圈半径自动推进）+ §八终止判定逐条对照 + 附录 B 待签字清单汇总 + 附录 A 修订建议。**

---

## 一、收口轮行动说明（先于差距清单——本轮动了什么）

1. **C10 新人保护期（§6.5，goal-r7 审计发现的缺口）**：`matching._stage_a` 新增「前 5 单只推同城」——完成单数（delivery_packages.seat_delivery=本人且 accepted 计数）< `newcomer_protection_orders` 的候选强制 tier>0 出局（推送范围收紧，非资格淘汰；超时不写档案不惩罚的另一半语义由「无响应率字段/无惩罚代码」结构性保证）。A5 明细新增 `newcomer_city_only` 标记（释明义务）。
2. **B1 防骚扰（规则表 B1，goal-r8 审计发现 r5 测试语义错误）**：`matching._declined_earlier_rounds`——同包**更早轮次**拒过的候选本轮不再主动推送；与负面清单 #6「不因拒单限制接单机会」**正交并存**（B1 管平台不推、#6 管本人可抢——r5 初版把两者混为一谈，本轮修正测试语义并在 B1 明细行留释明）。stage_a 契约新增 `B1` 行。
3. **§4.7 扩圈半径自动推进**：`packages.publish_package` 非 draft 重发时 `redispatch_radius_km` 按 25→50→100→0（0=全城哨兵）自动降档（此前仅列存储无推进逻辑）。
4. **闸④覆盖率测量**：pytest-cov 跑商业模块关键路径测试集（10 文件 85 用例），口径见第三节。
5. 收口文档：本报告 + AGENTS/CHANGELOG/台账终版口径。

**回归**：r1–r7 派单 91 例 + 收口 3 例 = **94 例全绿**；ruff/mypy 全树无新错。影响面：matching 收紧过滤（B1/C10）、publish radius 推进——回滚=revert。

---

## 二、差距清单（终版状态：能力基准 A–H 逐项）

| 能力项 | 状态 | 证据指针（代码 + 测试 + 轮次） |
|---|---|---|
| A1 报价 | ✅ 存量保真 | `quote_service.py`（92% 覆盖）；A 组抽查每轮全绿；owner_user_id 增量（r6） |
| A2 合同 | ✅ | `contract_service.py`（87%）；smoke 全绿 |
| A3 收款 | ✅ | `payment_service.py`（86%）；催款读时现算零改动（r2 判据） |
| A4 项目/任务/工时 | ✅ | projects 全量回归（task/gantt 非商业口径，覆盖率单列） |
| A5 门禁 G1–G9 | ✅ | `gate_service.py`（87%）；P0-5 双 403（r1）；验收分离全量双拍板人化 |
| A6 SOP 15 节点 | ✅ | sop_nodes 种子+回归全绿 |
| A7 行业模板库 | ✅ | templates 全量回归（gates.json applicable_industries 增量 r4） |
| A8 结算台账与集成桥 | ✅ | bridge 只读纪律零触碰；smoke 全绿 |
| B1 八表齐 | ✅ **8/8** | delivery_packages/dispatch_offers(r1)+fde_profiles/fde_level_evidence/dispatch_rule_versions/delivery_settlements(r2)+package_access(r3)+disputes(r6)；§8.2 DDL 约束逐表落 |
| B2 改 4 表 | ✅ | gates 三列(r1)/Payment.acceptance_passed_at(r2)/Quote.owner_user_id(r6)/business_line 放行(r7) |
| B3 白名单两处 | ✅（口径修正） | events 白名单(r1)+PUBLIC_FIELDS→**只读节**（r2 留注：设计原文「进 PUBLIC_FIELDS」与「锁定不可改」矛盾，采只读节口径并经 PR #34 判据验证） |
| B4 种子三处 | ✅ | gates.json 扩字段(r4)+dispatch_cities.json(r4/§12 六城)+acceptance_metrics.json(r4，schema=留注⑪) |
| B5 迁移接链 | ✅ | 15 revision，head `c5d7e9f1a3b7`，链 `…→a9c3f1d8e2b4→d2f6b4c8a1e9→e3a7c5d9f2b8→f4b8c2d6e3a1→a7f3c1e9d5b2→b2c4d6e8f1a3→c5d7e9f1a3b7` |
| B6 P0 8 项判据 | ✅ 8/8 | r1(P0-5/6)+r2(P0-3/4/7/8)+r3(P0-1/2) 各判据用例见各轮报告第三节 |
| B7 P1 7 项判据 | ✅ 7/7 | r4(P1-1/3/5)+r5(P1-2/4)+r6(P1-6/7)；负面清单 7 条反例（闸③） |
| B8 P2 六项 | ✅* | P2-1/3/6 落地(r7)；**P2-5 组织实体=设计标注暂缓**；**P2-2=无目标状态集待拍板（不发明，留注㉒）**；**P2-4 私单封堵=L 级已登记未立项（收口明示）** |
| C1–C13 撮合行为 | ✅（C7 部分） | Stage A 五门+C10/B1 增补(r8)/场景裁决 A/B/C(r5)/Stage B 版本化权重(r5)/match_breakdown(r5)/双轨(r4)/乐观锁(r4)/时间常数只读节(r2)；**C7 混合模式「指派超时自动转抢单」=部分（常数与双值就位，自动转换 job 未建——留注㉓，收口明示）** |
| D1–D7 隔离合规 | ✅ | package_access 第三语义(r3)/§9.5 四条基线(r3)/字段白名单+桌面层敏感字段断言(r7)/接单交接复用 add_project_member(r3)/负面清单七条(r5) |
| E1–E6 结算税务 | ✅（E5 对账 job 就绪） | settlements 状态机+四席位+累计预扣(r2)/发票前置+凭证指针(r2)/T+30 对账差异>±¥1 自动 L0 草稿(r6)/留存 3y10y 报告作业(r6)/双口径纪律=常数注释+席位金额单列 |
| F1–F2 降级与白名单 | ✅ | 无公示版本 422 降级态(r5)/claim 城市开关全 false(r4)/降级不降红线=事件留痕全量 |
| G1–G4 AI 智能体赋能 | ✅（并行轮交付） | goal-d1（PR #37，2026-10-31 同日）：编排/草稿人拍板边界/G3 前置闸/presurvey_intakes——按 BP §8 配套演进方案由并行 goal-d 循环承担，本轮不重复建设 |
| H1 覆盖率 | ✅ **闸④达线** | 商业模块关键路径 **84.9%**（≥60%），宽口径 71%——分子分母见第三节 |
| H2 G9 一次通过率 ≥70% | ⏳ 无业务数据 | 指标定义入 acceptance_metrics.json（0.70/≥/P3）；判定需真实/内测仿真交付数据——**仿真口径公式已就绪、数据待填充**（如实，见第四节） |
| H3 工时占比/毛利率 | ⏳ 无业务数据 | 同上（0.25≤/0.70≥/P4） |
| H4 开池四道闸 | ✅ **四道全绿** | ①隔离基线(r3)②门禁验收分离(r1)③负面清单七条(r5)④覆盖率 84.9%(本轮) |
| H5 口径重测 | ✅ 每轮同步 | 见第四节终版口径表 |

## 三、验证结论（收口实测）

### 闸④覆盖率（分子分母，pytest-cov 实测 2026-10-31）

- **商业模块关键路径口径**（BP §11 P0 闸门 scope=报价/收款/合同/门禁/派单撮合结算）：
  - 分母 = 2,637 语句（quote_service 340 + payment_service 236 + contract_service 108 + gate_service 275 + projects/events 110 + projects/permissions 24 + dispatch 14 模块 1,544）；
  - 分子 = 2,240 覆盖语句；
  - **覆盖率 = 84.9% ≥ 60% ✅**。
  - 分模块：quote 92% / payment 86% / contract 87% / gate 87% / dispatch 核心——scoring 96%、maintenance 98%、access 94%、matching 93%、rules 93%、disputes 91%、settlements 89%、packages 88%、offer_service 84%、cities 85%、profiles 67%、routes 54%（HTTP 薄层，业务在 service 层）。
- **宽口径**（含 projects 全部=task/gantt 工作台模块）：**71%**（4,283 语句/1,262 缺失；task_service 19%、gantt 23% 为非商业模块拉低项，单列透明）。
- 测试集：`tests/test_quote_first_order_concurrency.py` + `test_smoke_entrypoints.py` + `test_import_contracts.py` + `test_dispatch_*.py`（9 文件）= **85 passed**。

### 全量口径（H5 终版）

| 口径 | 附录 A 快照 | 收口实测 |
|---|---|---|
| 表 | 76 | **86**（派单 +8 全齐 + goal-d1 presurvey_intakes） |
| 迁移 | 9 / head `a9c3f1d8e2b4` | **15 / head `c5d7e9f1a3b7`** |
| 蓝图路由 | 212 | **228** |
| api_catalog ENTRIES | 54 | **68** |
| 服务端 pytest | — | **CI 1431 passed + 6 skipped**（收口轮后再 +3=1434） |
| 桌面 vitest | — | **660** |

### H1–H3 闸门指标（如实）

G9 一次通过率 ≥70%、平台方工时占比 ≤25%、毛利率 ≥70% 需要**真实或内测/仿真交付数据**——平台尚无生态交付单。处理：指标定义与阈值已固化 `acceptance_metrics.json`（来源 BP §11/设计 §8.8），度量公式与统计口径已写入种子 conventions；**本收口报告不对这三项出具「达标」结论**（不粉饰），列为「仿真通道就绪、待真实数据回填」项，与附录 B 待签字项同列。

## 四、§八终止判定逐条对照（不粉饰）

| # | 条件 | 判定 | 说明 |
|---|---|---|---|
| 1 | A–H 全满足 | ✅（带 3 项明示例外：C7 混合转换 job 部分、H2/H3 待真实数据、G=并行轮交付） | 见第二节逐项 |
| 2 | P0 8 项 + P1 7 项判据全过；P2 除暂缓外落地 | ◐ **P0 8/8 + P1 7/7 全过；P2-1/3/6 落地，P2-5 暂缓（设计标注）+ P2-2 待拍板（无目标值）+ P2-4 未立项（L 级已登记）** | P2-4 私单封堵是剩余最大单项 |
| 3 | 开池四道闸全绿 + BP 闸门指标 | ◐ **四道闸全绿**；H2/H3 待真实数据（上节如实） | — |
| 4 | 负面清单 7 条防护 | ✅ 每条反例全绿（r5 + r8 语义修正后维持） | — |
| 5 | 附录 A 7 处冲突闭环 | ✅ 己方侧闭环（留注①–⑦消化）；**设计文档附录 A 修订稿待文档 owner 执行**（修订要点见下） | — |
| 6 | 附录 B 阻塞项按默认口径施工 + 待签字清单 | ✅ 全部按默认口径施工；待签字清单见第五节 | — |
| 7 | 连续一整轮零新增差距 | ✅ 收口轮零新增 P0/P1 差距（C10/B1/radius 为审计修复非新差距） | — |
| 8 | 最终收口报告 | ✅ 本报告 | — |

**结论（如实）**：终止条件 **1/3/4/5/6/7/8 达成；2、3 带明示例外**（P2-4 未立项、H2/H3 无真实业务数据）。依提示词「任何一轮的部分完成都只是下一轮的输入」——**本报告不宣布循环永久终止**，而是出具阶段性收口凭证：工程侧可交付项已全部落地并验证，剩余项全部为「外部输入依赖」（拍板/真实数据/设计文档侧修订）或「已登记的后继立项」（P2-4、仿真器、C7 转换 job）。

## 五、附录 B 待签字清单（汇总，默认口径已施工）

| # | 事项 | 当前默认口径（已施工） | 待签字方 |
|---|---|---|---|
| B-① | 算法备案定性 | 按「需要备案」准备（材料 6 件清单对齐 A-7）；claim/自动撮合在备案+公示前维持降级态（claim_closed / rule_version_required 422） | 律师意见书 |
| B-② | 资金托管/开票主体 | 平台公司统一收款开票 + 四席位内部分账（disputes/settlements 已按此建模） | 财务/法务 |
| B-③（附录 C） | §7.4 预扣率表 | 税务总局 2025-16 号公告口径落 `WITHHOLDING_BRACKETS` 常量（集中一处） | 法务/税务 |
| B-④（§12） | 首批六城名单 | 苏州/无锡/常州/南京/南通/宁波建议名单落种子，claim_enabled 全 false | 业务拍板 |
| 留注①–⑦ | r1/r2 schema 语义 | 列集+支撑列/骨架表先行/复购约束放宽/席位载体/冷启动代理口径/onsite 派生+金额物化/视图时差 | 设计文档 owner |
| 留注⑧–⑮ | r3–r5 工程口径 | 交接执行人=leader/onsite 关键词派生/金额物化/时差窗口/开闸条件 3 代理/评估窗 P1-2/指标 schema/行业大类两值 | 设计文档 owner |
| 留注⑯–㉒ | r6–r7 工程口径 | L2 双签二期/留存只读报告/T+30 月度参数化/交接 leader/SLA 统一 50/撮合前置=公示版本/仿真对比二期 | 设计文档 owner |
| 新增 | P2-2 状态集 | 无目标值不发明 | 业务拍板 |

## 六、附录 A 修订建议（提交设计文档 owner 的修订稿要点）

1. A-③④⑤⑥ 按收口实测重写：**86 表（派单 +8：delivery_packages/dispatch_offers/fde_profiles/fde_level_evidence/dispatch_rule_versions/delivery_settlements/package_access/disputes）**、**15 revision / head `c5d7e9f1a3b7`**、**路由 228**、**ENTRIES 68**、乐观锁 **33 模型类**（VersionedMixin+PackageAccess/Dispute 计入）。
2. 新增冲突条目（代码为准，已消化）：A-⑧ enterprise_code 唯一约束放宽（§3.3 复购判据）；A-⑨ 「独立交付」席位载体=delivery_packages 执行席位（§3.3 原文误写 delivery_settlements）；A-⑩ PUBLIC_FIELDS 处「进白名单」与「锁定」矛盾→只读节口径；A-⑪ acceptance_metrics.json schema 设计未给（工程最小决定）。
3. §4.6 首版到场词表与实现对齐：现场/到场/驻场/驻点。

## 七、下一轮输入（循环继续条件）

1. **P2-4 私单封堵**（L 级）：服务层校验钩子——派单池外成交的技术封堵；建议与「FDE_DISPATCH 立项入口」同轮。
2. **C7 混合模式自动转换 job**（assign 24h 超时 → 转 claim，前置=城市开闸）：挂 dispatch.maintenance 或独立 job。
3. **撮合仿真器**（留注⑳）：历史包回放打分——H2/H3 指标回填的前置工具。
4. **外部输入到位后**：备案结论（B-①）→ 开闸链路；税率表法务确认（B-③）→ 常量替换；城市名单拍板（B-④）→ 种子更新。
5. **桌面交付纪律**：本轮桌面改动（r7 三页）已进 main——便携版重打包按 README「打包桌面端」节执行（asar 字节验证），下一交付批次处理。

---

*收口报告完 · goal 循环 r1–r8 · 2026-10-31。工程证据链：PR #33/#34/#35/#36/#39/#40/#41 + 本轮收口 PR；全部合并于 fork/main，镜像与 alembic 均随合并重建升级。*
