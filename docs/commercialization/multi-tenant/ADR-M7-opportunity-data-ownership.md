# ADR-M7 商机数据归属权与导出权（平台托管、企业确认前区域服务商不可导出客户名单、双方按授权可见）

> **状态**：按任务书 v1.2 §7-M7 拍板落成书面裁决 ｜ **轮次**：M7 ｜ **上游**：leader 任务书 §7 M7、sec 评审硬条件（「归属权与导出权须在 M7 写死」）、GAP-11、GAP-12、ADR-009（G4）、ADR-005（G5）
> **实施轮**：M7-1（2026-11-12）｜ **本 ADR 零迁移零新表零新列零新路由**

## 0. 决策摘要

**商机数据归属权写死：平台托管、企业确认前区域服务商不可导出客户名单、双方按授权可见。**

本轮（M7-1）只落**结构与测试**：硬约束落在**既有读面层**（列表读面 ＋ 序列化层），**不新开导出端点**、**不新增授权表/列**、**不新增路由**。

| # | 决策 | 落地形态 | 零结构变化自证 |
|---|---|---|---|
| D1 | **客户名单面＝既有列表读面** | `GET /api/v1/commercial/opportunities` **本身就是客户名单导出面**（admin 全量含企业代号＋「企业是否已注册」派生事实，且支持 `?enterprise_code=` 枚举）⇒ 硬约束落在 `list_opportunities` ＋ `serialize_opportunity`，**不新开 export 端点** | 零新路由 |
| D2 | **企业确认闸＝既有列** | `commercial_opportunities.enterprise_confirmed_at`（G4 第②步「企业确认有真实需求」时落值）——企业确认前，企业代号只是**未经平台核验的报备声明** | 零新列 |
| D3 | **区域服务商身份＝既有表推导** | 任一 `regional_partners` 行的申请账号（`applicant_user_id`）——G5 外部角色；**不新增授权表** | 零新表 |
| D4 | **托管方＝admin** | 平台 admin 全量可见（含未企业确认商机）**保持不变**——与 M3b「admin 跨 org 代操作留痕不阻断」一致 | 口径不变 |
| D5 | **主体归属走 `user.org_id` 间接归属** | OWNER 2026-11-12 拍板：不新增 org_id 列、不新增迁移、不改表结构；区域伙伴的 org 归属经 `applicant_user_id → users.org_id` 推导 | 零新列零迁移 |

## 1. 背景与问题（为什么必须写死）

sec 评审硬条件（`docs/commercialization/多客户工作平台-评审记录-2026-11-10.md:35`）：**归属权与导出权须在 M7 写死**。leader 任务书 §7 M7 原文：「商机数据归属权写死：平台托管、企业确认前区域服务商不可导出客户名单、双方按授权可见（v1.1 补，sec 评审——**渠道客户名单是商业敏感资产，归属不写死会成为渠道纠纷源头**）」。

M7-1 轮开工前的现测（fork/main@`fc9aa34`，commercial 域全域 grep）：

- **无 export 端点**（`routes.py` / `admin_routes.py` 对 `export|导出|download|csv` 零命中）；
- **无「客户名单 / 归属权 / 托管 / 授权可见 / escrow」任何模型或校验**；
- **无 `enterprise_confirmed_at` 闸**——列表读面 `list_opportunities` 只按 `reported_by_user_id` / `attribution_owner_user_id` / `presales_owner_user_id` 三列 `user.id` 收敛，admin 走 `scope="platform"` **全量**，且支持 `?enterprise_code=` 枚举。

**关键绕过路径（P1，研究员现测）**：`GET /api/v1/commercial/opportunities` 列表读面**本身就是客户名单导出面**——admin 返回全量含 `enterprise_code` 与 `enterprise_registered` 派生事实，还支持 `?enterprise_code=` 过滤。**故「只封一个新 export 端点加闸」无效**——硬约束必须落在 `list_opportunities` 与 `serialize_opportunity` 层。本 ADR 据此定 D1。

## 2. 授权模型（判定式）

### 2.1 客户识别字段

本域「客户名单」的**唯一可枚举面**＝两个字段：

