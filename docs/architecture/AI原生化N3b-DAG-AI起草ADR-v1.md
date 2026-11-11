# AI 原生化 N3b · G-03「DAG AI 起草」ADR v1

- **状态**：**已拍板**（蔡工交互拍板三问，2026-11-11；留痕可推翻，通道见 §8）。
- **性质**：设计轮纯文档——零代码、零迁移、零路由、零桌面；本体轮（任务书 §15 序 3）的**开工依据**。
- **来源**：任务书 §15 序 2「节点闭集是否扩展／双来源谁优先」＋ §N3b 四问；台账 G-03（OPEN，消解判据＝「AI 起草 DAG 草稿→validate 干跑→人工 create_definition 发布」完整链）。

## 0. 结论速览（三拍板）

| # | 设计问题 | 裁决 | 一句话理由 |
|---|---|---|---|
| Q1 | 节点类型闭集是否扩展？ | **不扩展**——维持四值 `call/skill/agent/human_approval` | AI 起草的价值在**编排既有积木**，不在发明新节点；闭集是治理面（validate 白名单＋执行器守卫），扩类型＝扩执行器风险面；`models.py:27` 注释既有裁决「新类型待真实需求」同向 |
| Q2 | AI 起草产物落在哪个态？ | **返件式草稿、零落库**——路由只返回草稿 DAG＋validate 干跑明细；人工采纳走既有 `create_definition`（draft 态）→ `publish_definition`（admin，D-2） | 与 G-03 消解判据逐段字面吻合；一切失败模式天然**零残留**；「定义创建者」语义不被 AI 污染（归因走事件＋审计账本）；零迁移零新表 |
| Q3 | 与 `compile_plan_workflow` 的关系？ | **并列双来源、闸唯一**——draft-from-plan（零 AI）维持缺省腿；AI 起草为旁挂增强腿，同输入域两稿可比、人工择优；两腿产物走同一条 create_definition＋publish 闸 | 缺 AI 时旧路径零回归（本体轮 DoD③）；对比择优是最诚实的 AI 采纳面；闸唯一＝AI 无任何旁路 |

## 1. 背景与现状锚（2026-11-11 现测）

G-03 现状：DAG 规划无 AI——节点类型四值闭集，图来源＝人工模板（`server/seeds/workflow-templates.json` 三套平台模板）或确定性编译器。真身锚：

- **定义侧闭集** `server/src/fde_api/workflows/models.py:27`：`NODE_TYPES = ("call", "skill", "agent", "human_approval")`（注释即裁决：「没有 condition/wait 节点——when 表达式与 depends_on 已覆盖既有需求；新类型待真实需求」）；
- **执行侧守卫副本** `server/src/fde_api/workflows/constants.py:50`：`SUPPORTED_NODE_TYPES`（「守卫防未来类型漏实现」——扩类型须两处同步改，本轮两处都不动）；
- **校验闸** `workflows/definition_service.py:124` `validate_dag`：节点字段白名单、key/占位符约束、环检测（出确定性拓扑序）、registry 对账（published 技能／在册 agent／审批能力白名单〔排除 `system.*`〕）；`validate_dag_against_registry`（:500）为生产注入口；P0-4 已放行五个草稿期契约字段（`timeout_seconds`/`input_schema`/`output_schema`/`failure_class`/`plan_ref`，执行器消费随 P1 执行通道轮）；
- **生命周期**：`create_definition`（:528，can_manage，落 `draft`＋`workflow_definition_created` 事件）→ `publish_definition`（:596，**发布前按当前 registry 复验**，发布权限 admin-only＝P0-4 D-2 拍板）→ 版本行不可变；
- **确定性编译器** `workflows/compiler.py:326` `compile_plan_workflow`：只收 approved/published 方案，三节点形 plan_review→implement→acceptance_review，确定性输出；`draft-from-plan` 路由（routes.py:196）落库走 create_definition 通道，不建平行持久化路径；
- **validate 干跑路由** `validate_workflow_route`（routes.py:243，对已落库定义零副作用）；
- **N2/N3a 先例机制**（本轮全量复用，不发明新机制）：`execute_ai_prompt` 单一入口（预算门＋审计账本＋purpose/prompt_version/model 归因三元）、J-1 system 组装点白名单、输出端兜底脱敏 `redact_text_detailed`（词典故障 fail-closed／凭据串拒绝）、契约失败整批零写入。

