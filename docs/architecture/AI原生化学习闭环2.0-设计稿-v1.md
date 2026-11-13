# AI 原生化学习闭环 2.0 设计稿-v1

> **性质**：设计轮产物。纯文档零代码零迁移零路由。**设计稿 ≠ 实施授权**——批准后按 §4 拆轮排期，逐轮独立 PR、独立验收。
> **缘起**：蔡工 2026-11-13 两项拍板——①「先立项写成正式架构设计稿」；②进化载体聚焦「**动态经验卡（Lessons）＋ 知识库 Skill**（零改码、经密码审批热生效/热回滚）」，并**同步覆盖代码级 Prompt 模板**。
> **取证基线**：fork/main `2054ea43`（2026-11-13 现测）。全部锚点为当轮现测行号，不承袭历史报告；施工轮开工须按锚点纪律重测（行号漂移按符号重 grep）。

---

## §0 结论速览

1. **骨架已全绿、回路五处断**：L1 摄取 / L2 可判定读数 / L3 知识接线 / V3.2 训练场（G4 评估、G5 提案、G6 回归）/ N2 归因账本 / N4 发布通道 / N6 版本注册表**全部在役**；但「真执行 → 真归因 → AI 起草 → 受控热生效 → 统计显著验证」这条主回路有 **5 个断点＋1 个潜伏断点**（§1.2，全部附现测行号）。
2. **三载体协同（本稿核心）**：进化不微调模型权重，进化的是三份**版本化、可审计、可秒级回滚的载荷**——
   - **Lessons 动态经验卡**：出厂静态底座（seeds）∪ 治理面已发布行（新表 `agent_lessons`）；
   - **Skill 知识库**：权威已在 DB（`skill_definitions`/`skill_versions` 不可变版本行＋`current_version_number` 指针），**零新治理**——只差「AI 起草草稿版」接进既有发布闸；
   - **Prompt Overlay 追加式补丁**：常量骨架仍在仓（可审计），DB 只存**追加式**治理片段，按 `purpose` 在 `execute_ai_prompt` 单一入口注入——**N6「提示词正文不入库」纪律的受控演进**（蔡工 2026-11-13 拍板；v1 仅追加、不替换）。
3. **热生效与回滚收敛单点**：全部经既有 `release_channel`（admin＋密码＋回归计划在案）；生效＝运行时直读已发布行（无缓存＝真热生效）；回滚＝既有 `rollback_release`（状态翻回＋载荷行退役，审计链不断）。
4. **验证升级**：回归对比从「写死 mock＋stub」真化为可配 `adapter/model_mode`，并接 L2 实测噪声带（`n≥3 ∧ |Δ|>带` 才判改进；带＝0.1049，仅 `rubric-v1|model:server` 轴有效）。
5. **拆轮**：L4（真执行面＋三源归因＋AI 起草）→ L5（三载体热生效＋回归真化）→ L6（真实交付反哺飞轮）。

---

## §1 现状取证（`2054ea43` 现测）

### 1.1 已在役的骨架（不重造）

