# 五席位分账规则：平台份额 30% ＋ 70% 池百份制（F 线成文规则唯一处）

- **状态**：**业务口径已拍板、工程未生效**。业务数值与规则的唯一权威是 **ADR-011 §3（v1.3）**（`docs/commercialization/decisions/ADR-011-分账口径裁决单.md`）；本文件是它在**规则成文层**的唯一落点（同款先例：`regional-partner-program-rules.md`／`opportunity-attribution-rules.md`）。拍板方式＝2026-11-10 对话拍板（16:43 全采纳推荐＋15:30 补充七项＋16:57 撤销公示），**书面签字待补**（见《分账口径改造-书面签字待补页》）；**本文件不得被当作「代码已生效」的证据**。
- **成文**：T0 轮（2026-11-10，纯文档，零业务代码改动）。
- **配套**：`docs/commercialization/分账口径改造任务书-v1.md`（v1.3，实施分解）、`docs/commercialization/分账口径改造-拍板决策包-v1.md`（v1.2，§7/§8/§8.5 拍板记录）。
- **与代码现态的关系**：代码现值（`DISPATCH_CONSTANTS.seat_shares`＝旧四席位 35/5/20/40、冷启动 40/5/15/40）**不是权威**，是「待迁移旧口径」；五席位承载层（`dispatch_settlement_allocations`）与原因码常量（`ALLOCATION_REASON_CODES`）**尚未建**（全仓零命中，T0 现测），由 T1/T2 落地。**机器闸现状＝目标态**：JSON 块 ↔ 代码常量 ↔ 迁移种子三方逐位一致的测试**随 T1/T2 建立**，T0 阶段只有本 JSON 块（如实登记，不假装已有闸）。

## 1. 术语与定性（不得写错的一句话）

**「平台份额 30%」是份额，不是成本扣除、不是抽佣。**

- 基数＝该项目**里程碑实收回款**（沿用 `payments.received_amount`，不重算、不二次扣）。
- Σ 五席位金额＝基数 T（审计硬断言）；**舍入尾差由平台吸收**。
- **无 C 层**：差旅／协拍／外包／驻场等额外成本**不进分账池**、不由平台代扣、不设统一扣减项——**谁发生谁承担**（企业愿出则企业出，否则交付者自负），线下双方法律关系，平台不介入、不记账、不担保。
- 对外话术亦不得写「抽佣率」（`DISPATCH_CONSTANTS` 注释既有禁令）。
- 3980 席位订阅费是**独立年费科目**（§8），不在本规则分账范围内。

## 2. 五席位定义

| 席位键 | 名称 | 主体范围 | 履行的职能 | 确权依据 | 本期状态 |
|---|---|---|---|---|---|
| `platform` | 平台 | 平台公司 | 技术提供、前端战略辅导、系统与模板、结算风控、统一收款开票、售后兜底 | 合同主体 | 恒在场 |
| `lead` | 拉单方 | **不限角色**（创业者／IP／网红／业务员等），唯一门槛＝**已缴 3980 席位订阅费** | 线索、报备、谈单、签约、回款 | ADR-009 `commercial_opportunities.attribution_owner_user_id`（归属确认＝admin 双闸）＋席位费科目行 | 有归属人即在场 |
| `delivery` | 交付者 | 经考核发证并获 `delivery_eligibility` 确认者 | 方案、现场执行、交付记录归集 | 派单包 `seat_delivery_user_id` | 恒在场 |
| `county` | 市县级服务商 | 本地服务主体 | 组织本地创业者／交付者／企业三方、服务客户、参与拉单与交付 | `regional_partners`（`city_service` 阶段，一单一结） | 有主体即在场 |
| `province` | 省级服务商 | 上级服务主体 | 同上，跨市县协调 | `regional_partners`（`regional_agent` 阶段——**本期不启用**） | **本期恒空缺**（§10） |

> **「组织本地三方」不单列服务费**：已含在市县／省级各 10 份里；职能确未履行（如自拉自交）按 §5 沉淀平台，不重复计提。
>
> **拉单资格口径变更**（ADR-011 §5-F／决策包 D-05）：现行代码 `attribution_service.py` 的「报备人必须 R2」硬闸（实测锚点 `:460-464`，409 `opportunity_reporter_role_required`）须在 T3 换成「存在有效席位费科目行／席位 active」闸，并同步 `rules/opportunity-attribution-rules.md` 与反例用例——**不得静默放宽**，须留书面依据指针。

## 3. 比例与算式（百份制）