## 2. 拍板一：节点闭集不扩展

**裁决**：AI 起草只产出**既有四值 type**＋`validate_dag` 白名单字段（含 P0-4 五个草稿期契约字段）。

**派生约束**：
- 执行侧守卫副本 `constants.py:50` 与定义侧 `models.py:27` 同步不动；本体轮不加「AI 可用类型」第二份清单——同一闭集就是全部可用面；
- `human_approval` 节点语义零改动（任务书 N3b「明确不做」同向）：人工确认点不可被 AI 弱化，AI 起草的图里出现 human_approval 时其审批流照旧走既有审批通道；
- **契约推荐项（留痕可推翻）**：AI 起草契约建议附「产出图须含 ≥1 个 `human_approval` 节点」约束——首批模板与 `compile_plan_workflow` 三节点形均含人工确认点，AI 稿对齐此形状可把「全自动图绕过人工」的结构风险关死；若真实需求出现合法的纯只读无人工图，属拍板项另行放宽，不在本 ADR 预支；
- 新节点类型需求出现时走独立设计轮（不并入 N3b 本体轮）。

## 3. 拍板二：返件式草稿、零落库

**裁决**：AI 起草路由**只返回草稿，业务域表零写入**；持久化只有人工一条路。

**路由形状（本体轮实施清单）**：NEW `POST /api/v1/projects/<project_id>/workflows/generate-ai-draft`（挂既有 `workflows_blueprint`——蓝图数不变；不进 api_catalog——控制台面先例；can_manage＝与 create_definition 同权限尺）。

- **请求体**：`{plan_id, implementation_skill_ref, approval_capability?}`——与 `compile_plan_workflow` 同输入域（拍板三对比性的前提）；
- **前置闸**：方案须 approved/published（同编译器）；skill ref 须在 published 白名单（registry 实测，与 create_definition 同尺）；capability ∈ `APPROVAL_CAPABILITIES`；
- **机制**：
  1. `execute_ai_prompt` 单一入口：`purpose=workflow_dag_draft`＋`prompt_version=workflow-dag-prompt-v1`（审计账本归因三元；预算门照走）；NEW `WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT` 进 J-1 白名单（`test_prompt_entrypoint_gate` 登记）；
  2. 契约校验器（NEW 纯函数）：AI JSON 输出形状闭集（顶层 `{"nodes":[…]}`、禁未知字段——同 validate_dag 尺）＋复用 `validate_dag_against_registry` 全尺校验＋AI 特有约束（节点数上界〔值本体轮定并钉测试〕＋§2 契约推荐项）；
  3. 契约/JSON 失败：瞬时/契约各重试一次仍违 ⇒ 409 `ai_draft_contract_failed`（N3a 同裁）；**全程业务域零写入**——事件与 ai_call_audits 照常留痕（那是审计面，不是业务面）；
  4. 输出端兜底脱敏：`redact_text_detailed` 覆盖 params/标题等文本字段（词典故障 422 fail-closed／凭据串 422 `sensitive_credential_detected`）；
  5. 确定性归一：成功稿 nodes 按 validate_dag 的确定性拓扑序重排；响应携 `dag_sha256`（`dag_sha256()` 现成纯函数）。
- **响应形状**：`{draft: {dag_json, validate: {errors, warnings, order}, dag_sha256, plan_ref, implementation_skill_ref}}`——validate 干跑明细随身返回（预检），草稿不落库；桌面会话持有草稿原件（易失可接受——重新起草成本低）；
- **事件**：`workflow_dag_ai_drafted`（detail＝purpose/prompt_version/model/dag_sha256/node_count——**不带 DAG 全文**，原件永不进库与客户资料红线同构）。

**为何不选「经 create_definition 落 draft 定义行」**（否决项留痕）：那会把「人工 create_definition」环节吞进 AI 路由，G-03 判据字面不再成立；draft 列表出现 AI 产物需新列/新事件区分来源（膨胀面）；N3a 落库是因为 test_cases 既有「不可消费直到 approved」的消费闸，而工作流定义草稿一旦落库即在定义列表可见、人工误发布风险面更大——返件式把「采纳」决策完全留给人工，最小权限。

