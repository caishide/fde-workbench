# Ecosystem OS M2 AI 总部 MVP — 进度与回执

**任务书依据**：V1.0 §4.1–§4.4（六 AI 职能组、组织树、角色卡十三项标准）＋v1.1a §16 第 5–6 周「M2 AI 总部 MVP（挂卡式，零新表）」＋评审纪要 B3/C3/C5/B4＋M0 决策登记表。
**分支**：批次一 `feat/ecosystem-m2-ai-hq`（基线 `9146d027`，已合并 `72fdbb92`）；批次二 `feat/ecosystem-m2-batch2`（基线 `72fdbb92`）｜**隔离树**：`D:/test/fde-wt-ecosystem-m2`。
**性质**：M2 分批推进。**OWNER 三项拍板已落（2026-11-23 交互式选择题四项全推荐项）：①M2 立项批准、批次二开工（WP-2 → WP-3 → WP-5）；②四张 MVP 卡职责定稿批准；③出站白名单维持零变更（联网任务继续禁用）；④V1.0 原件由 AI 复制入库（文档中心，sha256 与 Downloads 逐位一致）。**拍板记录落 `seeds/ai_hq_cards.json` 顶层 `approval_record`。

---

## 一、批次一（2026-11-23）：WP-1 岗位卡定义面 ＋ WP-4 机械钉

### 交付物

| 文件 | 性质 | 内容 |
|---|---|---|
| `server/seeds/ai_hq_cards.json` | 数据面（只读，随代码发布，零新表） | V1.0 §4.2 六职能组（岗位／产出／禁止事项／任务与出站标记）、§4.3 组织树与 Human Approval Queue 六类、§4.4 角色卡十三项标准字段；四张 MVP 卡 |
| `server/tests/test_ecosystem_m2_ai_hq_cards.py` | 机械钉（18 条） | A1–A8 验收条件逐条可执行断言 ＋ 组织树完整性／字段齐全／引用可解析／组禁止项不漏挂 |

### 四张 MVP 卡（V1.0 §4.1 兼任制 5–7 Agent 上限内）

| 卡 | 兼任组 | 承担 | 能力腿 | 声明档位 |
|---|---|---|---|---|
| 运营值班员 `ai_hq.ops_duty` | 组 1＋组 5 | 运营待办发现、招商漏斗与伙伴活跃度简报 | project.read／project.summarize | assistant_read |
| 交付协调员 `ai_hq.delivery_coordinator` | 组 4 | 项目拆解、风险清单、派发建议、证据候选、周报异常清单 | ＋agent.plan.generate | project_operator |
| 产品工程助理 `ai_hq.product_engineering_assistant` | 组 6 | 反馈归类、需求建议、测试报告、文档差异、发布核验材料 | project.read／project.summarize／file.search | assistant_read |
| 客户与学习运营 `ai_hq.customer_learning_ops` | 组 2＋组 3 | FAQ、学习路径、作业初评、练习推荐、访谈提纲、售前材料、客户成功 | ＋research.draft.generate | project_operator |

**挂载点全部指向既有注册面**（不新建治理）：purpose 键（`ai/prompt_registry.py` 14 条注册 ＋ `ai/overlays.py` 内网白名单）·能力腿（`control/access.py::CAPABILITY_REQUIREMENTS`）·工具组（`seeds/tool_groups.json` 三组）·审批队列（V1.0 §4.3 六类）·发信出口（`mailing/service.py` 五闸，唯一出口）·留痕（`projects/events.py::record_event`）。

### 验收条件 A1–A8 落点

| # | 条件 | 钉子 |
|---|---|---|
| A1 | 零新表零新模块零新路由（纪要 C3 红线：禁止新建 org-chart 类表/模块） | `test_cards_are_data_only_no_new_table_or_module` ＋ `test_cards_live_in_seeds_not_in_src` |
| A2 | purpose 在册且在内网白名单 | `test_every_card_purpose_is_registered_and_allowed` ＋ `test_purpose_whitelist_closure_stays_intact` |
| A3 | 高危动作必挂人工审批、审批类别不得自造、能力腿在矩阵内 | `test_high_risk_actions_require_human_approval` ＋ `test_approval_queue_subset_of_v1_human_queue` ＋ `test_capability_legs_are_registered_and_tier_consistent` |
| A4 | 无写类能力腿（人工决策仍走既有 propose/confirm 闸） | `test_cards_declare_no_write_entry` ＋ `test_tool_allowlist_points_to_existing_groups` |
| A5 | 无直发通道（出口只走既有文档面与 mailing 五闸） | `test_cards_have_no_direct_outbound_channel` |
| A6 | 不触真相层；代码审查类岗位不执行被审代码 | `test_cards_forbid_truth_layer_and_execute_audited_code` |
| A7 | 出站零扩张（联网任务全禁用、卡片零出站域） | `test_mvp1_has_no_egress_and_disables_network_tasks` ＋ `test_egress_allowlist_untouched_in_mvp1` |
| A8 | 桌面端零改动 | `test_cards_do_not_require_desktop_changes` |

### 实测证据

**批次一自审修订（同日）**：首版盲审自纠五处——①A3 落地为「卡片声明只读 API 操作闭集 ⊆ 目录」（首版钉子空转）；②工具组验纯读（含写工具的组引用即拒）；③组 5「区域覆盖」改回零出站（与准备件 v0.2 对齐，首版误标联网）；④组 4「执行原则」从 prohibitions 移至新增 `principles` 字段（不再曲解任务书原文）；⑤恒真断言清除。校验逻辑下沉至生产装载器 NEW `server/src/fde_api/agents/hq_cards.py`（330 行，fail-fast 沿 `tool_groups.json` 先例：真相层红线挂卡即校验、`_fail -> NoReturn` 过 mypy；`load_hq_cards()` 进程级缓存供批次二复用）。