```
T       = 该项目里程碑实收回款（payments.received_amount，不重算、不二次扣）
平台份额 = T × 30%
分配池   = T × 70%（按 100 份再分）
拉单 lead     = 池 × 30/100   交付 delivery = 池 × 50/100
市县 county   = 池 × 10/100   省级 province = 池 × 10/100
Σ 五席位      = T（审计硬断言；舍入尾差由平台吸收）
```

**折算到合同总额 T**：平台 **30%** ／ 拉单 **21%** ／ 交付 **35%** ／ 市县 **7%** ／ 省级 **7%**（Σ＝100%）。

> 「交付 35% vs 轮 3『交付 40%』」的取舍已由业务方主动选定双层制定案（ADR-011 §3.4 注），35% 为定案值，B1/B2 备选不再挂。

## 4. 六种情形（算式示例 T＝120,000，无池内成本；Σ 恒＝T）

| # | 情形 | 平台 | 拉单 | 交付 | 市县 | 省级 |
|---|---|---:|---:|---:|---:|---:|
| 1 | 满编 | 36,000 | 25,200 | 42,000 | 8,400 | 8,400 |
| 2 | 无省级服务商 | **44,400** | 25,200 | 42,000 | 8,400 | **0**（`no_province_partner`） |
| 3 | 市县级服务商自拉自交（只扣本级） | **44,400** | 自己 25,200 | 自己 42,000 | **0**（`self_sourced_self_delivered`） | 8,400 |
| 4 | 省级服务商自拉自交（补充拍板，只扣本级） | **44,400** | 自己 25,200 | 自己 42,000 | 8,400 | **0**（`self_sourced_self_delivered`） |
| 5 | 两种空缺同时发生 | **52,800** | 自己 25,200 | 自己 42,000 | **0** | **0**（两码并存） |
| 6 | 企业自来（无拉单方） | **61,200（51%）** | **0**（`no_sourcer`） | 42,000 | 8,400 | 8,400 |

> 情形 3–5 中自拉自交者合计 67,200＝56% T，单人过半——「份额随职能走、不设封顶」的必然后果，业务方知悉并接受（ADR-011 §3.4）；日后要压属上线后规则变更，须另立封顶规则并走版本＋公示治理流程，不在本裁决内。
>
> 情形 6 的「平台实得 51%」理由留档：企业本就是平台投放广告拉来的；平台是交付兜底方，有责任按算法把交付派发出去。**禁止「给企业折扣」**——对内分配不进对外话术。

## 5. 空缺沉淀规则（可结算、可举证）

**原因码闭集（本期三码，扩展须同步改闭集＋本文件 JSON 块＋机器闸）**：

| 原因码 | 触发条件 | 沉淀份额 | 去向 |
|---|---|---|---|
| `no_province_partner` | 该项目无省级服务商 | 省级 10 份（7% T） | 平台吸收 |
| `self_sourced_self_delivered` | 服务商（**市县级或省级**）自拉自交、未履行本级组织服务职能 | **仅本级 10 份（7% T）** | 平台吸收 |
| `no_sourcer` | 企业自来／平台自有渠道获客，无归属人 | 拉单 30 份（21% T） | 平台吸收 |

多种空缺同时发生：各份额累加，多码并存。**两级对称**（补充拍板）：`self_sourced_self_delivered` 的判定维度是「**本级主体是否履行了对他人的组织服务职能**」，与主体级别无关——省级自拉自交同样不拿本级 10 份。

**四条硬要求（缺一不可，否则结算单不可审计）**：

1. **显式记 0，不得省略席位行**——空缺席位金额显式 0、行必在。
2. **平台吸收**该份额，金额等式闭环（沉淀额＝池 × 份数/100），Σ 恒＝T。
3. **原因码 ＋ admin 人工确认**（ADR-007 admin 门＋密码双闸，**T4 已落闸**：`allocate_five_seats`/`allocate_five_seats_with_lead_attribution` 对调用方显式指定的 `vacant_reasons` 强制 admin＋`confirm_password`，限流同款）——**系统不得自动推断「谁没干活」**。**豁免**＝T3 解析器派生的 lead `no_sourcer`（§6-2 企业自来：零商机行 ⇒ 无拉单方，是**结构性派生事实**而非人工判定）。
4. `operation_events` 逐动作留痕（带 request_id，**密码不落事件**），记录原因码、份额、吸收金额、确认人。

## 6. 拉单确权（接 ADR-009，不造第二套）