## 4. 拍板三：并列双来源、闸唯一

- `draft-from-plan`（确定性编译器）**零改动**＝缺省腿——本体轮 DoD③「缺 AI 时旧路径零回归」的承重墙；
- AI 起草＝旁挂增强腿，与编译器**同输入域**（approved/published 方案＋published 技能显式版本引用）——同一方案可两稿并列、人工逐节点对比择优；
- **采纳唯一通道**：人工 `create_definition`（其内部 `validate_dag_against_registry` 是第二道干跑）→ `publish_definition`（发布前第三道复验＋admin-only）。AI 无任何旁路，**闸不因来源放松**；
- **provenance**：定义行不新增来源列（零迁移）；AI 来源事实由 `workflow_dag_ai_drafted` 事件＋ai_call_audits 承载——create_definition 的人工 actor 即「采纳人」，谁采纳谁署名，语义干净。

## 5. 强制闸链与红线对齐

**三道 validate 干跑＋两道人工闸**：AI 路由内预检（validate_dag_against_registry）→ 人工 create_definition 复验（can_manage）→ publish 复验（admin，D-2）。三道全尺同闸（同一 `validate_dag_against_registry`），无第二套校验逻辑。

红线对照：
- **AI 审查不执行被审代码**——AI 只产文本草稿，不检出、不运行任何被审面；
- **AI 不代发起 run**（G-02 Path 3 维持）——起草≠执行，run 发起面照旧全部面向人；
- **J-1 提示词卫生**——system 常量白名单登记，外部文字不进 system 组装点；
- **客户资料红线**——输出端兜底脱敏＋事件只带指纹不带全文；
- **不把 AI 起草的图直接进生产 run**（任务书 N3b「明确不做」）——发布与运行之间还有既有人工闸。

## 6. 本体轮实施清单（§15 序 3 的 DoD 分解）

- NEW `server/src/fde_api/workflows/draft_ai.py`（提示词常量＋契约校验器＋确定性归一）；
- NEW 路由（`workflows/routes.py`，路由 462→463，不进 api_catalog，蓝图不变）；
- 测试 NEW `test_workflow_dag_ai_draft.py`（预估 8–10 例：happy＋归因三元／契约失败零写入＋重试一次／方案未 approved 409／技能白名单外 409／脱敏 fail-closed／节点闭集外类型拒绝／双来源回归钉 compile_plan_workflow 零改动／J-1 白名单静态钉）＋**变异三验证**红→还原绿；
- G-04（方案条目 AI 起草）随本体轮同 PR 落地（§15 序 3 范围），沿 N3a 形态（draft 态＋两段式审核戳既有闸零改动）；
- 口径：路由 +1／零迁移／J-1 白名单 +1；mypy 基线不变；
- 桌面编排呈现不在本体轮硬性范围——挂 G-15/T-A10 合批（§15 序 4）；本体轮以 HTTP 层端到端演示「AI 起草→validate 干跑→人工 create_definition→publish」完整链（G-03 复测动作）。

## 7. 不做清单（本 ADR 明确拒绝项）

- 不扩展节点类型闭集（Q1 裁决）；
- 不新建 ai_draft 态／新表／新列（Q2 派生——零迁移）；
- 不动 `draft-from-plan`／`compile_plan_workflow` 语义（Q3 裁决）；
- 不自动发布定义、不自动运行、不进 api_catalog；
- 不放宽 create_definition／publish 权限（can_manage／admin 维持）；
- 节点补偿动作字段维持不建（P0-4 同裁：语义需设计轮拍板，与本 ADR 正交）。

## 8. 拍板留痕与可推翻通道

蔡工交互拍板（2026-11-11，三问均按推荐项）：
1. 节点闭集是否扩展？——**不扩展，维持四值闭集**；
2. AI 起草产物落在哪个态？——**返件式草稿，零落库**；
3. 与确定性编译器的双来源关系？——**并列双来源、闸唯一**。

推翻通道：任一拍板推翻即修订本 ADR 版本号（v1→v2）并回写台账修订记录；本体轮开工前推翻零成本，开工后推翻按在途变更评估。§2 契约推荐项（≥1 human_approval）与 §3 节点数上界值属本体轮实施时钉死的参数级决定，亦留痕可推翻。