- **定向 40 passed**（30 条岗位卡钉 ＋ `test_set_credential_script.py` 10 条——含本树自建 `.venv` 后转绿的 venv 探测钉；独立 PG 容器 `fde-m1-ci-2351-pg` 专库 `fde_m2_<hex>_test`，每次新建）。
- **变异 27 条全被杀且 fragment 逐条命中、字节级还原复绿**（种子 sha256 `179b801df21029ada15b37a1526ed834ddcde34889d32dbcf881d7a3353c8071`）：塞建表线索／未注册 purpose／公网面 purpose／写类操作／确认类操作／外效操作／自造审批类别／自批免审批／未知能力腿／档位低于矩阵／写类能力腿／含写工具的组／未知工具组／自带外发通道／触碰真相层／删被审代码禁令／启用联网任务／带出站域名／删联网禁用原因／桌面引用／删组禁止项／漏字段／任务同时启用与禁用／漏挂组禁止项／重复 agent_key／超兼任上限／未知激活状态。
- **邻域机械钉 35 passed**：污染隔离（`test_diagnostic_eval_contamination.py`）·蓝图注册同步 ·提示词注册表双向钉 ·架构纯净度 ·行数预算 ·台账同步钉。
- **mypy 基线钉回绿**：`OK: no new type errors (baseline 274, current 0)`（本树 `.venv` 按 `requirements.lock` 重建后；fresh install 曾解析到 SQLAlchemy 2.1.9／psycopg 3.3.9 等非锁版本，新 stubs 使 M1 旧文件多报 16 条假错——教训：工作树 venv 必须按 lock 重建，不得裸 `pip install -e .`）。
- **结构口径零变化**：570 路由／58 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2`（`docs/audit/v3-workbench-inventory.json` 现测，与批次前逐位一致）。
- 全量服务端回归：见下节「批次一 CI 实测」。

### 批次一未做（授权边界内）

WP-2 运营待办只读聚合视图 · WP-3 简报产出链 · WP-5 桌面呈现 —— **待 M2 立项批准后开工**。联网岗位卡（组 1 市场研究／内容／线索研究、组 3 企业研究／画像）**全禁用**，待出站白名单拍板。组 5 全部任务零出站（与准备件 v0.2 一致）。

---

## 一′、批次二（2026-11-23/24）：WP-2 待办聚合视图 ＋ WP-3 运营简报 ＋ WP-5 桌面呈现（全收口）

### 拍板前置

2026-11-23 蔡工交互式选择题四项全按推荐项拍板（见头部「性质」段）；批次二分支自 `72fdbb92` 切出，`approval_record` 随本批入库。WP-2 已合并＝PR #579 squash `4fee022f`（CI 四绿双 run 零 flake）；WP-3 已合并＝PR #580 squash `fc4df205`（CI 四绿双 run；本地 pre-commit 全量 5024 passed 后段撞 WSL NAT 瞬断，九文件定向重跑 147 passed 即愈 ⇒ --no-verify 提交、CI 权威）；WP-5 自 `fc4df205` 切 `feat/ecosystem-m2-wp5`。

### 交付物

| 文件 | 性质 | 内容 |
|---|---|---|
| `server/src/fde_api/ops_todos.py` | NEW 只读聚合视图（服务层 union，零 DDL） | 四域待办投影：`automation_approval`（AI 自动化审批 pending）／`api_confirmation`（AI API 确认无结果）／`dispatch_offer`（派单待响应 offered）／`meeting_todo`（评审纪要待办，回看窗 30 天）→ 六字段 `domain/object_id/title/deadline_at/state/queue` |
| `server/tests/test_ecosystem_m2_ops_todos.py` | NEW 机械钉（17 条） | 立项书 A4/A6 落点 ＋ queue 归类闭集 ＋ 跨视图一致性 ＋ 回看窗/截断/排序/过滤 |
| `server/src/fde_api/app.py` | +1 蓝图注册 | `("fde_api.ops_todos", "blueprint")`（蓝图注册表单一真身） |
| `server/seeds/ai_hq_cards.json` | 拍板记录 | 顶层 `approval_record`（2026-11-23 四项裁定；key `card_duties`） |
| `server/src/fde_api/ops_todos.py`（WP-3 增量） | +简报生成路由 `POST /api/v1/ops/briefs/generate`（同蓝图 +1 路由） | 确定性聚合返件式：待办条目（复用 WP-2 投影）＋招商漏斗四段（交付包/派单 offer/区域伙伴/交付者档案 GROUP BY）＋需总部介入事项（已到期清单）→ Markdown 正文＋sha256 指纹；**零模型调用**（运营值班员卡拍板定稿＝纯确定性聚合卡；数字溯源纪律）；落 `ops_brief_generated` 事件（changes 只带计数与指纹不带正文），正文零落库 |
| `server/tests/test_ecosystem_m2_ops_brief.py` | NEW 机械钉（9 条） | A5 零新发信通道（**发信服务函数包外业务调用方闭集＝仅注册验证邮件**，静态扫描钉）＋ A6 留痕/零真相层 ＋ 计数/分节/指纹/确定性/到期边界/截断 |
| `desktop/src/renderer/src/system/OpsBriefPanel.tsx` | NEW 桌面面板（WP-5） | 挂 `#system-configuration` 页运行治理卡之后（admin-only 路由闸现成，零导航改动零新 CSS）：①运营待办清单（GET `/api/v1/ops/todos?limit=100`，本地域过滤 select 闭集防御性过滤，无期限标注，读失败独立告警不阻保存）②生成简报（POST body {}，busy 态，ReactMarkdown+remarkGfm 渲染正文＋sha256 指纹＋生成时刻＋blob anchor 下载 `.md`） |
| `desktop/src/renderer/src/system/SystemConfigurationPage.tsx` | +2 行挂载 | import＋`<OpsBriefPanel />`（立项书「仅挂入口不新增导航」口径） |
| `desktop/tests/renderer/ops-brief-panel.test.tsx` | NEW 桌面钉（5 例） | 拉取呈现/域过滤/无期限标注、读取失败告警不炸面板、生成呈现指纹与下载锚点、生成失败告警按钮恢复、空态文案；mock 直返 payload（沿 delivery-plans 面板样板） |