| 面 | 锚点（现测） | 事实 |
|---|---|---|
| 执行面 | `simulation/adapters/mock.py:36`（MockAdapter）；`adapters/real.py:105-187`（沙箱投影→`agents_service.start_run`→产物回读） | mock＝确定性替身；real＝真 zcode 一次性行执行，`real.py:174-176` 自由文本 `structured=False` 诚实标注 |
| 评估面 | `simulation/evaluator.py:112`（`evaluate_run`，L-A＋可选 L-B）；`:324-371`（L-C 人工行，`evaluator_id="human:{id}"` `:356`） | 同 (run,层,评估器,规则版本) 幂等更新（`:136-143`）；分歧阈值与人工触发在位 |
| 归因账本 | `workbench/models.py:938`（AICallAudit，表 `ai_call_audits` `:952`）；`:980-981`（`prompt_version`＋`prompt_fingerprint`）；`ai/auditing.py:13`（purpose 必填，DB NOT NULL） | 每次 AI 调用四层归因（purpose／版本／指纹／主体） |
| 提案面 | `simulation/improvement_service.py:210-325`（`create_proposal`：train-only `:238-251`、confirmed-only `:252-267`、指纹去重 `:269-280`） | 提案状态机 draft→in_review→approved→published/rejected |
| 发布通道 | `simulation/release_channel.py:88`（发布：admin＋密码＋note＋回归计划在案 `:104-110`）；`:138`（回滚，`release_json.rollback` 累积）；`:179`（G-14 复审工单）；静态钉 `:17-19`（ImprovementProposal 引用面 ⊆ {models, improvement_service, release_channel}） | 发布是**受控记账面**：`models.py:363-364` 注释明示「正文零触碰、target_json 是文本指针」——这正是本稿要受控演进的点 |
| 回归面 | `simulation/regression_service.py:90`（建套件）；`:191`（run_regression：候选组＝基线＋`override_json.run_config` 合并 `:202-217`）；过拟合闸 `generalization_gap>0.15` `:260-266` | 五项检查（总分Δ/维度Δ/硬失败差/成本Δ/泛化差） |
| 知识面 | `agents/lessons.py:28`（SEEDS_PATH 静态文件）；`:58`（select_lessons 纯函数：能力腿＋行业过滤＋top_k/max_chars）；`:88`（`knowledge_snippets_for`）；接线 `agents/service.py:360-361`；配置 `config.py:207-209`（`agent_lessons_enabled/top_k/max_chars`） | 渲染面 `render_masked_context` 禁区词/遮蔽闸在位（零新脱敏面） |
| Skill 面 | `control/skill_center.py:4-6`（权威已在 DB：`skill_definitions`/`skill_versions`，含 `content_sha256` 与不可变版本行）；`:15-16`（按 `current_version_number` 读不可变版本行）；`:38-55`（published＋scope 可见性闸） | **Skill 已有完整版本生命周期**：草稿→发布→指针滚动；版本行不可变＝天然可回滚 |
| Prompt 面 | `ai/prompt_registry.py:36`（`PROMPT_REGISTRATIONS` 12 常量，key 即 purpose 风格如 `quality.testcase_draft`）；纪律 `:14-16`（版本-指纹双绑、不自动改内容、正文不入库） | 审计可按版本分组；改正文不升版本 ⇒ 测试红 |
| 读数面 | `docs/audit/训练场分布读数-L2底册-1.md`（`delta-noise-band-simulation-2026-11-12`：模型层纯评估噪声带 **0.1049**，锚点 n=3；规则层 0.0） | 判定规则已实证：n<3 ⇒ insufficient_data；verdict 在噪声内翻转不可作结论 |

### 1.2 六断点（全部现测，附证据）

