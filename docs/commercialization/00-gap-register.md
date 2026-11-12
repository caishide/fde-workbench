# 商业化线缺口登记（00-gap-register）

- **日期：** 2026-11-08 ｜ **基线：** `eee317c`（fork/main，PR #214）
- **口径：** 每条缺口 =「现状实测 → 目标语义（任务书）→ 缺什么 → 处置方向 → 所属 Goal」。新增判定均以 00-baseline-audit §F 的全库盘点为据；「既有能力为何不足」随条目注明。

## GAP-01 商业角色分层字段（G1）

- **现状：** `users.role` 是平台权限角色（admin/project_lead/fde_engineer/viewer，`auth/models.py:13–18` + `ROLE_RANK` + `DEFAULT_ACCESS_BY_ROLE`）；无任何 R1–R4 承载。
- **为何不复用：** 把商业分层塞进 `users.role` 会污染权限阶梯（ROLE_RANK 比较、AI 档位默认映射全链）并破坏 `VALID_ROLES` 校验与既有测试。
- **处置方向：** 另立商业角色字段（候选 `users` 加列或商业身份表，ADR-001 裁决），值域 R1–R4 + NULL 未分层；对外 L0–L4 仅经映射表推导（ADR-006）。

## GAP-02 四类权益字段（G1）

- **现状：** `training_entitlement` / `subscription_entitlement` / `certification_status` / `delivery_eligibility` 全库**零命中**（server/src + desktop/src grep 无结果）。
- **既有为何不足：** `fde_profiles.status`（pending/active/suspended）只管供给池生命周期；`fde_level_evidence` 只管能力等级评定；P4 quotes/payments 只管项目报价收款。四类权益语义无承载。
- **处置方向：** 独立建模（ADR-002 裁决表形/字段组），四类互不推导；与 `fde_profiles.status` 并存且写明同步关系；权益变更留审计事件 + 人工确认闸。

## GAP-03 对外 L 编号映射表（G1）

- **现状：** 无映射；代码中 L 编号只在交付能力等级/降级链/BP 文档口径三处（§0.4）。
- **处置方向：** 建唯一映射入口（角色＋订阅/认证状态 → 对外 L0–L4 商业编号），代码零散落换算；培训营档位称「实战营/陪跑营」，不用 L 编号（ADR-006）。

## GAP-04 企业免费额度与主体判定（G2）

- **现状：** 无额度模块；无企业主体认定键；无「一次一主体、不重置」结构。注册面 admin-only 建号（baseline-audit §E.2），企业无法自助进入。
- **既有为何不足：** `guidance/` presurvey 有诊断流但无「免费边界」闸与额度账；projects 按项目组织，无主体级额度。
- **处置方向：** 新增额度账（按主体计）；主体认定键 ADR-004（G2 内成文，提示法务）；六项交付物完成判据挂诊断流；三入口隔离。
- **§1.4/§17-3 裁定回填（2026-11-11，OWNER 经营裁决）**：额度去重终态＝USCC 单键（不分别体验，保守默认）＋只境内主体（mod-31 硬闸）＋归并主张证据指针制（`source_uri`＋sha256，只存指针不存原件，与 admin 人工闸双轨）；任务书 §17-3「额度去重规则最终化」据此**销号**，法务正式意见列可选后续复核（不阻塞 M 线）。

## GAP-05 六项交付物完成判据与呈现（G2）

- **现状：** 诊断相关产物散在 guidance（诊断报告）与 solutions（方案骨架）等处，无「六项齐备 + 企业确认」的完成判据聚合，也无三档描述性等级（不给数值）的呈现位。
- **处置方向：** 在 G2 落完成判据聚合（复用既有产物，不复制内容），企业确认留痕；三入口隔离（企业=真实问题／创业者=模拟／交付者=脱敏考核）。

## GAP-06 两档模拟体验上限配置（G2）

- **现状：** 无算力/人工指导上限结构；V3.2 `simulation/` 有 run 底座但无限额。
- **处置方向：** 可配置结构 + 保守缺省 + 「试点前须填实数」标注；禁止无上限（任务书 §6）。

## GAP-07 席位激活与首单扣费（G3）

