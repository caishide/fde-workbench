# AI 原生化差距台账 v1

配套 [AI原生化差距评估-v1.md](./AI原生化差距评估-v1.md) 的逐条对账台账。

- **评估基线**：fork/main `cddefd4`（#231）；活库探针 2026-11-09。
- **用途**：每轮实施前认领条目 → 实施后按「消解判据」复测 → 回写状态与实施轮号（PR 号）。锚点是行号级快照——**上游合并后行号漂移不算失效**，按符号重 grep 即可；**语义漂移**（锚点所指行为变了）须复核并在本行注记。
- **状态语义**：`OPEN`（未实施）／`IN_PROGRESS`（在途 PR）／`CLOSED`（消解判据复测通过，注记 PR 号）／`WONTFIX`（有意不消解，注记理由）。

| 编号 | 差距 | 归属特征 | 现状锚点（2026-11-09） | 消解路径 | 消解判据 | 状态 | 实施轮 |
|---|---|---|---|---|---|---|---|
| G-01 | 三条 AI 执行通道源码默认全关；agent 执行面活库零行使 | ①④ | `server/src/fde_api/config.py:83`（dsh）、`:147`（宿主通道）、`:158`（轮询）；agent_runs=0 | Path 0 | 受控试点内至少一条通道开启，且首个含 agent run 的真实订单至 G9 | OPEN | — |
| G-02 | AI 不能发起 run：MCP 17 工具无 initiate 类；发起路由全部面向人 | ①③ | `server/src/fde_api/control/mcp_gateway.py:36`（17 键全列见评估 §2） | Path 3 | MCP/api_actions 新增受 15min 确认窗的 run 发起动作，端到端审计留痕 | OPEN | — |
| G-03 | DAG 规划无 AI：节点类型四值闭集；图来源=人工模板或确定性编译器 | ① | `server/src/fde_api/workflows/constants.py:50`；`workflows/compiler.py:326`；`server/seeds/workflow-templates.json` | Path 1 | 存在 AI 起草 DAG 草稿→validate 干跑→人工 create_definition 发布的完整链 | OPEN | — |
| G-04 | 交付方案生成器确定性拼装，零 AI | ① | `server/src/fde_api/plans/service.py:64,75` | Path 1 | 方案条目支持 AI 起草且仅经 approved 闸发布（版本化不覆盖历史） | OPEN | — |
| G-05 | 测试用例生成器确定性拼装，零 AI | ① | `server/src/fde_api/quality/service.py:4,72` | Path 1 | test_cases 支持 AI 起草通道，审核语义仍由计划 draft→approved 闸承载 | OPEN | — |
| G-06 | 派单纯规则零 AI（低优——PRD 拍板「责任主体永远是人」，只做建议入口不夺权） | ① | `server/src/fde_api/dispatch/scoring.py:3,7` | Path 1（低优） | 派单例外建议由 AI 起草、人工终审采纳，责任主体语义不变 | OPEN | — |
| G-07 | 门禁 AI 起草证据候选链未接：captured_from 单一 human 源；agent_run:/workflow_node: 前缀全仓零生产者 | ①② | `server/src/fde_api/projects/gate_service.py:275`；`evidence/models.py:18`；`evidence/service.py:84-98` | Path 1/2 | 首个 agent run 产物自动登记为建议性证据候选（采纳仍走人工提交闸） | OPEN | — |
| G-08 | 人工接受信号只写不读：reviewed 无任何 AI 面消费点 | ② | `server/src/fde_api/agents/service.py:1445,1468`（写）；`:363`（仅 API 呈现） | Path 2 | 至少一个 AI 面消费点读取 reviewed（如审查优先级/提示词复审信号） | OPEN | — |
| G-09 | ai_call_audits 无提示词指纹/版本列，输出无法按提示词版本归因 | ②④ | `server/src/fde_api/workbench/models.py:920` 起（列集：request_id/actor/purpose/model/tokens/status/error_code） | Path 2 | 新列落地（迁移），新调用全量回填指纹，历史行容忍空值 | OPEN | — |
| G-10 | golden set 不连真实模型；CI 无 AI 评测 job | ②④ | `server/tests/fixtures/ai/opportunity_golden_set.json`（23 例）；`server/tests/test_ai_eval/test_ai_eval_opportunity.py:19`（直调后处理）；`.github/workflows/ci.yml`（四 job 无 eval） | Path 2 | CI eval job 按交付效果评测协议 v0 跑真实模型并出 uplift 报告（insufficient_data 语义保留） | OPEN | — |
| G-11 | 模拟实验室改进链止于 approved，「只提案不落地」无发布通道 | ②④ | `server/src/fde_api/simulation/improvement_service.py` 头注（P8 四条）；`server/tests/test_simulation_improvement.py:403`（静态钉） | Path 2 | 受控发布通道（发布闸+审计+可回滚），静态钉改为「只许经发布通道写」语义而非删除 | OPEN | — |
| G-12 | ~~模拟模型评估 server 模式未接线~~ | ④ | 已消解：`server/src/fde_api/simulation/model_evaluation.py:168`（ServerModelEvaluation→ai/deepseek complete_json purpose="simulation_evaluation"）+ `evaluation_prompt.py:17` + `evaluation_schema.py` 契约 | — | 真模型评估栈在仓（#231）；活库行使归 Path 0/2 | **CLOSED（#231，2026-11-09）** | #231 |
| G-13 | 提示词版本化 1/5：仅 discovery 带版本戳；模拟评估 Rubric 有版本、提示词本体无 | ④ | `server/src/fde_api/discovery/models.py:44,93`；`ai/research_form_prompt.py:9`；`ai/industry_template_prompt.py:10,21`；`simulation/evaluation_prompt.py:17` | Path 4 | 全部 SYSTEM_PROMPT 常量进版本注册表并回填审计归因 | OPEN | — |
| G-14 | 指标面只读无回流：metrics v31 七指标无任何自动消费方 | ② | `server/src/fde_api/metrics/service.py:341`（v31 节） | Path 2 | 指标触发至少一个自动改进动作（如阈值越限生成提示词复审工单） | OPEN | — |

## 附注

- **G-12 遗留小漂移**：`simulation/model_evaluation.py:10-11` 模块头 docstring 仍写「本轮未接线」（G1 陈旧注记）；类级 docstring（`:168` 起）为权威。属 #231 自身文档漂移，留给下一 V3.2 轮顺带清理。
- **红线约束适用于全部条目**：AI 不代拍板；门禁证据只存指针+sha256；客户资料不入库；写外呼/发信/付款永不降级不自动。任何条目的实施轮不得以「消解差距」为由放宽上述边界。
- **首圈注记（2026-11-09）**：售前链已有首批真实数据（discovery 2 / facts 22 / requirements 7 / delivery_plans 1 / test_plans 2 / workflow_runs 1 succeeded；ai_call_audits 3 succeeded + 3 failed `ai_output_invalid`）——G-01 的「售前段」半边事实上已破（部署侧 env 覆写），但源码默认值与 agent 执行面未动，条目维持 OPEN。
