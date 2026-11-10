# ADR-M3 全局面判定规则（盘点表的三类处置 + M3a/M3c/M3b 施工纪律）

> **状态**：M0 产出，作为《全局面盘点表》的判定准绳与 M3 三个子轮的施工纪律 ｜ **上游**：任务书 §7-M3、eng/arch 评审条件、红线 3/4/9/10/14
> **实施轮**：M3a / M3c / M3b ｜ **本 ADR 零代码改动**

## 1. 三类处置的判定规则（逐表逐端点可执行）

对每张全局表 / 每个涉全局写端点，按以下**顺序**判定（先命中先适用）：

| 序 | 规则 | 处置 | 判据（真实代码可验） |
|---|---|---|---|
| R1 | 平台私有（企业不可见不可写） | `platform-private` | 表内容是平台配置/台账/规则位（fee_configs / opportunity_rules / split_rules / regional_sale_gate / system_configuration / ai_provider_configs / ai_model_configs / plugin_packages / background_jobs / outbox_events / mailing_*）；端点仅 admin 可达（现 CSV auth= require_role/require_minimum_role admin）⇒ M3b **保持 admin-only，只加「org_id=NULL 平台身份留痕」**，无 org 语义 |
| R2 | 平台共享只读（企业可读不可写） | `platform-shared-readonly` | 目录/模板/技能定义类（module_catalog / template_* / industry_templates / document_templates / sop_nodes / skill_definitions / skill_versions / agent_registry / regional_partner_tiers / dispatch_rule_versions）；写端点全收 admin；企业读面在 M3a 统一入口按「目录白名单」放行 |
| R3 | 须主体隔离（写主体=某人/某主体，读默认限本人/本 org） | `subject-scoped` | 表含主体列（user_id / created_by_user_id / subject_key / actor_user_id）或经服务层绑定主体；写端点按「本人自助 / org 成员 / admin 代操作（留痕）」三分 |
| R4 | 特殊域单列（不入统一入口改造） | `special-domain` | dispatch 撮合（第三语义 `package_access`）与 simulation（V3.2 红线「表无 project_id」）——各自按既有闸语义做**主体归属校验增强**，不改架构 |

**冲突消解**：一张表多端点可各得不同处置（表处置=默认，端点处置=逐个覆写）；端点处置以盘点表「处置」列为准；**盘点表未登记的面不得改动**（红线 4），新发现疑似面登记「待 M0 补充」清单上报，不得顺手改。

## 2. M3a 统一入口（施工规格要求）

1. `projects/permissions.py`（现测 55 行 Python 全表扫描）改造为**带 org 维度的 SQL 下推**：可见性判定进 SQL（`EXISTS(project_members ...)` 谓词 + `projects.org_id` 谓词），禁止「SQL 后再加一层 Python 过滤」（红线 10）。
2. `visible_project_ids` 的 5 个精确消费域（agents/handover/meetings/transcripts/projects）+ `project_access` 助手广布的 38 文件是**回归面清单**：M3a 的改造必须保持函数签名与语义兼容（消费方零改动通过），回归以 `server/tests/test_visibility_parity.py`（#293 新增的可见性对等钉）为基线扩展。
3. JWT 加 `org_id` claim（可空；NULL=平台身份，ADR-M2 §4）：`auth/tokens.py` 7 claim → 8 claim；`auth/decorators.py` 消费。
4. **装饰器批量扩展行为规格先行**（红线 9）：现测装饰器 **428 处**（require_auth 384 / require_role 31 / require_minimum_role 13）。规格文档必须先于任何批量改动入库，内容至少含：org 校验发生层（装饰器 vs 服务层）、默认拒绝语义、平台身份白名单的显式形态、跨 org 动作留痕点、失败码闭集、**逐批验证方法（变异用例先红后绿）**。规格本身是 M3a 的交付物与 M3b 每批 PR 的先决引用件。

## 3. M3c 越权套件前置（TDD 顺序）

跨企业越权测试骨架**先于 M3b 端点改造合入**：企业 A token 打企业 B 资源全 403/404。覆盖面（任务书 §7-M3c）：项目 / 调研表 / 文件 / 导出 / AI 执行状态 / API-action 确认 / 对话。骨架合入时**允许红灯存在**（CI 单独 job 或 xfail 标记随批次摘除），但 M3b 每批必须「该批越权用例转绿」——**批批同 PR**（红线 3），越权用例未进 CI 不得申报 M3b 完成。

## 4. M3b 分批销号（以盘点表为唯一清单）

- 现测涉全局写端点 **236**（write-level 79 + read-only 157）。M3b 的**确认改造面 = write-level 79 + 处置列标记「须 org 校验」的 read-only 面**；`platform-private`/`platform-shared-readonly` 类只做 admin-only 核验 + 留痕补齐，不重写。
- 每批 ≤30 端点、独立 PR、批内同域不拆批、批批附越权用例（任务书 §7-M3b）。**建议批次划分见盘点表维度 2 末尾**（按蓝图域聚簇）。
- 每端点销号时回写盘点表：处置 + 测试指针 + PR 链接；全量销号 = M3 验收。

## 5. 特殊域纪律（盘点表维度 8 的展开）

1. **dispatch 撮合域**：`package_access` 是独立于 `project_access` 与 admin 的第三语义（`dispatch/access.py:1-16` 注释明示）；派单 SQL 零 join quotes/payments/contracts、响应白名单 schema、`require_package_access` 强制前置——这三条既有纪律不动。M3 对 dispatch 只做一件事：**`package_access` 授予/撤销端点补主体归属校验与留痕**（谁授权给谁，跨企业授权 admin-only+留痕）。
2. **simulation 域**：9 表零 project_id 是 V3.2 红线（表结构不得为隔离改造加列破坏「模拟与真实交付零耦合」）。主体隔离经 `created_by_user_id` 读过滤实现（表已有该列，现测确认）；场景库共享只读按 R2。GAP-08 认证消费保持只读。
3. 两域**不并入统一入口改造**，越权用例单独成套（M3c 覆盖面里单列）。

## 6. 漏网面治理（发现→登记→销号的闭环）

任何轮次发现盘点表外的疑似全局面：①登记进盘点表「待 M0 补充」节（表名/路由/疑似理由/发现轮次）；②**不得顺手改**（红线 4/14）；③下轮 M0 补充判定后入正式清单。M8 红队爬扫（企业 A 账号全 API 爬扫企业 B 资源）是漏网面的最终兜底，其发现按同流程回填盘点表。
