# AI 原生化差距评估 v1

**评估问题**：本项目离「AI 原生应用」还有多远？怎么才能成为真正的 AI 原生应用？

- **日期**：2026-11-09（评估框架经蔡工确认后落盘；含对 2026-11-08 口头评估的五处复核修正，见 §9）
- **评估基线**：fork/main `cddefd4`（#231，2026-11-09 合并）；结构口径=`docs/audit/v3-workbench-inventory.json` 现测 **397 路由 / 49 蓝图 / 132 表 / 52 rev 单头 `b3e7c9d1a5f2`**；活库=2026-11-09 生产库只读探针（docker exec + 只读 SQL）。
- **性质**：纯评估文档（零代码零迁移零路由）；**不构成任何实施授权**——§7 四路径均须随轮立项 + 拍板后才可施工。
- **配套台账**：[AI原生化差距台账-v1.md](./AI原生化差距台账-v1.md)（G-01–G-14，每条带 file:line 锚点 + 消解判据 + 状态，供逐轮实施对账）。

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 抽离测试（移除 LLM 会怎样） | **不通过**——决策与账务主干（方案/测试计划/门禁/派单/报价/收款/合同/权益）全部存活，只有售前与执行面的 AI 管线崩塌 ⇒ **当前是 AI+（AI 增强）形态，不是 AI 原生** |
| 四特征（信通院框架） | ①智能内生=**部分**；②数据飞轮=**生产段已通、回流段全断**；③人机协同=**接近达标**；④持续进化=**基建渐备、行使为零** |
| BP §1.3a 官方自评 L2+ | **复核成立**；L3 的两道坎=决策位 AI 起草（Path 1）+ 飞轮回流闭环（Path 2）；L4 ≈ AI Native 抽离测试通过的交付域形态 |
| 最关键的事实变化 | **飞轮首圈已于 2026-11-08→11-09 之间转过**（售前链首批真实数据落库，见 §5）——「从零开始」的门槛已过，但回流段四断点一条未通 |
| 差距总量 | 14 条（台账 G-01–G-14，其中 G-12 已被 #231 消解）；四条路径 Path 0–4 |

## 1. 评估口径

三把尺子（评估框架经蔡工提供确认）：

1. **抽离测试**：把系统里的 AI 模块整体拿掉——产品崩塌=AI 原生；只是降级=AI+。
2. **AI Native vs AI+**（信通院口径）：AI 的角色是「工具」还是「大脑」；业务流程是「原流程打补丁」还是「围绕 AI 重建」；人机关系是「人操作 AI」还是「人管理 AI Agent」。
3. **四特征**：①智能内生（AI 是心脏与调度中枢）②数据飞轮（业务执行产生数据持续优化 AI）③人机协同（AI Agent 是独立「第二工作主体」）④持续进化（AI 从使用中实时进化，而非只随版本更新）。

**与 BP §1.3a 的对齐**：BP v4.0 §1.3a 的交付智能化等级 L1–L5（L1 人工交付 → L2 流程自动化 → L3 AI 辅助交付=「AI 生成初稿物、人工审核修改后交付」→ L4 监督自主=「AI 端到端完成标准单全节点交付（含证据链），人只做异常处理、终审与客户沟通」→ L5 全自主）与本评估刻度天然同构：**L3=AI 进决策位（本评估 Path 1），L4=抽离测试通过的交付域形态（≈AI Native 语义），L5=全自主**。BP §1.3a 同时钉死命名空间：L1–L5 是系统智能化轴，人的五层角色 L0–L5 是职级轴，两轴互不引用；`fde_profiles.level`（个人资历轴）与 `agent_runs.fallback_level`（单 run 降级链 L0–L3，`agents/models.py:74` CHECK）都不是这条轴。

## 2. 结构基线与 AI 资产盘点（2026-11-09 现测）