1. **断点①执行面失真**：训练场默认跑 `mock`（测的是脚本替身而非真实 Prompt/Skill/Lessons 能力）；`real` 档单题 ≈30 分钟（宿主 zcode 四相位），134 题不可日常迭代。缺一个 **API 内轻量真模型执行面**。
2. **断点②归因面失明**：`improvement_service.py:136-143` `analyze_run` **只读 `layer=="deterministic"`**——L-B 真模型层（`layer=="model"`，实测 `MiniMax-M3.1-Flash` 已能稳定出分）与 L-C 人工终裁行（`layer=="human"`）**完全不进失败归因**；而 `real` 档产物 `structured=False`（`real.py:174-176`）时恰恰只有 L-B/L-C 看得懂。
3. **断点③蒸馏面缺失**：无 AI 起草提案端点；提案 `change_summary` 是自由文本，无结构化候选载荷；桌面端无「从失败发现创建提案」入口（`FailureAnalysis.tsx:78` 仅静态徽标；在途 PR #448 补的是**发布钮与原文视图**，未补创建/AI 起草链——边界见 §3）。
4. **断点④验证面假绿**：`regression_service.py:154-163` `_run_group` **硬编码 `"adapter_mode": "mock"`** 且 `evaluate_run` 走默认 `model_mode="stub"`（`evaluator.py:117`）——回归面板跑的是替身分数；L2 实测噪声带 0.1049 **未接入**回归判定（单点 Δ 即判 improved）。
5. **断点⑤回流面断路**：`release_proposal` 只翻状态字段（`models.py:363-364` 注释自证「正文零触碰」）；Lessons 锁死静态文件（`lessons.py:28`，改一条经验＝改代码重发镜像）；Skill 的版本生命周期在但**没有 AI 起草接线**；Prompt 常量无任何运行时治理面。
6. **断点⑥（潜伏，本轮现测新发现）**：`lessons.py:95/111/112` 用 `getattr(settings, "fde_agent_lessons_enabled"/"fde_agent_lessons_top_k"/"fde_agent_lessons_max_chars", …)` 读配置，而 `config.py:207-209` 字段名是 `agent_lessons_enabled/top_k/max_chars`——**键名不匹配 ⇒ getattr 恒走缺省（False/3/400），生产注入恒关**。既有测试（`test_lessons_wiring.py:145-157`）用假 settings 对象自带 `fde_` 前缀键，故全绿掩盖了该缺陷。L4 第一件事：现测核实并修正（修 `lessons.py` 读真实字段名，或 `config.py` 加 validation_alias——实施轮定，两向皆一行级改动）。

---

## §2 六断点 × 方案设计（推荐前置，否决留痕）

### 2.1 断点①：NEW `adapters/workbench.py`（API 内真模型执行面）

- **形态**：第三档适配器（`adapter_mode="workbench"`），`mock`/`real` 两档原样保留：
  - `probe()`＝真模型生成下一问：输入＝客户可见简报＋已披露事实＋**候选载荷（被测的 lessons/skill/overlay 注入）**，输出一问，交既有 `customer_simulator` 判定关键词披露——**直接考出「注入这条经验后问得更准」**；
  - `analyze()/design()`＝真模型按 mock 同款 JSON 契约产出结构化结果；结构化失败回落自由文本并 `structured=False`（沿用 `real.py` 诚实语义）。
- **模型通道**：复用 `DeepSeekClient` 直连腿；NEW 配置 `deepseek_simulation_workbench_model`（缺省**回落**评估槽位值）；purpose=`simulation_workbench`（审计＋J-1 白名单＋注册表 +1）；单 run ≈8 次调用（6 轮访谈＋分析＋方案）≈30–60s。
- **否决 A**：全量切 `real`——30 分钟/题 × 134 题不可日常迭代，留作里程碑验收档。
- **否决 B**：把 mock 做得更逼真——测的仍是替身，分数对能力无外推力。

### 2.2 断点②：`analyze_run` 三源化

- **L-C（最高优先）**：存在 `layer=="human"` 行 ⇒ 生成 `confidence="confirmed"` 发现（人工即真值，直接解锁提案资格）；人工 note 全文入 description 留痕。
- **L-B（第二意见）**：`layer=="model"` 且 `verdict != "unavailable"` 且总分低于阈值 ⇒ 生成 `confidence="likely"` 发现（**只进人工复核队列，不直接解锁提案**——守「不把猜测当结论」纪律）；低分判据按 `evaluation_schema.py:29` 的 D1–D7 维度聚类进 evidence_refs。
- **L-A**：既有 `FAILURE_CATEGORIES`（FA-01..10）确定性映射原样保留（`failure_analyzer.py:82-97`）。
- **否决**：L-B 直接 confirmed——L2 底册读法边界已证「模型层单点分数与 verdict 均不可作能力结论」（噪声带内 verdict 翻转实录）。

### 2.3 断点③：NEW `POST /simulation/findings/draft-ai`（返件式 AI 蒸馏）

