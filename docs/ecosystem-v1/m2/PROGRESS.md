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

## 一′、批次二（2026-11-23）：WP-2 运营待办只读聚合视图

### 拍板前置

2026-11-23 蔡工交互式选择题四项全按推荐项拍板（见头部「性质」段）；批次二分支自 `72fdbb92` 切出，`approval_record` 随本批入库。

### 交付物

| 文件 | 性质 | 内容 |
|---|---|---|
| `server/src/fde_api/ops_todos.py` | NEW 只读聚合视图（服务层 union，零 DDL） | 四域待办投影：`automation_approval`（AI 自动化审批 pending）／`api_confirmation`（AI API 确认无结果）／`dispatch_offer`（派单待响应 offered）／`meeting_todo`（评审纪要待办，回看窗 30 天）→ 六字段 `domain/object_id/title/deadline_at/state/queue` |
| `server/tests/test_ecosystem_m2_ops_todos.py` | NEW 机械钉（17 条） | 立项书 A4/A6 落点 ＋ queue 归类闭集 ＋ 跨视图一致性 ＋ 回看窗/截断/排序/过滤 |
| `server/src/fde_api/app.py` | +1 蓝图注册 | `("fde_api.ops_todos", "blueprint")`（蓝图注册表单一真身） |
| `server/seeds/ai_hq_cards.json` | 拍板记录 | 顶层 `approval_record`（2026-11-23 四项裁定；key `card_duties`） |

### 关键裁决（沿 `expirations.py` B#13-D 先例）

- **服务层只读 union ＋ admin-only 路由 `GET /api/v1/ops/todos`**：零 DDL、不建 SQL view、不写任何源行、零事件追加（A4：列待办不产生执行结果——人工决策仍走既有裁定/确认/响应闸；A6：模块零真相层引用、零写路径原语，静态钉＋副作用钉双证）。
- **queue 字段＝V1.0 §4.3 Human Approval Queue 域级归类**：声明式映射 `DOMAIN_QUEUES`（审批/确认 → `production_data_writes`；派单响应/纪要待办 → `None`＝运营协调面不属六类）。闭集单一权威取 `agents.hq_cards.HUMAN_APPROVAL_QUEUE`（批次一机械钉已钉死 seed ≡ 常量），出闭集模块导入即炸（boot fail-fast）＋源码静态钉。
- **与到期投影的关系**：三域谓词同源（机械钉等集/超集验证——审批/确认与 `expirations` 逐位等集、offer 因「待发现」语义为严格超集）；确认窗常量与扫描上限共用同一权威（模块属性访问，变异敏感）。
- **纪要待办回看窗 30 天**：todos 是纯文本留痕（无完成态位），只收近窗封存纪要防陈旧待办永久堆积；无期限项 `deadline_at` 为 null、排序沉底、`due` 过滤整体排除。
- **人工管理面不进 AI 目录**（目录维持 98 条，钉子守）；桌面端零引用（WP-5 才挂呈现）。

### 验收条件落点（立项书 §四）

| # | 条件 | 钉子 |
|---|---|---|
| A4 | 视图只读：无人工确认不得产生执行结果 | `test_listing_has_no_write_side_effects`（状态/事件计数逐位不变）＋ `test_module_source_is_read_only_and_truth_layer_free`（零写路径原语）＋ `test_route_not_in_ai_catalog` ＋ `test_decided_confirmation_not_a_todo` |
| A6 | 全程留痕、不触真相层 | `test_module_source_is_read_only_and_truth_layer_free`（真相层 token 扫描）＋ 零事件追加副作用钉 |

### 实测证据

- **定向 17 passed**（独立 PG 容器专库 `fde_m2_<hex>_test`，每次新建）。
- **变异 13 条全被杀且 fragment 逐条命中、字节级还原复绿**（admin 闸短路／归类漂移／闭集校验掏空／boot 校验拆除／offer 无期限项改排除／回看窗拉宽／标题截断拆除／确认窗硬编码／due None 护栏拆除／排序沉底拆除／审批标题漂移／已决确认重回待办／状态词漂移）。★回看窗变异首轮**幸存**——测试自己用常量造数（恒真缺陷，批次一自审同类问题的重演），改为字面天数造数＋口径字面钉后杀灭（变异验证抓真缺陷的实例）。
- **邻域机械钉 49 passed**：批次一岗位卡 30 钉 ＋ 蓝图注册同步 ＋ expirations 投影 ＋ 行数预算 ＋ 架构纯净。
- **mypy 基线钉回绿**：`baseline 274 / current 274` 零新增；ruff 清。
- **结构口径推进（设计内 +1 路由 +1 蓝图）**：**571 路由／59 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2` 不变**（零 DDL）；inventory 三件套＋route CSV ＋1 行＋archify architecture 图 finalize 四闸过＋preview 整页实拍＋防陈旧闸绿。
- 全量服务端回归：见批次二 CI 回执（PR 待合并后补记）。

### 批次二未做（授权边界内）

WP-3 简报产出链、WP-5 桌面呈现（批次二续轮或下一分支）；联网型岗位卡维持禁用（拍板③＝出站白名单零变更）；发信／扣费／签约／售卖零动作。

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