**结构口径**（`docs/audit/v3-workbench-inventory.json`）：132 业务表 / 52 迁移（单链 head `b3e7c9d1a5f2`）/ 397 路由 / 49 蓝图；`api_catalog` 94 ENTRIES；pytest CI 2396 passed + 6 skipped（#228 run 42503516295）/ vitest 960 / mypy 279。

**AI 面资产（都已存在，这是「底子好」的一面）**：

| 资产 | 锚点 | 状态 |
|---|---|---|
| AI 单一入口 execute_ai_prompt（预算门+审计+降级直连） | `control/ai_server_client.py:186` | 在役；活库已有成功调用 |
| DSH 版本化运行时客户端 | `control/dsh_runtime.py` | 默认关 |
| 宿主侧 zcode 代理（裁定 A） | `agents/host_channel.py` | 默认关，零行使 |
| 宿主轮询领取/回执面 | `agents/`（#204 三路由） | 默认关，零行使 |
| MCP 工具面 **17** 个（15 只读 + 2 写） | `control/mcp_gateway.py:36`（写：`file_send_wechat` :39、`api_execute` :41） | 在役 |
| AI 发起写动作的 propose→密码确认→execute 模式 | `control/api_actions.py:33`（15min 确认窗） | 在役（模板价值见 Path 3） |
| AI 访问分层 ACCESS_RANK 五级 | `control/access.py:36` | 在役 |
| 单 run 降级链 L0–L3 | `agents/models.py:74`（CHECK） | 在役 |
| 提示词常量 **5** 个 | `discovery/prompt.py`（DISCOVERY_SYSTEM_PROMPT）、`ai/research_form_prompt.py:9`、`ai/industry_template_prompt.py:10,21`、`simulation/evaluation_prompt.py:17` | **仅 discovery 带版本戳**（G-13） |
| 机会点 golden set 23 例 | `server/tests/fixtures/ai/opportunity_golden_set.json` | 只测后处理，不连模型（G-10） |
| 模拟实验室 L-A/L-B/L-C 三层评估 | `simulation/evaluator.py:14`（三层定义）、`simulation/model_evaluation.py:168`（G9 真模型层） | L-B 已接真模型栈，活库零行使 |
| 交付效果评测协议 v0 | `docs/architecture/交付效果评测协议-v0.md` | 文档层冻结，无 CI 消费 |

## 3. 抽离测试（逐链）

把 LLM 从系统里整体拿掉，逐链看崩不崩（✅=存活，❌=崩塌）：

| 链路 | 移除 LLM 后 | 判定 | 锚点 |
|---|---|---|---|
| 交付方案生成 | ✅ 完全存活——**本就确定性拼装，从未调用 AI** | AI+ 证据 | `plans/service.py:64,75` |
| 测试计划生成 | ✅ 同上，注释明言「AI 用例通道为未来增强」 | AI+ 证据 | `quality/service.py:4,72` |
| 门禁 G1–G9 | ✅ 零 AI 调用；证据 captured_from 单一来源 `human` | AI+ 证据 | `projects/gate_service.py:231,275,362` |
| 派单撮合 | ✅ 纯规则引擎（「纯函数、无 DB 依赖」「零画像输入」） | AI+ 证据 | `dispatch/scoring.py:3,7` |
| 报价/收款/合同/权益/免费额度 | ✅ 规则+密码确认闸，无 AI | AI+ 证据 | `commercial/`（G1/G2 两轮） |
| 访谈事实抽取 | ❌ 崩——活库已有 2 次真实调用 | AI 在役 | `discovery/jobs.py:108` |
| 售前分析/预调研 | ❌ 崩 | AI 在役 | `guidance/`（ai_prompt 管线） |
| 机会点候选 | ❌ 崩——golden set 只测 `_normalize_candidates` 后处理 | AI 在役 | `server/tests/test_ai_eval/test_ai_eval_opportunity.py:19` |
| 行业模板/调研表 AI 生成 | ❌ 崩 | AI 在役 | `ai/industry_template_prompt.py:10,21` |
| chat | ❌ 崩（16 轮真实会话在库） | AI 在役 | ai_chat_turns 表 |
| agent run（DSH/宿主通道） | ❌ 崩——通道在、默认关、活库 0 run | 结构在役 | `agents/host_channel.py`、`config.py:83,147,158` |
| workflow skill 节点 | ❌ 崩（use_tools=False 文本变换走 LLM） | 结构在役 | `workflows/dispatch.py:316` |
| 模拟实验室 L-B 模型评估 | ❌ 崩（G9 已接真模型，活库 0 次） | 结构在役 | `simulation/model_evaluation.py:168` |

