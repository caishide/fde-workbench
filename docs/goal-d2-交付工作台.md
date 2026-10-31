# goal-d2 · 交付工作台升级轮次报告（2026-10-31）

> 第二轮，输入：goal-d1 报告 + PRD §4 F2/§10 P0 四指标 + 技术实施方案 S0-3~S0-6 + goal 循环提示词 v1.0。
> 本轮 Goal（S0 收尾）：**S0-3 确认流 UI 三缺陷 + S0-4 方案骨架与健康分 + S0-5 SOW 串联审计 + S0-6 行业模板种子 + P0 四指标埋点。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，fork/main 77fc03c 实测） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | S0-3a cancelled 分层 | 非 ready 态文案分层，cancelled 显式「已取消」（台账五.1） | `GuidanceReview.tsx` 非 ready 只分 failed 与否——cancelled（终态）也显示「预调研分析正在后台继续」，用户空等 | P1 | 非 ready 三分：failed→错误；cancelled→「分析已取消」；其余→后台继续 |
| 2 | S0-3b start 失败透传 | start 失败显示 `failure_message` 明细（台账五.2） | `PresurveyAnalysisAction.start()` catch 对非 ApiClientError 一律「无法开始 AI 分析，请稍后重试。」——任务内 poll 到 failed 抛的 `Error(failure_message)` 被吞 | P1 | catch 优先用 `Error.message`（runTask 原样 rethrow，AIExecutionProvider.tsx:84），仅「invalid guidance」哨兵回落通用文案 |
| 3 | S0-3c PATCH 即 setDraft | PATCH 成功即推进本地版本，confirm 失败不与库态分叉（台账七.1） | `GuidanceReview.save()` 仅在 PATCH+confirm 双成功后 `setDraft(next)`；PATCH 成功→confirm 网络失败→本地 version 陈旧→重试必 409 死循环 | P1 | PATCH 成功立即 `setDraft/baseline(next)`；confirm 成功后再推进一次。两处父组件（PresurveyAnalysisAction/ProjectGuidanceCard）initial 引用稳定至 onSaved，无回置风险 |
| 4 | S0-4 方案骨架 | 按 ProblemItem[]+行业模板生成 `ProjectSolution` 草稿（generated_by=human）（PRD F2/技术文档 S0-4） | 零存在：方案只能手工创建或 ai-organize 建议；d1 的 severity/module 标注无处消费 | P0 | `POST /projects/<id>/solutions/skeleton`：读最新 confirmed 指引（409 兜底）+ 录入卡行业匹配已发布行业模板 → 组装六段骨架；溯源入 `source_json.kind="skeleton"`（generated_by 列化留待 d3，本轮不迁移） |
| 5 | S0-4 健康分 v0 | 模板覆盖率/引用完整性/报价合法三因子评分（PRD F2 四类质量保障之规则校验） | 零存在 | P0 | `GET /projects/<id>/solutions/<sid>/health`：覆盖率 40（六段非空比例）+ 引用 30（机会≥1:15 + confirmed 指引:15）+ 报价 30（finalized:30/draft:15/无:0），issues 中文清单 |
| 6 | S0-5 SOW 串联 | 拍板→Export→合同登记链路审计事件（技术文档 S0-5「多数已存在，补状态串联」） | `project_solution_sow_exported`（solutions/service.py:424，含 solution/document 双 id）与 `project_document_version_confirmed`（version_service.py:388）、`contract_recorded`（contract_service.py:139）各自存在，但**合同行与导出物之间无任何关联事件**——四指标之「SOW 一次拍板通过率」无法归因到方案版本 | P0 | `record_contract` 创建（非更新）且项目存在「来自方案导出且已 confirmed」的 SOW 文档版本时，追加 `sow_contract_linked` 事件（sow_type/solution_id/solution_version/document_id/document_version_id） |
| 7 | P0 埋点① | 售前独立完成录入+确认（PRD §10） | `presurvey_intake_saved` 有（d1）；**`confirm_analysis` 全程无打点**——确认侧无事件，指标①不可算 | P0 | `confirm_analysis` 成功路径补 `guidance_analysis_confirmed` 事件（analysis_id/version_number/source_file_version_id） |
| 8 | P0 埋点②③④ | 方案草稿耗时/SOW 一次拍板率/资深介入时长（PRD §10） | ②`project_solution_created`→已有；③export+confirmed→已有；④`project_created`（projects/service.py:176）→`gate_decided`（gate_service.py:498）→已有 | P0 | 全部复用既有事件，本轮零新增；指标口径与事件映射写入本轮报告 §五，报表页归 d8 |
| 9 | S0-6 行业模板种子 | 首批 2–3 个行业 `TemplateResearchForm`（技术文档 S0-6） | `workbench/seed.py` 只有通用模板（GENERIC_TEMPLATE_KEY）；行业模板零种子，骨架的行业匹配无数据 | P1 | `seed_workbench` 扩展 `seed_industry_templates`：3 行业（零售连锁/餐饮连锁/制造业）× published v1 × BASE 五模块 × 各 1 张项目级调研表（2 节 × 3 字段），template_key 稳定幂等 |
| 10 | S0-6 会议模板蒸馏准备 | D10（PRD 决议表）：S1–S6 模板内容从 SOP v2.4.7 蒸馏→蔡工审定 | 未启动（内容蒸馏排 d7，本轮只做「准备」） | P2 | 蒸馏准备文档：SOP 九卡/报价卡/门禁验收表/移交四件套 → S1–S6 模板节的来源映射 + 待蔡工拍板清单 |
| 11 | [d1 登记] 录入卡 UI 入口 | 项目详情页录入卡表单（d1 报告四.2） | d1 只交付 API；desktop 对 presurvey-intake 两路由 0 引用 | P2 | `PresurveyIntakeCard` 组件挂 ProjectGuidanceCard；GET 回显 + PUT 保存 + 错误透传 |