1. `lead` 席位默认收款人＝`commercial_opportunities.attribution_owner_user_id`；**归属未确认 ⇒ lead 席位不得计提**（409 `attribution_not_confirmed`），**不得回落「平台代持」**。
2. **企业自来**＝无归属人的合法态：lead 席位 `status='vacant'` ＋ `no_sourcer`，平台吸收 21% T（平台实得 51%）——与 1 的区别：1 是「有归属但未确认」的**阻塞态**，2 是「本就无归属」的**空缺态**。
3. **归属确认后企业自行注册不转移归属**（ADR-009 §2.5 反例用例既有，T3 复用不重造）。
4. `protection_period_days` 本期 unset ⇒ 归属争议走线下，撬单风险**显式挂账**（任务书 L-2／D-10），**不得编天数**。

## 7. 兼任与验收（T4 落地）

1. `lead` 与 `delivery` **可为同一 `payee_user_id`**（本平台允许兼任；份额与职能履行绑定，不设统一封顶）。
2. **自拉自交项目的验收人恒为平台**（T4 已落）：`acceptance_passed_at` 唯一写咽喉 `projects.payment_service.mark_acceptance_passed` 排除席位收款人本人（交付席位＝`DeliveryPackage.seat_delivery`；拉单席位＝已确认归属 owner，与 T3 `resolve_lead_seat` 同一谓词）⇒ 403 `self_acceptance_forbidden`（反例用例：本人验收 403）。市县/省级收款人在分配时才产生，验收时刻无从辨认，由 G8 拍板权限尺（manage 门）共同守。
3. 兼任承载表 `commercial_role_assignments` **已建**（T4 迁移 `e5c9f2a7d4b6`，挂 T2 `c8d2f6a4e9b1` 之后保单头）：一人多角色（一人多行并存），附生效区间（`valid_from`/`valid_until` 可空＝长期，窗口倒挂 400＋DB CHECK 兜底）与来源（书面依据指针＋sha256 指纹）；同角色区间重叠 409 `role_assignment_overlap`（行锁＋重叠判定）；写入＝关键流转（admin＋密码双闸，CR-047 限流同款）；**不动 `users.role`**（ADR-001 保护清单）；`commercial_entitlements.commercial_role` 单值保留为「主角色」兼容读面（兼任**永不回写**主角色列），不删列。治理面不进 api_catalog。

## 7bis. 就近硬闸加固（T5 落地，**不提权**）

依据 ADR-011 §5-D ＋ 任务书 §4-T5／§12。**核查后撤回「就近只有 10% 权重、
需提权」的前判**——到场型本就是硬闸，真实缺口在派生判定与扩圈调度两处。

1. **到场型默认 True，仅显式标记纯远程才 False**（`delivery_packages.
onsite_required` 三态化，迁移 `a7c2f9e1b4d8`，挂 T4 `e5c9f2a7d4b6` 之后
保单头）：
   - 旧形态按 `ProjectSolution.schedule` 四关键词（现场／到场／驻场／驻点）
     **派生** ⇒ 方案文本漏写即**同城硬闸整体失效**，只剩 `geo_remote=10` 
     的软权重；
   - 新形态：`NULL`＝未设置（读侧兜底判 **True**）／`True`＝显式到场型／
     `False`＝**仅此一种**是纯远程型（须显式标记，写入口＝既有创建路由的 
     `onsite_required` 载荷）；四关键词派生降级为「字段为空时的兜底」，
     **未命中关键词不再据此判为纯远程**；
   - **存量行按旧派生规则回填**（命中⇒True／未命中⇒False）⇒ 存量行为
     **逐位零变更**（存量远程型包不被误加围栏），新语义只作用于新建/后续写入；
   - 判定唯一权威原语＝`dispatch.models.resolve_onsite_required`（读侧
     matching／simulator／access 一律走它，避免口径漂移）。
2. **15 分钟逐级自动扩圈**（`radius_expand_wait_minutes=15`，§6.2 唯一权威表；
本轮只加**调度消费方**，常量值不变）：`dispatch.offer_service.
expand_stale_offers` 接进 `expire_stale_offers` ⇒ 同城无人且已过 15 分钟 ⇒
自动重发（`dispatch_round+1` ＝ 扩圈一档：同城→同省→邻接都市圈→全国）；
包行锁防并发双推，状态机唯一迁移保幂等，留痕事件 `dispatch_offer_expanded`。
3. **全国档门槛保持不动**：`allowed_geo_tier` 在 round≥4 且报价非旗舰档时
封顶 tier2 ⇒ 非旗舰档**不会**扩到全国（「旗舰档＋客户书面确认」由既有逻辑
守住，本轮未改 `matching.py` 的分档规则）。
4. **权重未变**（任务书 §12 动作 3）：`stage_b_weights` 维持 
**40/30/20/10**；`geo_remote`／`sort_key_onsite`／`sort_key_remote` 
**一字未改**。本轮属缺陷修复、非规则重大调整 ⇒ 无需另发规则版本。