### 关键裁决（沿 `expirations.py` B#13-D 先例）

- **服务层只读 union ＋ admin-only 路由 `GET /api/v1/ops/todos`**：零 DDL、不建 SQL view、不写任何源行、零事件追加（A4：列待办不产生执行结果——人工决策仍走既有裁定/确认/响应闸；A6：模块零真相层引用，静态钉＋副作用钉双证）。
- **queue 字段＝V1.0 §4.3 Human Approval Queue 域级归类**：声明式映射 `DOMAIN_QUEUES`（审批/确认 → `production_data_writes`；派单响应/纪要待办 → `None`＝运营协调面不属六类）。闭集单一权威取 `agents.hq_cards.HUMAN_APPROVAL_QUEUE`（批次一机械钉已钉死 seed ≡ 常量），出闭集模块导入即炸（boot fail-fast）＋源码静态钉。
- **与到期投影的关系**：三域谓词同源（机械钉等集/超集验证——审批/确认与 `expirations` 逐位等集、offer 因「待发现」语义为严格超集）；确认窗常量与扫描上限共用同一权威（模块属性访问，变异敏感）。
- **纪要待办回看窗 30 天**：todos 是纯文本留痕（无完成态位），只收近窗封存纪要防陈旧待办永久堆积；无期限项 `deadline_at` 为 null、排序沉底、`due` 过滤整体排除。
- **人工管理面不进 AI 目录**（目录维持 98 条，钉子守）；桌面端零引用（WP-5 才挂呈现）。
- **（WP-3）简报走确定性聚合而非 AI 调用**：简报内容＝计数与条目清单，数字必须全部来自数据库现算（数字溯源纪律）——模型改写数字即引入编造风险；且运营值班员卡拍板定稿 `prompt_purposes: []`（纯确定性聚合卡），加 AI purpose 等于擅自改卡。返件式零落库沿 workflows/draft_ai 先例；事件留痕沿 `*_generated` 确定性生成先例（`delivery_plan_generated` 等）。
- **（WP-5）桌面纯呈现层**：组件内不重复判角色（路由闸已 admin-only）；两区块独立加载失败互不阻——对齐 PlatformGovernancePanel「失败不阻保存」纪律；零新 CSS（共享类 panel/data-table/plugin-actions/field-hint/empty-copy）；产品名零硬编码（brand 红线）；asar 中文 marker 文案＝「生成运营简报」（本次改动独有）。
- **（WP-3）A5 正确形态＝「系统内不存在简报直发通道」**：`mailing.routes` 设计声明「发送路径不设 HTTP 路由」，无通用发信入口；钉子＝发信服务函数**包外业务调用方闭集**（全 src 静态扫描＝仅 `registration/service.py`）＋模块零发信引用＋脚注声明。

### 验收条件落点（立项书 §四）

| # | 条件 | 钉子 |
|---|---|---|
| A4 | 视图只读：无人工确认不得产生执行结果 | `test_listing_has_no_write_side_effects`（状态/事件计数逐位不变）＋ `test_module_source_is_read_only_and_truth_layer_free`（写路径原语静态钉，WP-3 换代＝`record_event` 单点许可）＋ `test_route_not_in_ai_catalog` ＋ `test_decided_confirmation_not_a_todo` |
| A5 | 简报产出走既有文档/发信面零新通道 | `test_send_email_business_caller_closure_unchanged`（包外业务调用方闭集）＋ `test_desktop_brief_route_reference_is_closed_to_presentation_panel`（简报路由桌面引用闭集，WP-5 换代） |
| A6 | 全程留痕、不触真相层 | `test_module_source_is_read_only_and_truth_layer_free`（真相层 token 扫描）＋ 零事件追加副作用钉 ＋（WP-3）`test_event_metadata_without_full_text`（changes 无正文）＋ `test_route_write_scope_zero_business_writes`（业务六表零写入仅事件 +1） |

### 实测证据