- **输入**：finding_ids（服务端强制 train split——复用 `create_proposal:238-251` 同尺过滤）。
- **起草**：走 `execute_ai_prompt` 单一入口（purpose=`simulation_improvement_draft`，提示词常量进注册表＋J-1 白名单）；跨题聚类 v1 按 FA 码分组（同码多条 findings 合并一份候选）；产出**结构化候选载荷**三型（§2.5 三载体同构）：
  - `lesson_entry`：{capability_tags, industries?, text≤300 字, anti_pattern, actionable_rule}；
  - `skill_version_draft`：指向既有 SkillDefinition 的新版本草稿正文（走 Skill 既有发布闸）；
  - `prompt_overlay_fragment`：{purpose_key, fragment≤200 字}。
- **污染双卡**：返件前过 `redact_text_detailed`（词典故障 fail-closed 同码）＋答案侧词表闸（`contains_forbidden_keys`/`ANSWER_SIDE_KEYS` 同尺）——**蒸馏器只看失败 Trace＋丢分维度名＋脱敏评语，reference 判卷基准物理不可达**（服务端查询即不含 reference）。
- **人工闸**：AI 只返件；采纳＝人工确认后落 `create_proposal`（NEW 可选字段 `candidate_payload_json` 随提案入档）；契约失败整批零写入重试一次 409（沿 N3a/N3b 家族语义）。
- **否决**：蒸馏器读 reference（违污染单向阀）；AI 直接建提案绕人工（违不代拍板）。

### 2.4 断点④：回归真化＋噪声带闸

- `_run_group` 参数化：`adapter_mode`/`model_mode` 进 `suite.baseline_config`（缺省维持 mock/stub＝零回归），候选组另叠加提案 `candidate_payload_json` 的 **run 级沙箱注入**（只影响该组 run 的上下文装配，零全局变更；run 的模型调用审计行带实验标记便于对账）。
- **噪声带闸**：模型层 Δ 判定须 `n≥3 ∧ |Δ| > band`（严格大于；不足 ⇒ `insufficient_data`）；NEW 配置 `simulation_regression_noise_band` 缺省 0.1049，**轴绑定注记**：仅对 `rubric-v1|model:server` 轴有效，换 rubric/评估器/模型必须重测锚点带（底册读法边界④同尺）。L-A 确定性层照旧单点判定（噪声 0）。过拟合闸 0.15 不动。
- **异步化**：`model_mode=server` 或 `adapter=workbench` 的回归转后台作业（自研 Redis 队列在位；`jobs/queue.py`），UI 轮询；stub/mock 小跑保持同步（零回归）。
- **否决**：以单 run Δ 下「变好/变坏」结论（round16/第十七轮两度证伪的家族坑）。

### 2.5 断点⑤＋载体拍板落地：三载体热生效机制（本稿核心）

**统一原则**：发布动作＝既有 `release_channel` 密码闸（零新闸）；生效点＝运行时**直读**已发布行（无缓存直查 ⇒ 真热生效；`_render_context` 每 run 一次，QPS 无压力）；回滚＝既有 `rollback_release`；静态钉面同步扩三支执行器（仍锁 `{models, improvement_service, release_channel}` 单点写）。

**A. Lessons（动态经验卡）**——NEW 表 `agent_lessons`：
- 行 schema 与 seeds **同构闭集**（id/capability_tags/text/source_ref/sha256＋可选 industries）＋ `status ∈ (draft, published, retired)` ＋ `source_proposal_id`；落库时词表闸双卡（答案侧字段名＋未溯源数字拒绝，同 seeds 纪律）；
- `lessons.py` 装载改为 `seeds 底座 ∪ published 动态行`（seeds 永为出厂基线不被覆盖）；`select_lessons` 过滤逻辑零改动（top_k/max_chars 沿用 `config.py:207-209`）；断点⑥修正在此轮一并落地。
- **否决**：动态层写回 seeds 文件——`server/seeds` 在污染钉扫描面，禁入。