## 8. 3980 席位订阅费边界（不被「成本自理」改写）

- 3980 是**独立年费**，走 ADR-008 科目层 `seat_fee`，**不进 `delivery_settlements`、不进分账池、不从分成池二次扣**。
- **首单交付完成并验收后**触发，且须本人事先书面选定扣费方式；未接单不欠费、验收前不扣、含首年席位套餐（实战营 9800／陪跑营 19800）不重复收——既有 G3 反例用例钉死，零松动。
- 拉单资格的「缴 3980」以此科目层为准（存在有效席位费科目行／席位 active），不改 3980 的计费语义。

## 9. 证书、企业订阅费（本期实数不落）

| 项 | 裁决 | 纪律 |
|---|---|---|
| 学员证书 | **不另付费，含在学费里**（D-08 方案①） | `certification_fee` 配置槽**保持 unset**、不生成认证费科目行、新增「含学费」标志；**禁止填 0** 绕过 §17 纪律；通过线 unset ⇒ 本期不开放发证派单并显式挂账（L-1） |
| 企业订阅费 | **要交**，换取正式诊断书／陪跑内容／培训课程三项权益；触发点＝**企业选择付费选项之后**（不与 ADR-010 免费边界冲突） | 金额／时点／方式**未给 ⇒ 不得进报价单、配置槽、结算单**（R-1／L-3）；承载＝线下约定金额＋`source_uri`＋sha256（科目层有位置、金额层不落数） |

其余 §17 数值（陪跑期／保护期五规则位／试运营升级指标与首期金额等）**本期不做**，挂账保留，不得预写默认值。

## 10. 规则版本发布路径与初始基线豁免（★适用边界）

- **上线后任何改值**＝`dispatch_rule_versions` 新版本 ＋ **公示 ≥30 天**（`weight_public_notice_days=30`，`create_rule_version` 闸零改动——422 `notice_window_required`）。四处既有反例钉死「公示不绕过」，一字不改：`dispatch/rules.py`（`create_rule_version` 判定段）、`dispatch/admin_routes.py:13-15` 与 `:149`、`server/tests/test_dispatch_p0_r2.py:798`（常量断言）、`server/tests/test_dispatch_p0_r2.py:850-860`（29 天→422）、`server/tests/test_dispatch_admin_rules.py:64-71`（HTTP 10 天→422）。
- **本期（上线前）初始基线豁免**（2026-11-10 16:57 拍板「不用公示，本项目还没上线呢」）：
  - **适用边界：仅上线前首版（初始基线）一次**。T2 由**迁移**种入 `dispatch_rule_versions` 一行 `status='active'`，`rule_snapshot` 以 **`five_seat` 块**（`platform_share_percent` + `pool_shares`——平台份额与池内份数是**两个 100**，不能摊平进一个键）表达「平台份额 30% ＋ 池内 lead 30／delivery 50／county 10／province 10」（**不得沿用旧四席位 35/5/20/40 语义**：基线快照**不含** `seat_shares`/冷启动键，`seat_shares_for` 对缺键回退常量、旧路径行为逐位不变；`stage_b_weights`/`level_score_map` 与常量同值随行，基线 active 后撮合按快照打分不落空权重），`published_at`＝`effective_at`＝**真实迁移执行时刻**，`version_no=100`（保留段；1–99 留给上线后人工版本序列），`operation_events` 留 `initial_baseline` 痕迹（迁移时刻无 user 则诚实跳过事件——`actor_user_id` NOT NULL FK 不允许伪造 actor）。
  - **豁免依据**：无存量用户、无存量派单规则受影响 ⇒「初始基线」不是「对存量规则的变更」，§6.2 公示窗不适用。**不是永久豁免，也没有豁免分支**——上线后第一次改比例即自动恢复完整公示。
- **五条禁止（违者即破坏治理闸）**：
  1. 把 `weight_public_notice_days` 改 0；
  2. 给 `create_rule_version` 加通用豁免分支；
  3. 倒填 `published_at` 到 30 天前；
  4. 直接 SQL 造「零公示 published 版本」再催生效；
  5. 改 `DISPATCH_CONSTANTS.seat_shares` 硬编码作为生效路径。