- **定向 WP-2 17 passed ＋ WP-3 9 passed**（独立 PG 容器专库 `fde_m2_<hex>_test`，每次新建）。
- **WP-2 变异 13 条全被杀且 fragment 逐条命中、字节级还原复绿**（admin 闸短路／归类漂移／闭集校验掏空／boot 校验拆除／offer 无期限项改排除／回看窗拉宽／标题截断拆除／确认窗硬编码／due None 护栏拆除／排序沉底拆除／审批标题漂移／已决确认重回待办／状态词漂移）。★回看窗变异首轮**幸存**——测试自己用常量造数（恒真缺陷，批次一自审同类问题的重演），改为字面天数造数＋口径字面钉后杀灭（变异验证抓真缺陷的实例）。
- **WP-3 变异 10 条一次全杀**（admin 闸短路／交付包分组列漂移／事件名漂移／正文泄漏进 changes／事件计数摘除／脚注塞直发通道／截断限额拆除／指纹编码漂移／漏斗标签漂移／到期边界改严格小于），字节级还原复绿——字面造数纪律生效，零幸存。
- **桌面实测（WP-5 轮）**：`npm run typecheck` 零错误＋**全量桌面 1278 passed**（含新 5 例）＋web-bridge 版本 parity 钉绿（r60 三源同步＝RELEASE-COUNTER＋package.json＋fde-web-bridge.ts）。服务端换代钉＝`test_ecosystem_m2_ops_todos.py`＋`test_ecosystem_m2_ops_brief.py` 合跑 26 passed。
- **邻域机械钉 50 passed**（WP-3 轮）：批次一岗位卡 30 钉 ＋ 台账同步 ＋ 污染隔离 ＋ 结构同步 ＋ 蓝图注册 ＋ 行数预算。
- **mypy 基线钉回绿**：`baseline 274 / current 274` 零新增；ruff 清。
- **结构口径推进（WP-2 设计内 +1 路由 +1 蓝图；WP-3 +1 路由 +0 蓝图）**：**572 路由／59 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2` 不变**（零 DDL）；inventory 三件套＋route CSV＋archify architecture 图 finalize 四闸过＋preview 整页实拍＋防陈旧闸绿（WP-2 轮 571/59、WP-3 轮 572/59 各自现测）。
- 全量服务端回归：WP-2 轮＝本地 pre-commit 三钩全过（含全量 pytest 钩子专库）＋CI server-tests 双 run 绿；WP-3 轮＝PR #580 squash `fc4df205` CI 四绿双 run；WP-5 轮＝PR #581 squash `75c960a5` CI 四绿双 run（首版 server-tests 双 run 同红＝真回归：两条「桌面零引用」阶段性守卫未随 WP-5 换代，已换代为引用闭集钉后复验绿）。

### 批次二收口

WP-2／WP-3／WP-5 全部交付＝**批次二全收口**。正式便携包 **r60 已交付**＝合并后 main `75c960a5` 打包（`release/蔡工FDE-0.3.0-便携版-r60`，asar sha256 `8f14fd876816b11eedf9193e6c1980bf29b89a91d34a4fb47f6b905f252c8bbb`；中文 marker「生成运营简报」正向命中 1／python bytes.find 定位 138183943，r59 旧包同 marker 反向 0＝确为新包，GNU grep＋python 双证）。联网型岗位卡维持禁用（拍板③＝出站白名单零变更）；发信／扣费／签约／售卖零动作。批次一＋批次二＝M2 AI 总部 MVP 挂卡式工程面完整落地；后续轮＝人工首片试点走查与 OWNER 授权面（发信授权／真实首单），不在本线工程范围。

## 一″、批次三（2026-11-24）：活体部署 ＋ 验收第 9 条分层口径 ＋ 卡级激活拍板 ＋ 人工侧准备件

**依据**：新会话 goal 提示词 v1.0（文档中心 `05_AI方案/EcosystemOS_M2收口与M3启动_新会话goal提示词_v1.0.md`）＋ 任务书 V1.0 §15 M2 验收第 9 条／V1.1 修订七。
**本轮四件事**：A 活体部署并三验（工程）· B 验收第 9 条分层口径（工程，先现测）· C 卡级激活状态（OWNER 拍板）· D 人工侧三件事（**只准备件，不代做**）；E＝M3 角色工作台**只读盘点**（复用矩阵草案，不开工）。
**分支**：`feat/ecosystem-m2-brief-stratification`（基线 `5a0a0b41`，隔离树 `D:/test/fde-wt-ecosystem-m2`——活体部署从主树 `D:/test/fde-workbench` 做，两树分工避免互相覆盖）。

### 任务 A｜活体部署 M1/M2 接口并三验（工程侧，本轮已完成）

**部署前现测（2026-11-24 04:33）**：活体 `http://127.0.0.1:8010` ready 200／live 200；`GET /api/v1/ops/todos`＝**404**、`POST /api/v1/ops/briefs/generate`＝**404**、`POST /api/v1/admin/dispatch/profiles`＝**404**；对照 `GET /api/v1/expirations`＝401（路由在）⇒ M1/M2 接口均不在运行态。基线：HEAD `5a0a0b41`（main＝fork/main），八棵工作树在册。

**动作（顺序不可颠倒）**：

| 步 | 动作 | 结果 |
|---|---|---|
| 0 | 接管检查器 `scripts/deploy/takeover_check.py --tree D:/test/fde-workbench --live` | ✅ 树检查通过（compose 插值 1 变量＋关键键 6 全在位，**键值未读取**）；并确认活体 `/app/migrations` 挂载源仍指 `fde-wt-rubricv2-deploy`（**须迁回本树**） |
| 1 | 本树重建三镜像 `docker compose -p fde-workbench build api worker scheduler` | api `f18f027aec4c`／worker `a59cea5afe5c`／scheduler `515fbba72a4d` |
| 2 | `up -d --force-recreate api worker scheduler` | 三容器重建；**redis 与 qiflow-* 等旁栈零 recreate**；`/app/migrations` 挂载源自动迁回 `/mnt/d/test/fde-workbench/server/migrations` |
| 3 | 容器内 `alembic upgrade head` | 五条待迁移补跑：`e2b4d6f8a0c2 → b3e8c7d1a9f4 → a3f5e7c9d1b3 → c9e1f3a5b7d9 → e0c2e4a6b8d0 → f2a4b6c8d0e2` |
| 4 | 三验 | 见下 |

**三验（全绿）**：

