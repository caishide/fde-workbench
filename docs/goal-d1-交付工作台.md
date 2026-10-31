# goal-d1 · 交付工作台升级轮次报告（2026-10-31）

> 第一轮，输入：《交付工作台升级 PRD v1.0 定稿》§4 F1 + 《技术实施方案-智能体交付工作台》§3 goal-d1 施工单 + goal 循环提示词 v1.0。
> 本轮 Goal（S0 服务端地基）：**S0-1 售前轻量录入卡 + S0-1b G3 前置闸 + S0-2 ProblemItem 契约增强全部落可判定用例。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | S0-1 录入卡 | 售前轻量卡（行业/规模/地域/访谈方式/对象角色/诉求/阶段目标），S1–S2 可填（PRD F1/D16） | 零存在；售前结构化输入只能等 DOCX | P0 | `presurvey_intakes` 表 + GET/PUT 路由 + 服务层校验 + `presurvey_intake_saved` 审计事件 |
| 2 | S0-1b S3 前置闸 | DOCX 上传与 AI 分析仅限 S3 之后（D16：SOW-A+到账+授权书=系统闸） | `set_presurvey_source`/`create_analysis` 无任何阶段闸 | P0 | 两入口查 `Gate(gate_key="G3")`，status ≠ passed → 409 `presurvey_s3_gate_open`（**行为变更**，见二.2） |
| 3 | S0-2 契约增强 | 问题清单条目可附 severity/module（架构方案 §3.2 ProblemItem） | `GuidanceItem` 四键精确匹配，11 个 list 字段一刀切 | P0 | 仅 `key_business_problems` 放开可选键（其余 10 字段维持精确键集防漂移）；AI 提示词同步；桌面编辑透传两键 |

## 二、行动说明

分支 `feat/delivery-d1-presurvey-intake`（1 迁移 + 9 文件 + 2 新测试文件）。动了什么：

1. `guidance/models.py`：`PresurveyIntake`（PK=project_id，RESTRICT 双 FK；interview_mode Check ∈ onsite/remote/hybrid）；`INTERVIEW_MODES` 常量。
2. `guidance/service.py`：`get/save_presurvey_intake`（upsert、未知字段 400 `unknown_field`、三串 ≤80/三 Text ≤2000/roles ≤20×≤80、`record_event("presurvey_intake_saved")`）+ `_require_s3_gate`（读 `workbench.models.Gate`，不 import gate_service 避免环；Gate 行缺失=未初始化=不放行）。
3. `guidance/routes.py`：`GET/PUT /api/v1/projects/<id>/presurvey-intake`；**不进 api_catalog**（人工写路径，沿门禁三路由先例）。
4. `guidance/ai_schema.py`：`PROBLEM_FIELD`/`SEVERITIES`/`ITEM_OPTIONAL_KEYS`；条目校验改「base 键必含 + 可选键仅 problem 字段放行」，`invalid_severity`/`invalid_module` 新失败码；`GuidanceItem` TypedDict 用 `NotRequired`。
5. `guidance/ai_prompt.py`：两个 builder 的 key_business_problems 段补两键说明（判断不了就省略，不要编造）。
6. 迁移 `a7f3c1e9d5b2`（down_revision `f4b8c2d6e3a1`，pure CREATE TABLE，down 可逆）；`test_migrations.py` HEAD 常量同步；`conftest.py` 清理序 PresurveyIntake 先于 projects/users。
7. 桌面端：`types.ts` GuidanceItemDto + 可选 severity/module；`GuidanceReview.changeItems` 重建条目透传两键（防 PATCH 丢 AI 标注）。

**行为变更单列（二.2）**：G3 闸是既有链路的新前置——存量项目若 G3 未在工作台拍板为 passed，上传预调研源/发起分析会被 409 拦住。**这不是代码缺陷，是 D16 决议的落地**；运营口径=在门禁页补齐 G3 证据（SOW-A/付款凭证/授权书指针+sha256）并拍板。本地测试证明闸序正确：过闸后落到既有 `presurvey_source_required` 400。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| 新增用例 | ✅ `tests/test_presurvey_intake.py` 17 例（闸 4：无 G3 双入口 409 / 过闸放行到既有 400 / evidence 态不放行；卡 13：默认卡/往返/upsert 保留/权限三层/认证/未知字段/枚举/超长/roles/空载荷/审计事件）+ `test_guidance_ai_schema.py` +6 例（接受/省略/非法 severity/超长 module/未知键/其他字段拒新键）= **23 例全绿** |
| 迁移可逆 | ✅ conftest 每会话 downgrade base → upgrade head 全链；单跑日志见 `Running downgrade a7f3c1e9d5b2 -> f4b8c2d6e3a1` |
| 变异验证 | ✅ 临时删除 `create_analysis` 的闸调用 → `test_create_analysis_blocked_without_g3` 红（1 failed）→ 还原 → 回绿（反假绿灯第 2 条） |
| 桌面端 | ✅ typecheck 零错误；vitest **654/654**（50 files） |
| ruff | ✅ All checks passed（F401,F841） |
| 全量服务端 | ⚠️ 见下「并发污染仲裁」——**PR CI 为最终干净仲裁** |
| 口径 | ✅ AGENTS.md（84 表/13 revision/head `a7f3c1e9d5b2`/路由 220/ENTRIES 60 不变）+ 技术实施方案 §0 基线行 |

**并发污染仲裁（C-9a，如实）**：全量首跑 `9 failed + 11 errors`（tail 管道吞退出码，已识别为假绿灯手法）。单跑复现：`test_users_api.py` **41 passed**、`test_worker.py` **5 passed** —— 单跑全绿坐实并发污染，不计回归。根因：**并行会话正在同一工作区施工派单 goal-r4**（未提交改动：`api_catalog.py`/`dispatch/routes.py`/`dispatch/packages.py`/`offer_service.py`/`seeds/dispatch_cities.json` 等，混入全量运行）。本轮提交严格只暂存本轮文件；push 后远端 CI（4 job）在干净树运行，为最终判定。

**反假绿灯四条自检**：① 声明=断言 ✅（服务层 docstring 的 D16 口径有对应闸用例）；② 变异 ✅（红色证据：`1 failed` → 还原 `1 passed`）；③ 真执行 ✅（23 例断言均命中 DB/API/契约实体；迁移 downgrade 日志实证）；④ 数字实测 ✅（上表全部本包实测，未抄提示词基线）。

## 四、下一轮建议 + 新登记

1. **goal-d2**：S0-3 确认流 UI（cancelled 文案分层 + start 失败透传 + PATCH 即 setDraft）+ S0-4 模板式方案骨架 + S0-5 SOW→合同串联 + S0-6 行业模板种子 + P0 四指标埋点。
2. **[P2·桌面] 录入卡 UI 入口**：本轮只交付 API；项目详情页加录入卡表单随 d2 桌面轮一起。
3. **[P2·存量运营]**：somwyn 等存量项目上线前需补 G3 拍板（运营动作，非代码）——已写入 AGENTS.md 口径行。
4. **[留注①] G3 闸读 Gate 不触发懒初始化**：从未访问过门禁页的项目 Gate 行缺失 → 409（文案指引先走门禁页）；懒初始化属门禁域副作用，guidance 不代做。若试点期反馈「闸太隐蔽」，可在 d2 评估 409 文案带直达链接。
5. **[留注②] severity/module 的 rank 排序**未随本轮（架构方案 §3.2 的 rank 步骤属 S0-4 方案骨架编排，随 d2）。