**判定**：决策权威（门禁拍板）、交付主干（方案/测试计划/派单）、账务主干（报价/收款/合同/权益）在无 LLM 的世界里**一行代码都不用改**。AI 是「内容处理器」，不是「调度中枢」⇒ **AI+**。抽离测试不过。

## 4. 四特征评分

### ①智能内生 —— 部分

**成立面**：售前 AI 管线完整且已有真实吞吐（§5 首圈）；执行面结构齐备（17 MCP 工具、L0–L3 降级链、预算闸、审计账本、宿主双通道）。
**缺口面**：AI 不在调度位——**run 只能人发起**（17 个 MCP 工具无一可发起 agent/workflow run，`control/mcp_gateway.py:36`；发起路由全部面向人）；**DAG 只能人规划**（节点类型四值闭集 `workflows/constants.py:50`，图来源=人工模板 `server/seeds/workflow-templates.json` 或确定性编译器 `workflows/compiler.py:326`）；**决策位零 AI**（§3 前五行）。

### ②数据飞轮 —— 生产段已通、回流段全断

2026-11-09 起，飞轮的「业务执行产生数据」半圈已真实转过（§5）；但「数据反哺优化 AI」半圈**四断点一条未通**：

- **断点 a**：人工接受信号只写不读——`agents/service.py:1445` 写 `reviewed`，全仓无任何 AI 面消费点（仅 API 呈现 `:363`）；
- **断点 b**：审计账本无提示词指纹——`ai_call_audits` 列集（`workbench/models.py:920` 起）存 model/tokens/status，无 prompt 指纹/版本列 ⇒ 输出质量无法归因到提示词版本；
- **断点 c**：golden set 不连模型（G-10）；CI 无 AI 评测 job（`.github/workflows/ci.yml` 仅 server-tests/pseudonymization/desktop/secrets-scan 四 job）；
- **断点 d**：模拟实验室改进链止于 `approved`（「只提案不落地」P8 四条强制落点，`simulation/improvement_service.py` 头注；静态钉 `server/tests/test_simulation_improvement.py:403`）——提案永远到不了生产提示词/技能/工作流。

### ③人机协同 —— 接近达标

Agent 作为「第二工作主体」的主体性结构最完整：独立 run 生命周期（queued→host_running→终态，含 `succeeded_but_receipt_invalid` 诚实终态）、逐 run 预算与 L0–L3 降级链、产物 sha256 指针化+人工接受/撤回面（tb2 轮）、宿主代理与授权 run 一一对应（红线第 5 条边界五条）。商业化 G2 又加了当事人自证动作（企业确认）等协同语义。**缺口**：AI 不能自启动（G-02，Path 3 的提议+确认模式是补法）；多 Agent 编排未开；桌面单 run 控制台。

### ④持续进化 —— 基建渐备、行使为零

G9 已把真模型评估层接进仓库 AI 栈（`simulation/model_evaluation.py:168` ServerModelEvaluation→`ai/deepseek` complete_json + `evaluation_schema` 严格契约 + `evaluation_prompt.py:17` 三纪律提示词）——**评估基建是四特征里最新到位的一块**；但活库 `simulation_runs=0`（一次都没跑过）、提示词版本化 1/5（G-13）、CI 无模型评测（G-10）、改进链无发布通道（G-11）。「从使用中实时进化」目前是零。

## 5. 通道与活库现状（两次探针对照）