| 字段 | 含义 | 客户名单意义 |
|---|---|---|
| `enterprise_code` | 企业代号（三段式，**非真实企业名**） | **客户标识**本身 |
| `enterprise_registered` | 企业是否已自助注册（派生事实） | **客户存在性**旁路 |

代码落点：`OPPORTUNITY_CUSTOMER_IDENTITY_FIELDS`（`attribution_service.py`）。

### 2.2 判定式（`customer_identity_visible`）

1. **托管方（`users.role == 'admin'`）⇒ 恒可见**——平台方全量可见，本轮口径不变（D4）；
2. **写面回显**（`enforce_ownership=False`）⇒ 可见——回显是**自证回执**（本人刚提交的报备／刚确认的流转），遮蔽它不产生任何信息安全收益；
3. **非区域服务商身份** ⇒ 既有可见性语义**逐位不变**——本轮硬约束的作用对象是**外部角色**，不越界改写既有读面口径（与 M6 的 org 隔离接线分工正交）；
4. **区域服务商**（外部角色）⇒ 客户识别字段**以企业确认为闸**：
   - 已企业确认 ⇒ 可见（**双方按授权可见**）；
   - 企业确认前 ⇒ **不可见**（平台托管的客户识别事实不得外发给区域服务商——**含其本人刚报备的行**：企业代号此时是**未经核验的报备声明**，客户名单的主体是平台而非报备人）。

### 2.3 枚举探针（`require_enterprise_confirmed_for_customer_list`）

「按企业代号取数」是**存在性探针**——即使命中行全在 actor 可见域内，它也回答了「该企业代号在平台是否存在」。故判定口径精确到「是否会泄信息」：

| 情形 | 结果 |
|---|---|
| 命中行全在 actor **可见域内** | 放行（actor 本就能看见，无新信息泄露） |
| 命中行全**已企业确认** | 放行（已确认的客户识别事实属「双方按授权可见」） |
| 存在「**域外 ＋ 未企业确认**」的行 | **403** `opportunity_customer_list_not_confirmed` |

### 2.4 错误码

| 错误码 | 状态 | 语义 |
|---|---|---|
| `opportunity_customer_list_not_confirmed` | **403** | 企业确认前，区域服务商请求客户名单（枚举探针命中「域外 ＋ 未企业确认」的行） |

**为什么是 403 而不是 409**：这是**读面授权**判定，不是状态机冲突——403 与既有读面越权码（`opportunity_forbidden`）同族，语义是「该身份此刻无权取得该客户识别数据」；409 留给**状态机**冲突（链路步序、规则位未配置等）。既有错误码**逐位不变**，本轮只增不改。

### 2.5 遮蔽而非删除

不可见时两字段输出 `None`，并置 `customer_identity_visible=false` 显式透出判定结果——**字段形状稳定**（前端与测试可据该字段判别），避免「静默遮蔽」。

## 3. 授权推导来源（零新表零新列零新路由）

| 判定要素 | 来源（**全部为既有列/既有表**） |
|---|---|
| 托管方判定 | `users.role == 'admin'` |
| 区域服务商身份 | `regional_partners.applicant_user_id == actor.id`（**既有表**） |
| 企业确认闸 | `commercial_opportunities.enterprise_confirmed_at IS NOT NULL`（**既有列**） |
| 当事方判定 | `reported_by_user_id` / `attribution_owner_user_id` / `presales_owner_user_id`（**既有 FK 列**） |
| 组织归属 | `users.org_id`（**间接归属**——D5） |

**为什么不需要新表**：授权可见范围由「**谁**（既有 FK 列）＋ **平台是否已核验该客户**（既有 `enterprise_confirmed_at`）＋ **该读者是不是平台方**（既有 `role`）＋ **该读者是不是外部伙伴**（既有 `regional_partners` 行）」四个既有事实**完全推导**得出。新增授权表只会制造「授权与归属两套事实」的漂移面（AGENTS 红线：归属与授权分离但**不得平行建表**）。

## 4. 区域面 org 维度接线（M7 轮）

区域面读面（`list_partners` / `get_partner`）的 org 维度收敛按 D5 接线（**零新列**——org 归属经 `applicant_user_id → users.org_id` 推导）：