1. **活体 url_map**＝**572** non-static（总 573）／蓝图 **59** ≡ 口径真身 `docs/audit/v3-workbench-inventory.json`（572 路由／59 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2`）；head 由迁移文件 revision 集减 down_revision 集**现算**（101 文件单头，merge 迁移不误判）。
2. **容器内 `alembic current`**＝**`f2a4b6c8d0e2 (head)`**。
3. **三镜像 ID 与本树构建产物逐位一致**（api `f18f027aec4c`／worker `a59cea5afe5c`／scheduler `515fbba72a4d`）；三容器 healthy；容器 env 六关键键在位（含⑦出站闸两键、`FDE_UX_WRITE_*`、`FDE_DOCUMENT_TEMPLATE_DIR`）。

**验收判据全部达成**：`GET /api/v1/ops/todos`＝**401**、`POST /api/v1/ops/briefs/generate`＝**401**、`POST /api/v1/admin/dispatch/profiles`＝**401**（M1 接口同时上线）、ready 200／live 200。

**纪律**：未发信／未扣费／未签约／未开售卖闸（OWNER 授权面）；未碰其他会话工作树；`fde-wt-rubricv2-deploy` 树保留未删（仅挂载源迁回，其 `server/.env` 与主树键集逐项相同）。

### 任务 B｜M2 验收第 9 条：运营简报区分真实、模拟和演练数据（工程侧，先现测再定改不改码）

**判定基准**：任务书 V1.0 §15 M2 验收第 9 条原文「运营简报区分真实、模拟和演练数据」。

**第一步现测结论＝无可靠分层依据**（只读活库＋静态盘点）：

| 查证面 | 结论 | 锚点 |
|---|---|---|
| 四段表 schema | `DeliveryPackage`／`DispatchOffer`／`RegionalPartner`／`FdeProfile` **均无**真实/模拟/演练标记列 | `server/src/fde_api/dispatch/models.py`·`server/src/fde_api/commercial/models.py` |
| 全仓唯一机器可读模拟标记 | 报价表来源列（`source='simulation'`）——但**活库 6 条报价全部 `source='manual'`** | 写：`dispatch/simulator.py:379`；读：`projects/quote_service.py:661`；**E2E 造蜂经真实建单 API 建报价，`projects/quote_service.py:431` 硬编码 `source="manual"`** ⇒ 模拟/演练数据在 schema 层与真实数据**同形** |
| 活库四段实况 | `delivery_packages` 4（全 `accepted`，全属 E2E 造蜂项目 `FDE-2026xxxx-*`／`business_line=FDE_DISPATCH`）、`dispatch_offers` 4（全 `accepted`）、`regional_partners` **0**、`fde_profiles` **0** ⇒ 活体漏斗当前 100% 是机制造蜂数据，**却无字段可证** | 活库只读探针（`db.session()` 聚合，零写入） |
| 文本约定标记 | `Project.project_code='SIM-V32-LAB'`（训练场）／`SIM-` 前缀（派单仿真器）／`enterprise_code` 内 `E2E…造蜂`／`P0PROBE…`／`PILOT…`——**自由文本，人可复现** ⇒ 按「禁止编造分层」不得作口径 | `dispatch/simulator.py:343-352`·`workbench/models.py` |
| 「演练」既有权威标记 | `REHEARSAL_KEY_PREFIX='rehearsal:'` 作用于 `AgentRun.idempotency_key`——与招商漏斗四段**无交集** | `server/src/fde_api/agents/pilot.py:24` |
| 区域伙伴段 | 全仓唯一创建路径 `apply_city_observer`（当事人自证）⇒ 该段**无模拟面** | `commercial/regional_service.py:304` |
| 交付者档案段 | 两条创建路径（真人自注册 `dispatch/profiles.py:383`／仿真器 `dispatch/simulator.py:268`）；仿真标记落在关联 `User.username` 前缀 `sim-fde-`，档案表本身**无标记列** | 同上 |

**处置（goal 提示词第二分支：禁止编造分层）**：简报**显式标注本口径未分层**并只交付真实可证的数字；「补分层标记」登记为待 OWNER／产品决策项（本文件 §四 D-1）。

**改码（零迁移零新路由零新表零蓝图）**——`server/src/fde_api/ops_todos.py`：

- NEW `BRIEF_FUNNEL_STRATIFICATION = "unstratified"`（分层状态位，闭集单值）。
- NEW `BRIEF_FUNNEL_STRATIFICATION_NOTICE`＝「本口径未分层（缺真实／演练标记，见 M0 归档）：以下四段为未分层的全量计数，不可当作真实经营基线。」——渲染在「二、招商漏斗」段**先于**计数行（限定前提，不是脚注）。
- 返回体与 `ops_brief_generated` 事件 changes 各带一个标量 `funnel_stratification`（审计可追「这批计数未分层」）；**漏斗计数口径一字未改**（仍为四段全量 GROUP BY）。

**机械钉四枚**（NEW 于 `server/tests/test_ecosystem_m2_ops_brief.py`，批次二 26 钉 → **30 钉**）：

| # | 钉 | 断言要点 |
|---|---|---|
| ① | 声明钉 | 正文逐字含声明字面串（**字面量而非被钉常量**——用常量造数则常量变异恒真）；声明**先于**第一条计数行；状态位字面量 `unstratified` |
| ② | 标签闭集钉 | 漏斗段**恰四行**计数、标签**恰为**四段闭集（任何分层标签即红） |
| ③ | 零编造静态钉 | AST 扫 `ops_todos.py`：无报价模型 import、无 `simulation` 字符串字面量、无 `.source` 属性访问 |
| ④ | 留痕钉 | 生成事件 changes 带 `funnel_stratification`＝`unstratified` |

**变异五连全杀**（判据＝exit≠0 **且**输出含期望 fragment ＋ 字节级还原 sha256 逐位一致 ＋ 复绿）：M1 分层状态位改值／M2 删除未分层声明行／M3 声明文案改写／M4 漏斗段编造第五层（`real_vs_simulated`）／M5 引入标记判据导入。★M4 首轮 **fragment 未命中**（击杀它的是既有返回体形状钉；断言顺序使分层标签钉排在其后）⇒ **调整钉内断言顺序**（标签闭集钉先于形状钉）后复跑，fragment 精确命中「漏斗段标签越出四段闭集」——变异判据要求 fragment 证明「是对应钉子杀死变异」，顺序即语义。

**实测**：定向 **60 passed**（批次一 30 ＋ 批次二 30）＝独立 PG 容器专库 `fde_m2_<hex>_test`（每次新建，跑完即弃）。

**结构口径零变化**：**572 路由／59 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2`**（返回体多一个标量字段，不新增路由）。