- **T2 新增反例**：基线存在后再发第二版且零公示 ⇒ 422 `notice_window_required`（M6）；**T2 新增机器闸**：本文件 JSON 块 ↔ 代码常量 ↔ 迁移种子三方逐位一致（M6b）。

## 11. 冷启动档废止（显式，不留两条口径）

- **废止清单**：`DISPATCH_CONSTANTS.cold_start_seat_shares`（40/5/15/40）、`cold_start_first_orders`（前 3 单）、`seat_shares_for` 冷启动分支（`dispatch/settlements.py:64-68` 一带）、`rules.py` 快照键（`dispatch/rules.py:44-46`）、`test_dispatch_p0_r2.py:525` 用例。
- `_city_order_rank`（`dispatch/settlements.py:75`）：T0 现测仅 `settlements.py:70` 一处消费——T2 废止时一并清理（先 grep 复核再动手）。
- **同名不同义警示（T2 禁伤）**：报价域 `anchor_mode='cold_start'`（`projects/quote_service.py`、`workbench/models.py` 的 quotes CHECK）是**报价锚点模式**，与派单域冷启动席位档无关——**不在废止范围**。
- 废止须留痕（CHANGELOG＋本文件），**不得静默留两条口径**。

## 12. 省级席位本期后置（T7 保持关闭）

- `province` 席位本期**恒 `vacant` ＋ `no_province_partner`**，10 份（7% T）沉淀平台——T1–T6 只跑这条空缺路径，不被合规闸卡住。
- 省级主体启用＝独立轮次 T-12b（T7）：前置＝`regional_sale_gate` 四项合规签署证据（指针＋sha256）＋**律师意见**（「本模式是否构成特许经营」）＋ `OWNER` 双闸开闸。
- 合规未齐前**不得把 `province` 写成 `paid`**，严禁「先分钱后补手续」；不得用「线下临时结算」绕开售卖闸（会形成第二套结算引擎，撞 ADR-008 §2.5）。

## 13. 机器可读块（JSON）

> **机器闸目标态**：`server/tests` 解析本块，与代码常量（T1 新建：席位键闭集／池内份数／原因码闭集）与迁移种子（T2 初始基线版本）**三方逐位相等**（复用 G5／G4 双向闸模式）。**T0 现状＝代码常量未建（全仓零命中，现测）**，本块先行成文作为 T1/T2 的唯一目标规格；机器闸测试随 T1/T2 落地——不假装已有闸，不写假绿。