**三条 AI 执行通道源码默认全关**：`config.py:83 dsh_enabled=False` / `:147 agent_host_channel_enabled=False` / `:158 agent_host_poll_enabled=False`（部署可经 `server/.env` 覆写；售前段的 audits 成功行说明部署侧确已覆写开启）。

**活库对照（2026-11-08 首探 → 2026-11-09 复测）**——这是本评估相对 2026-11-08 口头结论的最大事实更新：

| 表 | 11-08 | 11-09 | 读法 |
|---|---|---|---|
| discovery_extractions | 0 | **2** | 真实抽取已跑 |
| business_facts | 0 | **22** | 事实已入库 |
| requirements | 0 | **7** | 需求已结构化 |
| delivery_plans | 0 | **1** | 方案已生成 |
| test_plans | 0 | **2** | 测试计划已生成 |
| workflow_runs | 0 | **1（succeeded）** | 首个工作流跑通 |
| ai_call_audits | 4（3 failed/ai_output_invalid） | **6（3 succeeded + 3 failed/ai_output_invalid）** | 真模型调用成功 2 次（对应 2 次抽取）；失败率仍 50% |
| ai_chat_turns | 16 | 16（15 completed + 1 failed） | 持平 |
| agent_runs | 0 | **0** | 执行面仍未动 |
| agent_artifacts | 0 | **0** | 无产物 |
| simulation_runs | 0 | **0** | 模拟场未行使 |
| automation_task_runs | 0 | **0** | 自动化未行使 |

**读法**：**V3.1 售前链（抽取→事实→需求→方案→测试计划→工作流）的首圈是真实转过的**——正是 pilot-runbook 的 E2E 语义；AI 在其中真实出力（audits 成功行）。但①执行面（agent）零行使——「AI 作为第二执行主体」还停留在结构；②ai_call_audits 成功/失败对半（3/3，失败码 `ai_output_invalid`=契约不合规），提示词与契约成熟度有待首份质量复盘；③飞轮回流段四断点未通（§4②）。

## 6. BP §1.3a 等级复核

BP v4.0 §1.3a 官方自评 **L2+（强 L2，向 L3 演进中）**（2026-11-01 口径）。本次复核**成立**，并可细化：

- **L2 证据充分**：门禁 G1–G9、报价/收款/合同、派单规则引擎、SOP 状态机全部在役（§3 前五行）——「系统不通过门禁就走到不了下一步」成立。
- **已触及 L3 的部分比 BP 成文时更实**：BP 说「AI 辅助生成已上线」，当时主要指售前初稿；2026-11-09 活库已出现**AI 真实出力的结构化链样本**（2 抽取→22 事实→7 需求）——L3 的「AI 生成初稿物→人审」语义在售前段有了真实样本。
- **L3 未达成的两道坎**（=台账 Path 1+2）：①**决策位 AI 起草**——方案/测试计划生成器仍是确定性拼装（G-04/G-05），DAG 无人规划不可言（G-03）；②**飞轮回流闭环**——AI 生成物的人工接受信号、审计归因、评测回归全部断链（G-07…G-11、G-13、G-14）。
- **L4=监督自主 ≈ AI Native 语义的交付域形态**：抽离测试通过（拿掉 AI，标准单交付崩塌）+ 人只做异常处理与终审。BP §1.3a「P0–P1 推进 L3 落地、P2 之后探索标准单 L4」的节奏与本评估 Path 0→1→2→3 顺序一致。

## 7. 成为 AI 原生的四条路径（每条须随轮立项+拍板）

**Path 0 · 前置通道跑通（存量闸，最优先）**：在受控试点（pilot-runbook C1–C7 前置闸）内开启执行通道，完成首个含 agent run 的真实订单至 G9。活库 `agent_runs=0` 意味着「第二执行主体」从未上岗——这是其后一切路径的数据前提。红线：宿主通道边界五条（AGENTS 红线第 5 条）、H1–H13 强制人工节点不解除。