## 二、行动说明

分支 `feat/delivery-d2-s0-closeout`（基于 fork/main `77fc03c`，含 r5–r8 与 d1 全部合并成果）。**零新表、零新迁移**——全部为服务层/路由/种子/桌面增量。动了什么：

1. **S0-3 桌面确认流三缺陷**（`guidance/GuidanceReview.tsx`、`PresurveyAnalysisAction.tsx`）：
   - 非 ready 三分：failed→错误原文；**cancelled→「分析已取消」**；其余→后台继续（台账五.1）。
   - `start()` catch 优先透传 `Error.message`（runTask 原样 rethrow，任务内 poll 抛的正是 failure_message），仅内部哨兵「invalid guidance」回落通用文案（台账五.2）。
   - `save()` PATCH 成功**立即** `setDraft/setBaseline(next)`，confirm 成功后再推进一次；两处父组件 initial 引用稳定至 onSaved，无回置风险（台账七.1）。
2. **S0-4 方案骨架 + 健康分**（`solutions/service.py` +118 行、`routes.py` +2 路由、`api_catalog.py` +2 条目）：
   - `POST /projects/<id>/solutions/skeleton`：读最新 confirmed 指引（缺失 409 `solution_skeleton_guidance_required`）+ 录入卡行业 casefold 匹配最新已发布行业模板版本 → 六段骨架（设计/交付物/验收/数据系统/排期/风险），问题条目带 `severity/module` 标注；**AI 不参与内容生成**，溯源入 `source_json.kind="skeleton"`（generated_by 列化留 d3，本轮不迁移）。
   - `GET /projects/<id>/solutions/<sid>/health`：模板覆盖率 40（六段非空）+ 引用完整性 30（机会≥1:15 + confirmed 指引:15）+ 报价合法 30（finalized/draft/missing）＝满分 120；issues 中文清单。
   - 两个路由**进 api_catalog**（`solutions.skeleton`/`solutions.health`）：骨架保存的是草稿非拍板，与已在册的 `solutions.create` 同层（报告「行为边界」单列说明）。