<!-- five-seat-split-rules:begin -->
```json
{
  "basis": {
    "decision_doc": "ADR-011 v1.3 §3",
    "decision_dates": ["2026-11-10 15:30", "2026-11-10 16:43", "2026-11-10 16:57"],
    "status": "business_decided_engineering_not_effective",
    "written_signoff": "pending"
  },
  "term": {"platform_share_name": "platform_share", "forbidden_names": ["cost_deduction", "commission"]},
  "base": "milestone_received_amount",
  "platform_share_percent": 30,
  "pool_share_percent": 70,
  "pool_total_shares": 100,
  "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "province": 10},
  "seat_keys": ["platform", "lead", "delivery", "county", "province"],
  "rounding_remainder_absorbed_by": "platform",
  "sum_invariant": "sum_five_seats_equals_base",
  "cost_model": "who_incurs_pays_not_in_pool",
  "vacant_reason_codes": ["no_province_partner", "self_sourced_self_delivered", "no_sourcer"],
  "vacancy_rules": [
    {"trigger": "no_province_partner_enrolled", "seat": "province", "shares": 10, "code": "no_province_partner"},
    {"trigger": "partner_self_sourced_self_delivered", "seats": ["county", "province"], "shares_each": 10, "code": "self_sourced_self_delivered", "symmetric_across_levels": true},
    {"trigger": "no_attribution_owner", "seat": "lead", "shares": 30, "code": "no_sourcer"}
  ],
  "vacancy_requirements": ["explicit_zero_row_no_skip", "platform_absorption_closed_loop", "reason_code_plus_admin_confirm", "operation_events_audit_no_password"],
  "no_auto_inference_of_non_performance": true,
  "lead_seat": {
    "eligibility": "any_role_with_paid_seat_fee",
    "role_restriction": null,
    "attribution_source": "commercial_opportunities.attribution_owner_user_id",
    "unconfirmed_attribution": "no_accrual_409_attribution_not_confirmed",
    "fallback_platform_custody": false
  },
  "concurrent_roles": {"lead_and_delivery_same_payee": true, "acceptance_authority": "platform_only", "carrier_table": "commercial_role_assignments", "users_role_untouched": true},
  "seat_fee_boundary": {"amount": 3980, "ledger": "commercial_revenue_ledger.seat_fee", "in_split_pool": false, "trigger": "after_first_delivery_acceptance", "covers_first_year_packages": ["bootcamp_practical", "bootcamp_mentorship"]},
  "certification_fee": {"policy": "included_in_tuition", "config_slot_status": "unset", "fill_zero_forbidden": true, "issuance_dispatch_open": false},
  "enterprise_subscription": {"policy": "pay_after_paid_option_choice", "amount_status": "unset", "into_quotes_or_slots_or_settlement": false, "entitlements": ["formal_diagnosis_report", "mentoring_content", "training_courses"]},
  "rule_versioning": {
    "post_launch_change": {"requires_new_version": true, "public_notice_days": 30, "gate": "create_rule_version_422_notice_window_required"},
    "initial_baseline": {
      "exemption_scope": "pre_launch_first_version_only",
      "not_a_permittable_branch": true,
      "seeded_by": "migration",
      "version_no": 100,
      "status_seeded": "active",
      "published_at_equals_effective_at": true,
      "timestamps": "real_execution_time_no_backfill",
      "snapshot_seat_shares_semantics": {"platform_share_percent": 30, "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "province": 10}},
      "legacy_four_seat_semantics_forbidden": true,
      "audit_event": "initial_baseline"
    }
  },
  "cold_start": {"status": "abolished", "abolished_keys": ["cold_start_seat_shares", "cold_start_first_orders"], "quote_anchor_mode_cold_start_out_of_scope": true},
  "province_seat": {"enabled": false, "vacant_code": "no_province_partner", "absorbed_shares": 10, "reopen": "T7_requires_compliance_evidence_plus_legal_opinion"},
  "scenarios_base_amount": 120000,
  "scenarios": [
    {"name": "full", "platform": 36000, "lead": 25200, "delivery": 42000, "county": 8400, "province": 8400},
    {"name": "no_province_partner", "platform": 44400, "lead": 25200, "delivery": 42000, "county": 8400, "province": 0},
    {"name": "county_self_sourced_self_delivered", "platform": 44400, "lead": 25200, "delivery": 42000, "county": 0, "province": 8400},
    {"name": "province_self_sourced_self_delivered", "platform": 44400, "lead": 25200, "delivery": 42000, "county": 8400, "province": 0},
    {"name": "both_vacant", "platform": 52800, "lead": 25200, "delivery": 42000, "county": 0, "province": 0},
    {"name": "no_sourcer", "platform": 61200, "lead": 0, "delivery": 42000, "county": 8400, "province": 8400}
  ],
  "scenario_invariant": "sum_of_five_seats_equals_base_amount"
}
```
<!-- five-seat-split-rules:end -->

> **数值唯一性对照（T1/T2 机器闸的锚点表）**：`platform_share_percent=30` ↔ 迁移种子快照与新分配层常量；`pool_shares` 四份数 ↔ 同上；`vacant_reason_codes` ↔ T1 新建 `ALLOCATION_REASON_CODES`；`public_notice_days=30` ↔ 既有 `DISPATCH_CONSTANTS["weight_public_notice_days"]`（零改动）；`seat_fee_boundary.amount=3980` ↔ 既有 G3 唯一落数金额（零改动）。**代码现值 `seat_shares 35/5/20/40` 与冷启动 40/5/15/40 不在本表**——它们是待迁移旧口径／已废止口径，不得写进新层。

## 14. 与其他裁决的边界

- 本文件**只管项目分账**（五席位百份制）；3980 席位费／培训费／认证费／企业订阅费的科目层口径归 **ADR-008**；区域四阶段与售卖闸归 **ADR-005**；商机归属七步链路归 **ADR-009**；关键流转人工确认归 **ADR-007**；`delivery_settlements` 零加列结构钉归 **ADR-003**。
- 分成比例落 `commercial_split_rules`（G3）时仍须**附书面依据指针＋sha256**（H9）；N-8：v4.0 BP 原件未核验 ⇒ 依据指纹**暂不生成**，不得硬编码凑数。该表**不参与金额计算**，只提供落位与可见性。