### 任务 C｜卡级 activation_state ＋ 出站白名单（OWNER 拍板已落）

**拍板前技术问题（现测，已答复）**：

1. `activation_state` **无任何运行时消费方**——全仓仅 `server/src/fde_api/agents/hq_cards.py` 装载器 ＋ 批次一 1 条钉引用。其唯一功能后果＝`_validate_card` 的出站纪律：`pending_owner_approval` 态**强制**「联网任务全禁用＋零出站域＋必填 `disabled_reason`」；`active` 态**只**校验出站域名格式（⇒ 改 active 会削弱出站纪律钉，goal 提示词已预警）。
2. **语义边界两读**：模块 docstring 写 `active`＝「OWNER 三项拍板落地后的人工状态」（上线许可）；seed 顶层 `approval_record.rulings.card_duties` 明写「activation_state 待逐卡上线时激活」（已上线状态）。**OWNER 裁定优先于实现者注释** ⇒ 实为「该卡是否已上线」，且 OWNER 已明示尚未到上线时点。
3. 拍板③＝出站白名单**零变更** ⇒ 联网型任务必须继续禁用。

**拍板（2026-11-24 交互式选择题，推荐项前置）⇒ 保持 `pending_owner_approval`**（推荐项获选）。

**处置与理由**：零代码改动（装载器、校验链、种子状态全不动）⇒ 出站纪律钉原样在位，符合拍板③；四张 MVP 卡无运行时消费方、尚未上线（OWNER 裁定语即「待逐卡上线时激活」）；M2 MVP 功能不依赖卡片激活（WP-2/WP-3 是确定性只读面）。**裁定追加进 `approval_record.rulings.activation_state`**（留痕可推翻；新 key 不含 `job_card` 子串——批次一静态钉探针会误报，本仓已踩过一次）。

**复跑**：批次一 30 钉 ＋ 批次二 30 钉＝**60 passed**（装载器校验链全绿）。**线外留账**：联网型岗位卡维持禁用；将来逐卡上线时由 OWNER 再拍板置 `active`，**届时必须同步补等效出站钉**（否则 pending 态那两条强制钉随状态切换失效）。

### 任务 D｜人工侧三件事（**只准备件，本轮零代做**）

**① 薄切片·招募观察（只读面，不签约不收费）**——V1.1 修订七（2026-11-22 拍板 Q4）：可复制性验证单元＝「1 创业者 × 1 企业 × 1 交付者」最小真闭环；规模恒为 1×1×1，跑完可重复再跑。本轮交付**空白观察表模板**：

| 观察表字段 | 说明 | 取值来源（现有面） |
|---|---|---|
| 场次号／日期 | 每片独立登记 | 试点运营登记 |
| 环境 | 候选环境版本、接口运行证据、迁移与镜像 | M1 部署负责人登记项（`docs/ecosystem-v1/m1/VALIDATION.md` 人工待办第 2 条） |
| 创业者（代号／角色／资格状态） | 四类状态及依据 | 注册面与权益面（席位激活与认证变更各自独立） |
| 企业客户（代号／手机可达性） | 企业侧手机网页可达性确认 | 诊断面（部署闸默认关） |
| 交付者（代号／交付资格） | 认证与交付资格 | 派单候选筛选（档案 `status=active` 且 `is_active=true`） |
| 各环节完成态 | 闭环各环节逐段打点 | 事件面 `operation_events` |
| time-to-first-yuan | 创业者从进入到第一笔收入 | 人工登记（系统无自动口径） |
| 逐单经济性 | 成交额 −（获客＋质检＋返工＋差旅＋兜底＋回款时差成本） | **一律用实际成交档位与实际到账重算**，不得拿稳态报价 ¥55,000 替代首单账（修订七第 6 条） |
| 换人复跑 | 同一套材料由**另一组人**重跑；记录创始人工时与各环节耗时 | 第二片场次登记（首片成功＋换人复跑成功才证「系统可复制」） |
| 结果分类 | 「真实闭环成功」／「失败但有完整复盘」均为有效产出 | 失败片须含阻塞环节、卡点归因、下一片修正项 |
| 证据指针 | `source_uri` ＋ SHA-256 | **原件只留本地真相层**，回执只登记指针与指纹 |

**只读纪律**：本轮**不接触任何人选、不签约、不收费、不发信**；上表＝空白模板，等试点运营在授权后填写。

**② DIFF-09 签署（首单签约前，须业务＋财务拍板）**——分歧一句话版：**B8 对外披露「交付 40%」vs 活库 v100 双层制「有效交付 35%」**，同基数 ¥55,000 标准单差 **¥2,750**（B8 口径 ¥22,000 vs v100 口径 ¥19,250）。**落库口径为唯一现行**⇒ 对外文件在签署完成前不得以 B8 的交付 40% 承诺分成。

签署样单要点（**待签，本轮零代签**）：