**Path 1 · AI 进决策位（翻抽离测试的第一步）**：把「AI 起草→人工审核→发布」两段式推进到三个确定性生成器——方案条目起草（G-04）、测试用例起草（G-05，quality 两段式审核戳先例）、任务分解/DAG 草稿（G-03，`compile_plan_workflow` 输入侧 AI 化，产出仍走 validate+create_definition 人工通道）。门禁拍板不 AI 化（红线），只补 AI 起草的证据候选链（G-07）。

**Path 2 · 飞轮回流闭环（AI+ 与 AI Native 的分水岭）**：①`ai_call_audits` 加 prompt_fingerprint/prompt_version 列（G-09）；②消费 `reviewed`/验收信号驱动复审（G-08）；③golden set 接真实模型进 CI eval job，按交付效果评测协议 v0 出 uplift 报告（G-10）；④给模拟实验室改进提案建**受控发布通道**（发布闸+审计），替代「只提案不落地」的死锁——静态钉改语义而不是删除（G-11）。

**Path 3 · AI 提议+人确认（自主化的安全形态）**：把 `control/api_actions.py:33` 的 propose→密码确认→execute（15min 窗）成熟模式扩到「发起 workflow/agent run」——AI 可提议，人一键确认（G-02）。这与「AI 不能自启动」的缺口一一对应，且不越 H1–H13。

**Path 4 · 版本注册表与按质量路由（进化底座）**：全部 5 个 SYSTEM_PROMPT 常量进版本注册表（G-13），审计按版本归因，模型选择从人工配置走向按评测质量路由（消费 Path 2 的 eval 产出）。

**建议顺序**：Path 0 → 2（先闭环再扩位——飞轮比决策位便宜且不碰红线）→ 1 → 3 → 4。每条路径的逐条差距、消解判据、状态见台账。

## 8. 红线边界（评估与实施都不逾越）

- AI 不代拍板：门禁拍板、审批、终审永远是人工（H1–H13 强制人工节点）；AI 只起草、建议、候选。
- 客户真实资料不入库不入仓：AI 面只传代号化上下文（T-A2 三道防线、discovery fail-closed 脱敏）。
- 门禁证据只存 `source_uri` 指针 + sha256；AI 产物原件永不入库。
- 写外呼、发信、付款永不降级、永不自动（`file_send_wechat` 事前密码确认边界维持）。
- AI 审查不执行被审代码（红线第 7 条）；宿主通道五边界（红线第 5 条）。
- 「写错不重做」语义（`succeeded_but_receipt_invalid`）与 L0–L3 降级链是 AI 自主化的安全底座，Path 1–3 不得绕开。

## 9. 复核记录（2026-11-09 相对 2026-11-08 口头评估的修正）

口径纪律「引用前现测」的实例——五处修正，全部发生在落盘复核时：

1. **三通道锚点漂移**：`config.py` 的 `dsh_enabled`/`agent_host_channel_enabled`/`agent_host_poll_enabled` 行号 80/144/155 → **83/147/158**（同文件前部增码所致）。
2. **MCP 工具数**：16 → **17**（15 只读 + 2 写；17 键全列见 §2 表）。
3. **「模拟模型评估未接线」已过时**：#231（2026-11-09 合并）已落 G9 真模型评估层——`ServerModelEvaluation` 走 `ai/deepseek` 真栈+严格契约。**遗留小漂移**：`simulation/model_evaluation.py:10-11` 模块头 docstring 仍是 G1「本轮未接线」陈旧注记（类 docstring `:168` 为权威），留给下一 V3.2 轮顺带清理，本轮纯文档不代修。
4. **「飞轮未转过」已过时**：2026-11-09 复测发现售前链首批真实数据（§5 对照表）——结论改写为「生产段已通、回流段全断」。
5. **提示词常量盘点更新**：4 → **5 个**（G9 新增 `simulation/evaluation_prompt.py:17`；仍仅 discovery 带版本戳）。