- **现状：** 无席位订阅表；`seat_shares_for`（settlements.py:59）只算分成份额，不管年度席位费 3980；无「交付完成并验收后扣费」触发点；无方案 A（一次性扣除）的书面选定承载。
- **处置方向：** 新增订阅权益与激活流；扣费挂结项验收后沿 `handover_packages`/Gate 验收事实；实战营/陪跑营含首年席位=可测不变量（反例用例）。
- **M6-1 轮回填（2026-11-12，只追加）**：**商业计量面按 org 隔离接线**落地——席位/权益类读面（`get_entitlement_for_view`）的跨 org 隔离已接线（企业身份读别家企业账号 ⇒ 403 `commercial_entitlement_forbidden`；同企业成员互相可见；平台身份存量用户零回归；admin 全量不变）。**本轮零迁移零新表零新列零新路由**；`activate_seat` 与 `FIRST_ORDER_SEAT_FEE = 3980.00` **一字未动**，`commercial_fee_configs` 三槽位**保持 unset**（缺省不可收款）。证据：`server/tests/test_m6_commercial_org_isolation.py`（20 例）＋对照表 `docs/commercialization/multi-tenant/M6-验收对照-v1.md`。**本条不销号**——席位激活闸与真实扣费流未激活，属业务闸层待授权。

## GAP-08 认证独立收费项与模拟考核驱动（G3）

- **现状：** 无认证费配置位；认证状态无承载（GAP-02 的 `certification_status`）；`simulation_evaluations` 存在但无「通过线」结构（本期也不设通过线）。
- **处置方向：** 认证费独立收费项（金额缺省不可收款）；认证状态由模拟考核结果驱动（只读消费 simulation，遵守 V3.2 表无 project_id 红线）。
- **M6-1 轮回填（2026-11-12，只追加）**：认证记录读面（`list_certification_records`）的跨 org 隔离已接线——企业身份读别家企业账号 ⇒ 403 `commercial_certification_forbidden`（沿用既有码，不自造失败码）。**认证费金额仍 unset**（缺省不可收款）；通过线未配置 ⇒ 认证**不判定通过**（停在 `pending_threshold`），本轮**未改**该语义。证据：`test_cross_enterprise_certification_records_read_forbidden`。**本条不销号**——金额与通过线属业务闸层待授权。

## GAP-09 收入科目层（G3）

- **现状：** `delivery_settlements` 是项目级派单分账（四席位份额），无收入科目维度；在它上面加列硬塞被任务书 §0.3 禁止。
- **处置方向：** 新增科目层（收入类型→金额→关联订单/席位/分成事件），外键指回 quotes/payments/contracts 与既有结算；六项计费名目只定义归属不定义计算；分成比例只落配置结构不落数（ADR-003）。
- **M6-1 轮回填（2026-11-12，只追加）**：科目层读面（`list_revenue_entries`／`get_revenue_entry`／`reconcile_revenue`）的跨 org 隔离已接线——企业身份读别家企业账号 ⇒ **404** `revenue_entry_not_found`（M3a §3.5 默认口径「不确认资源存在」；探测不可分辨已钉）；同企业成员互相可见；平台身份存量用户仍既有 403（零回归）；admin 全量不变。**归属推导走 `subject_user_id`／`payee_user_id` → `users.org_id`**（零迁移零新表零新列零新路由）。**分成比例仍只落配置结构不落数**（`commercial_split_rules` 零行、`status='unset'`）；`FIRST_ORDER_SEAT_FEE = 3980.00` **一字未动**。证据：`test_cross_enterprise_revenue_entry_*` 四例＋`test_cross_enterprise_revenue_reconciliation_returns_not_found`。**本条不销号**——科目层业务闸未激活。

## GAP-10 陪跑期限与培训周期挂钩结构（G3）

- **现状：** 无陪跑/培训期概念。
- **处置方向：** 结构先落、数值待定（「本次不定数」纪律，配置位缺省不预写业务数值）。
- **M6-1 轮回填（2026-11-12，只追加）**：培训权益读面随权益面同轮完成 org 隔离接线（权益面读面返回 `trainings` 明细，跨企业账号 ⇒ 403）。**陪跑期限数值仍不落数**（`commercial_fee_configs.mentoring_period_days` 未配置 ⇒ `TrainingEntitlement.valid_until` 留空），本轮**未改**该语义。证据：`test_cross_enterprise_entitlement_read_forbidden`。**本条不销号**——数值待业务拍板。