3. **S0-5 SOW 串联审计**（`projects/contract_service.py`）：`record_contract` 首次建档（created，非更新）且项目存在「来自方案导出且已 confirmed」的 SOW 文档版本时，追加 `sow_contract_linked` 事件（sow_type/solution_id/solution_version/document_id/document_version_id）——打通 方案→Export→文档拍板→合同登记 归因链。solutions 模型走函数内延迟导入，避免 projects↔solutions 环。
4. **P0 四指标埋点**：本轮唯一新增事件 = `confirm_analysis` 成功路径的 `guidance_analysis_confirmed`（指标①确认侧，此前全链无打点）。指标②③④全部复用既有事件（`presurvey_intake_saved`+`guidance_analysis_confirmed`｜`project_solution_created`｜`project_solution_sow_exported`+`project_document_version_confirmed`+`sow_contract_linked`｜`project_created`→`gate_decided`(G3)），口径映射见 §五。
5. **S0-6 行业模板种子**（`workbench/seed.py`）：`INDUSTRY_TEMPLATE_SEEDS` ×3（零售连锁/餐饮连锁/制造业，template_key `industry_seed_*` 稳定幂等）× published v1 × BASE 五模块 × 各 1 张项目级预调研补录表（2 节 × 3 字段，仅 short/long_text）；并入 `seed_workbench`（bootstrap 全量装载）。会议模板蒸馏准备=D10 准备稿落文档中心（05_AI方案/D10会议模板内容蒸馏准备_SOP来源映射.md）。
6. **桌面端**：`PresurveyIntakeCard` 新组件（读取回显/保存/错误透传/本地 roles 行数校验）挂 `ProjectGuidanceCard`「售前录入卡」按钮（d1 登记的 UI 缺口）；`SolutionDesign` 列表页「按预调研生成骨架」按钮；`SolutionDetailPage` 健康分徽标（加载失败静默隐藏）；`solutionErrors.ts` 补 `solution_skeleton_guidance_required` 映射；`types.ts` + `PresurveyIntakeDto` 校验。

### 既有测试的最小适配（循环纪律要求单列）

- `test_workbench_seed.py`：行业种子并入后模板总数 1→4——通用模板断言改为按 `GENERIC_TEMPLATE_KEY` 作用域查询 + 总数钉 4；drift 测试的 `.one()` 同步加键过滤。
- 11 个测试文件的「任取一个 published 模板版本」查询（`test_projects_api`/`test_users_api`/`test_gates_api`/`test_gantt_api`/`test_project_{members,tasks,modules}_api`/`test_research_{imports,subjects}_api`/`test_dispatch_p0{,_r2}`）统一钉到 `GENERIC_TEMPLATE_KEY`（消除行业种子引入后的非确定性取版）。
- `solutions/service.py::_error` 标注 `NoReturn` + `BASE_MODULES`/种子常量补 `dict[str, Any]` 注解：mypy 基线反而**消解 10 处存量误报**（289→279）。
- 桌面 `guidance-chain-scenarios.test.tsx` 两个**缺陷基线钉子**（cancelled 仍显示进行中占位 / start 吞明细）翻转为修复后行为并注明台账编号。

### 行为边界（无行为变更声明）

- 既有路由契约零改动：guidance/solutions/contracts 原路径的请求与响应形状不变；`confirm_analysis` 返回值不变（仅追加审计事件）。
- `sow_contract_linked` 只在「新建合同档 + 已 confirm 的导出 SOW」双条件齐备时出现，纯增量审计。
- 骨架路由为新建草稿（非拍板），与 `solutions.create` 同权限层（项目负责人/管理员）。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| 新增服务端用例 | ✅ `tests/test_goal_d2_s0_closeout.py` **8 例全绿**：闸 409/权限/校验 3 + 骨架组合（行业模板匹配+标注透传+审计事件）+ 通用骨架（无录入卡回退+机会关联）+ 健康分三因子全路（20→105→120）+ SOW 串联（未 confirm 不联动/confirm 后联动/更新不重复联动/无导出不联动）+ confirm 埋点 + 种子幂等完整性 |
| 变异验证 | ✅ M1–M4 全闭环（见下表） |
| 既有用例适配集 | ✅ 适配的 16 个测试文件 + 受影响域（guidance/solutions/projects/workbench/documents）定向批跑 **302 passed / 3 skipped / 0 failed**（4:36） |
| 桌面端 | ✅ typecheck（node+web）零错误；vitest **667/667**（52 files，654→667 净增 13）；electron-vite build 成功（交付版按纪律待合并后从 main 切） |
| ruff | ✅ All checks passed（F401,F841 全部改动文件） |
| mypy 基线 | ✅ no new type errors（基线 289 → 当前 279，净修 10 处存量） |
| 迁移 | N/A（零新迁移；无 schema 变更） |
| 全量服务端 | ✅ 安静窗口单跑 **1442 passed / 6 skipped / 0 failed**（EXIT=0，11:14；收集 1448，skip 6） |
| 口径 | ✅ AGENTS.md / 技术实施方案 §0 同步（路由 230 / ENTRIES 70 / 用例 1448 收集 / 表 86 不变 / head `c5d7e9f1a3b7` 不变） |