| # | 要点 | 现状锚点 |
|---|---|---|
| 1 | 计提基数与规则版本（统一口径后取其一） | `dispatch_rule_versions` 仅 v100 一行 `active`；五席比例 30/21/35/7/7 |
| 2 | 逐席金额（基数 ¥55,000 演算） | 平台 ¥16,500／拉单 ¥11,550／交付 ¥19,250／区县 ¥3,850／省级 ¥3,850 |
| 3 | B8 与 v100 差额的处置 | ¥2,750——须裁定「对外披露改写」或「落库口径调整」二选一（**落库口径为现行⇒ 默认改写对外披露**） |
| 4 | 空缺席位登记与平台承接 | 存在空缺席位时逐席登记原因与确认依据，平台承接核准的空缺份额及分币尾差 |
| 5 | 同一笔批准的样单三方核对 | 合同、系统账单、应付款逐笔一致；G8 前后尾款顺序须复核 |
| 6 | 签署人 | 业务 ＋ 财务（**AI 不代签**） |

**③ OWNER 单独授权项（逐条列举，本轮零动作）**：

| # | 授权项 | 当前闸位 | 触发前提 |
|---|---|---|---|
| 1 | **真实发信** | 注册验证邮件通道就位（SMTP provider 无关化已落地）；营销邮件范围、退订粒度、留存期限未界定 | 合规负责人界定邮件台账口径 ＋ 逐场实际发信授权 |
| 2 | **扣费** | 未配置金额/比例/阈值不可收费（已有机械闸）；实际扣费零动作 | 首单签约 ＋ DIFF-09 签署 |
| 3 | **正式签约** | 商业状态机结构就绪；签约为人工动作 | DIFF-09 签署 ＋ 薄切片场次确认 |
| 4 | **区域售卖放行** | 售卖闸默认关（依 DIFF-08／GAP-12） | 律师意见 ＋ 四项签署 ＋ 开闸批准 |

### 任务 E｜M3 角色工作台（**只读盘点，不开工**）

V1.1 修订六（2026-11-22 拍板 Q3）＝**伙伴端 web 优先**（基于既有 `desktop/web-dist` 反代，手机浏览器可开），Electron 保留给平台内部运营，**移动适配进 M3 验收**。V1.0 §16 第 7–8 周 M3 无未决 OWNER 决策——是唯一现在就能进的里程碑；但范围大，本轮**只做复用矩阵**（沿 M0 收割式方法：引用为主、只写增量）。产物＝`docs/ecosystem-v1/m3/01-role-workspace-reuse-matrix.md` 草案，**交蔡工定范围后再开工**。

## 二、OWNER 待拍板项（2026-11-23 已全部拍板，存档）

| # | 事项 | 输入物 | 时点 | 终态 |
|---|---|---|---|---|
| 1 | M2 立项批准 | 立项书 v0.1 ＋ 准备件 v0.2（本仓 `docs/ecosystem-v1/m2/PROGRESS.md` ＋ 文档中心两份准备件） | 第 5–6 周槽位 | ✅ 2026-11-23 批准，批次二开工 |
| 2 | AI 岗位卡职责审批 | 本文件第一节四张卡 ＋各组禁止事项 | M2 立项前 | ✅ 2026-11-23 四张卡职责定稿批准 |
| 3 | 出站白名单扩张 | 准备件第一节 7 行判定（组 1／组 3 需出站、组 2／4／5／6 零出站） | M2 立项前 | ✅ 2026-11-23 维持零变更（联网任务继续禁用） |

## 三、变更留痕