**B. Skill（知识库）**——**零新治理**：
- AI 起草（§2.3）落 `SkillVersion` 草稿 → 既有 skill 审阅/发布闸 → `current_version_number` 滚动＝**热生效**；回滚＝指针回指旧不可变版本行（`skill_center.py:15-16` 既有语义，天然可回滚）。回归验证走提案 `candidate_payload_json.skill_ref`（候选组 run 按 ref 装配该版本）。
- **否决**：为 Skill 另建发布通道——与 release_channel 收敛单点矛盾。

**C. Prompt Overlay（代码级模板同步覆盖）**——NEW 表 `prompt_overlays`：
- 行＝{purpose_key, fragment(≤200 字), status, content_sha256, min_prompt_version, source_proposal_id}；**只允许追加语义片段，不允许替换常量正文**——代码骨架仍在仓、注册表指纹仍逐条可验（`prompt_registry.py` 纪律对常量本体不变）；
- **注入点＝`execute_ai_prompt` 单一入口**：按 purpose 匹配已发布 overlay，**追加至 system_prompt 尾部**（`[治理补丁]` 分隔标记）；审计行记 overlay id 集合 ⇒ 归因链完整（purpose＋prompt_version＋overlay 指纹三元）；
- **★N6 纪律受控演进声明**：注册表纪律「提示词正文不入库」（`prompt_registry.py:15`）约束对象是**常量正文的存储**；overlay 是经蔡工 2026-11-13 拍板纳入的**追加式治理片段**（不改常量、可审计、可秒回滚、过回归闸），本稿将其登记为该纪律的受控例外——留痕可推翻；**替换类提示词改动仍走代码 PR**（守住「行为骨架在代码」的可审计底线）。
- **否决**：热改代码常量（不可审计不可回滚）；三个载体三套闸（治理面发散）。

---

## §3 与在途/既有面的边界（防重复施工）

| 面 | 状态 | 本稿关系 |
|---|---|---|
| PR #448（在途，桌面五断链：图片CSP/**训练场原文与提案发布**/产物采纳/派单撮合） | OPEN | 其补的是**发布钮＋原文视图**；本稿 L4 的「创建提案/AI 起草入口」、L5 的「发布钮挂三载体执行器」建立在其上，实施轮 rebase 融合，不重复 |
| PR #426/#439（已合并）：案例导入/启停原地切换（r44 已交付） | 已合并 | L4 场景选择器建立在 r44 行为之上 |
| N6 质量路由（`ai/model_routing.py`，fail-safe 默认关） | 在役 | 本轮**不接**——回归读数先攒轴组样本，接线路登记 L6 可选 |
| lessons 展示面 | 蔡工 2026-11-12 拍板「不增设」 | 不重开；动态层只进运行时注入与治理面列表 |

---

## §4 实施拆轮建议（批准后逐轮立任务书）

| 轮 | 内容（NEW/改动） | 验收判据（复测动作） |
|---|---|---|
| **L4** 真执行面＋归因真化＋AI 起草 | NEW `adapters/workbench.py`＋workbench 模型槽位；`analyze_run` 三源化；NEW `draft-ai` 返件端点（+1 路由不进 api_catalog）＋蒸馏提示词注册（注册表＋J-1 各 +1）；`ImprovementProposal.candidate_payload_json` 加列（迁移）；**断点⑥键名修正**；桌面「失败→AI 起草→采纳建案」入口＋运行台场景选择器（替换 `SimulationRunDetail.tsx:139` 的 `scenarios[0]` 硬编码） | workbench 单题端到端真模型分（audit 行 purpose/version 齐全）；L-C/L-B 发现各就位（confirmed/likely 分流钉）；AI 起草返件→人工采纳→提案带 candidate_payload；mock/real 零回归；变异三连红→还原绿 |
| **L5** 三载体热生效＋回归真化 | NEW 表 `agent_lessons`＋`prompt_overlays`（迁移×1 两表）；`release_channel` 三支执行器（lesson 上下线／skill 指针建议／overlay 发布，均零生产正文直写、skill 走既有闸）；`lessons.py` 双层装载＋断点⑥回归验证；`execute_ai_prompt` overlay 注入＋审计扩展；回归参数化＋噪声带闸＋异步作业；桌面发布/回滚钮挂真载荷（融合 #448） | 发布→**下一 run 即注入**（audit 行带 overlay/lesson 指纹）；回滚→立即消失；盲测 `within_noise`/退化拦截各有反例钉；`test_diagnostic_eval_contamination` 全绿＋NEW 静态钉（`fde_api/diagnostics/**` 禁 import 新治理模块；seeds 零动态写）；过拟合闸反例钉 |
| **L6** 真实交付反哺飞轮 | NEW 宿主侧只读脚本 `scripts/simulation/extract_case_from_project.py`（门禁 fail→pass 迁移与产物拒收事件 → 真相层 `import_card_v1` 候选卡，代号化＋T-A2 脱敏）；复用既有 L1 导入管线人工激活；L-C 原文核对视图收口（随 #448 后补） | 一次真实门禁驳回/产物拒收 → 脱敏候选卡落真相层（不入仓/不入被扫面）；四不漏：不入仓、代号化、人工激活、答案侧零回流 |