**变异台账（反假绿灯②）**：

| # | 变异 | 预期红 | 实测 |
|---|---|---|---|
| M1 | 删除 `create_solution_skeleton` 的 confirmed 指引 409 检查 | `test_skeleton_requires_confirmed_guidance_and_manager` 红 | ✅ `1 failed` → 还原回绿 |
| M2 | `solution_health` 删除 coverage 缺段扣分 | `test_solution_health_scores_coverage_reference_and_quote` 红 | ✅ `1 failed` → 还原回绿 |
| M3 | `record_contract` 删除 `sow_contract_linked` 联动块 | `test_sow_contract_link_event_follows_confirmed_export` 红 | ✅ `1 failed` → 还原回绿 |
| M4 | `confirm_analysis` 删除 `guidance_analysis_confirmed` 打点 | `test_confirm_analysis_records_metric_event` 红 | ✅ `1 failed` → 还原回绿 |

**过程事故（如实登记，已完全恢复）**：M1 变异的还原误用 `git checkout --`（该文件当时未暂存），把 service.py 整体回滚到 fork/main 基线；随即发现并按上下文逐字重建（part1 导入/常量 + part2 S0-4 全函数），重建后 8/8 全绿 + ruff/syntax 过 + 与批量回归时被测内容一致（重建段为纯追加，前缀字节相同）。变异程序从此改用备份文件恢复（`.mutbak`），不再用 git checkout。另有一笔写错目录的脚本执行（写入主工作树 service.py 尾部 206 行）——主工作树该文件当时无他人未提交改动（diff 仅含本块），已即时 `git checkout --` 还原干净并复核状态为空。教训入记忆。

## 四、下一轮建议 + 新登记差距

1. **goal-d3**（按循环队列）：S1 表簇 5 新表 + `solution_review_checkpoints` + `ProjectSolution` 增 4 列（generated_by/agent_run_id/template_id/confidence——本轮骨架已用 `source_json.kind="skeleton"` 占位，d3 迁移时回填）+ CAPABILITY +4 + sandbox 基座 + V2 四断言。
2. **[P2·桌面] 健康分仅在详情只读态展示**：编辑态（SolutionEditor）未挂健康分；若试点反馈「编辑时看不到扣分项」，d3 顺手把 issues 清单带进编辑页头部。
3. **[P2·产品] 骨架的行业匹配是 casefold 精确匹配**：录入卡行业自由文本与种子行业名不一致时静默回退通用骨架（`industry_template_version_id=null` 可辨）。试点期若命中率低，升级为别名表或模糊匹配——**需产品拍板**，本轮不做。
4. **[留注] `sow_contract_linked` 以「首个 confirmed 导出版本」为联动对象**：一项目多方案多轮导出时只链最近一次 confirm——四指标③够用；若未来要按合同逐笔归因，需给 Contract 增 document_version_id 列（届时立项）。
5. **[运营交接] `seed_workbench` 装载行业种子**：存量环境升级后需手动跑 `flask --app fde_api.wsgi:app seed-workbench`（幂等）或等 bootstrap；README 部署节已在 PR 中补一行。

## 五、P0 四指标 → 事件口径映射（PRD §10）

| 指标 | 分子/分母口径 | 事件对（OperationEvent） |
|---|---|---|
| ① 售前独立完成录入+确认率 | 项目内「确认完成」数 / 「录入启动」数 | `presurvey_intake_saved`（d1）→ `guidance_analysis_confirmed`（本轮新增） |
| ② 方案草稿生成耗时（人）↓50% | `project_solution_created`(changes.source=skeleton) − 同项目最新 `guidance_analysis_confirmed` 的时间差中位数 | 既有 + 本轮 source 标注 |
| ③ SOW 一次拍板通过率 ≥70% | confirmed 的导出版本数 / 导出总次数；联动数以 `sow_contract_linked` 复核 | `project_solution_sow_exported` + `project_document_version_confirmed` + `sow_contract_linked`（本轮） |
| ④ 资深工程师售前介入时长 ↓60% | `gate_decided`(target=G3) − `project_created` 时间差（按 actor 角色切分） | 既有事件，零新增 |

报表页与阈值计算属 d8（PRD §10 P0/P1 指标报表页）；本轮交付的是「事件全链可算」。