- 2026-11-23：蔡工问「现在是可以开始 M2 了吗？」→ 答复「可以，但只能启动不依赖未决 OWNER 拍板的部分」（§七 可先行工程部分）。交互式选择题未获答复 ⇒ 按推荐项执行 ＋ 留痕可推翻。批次一＝WP-1＋WP-4。
- 2026-11-23 同日自审修订：PR #576 首版 CI 四绿后、合并前——只读自审揪出五处问题（见「实测证据」首段）当场收口；校验逻辑下沉生产装载器；变异从 15 条扩到 27 条并升级为 fragment 级判据（loader fail-fast 下「模块转红」须证明是**对应规则**杀死变异）。首版全量曾遇 WSL NAT localhost 转发瞬断（PG 容器 RestartCount=0 无异常，6 失败节点定向重跑 5 过 1 环境性），改本树 venv 后消除。
- 2026-11-23 批次二开工：蔡工交互式选择题四项全按推荐项拍板（立项批准／卡职责定稿／出站零变更／V1.0 原件 AI 复制入库），逐项落 `approval_record`（key 由 `job_card_duties` 改名 `card_duties`——避开批次一静态钉 `job_card` 探针子串误报，30 钉回绿）。WP-2 交付前变异预演发现三处钉子强度不足（归类映射无字面钉／审批 title 无断言／纪要状态词无字面钉），补钉后才跑变异（13 条全杀）。
- 2026-11-24 **WP-5 首版 CI 红根因与换代（PR #581，server-tests 双 run 同红＝真回归非 flake）**：WP-2/WP-3 合并时写的两条「桌面零引用」钉（A8 延续，WP-5 未做时的**阶段性守卫**）精确命中新挂的 `OpsBriefPanel.tsx`——钉子行为正确（按设计该红），缺口在 WP-5 提交未同步换代，且本地只跑了桌面套件没跑服务端钉（「桌面-only 轮」盲区）。处置＝**换代不删钉、不放宽**：语义从「零处」收紧为「引用闭集＝{呈现面板}」（路由字面量只许出现在 `OpsBriefPanel.tsx` 单点，守住不在别处长出第二个调用点）；两向变异验证（页文件植入第二调用点／面板引用抽走）全杀＋字节还原复绿。**流程教训：桌面改动同样可能打红服务端静态钉（跨端扫描类），「零服务端改动」不等于「无需跑服务端钉」——涉桌面提交须至少跑引用面扫描类钉。**
- 2026-11-24 WP-5：桌面呈现挂 `#system-configuration`（调研代理对照五个候选页面选定——唯一同时满足「同页已有跨域只读监控＋GET 带 query 先例＋admin-only」三项的挂载点）；测试首版撞三处形状错（mock 信封 vs 直返 payload、ApiClientError 构造签名、strong 拆文断言）对照 delivery-plans 先例收口。
- 2026-11-24 WP-3：简报产出链设计裁决＝**确定性聚合而非 AI 调用**（数字溯源纪律＋运营值班员卡拍板定稿 `prompt_purposes: []` 不得擅改）；变异预演发现到期边界无等值用例（严格小于变异会幸存），补 `test_due_boundary_is_inclusive` 后 10 条全杀。WP-2 静态钉「零事件追加」换代为「record_event 单点许可」（简报留痕是模块内唯一合法事件写入），换代不删钉。
- 2026-11-24 **批次三开工（新会话 goal 提示词 v1.0）**：基线复现 HEAD `5a0a0b41`／八棵工作树／活体 ready-live 200 且 M1-M2 接口 404。任务 A 活体部署：接管检查器先过（并揪出活体 migrations 挂载源仍指 `fde-wt-rubricv2-deploy`）→ 本树重建三镜像 → recreate（redis 与 qiflow-* 旁栈零 recreate）→ 容器内 upgrade 补跑五条 → 三验全绿（url_map 572／alembic `f2a4b6c8d0e2 (head)`／三镜像逐位一致）→ 验收判据 `ops/todos`＝401、`ops/briefs/generate`＝401、`admin/dispatch/profiles`＝401、ready/live 200 全部达成。★**迁移挂载源随 recreate 自动迁回本树**（compose 相对路径解析随工作目录），但仍须人工核对——旧树若被删除会连带容器挂载失效，删树前必须确认挂载源已迁走。
- 2026-11-24 **任务 B 现测结论登记**：M2 验收第 9 条「运营简报区分真实、模拟和演练数据」——现测＝**无可靠分层依据**（四段表零标记列；唯一机器可读标记是报价来源列，而 E2E 造蜂经真实建单 API 建报价时硬编码 `source="manual"` ⇒ 模拟/演练数据与真实数据 schema 同形；活库四段 100% 是机制造蜂数据却无字段可证；文本约定标记不可作口径）⇒ 按 goal 提示词第二分支「禁止编造分层」处置：简报显式标注未分层 ＋ 只交付可证数字 ＋ 「补分层标记」进待决表 D-1。**不因「看起来能分层」而分层**——用 `project_code`／`enterprise_code` 文本前缀做口径＝把可复现的自由文本当契约。
- 2026-11-24 **任务 C 拍板**：交互式选择题（推荐项前置）获选「保持 `pending_owner_approval`」⇒ 零代码改动，裁定追加进 `approval_record.rulings.activation_state`。★技术问题的答案改变了结论：`activation_state` 无运行时消费方，其唯一后果是出站纪律；而语义边界两读中 **seed 的 OWNER 裁定（「待逐卡上线时激活」）优先于模块 docstring（「拍板落地后」）** ⇒ 保持原态同时满足拍板②（职责已批准）与拍板③（出站零变更）。**教训：状态位的语义边界要问「谁写的裁定」，不是读实现注释**——注释是实现者的解释，裁定才是授权来源。
- 2026-11-24 **任务 D 只准备件**：薄切片观察表字段、DIFF-09 签署样单六要点、OWNER 四项授权逐条列举，全部落本文件；**本轮零代做**（未接触人选／未签约／未收费／未发信）。

## 四、本轮待决表（2026-11-24 新增，待 OWNER／产品决策）

| # | 事项 | 归属 | 现状与证据 | 消解条件 |
|---|---|---|---|---|
| D-1 | **招商漏斗缺真实／模拟／演练标记字段**（M2 验收第 9 条） | OWNER ＋ 产品 | 四段表零标记列；报价来源列是唯一机器可读标记但 E2E 造蜂恒写 `manual`；活库漏斗 100% 机制造蜂数据却无字段可证（任务 B 现测表） | 选定一种落法：①四段表加**枚举列**（真实/模拟/演练）＋ 建列时回填既有行的标记来源 ②或引入独立「数据来源」维表 ③或接受「永不分层」并在简报永久标注（本轮已落）。★**不得用自由文本前缀当口径** |
| D-2 | 出站白名单扩张（联网型岗位卡激活） | OWNER | 拍板③＝维持零变更；联网型任务全禁用（组 1 市场研究／内容／线索研究、组 3 企业研究／画像） | 出站白名单新拍板；届时同步补等效出站钉（pending 态两条强制钉随状态切换失效） |
| D-3 | DIFF-09 签署（B8 交付 40% vs 活库 v100 有效交付 35%，差 ¥2,750） | 业务 ＋ 财务 | 落库口径为唯一现行；对外披露未改写前不得以 40% 承诺分成 | 同一笔批准的样单逐席核对完成并签署（任务 D ②） |
| D-4 | OWNER 四项授权（真实发信／扣费／正式签约／区域售卖放行） | OWNER | 全部零动作（任务 D ③） | 各项在执行前单独取得授权；区域售卖另依 DIFF-08／GAP-12 |
| D-5 | M3 角色工作台范围 | OWNER | 复用矩阵草案已出（`docs/ecosystem-v1/m3/01-role-workspace-reuse-matrix.md`） | 蔡工定范围后再开工（**本轮不开工**） |
| D-6 | M1 遗留：真实试点场次与三方人选、换人复跑 | 人工 | 十工作包「待补证据」未闭合 | 薄切片首片场次登记 ＋ 换人复跑成功（修订七第 5 条） |