## GAP-11 商机归属七步链路（G4）

- **现状：** 无线索/报备/归属/保护期任何表。`project_ai_opportunity_profiles`（research）是项目内 AI 机会画像，`project_solution_opportunities` 是方案挂接——均非渠道商机，不能复用为主表。
- **处置方向：** 新增归属链路（报备→企业确认→平台确认→保护期→售前→撮合→结算），规则数值可配置且**不预写默认值**（保护期为空=「未配置」，可区分于「永久保护」/「立即失效」）；已确认归属不因企业自行注册转移（反例用例）。
- **处置结果（G4，ADR-009）：** 链路已落（`commercial_opportunities` ＋ `commercial_opportunity_rules`，七步转移函数齐备，五规则位迁移播种全 `unset`，未配置动作 fail-closed 409 `rule_not_configured`）。
- **处置结果补充（2026-11-12 M7-1 轮，只追加）：** **商机数据归属权与导出权硬约束**已写死（sec 评审硬条件「归属权与导出权须在 M7 写死」；leader 任务书 §7 M7）——「平台托管、企业确认前区域服务商不可导出客户名单、双方按授权可见」。落地：`docs/commercialization/multi-tenant/ADR-M7-opportunity-data-ownership.md` ＋ `docs/commercialization/rules/opportunity-attribution-rules.md` §9（含机器可读块，文档/代码常量/测试三方一致）。**零迁移零新表零新列零新路由**——授权可见范围由既有列推导（`enterprise_confirmed_at` ＋ 三列 FK ＋ `users.org_id`）。硬约束落点＝**既有列表读面与序列化层**（`list_opportunities` ＋ `serialize_opportunity`）——**不另开 export 端点**（既有列表读面本身就是客户名单导出面，另开端点无效）。证据：`server/tests/test_m7_opportunity_data_ownership.py` 13 例＋`server/tests/test_m7_s5_e2e.py` 9 例。**GAP-11 状态：结构已收口**（七步链＋归属权硬约束＋S5 端到端；数值仍待拍板，五规则位维持 `unset`）。

## GAP-12 区域合作商四阶段与售卖开关（G5）

- **现状：** 无区域伙伴任何概念。
- **处置方向：** 四阶段可区分落库（区域代理标注「暂不启用」）；前两阶段无独家权；城市服务伙伴按项目结算无固定年费；**售卖能力默认关闭**，开关绑定合规条件清单已签署；试运营指标不落数（ADR-005 于 G5 成文，含「两店一年」合规条件登记）。
- **处置结果（G5，ADR-005）：** 四阶段已落库（`regional_partners` ＋ `regional_partner_tiers` ＋ `regional_sale_gate` ＋ `regional_service_settlements`）；售卖闸单行播种 `closed`；`require_sale_gate_open` 为唯一对外收费签约闸门（闸关 409 `regional_sale_gate_closed`）；「登记≠开启」（`register_gate_condition` 只登记证据）。
- **处置结果补充（2026-11-12 M7-1 轮，只追加）：** **区域面 org 维度接线**已落（`regional_service.py` 的 `list_partners`／`get_partner`）——零新列零迁移零新表，org 归属经 `applicant_user_id → users.org_id` 推导（OWNER 2026-11-12 拍板：主体归属走 `user.org_id` **间接归属**，不新增 org_id 列、不新增迁移、不改表结构）。S5 场景端到端已落（`server/tests/test_m7_s5_e2e.py`）＋售卖闸关闭态边界显式钉住（关闭态下区域档目录**仍可见**＝既有行为、**不是漏洞**；进入售卖流必 409）。**GAP-12 状态：结构就绪·待授权**——**合规条件清单四项签署证据仍缺**（`regional_sale_gate` 四条件槽全空、ADR-011:288「合规四项签署证据＋律师意见仍缺」）；本轮**未登记任何合规条件证据、未开启售卖闸、未代做合规签署**。**「开关条件与合规清单结构性绑定」已验收 ≠「已签署」**（口径澄清见 `phase-status.md` §16 #13）。

## GAP-13 四类注册入口与自助态（G6）

