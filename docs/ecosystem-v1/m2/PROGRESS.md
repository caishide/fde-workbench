# Ecosystem OS M2 AI 总部 MVP — 进度与回执

**任务书依据**：V1.0 §4.1–§4.4（六 AI 职能组、组织树、角色卡十三项标准）＋v1.1a §16 第 5–6 周「M2 AI 总部 MVP（挂卡式，零新表）」＋评审纪要 B3/C3/C5/B4＋M0 决策登记表。
**分支**：`feat/ecosystem-m2-ai-hq`（基线 `9146d027`＝r59 交付后的 main 顶）｜**隔离树**：`D:/test/fde-wt-ecosystem-m2`。
**性质**：M2 分批推进。OWNER 三项拍板（出站白名单扩张／AI 岗位卡职责审批／M2 立项批准）未落 ⇒ 本批只交付**不依赖拍板**的工程部分。

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

- **定向 18 passed**（独立 PG 容器 `fde-m1-ci-2351-pg` 专库 `fde_m2_<hex>_test`，每次新建）。
- **变异 15 条全被杀且字节级还原复绿**（种子 sha256 `153da343dcbb79f774dc48e9e3b1fff460bd53b83a44ae40d8176c0d24393474`）：塞建表线索／引用未注册 purpose／引用公网面 purpose／挂未知能力腿／自造审批类别／自批免审批／引入写类能力腿／自带外发通道／触碰真相层／启用联网任务／带出站域名／删组禁止项／漏字段／任务同时启用与禁用／漏挂组禁止项。
- **邻域机械钉 33 passed**：污染隔离（`test_diagnostic_eval_contamination.py`）·蓝图注册同步 ·提示词注册表双向钉 ·架构纯净度 ·行数预算。
- **结构口径零变化**：570 路由／58 蓝图／172 表／101 迁移，单头 `f2a4b6c8d0e2`（`docs/audit/v3-workbench-inventory.json` 现测，与批次前逐位一致）。
- 全量服务端回归：见下节「批次一 CI 实测」。

### 批次一未做（授权边界内）

WP-2 运营待办只读聚合视图 · WP-3 简报产出链 · WP-5 桌面呈现 —— **待 M2 立项批准后开工**。联网岗位卡（组 1 市场研究／内容／线索研究、组 3 企业研究／画像、组 5 区域覆盖）**全禁用**，待出站白名单拍板。

## 二、OWNER 待拍板项（本轮不代拍）

| # | 事项 | 输入物 | 时点 |
|---|---|---|---|
| 1 | M2 立项批准 | 立项书 v0.1 ＋ 准备件 v0.2（本仓 `docs/ecosystem-v1/m2/PROGRESS.md` ＋ 文档中心两份准备件） | 第 5–6 周槽位 |
| 2 | AI 岗位卡职责审批 | 本文件第一节四张卡 ＋各组禁止事项 | M2 立项前 |
| 3 | 出站白名单扩张 | 准备件第一节 7 行判定（组 1／组 3 需出站、组 2／4／5／6 零出站） | M2 立项前 |

## 三、变更留痕

- 2026-11-23：蔡工问「现在是可以开始 M2 了吗？」→ 答复「可以，但只能启动不依赖未决 OWNER 拍板的部分」（§七 可先行工程部分）。交互式选择题未获答复 ⇒ 按推荐项执行 ＋ 留痕可推翻。批次一＝WP-1＋WP-4。