**顺序与依赖**：L4 → L5 强串行（L5 的 A/B 验证依赖 L4 的 workbench 执行面与三源 findings）；L6 独立可并行。

---

## §5 红线自证（逐条）

| 红线 | 本设计落法 |
|---|---|
| 客户真实资料不入 git/远端 | 蒸馏输入＝simulation 域合成数据＋已代号化 trace；L6 提取走 T-A2＋真相层，repo 被扫面零真实资料 |
| 评测集污染隔离 | 蒸馏只读 train findings（服务端过滤）；reference 物理不可达；返件过答案侧词表＋脱敏双卡；NEW 静态钉双向（diagnostics 禁 import 治理模块；seeds 禁动态写） |
| AI 不代拍板 | AI 只返件起草；热生效恒经 admin＋密码 `release_channel`；L-B 只 likely 进复核队列 |
| 进化可判定可归因 | audit 行 purpose＋prompt_version＋overlay/lesson 指纹三元；RegressionResult↔proposal↔run 全链可对账；噪声带轴绑定注记 |
| 不自动改提示词（N6 纪律） | 常量本体零触碰；overlay 为登记过的受控例外（仅追加、密码闸、可秒回滚、过回归闸）；替换类改动仍走代码 PR |
| 台账三同步 | 各实施轮随轮回写台账/CHANGELOG/任务书；本设计稿单文件 PR（沿 #282 剥离先例） |
| B#35 第三方材料 | 零第三方结构化表达（本稿机制描述以本仓代码为唯一事实源） |

## §6 待拍板项（剩余项；载体与覆盖范围已由蔡工 2026-11-13 拍板，不重开）

1. **Overlay join key＝purpose 且仅追加**（推荐确认——purpose 已是审计四层强制项，注入点天然单点）。
2. **workbench 模型槽位**：独立配置键缺省回落评估槽位值（推荐确认——零新增配置即可用，需换档再配）。
3. **噪声带配置位**：缺省 0.1049＋轴绑定注记「仅 rubric-v1|model:server，换轴必须重测」（推荐确认）。
4. **L-B likely 发现的复核流形态**：v1 仅在失败分析列表呈现待复核标记（不建专属审批流），复核动作＝人工确认后按 L-C 路径补终裁（推荐确认——避免与提案审批流重复建闸）。

## §7 来源对照表

- 本稿为**独立撰写**；机制描述以本仓代码为唯一事实源（§1 锚点现测于 `2054ea43`）。
- 与《交付案例学习闭环-三缺口设计稿-2026-11-11》为接续关系：该稿三缺口（L1/L2/L3）已全部实施合并；本稿处理其遗留的「回路五断点」与载体热生效，不推翻其任何拍板（污染单向阀、lessons 展示面不增设等维持）。