- **admin** ⇒ 全量可见（口径不变）；
- **平台身份非 admin**（`org_id IS NULL`，存量账号）⇒ **可见性逐位不变**（仍「只见本人申请的」）——不越界改写既有语义；
- **企业身份**（`org_id = X`）⇒ 可见「本人申请的」**或**「申请人在**同一企业 org** 内」的伙伴行；**跨 org ⇒ 404**（不确认资源存在，CR-062）。

**与 M6 的边界**：M6 负责**商业域读面按 org 隔离的通用接线**（科目层／额度账／企业空间／权益／认证记录／**商机列表**）；M7 只补**区域面特有部分**（`regional_partners` / `regional_partner_tiers`）＋**商机数据归属权硬约束**。

★**与 M6 的唯一重叠点是 `attribution_service.py::list_opportunities`**（M6 把可见域谓词换成 `visible_user_ids_query(actor)` 的 org 谓词下推；M7 改的是**可见行内哪些客户识别字段可读**＋**枚举探针闸**）。双方口径**正交可叠加，不需要任何一方让步**——**合并策略＝以 M7 的谓词结构为底（`_opportunity_scope_filter(actor)` ＋ `scoped_ids` 与 `scope_filter` 共用同一谓词），把 M6 的 org 谓词融进去**。M6 侧其余改动文件（`billing_service.py`／`enterprise_service.py`／`ledger_service.py`／`quota_service.py`／`service.py`／NEW `org_read_scope.py`）与 M7 **零文件重叠**。

⚠️ **合并前置检查项**：M7 改了 `serialize_opportunity` 签名（新增 `actor` 关键字参数 ＋ `enforce_ownership`）——**M6 当前 diff 未改该函数的调用点**，故合并时无需改动；但**合并后 M6 若新增调用点，须带 `actor=`**（漏带会直接 `TypeError`）。

## 5. 区域档目录在售卖闸关闭态下仍可见（既有行为，不是漏洞）

`GET /api/v1/commercial/regional-partner-tiers` **任意认证用户可见**三档目录＋`sale_gate_status`。这**不**与「无法进入售卖流」冲突：

- **目录可见 ≠ 可签约**——对外收费签约被 `require_sale_gate_open` 闸住（默认 `closed`），推进正式档必 409 `regional_sale_gate_closed`；
- 本 ADR **显式钉住这条边界**（`test_m7_s5_e2e.py::test_s5_sale_gate_read_face_still_closed_and_catalog_visible`），避免后续被误读成「售卖闸失效」。

## 6. 本轮不做的事（如实登记）

| # | 不做 | 理由 |
|---|---|---|
| N1 | **不开售卖闸、不登记合规条件证据** | `register_gate_condition` / `open_sale_gate` **本轮零调用**；四条件槽全空（ADR-011:288「合规四项签署证据＋律师意见仍缺」） |
| N2 | **不激活席位计费** | §17-1 拍板「席位计费在有真实外部交付者前不激活」，工程侧零门控；S5 e2e **复用测试夹具 `_activate_seat`（测试态）**，用例 docstring 显式标注「席位为测试态激活、非商用态、不触发真实计费」 |
| N3 | **不改 G4 七步转移函数语义 / G5 区域四阶段语义 / 售卖闸开闭逻辑 / `_require_sourcer_seat` 判定式 / `activate_seat` / `FIRST_ORDER_SEAT_FEE`** | 硬约束纪律：只在既有结构上加约束，不重建 G 线已交付产物 |
| N4 | **不落任何业务数值** | 规则数值本期不定数（`OPPORTUNITY_RULE_KEYS` 五槽全 `unset`） |
| N5 | **非区域服务商账号的账号级客户名单遮蔽** | 属可能的扩展，**须 OWNER 裁决后再落**——本轮不越界改写既有语义（见 §2.2 第 3 条） |
| N6 | **不代做合规签署、不代填签闸栏日期、不代填真实发布记录** | 回写纪律 |

## 7. 留给 OWNER 的决策点

> **每个决策点附「若 OWNER 收紧／放宽，改动落点是 X」**——供拍板后直接落代码，不必重新找代码位置。