- **现状：** 建号 admin-only（users/routes.py:50）；无任何自助注册。
- **处置方向：** 四类注册入口 + 企业空间复用 `projects` 权限模型（add_project_member）；「企业客户=企业自助用户」同一主体两状态；不新建平行权限表。

## GAP-14 三档分流人工判定留痕（G6）

- **现状：** 无分流记录结构。
- **处置方向：** 定性判据＋交付咨询环节人工判定并留痕（可回看判了哪档）；**无量化阈值硬编码**；系统可出建议但判定权在人（§0.5 L3 形态）。

## GAP-15 AI 草稿采纳率埋点（G2 消费，跨线登记）

- **现状：** 活库实测「接受/修改/拒绝」零承载事件（baseline-audit §H）。
- **处置方向：** 在诊断/方案确认流上落采纳留痕（复用 operation_events，不建第二套事件体系）；首批真实 run 后供智能化评级复审（BP §1.3a 证据口径）。
- **处置结果（2026-11-10 挂账清偿轮 1，`feat/commercial-gap15-adoption`）：** 埋点已落，零新表零迁移零新路由——①方案确认流**系统派生**：`solution_signoff_resolved`／`project_solution_archived` 事件在 AI 草稿方案（`generated_by='agent'`）上携带 `ai_draft` 派生块（generated_by/agent_run_id/modified_after_generation），`update_solution` 对 agent 方案首改即落 `source_json.ai_draft_modified` 戳（首改即定不翻回；人工方案零触碰、事件形状零漂移）；②诊断确认流**人工申报**：`complete_diagnosis` 可选 `ai_draft_adoption` ∈ accepted/modified/rejected 闭集（`AI_DRAFT_ADOPTION_OUTCOMES`），随 `commercial_quota_completed` 事件留痕、缺省不落键（向后兼容）。**数据仍待首批真实 run**——ADR-007 §2.5 复审触发器的「采纳率埋点有数」条件自本轮起具备承载；NEW `test_solution_ai_draft_adoption.py` 8 例＋quota 申报 3 例，变异三连全红→还原→绿。
- **复审中间态（2026-11-11 挂账清偿收口轮现测，`fork/main` `a0b9ec3` 部署活库）**：ADR-007 §2.5 触发器两条件——①**agent_runs 非零＝已达成**（实 run **12**：`idempotency_key not like 'rehearsal:%'`，落库 2026-11-09，status＝completed 6／failed 3／timeout 2／succeeded_but_receipt_invalid 1；`fallback_level` 分布 L2×3、None×9）；②**采纳率埋点有数＝未达成**（`solution_signoff_resolved` 带 `ai_draft` 派生块＝**0**，`commercial_quota_completed` 带 `ai_draft_adoption`＝**0**，`guidance.draft_*`＝∅——12 条实 run 无一在方案确认流上产生采纳留痕，缺的是**首条采纳样本**而非样本量不足）。判定：触发器**半激活**，「默认人工确认」维持不放松；人工拍板侧已有对照信号（门禁 `gates` passed 6／failed 1／pending 11；`automation_approvals` approved 2）。**销号条件**：任一真实采纳/否决样本落 `operation_events` 即具备完整复审证据，按 BP §1.3a 证据口径复核智能化评级与确认点密度——数据到位即销号，无需再开轮。

## 缺口与 Goal 矩阵

| GAP | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|---|---|---|---|---|
| 01 角色字段 | ● | | | | | |
| 02 四权益字段 | ● | | ○席位 | | | |
| 03 L 映射表 | ● | | | | | |
| 04 额度/主体 | | ● | | | | ○ |
| 05 六项判据 | | ● | | | | |
| 06 两档上限 | | ● | | | | |
| 07 席位/首单扣费 | | | ● | | | |
| 08 认证费/考核 | ○状态 | | ● | | | |
| 09 科目层 | | | ● | | | |
| 10 陪跑结构 | | | ● | | | |
| 11 商机归属 | | | | ● | | |
| 12 区域四阶段 | | | | | ● | |
| 13 注册入口/企业空间 | | ○隔离 | | | | ● |
| 14 三档分流 | | | | | | ● |
| 15 采纳率埋点 | | ● | | | | |

（●=主责 Goal，○=交叉消费）