| # | 决策点 | 建议默认 | 时机 | **若拍板收紧／放宽，改动落点** |
|---|---|---|---|---|
| 1 | 非区域服务商账号是否也须受「企业确认前客户代号遮蔽」约束（§2.2 第 3 条的放宽或收紧） | **本轮维持既有语义**（只约束外部角色）——须 OWNER 拍板 | M7-2 或试点前 | **落点＝`customer_identity_visible()` 判定式第 3 条**（`attribution_service.py`）——把「非区域服务商身份 ⇒ 可见」改为「一律以企业确认为闸」；连带用例落点＝`test_m7_opportunity_data_ownership.py::test_non_partner_role_visibility_is_unchanged`（该用例当前钉住「既有语义逐位不变」，拍板后需改钉为「非区域服务商同样遮蔽」）＋`test_enterprise_confirmation_is_the_gate_for_customer_identity`（正例已覆盖确认后恢复）。**零结构变化**（仍不新增表/列/路由） |
| 2 | 区域服务商在**企业确认后**可见到何种粒度的客户名单（仅企业代号？＋行业/城市？＋报备时间？） | 本轮只放行企业代号＋已注册派生事实 | 试点前 | **落点＝`serialize_opportunity()` 的客户识别字段输出块**（`attribution_service.py`）＋**`OPPORTUNITY_CUSTOMER_IDENTITY_FIELDS` 常量**（决定「客户识别字段」的字段集）；新增粒度字段（如行业/城市/报备时间）须**从既有列派生**（`enterprise_code` 三段式已含行业/城市；`reported_at` 已是列）——**零新增列**；若需新列则本条升格为「需 OWNER 授权结构变更」。连带用例落点＝`test_m7_opportunity_data_ownership.py::test_enterprise_confirmation_is_the_gate_for_customer_identity` ＋ `::test_primitive_layer_judgements` |
| 3 | 「双方按授权可见」是否需要显式的**企业侧可见位**（企业账号在商机读面的可见范围） | 本轮企业侧未开商机读面（商机读面在商业域，非企业空间） | M7-2 | **落点＝「商机读面是否对企业身份开放」这一判定**，具体在 `list_opportunities()` 的可见域谓词 `_opportunity_scope_filter(actor)`（`attribution_service.py`）＋ `get_opportunity()` 的可见性判定（`:426` 起）——若开放，须同时定义「企业身份在商机读面的可见域」（现有列：`enterprise_code` 段的企业 org 无归属列 ⇒ 企业侧可见位**当前无既有事实可依**，须 OWNER 先定「企业账号 ↔ 商机」的归属依据，否则**不建议本轮开放**）。⚠️ 该落点与 **M6 的 org 维度接线同一谓词** ⇒ 改动须与 M6 合并后形态同步，**勿两侧各改一处** |

## 8. 验收证据

| 验收项 | 证据（测试名＋文件） |
|---|---|
| 规则文件 ↔ 代码常量 ↔ 测试三方一致 | `test_m7_opportunity_data_ownership.py::test_ownership_rule_document_block_matches_code_bidirectionally` |
| 企业确认前区域服务商不可导出客户名单 | `::test_regional_partner_cannot_enumerate_customer_list_before_confirmation`（403）＋`::test_regional_partner_cannot_read_other_customer_identity_field`（遮蔽） |
| 双方按授权可见 | `::test_enterprise_confirmation_is_the_gate_for_customer_identity`（确认前遮蔽→确认后可见） |
| 托管方例外 | `::test_admin_custodian_sees_every_customer_identity`＋`::test_non_partner_role_visibility_is_unchanged` |
| 零新表零新列零新路由 | `::test_no_new_authorization_table_or_column_or_route`＋`::test_no_new_export_route_in_commercial_domain`＋`::test_no_new_authorization_model_in_attribution_service` |
| 错误码闭集 | `::test_m7_error_code_is_registered_in_service_source`＋`::test_existing_error_codes_are_unchanged` |
| S5 全链端到端 | `test_m7_s5_e2e.py::test_s5_e2e_partner_registers_reports_confirms_protects_and_matches` |
| 售卖闸关闭态无法进入售卖流 | `::test_s5_sale_gate_closed_blocks_formal_partner_entry`（409 `regional_sale_gate_closed`） |
| 区域面跨 org | `test_m7_cross_org_opportunity.py`（10 例） |
