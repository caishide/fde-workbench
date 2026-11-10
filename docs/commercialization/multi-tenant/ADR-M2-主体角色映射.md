# ADR-M2 主体—角色映射（四类主体 × `users.role` × 商业分层的三层关系）

> **状态**：按任务书 v1.2 §11 拍板落成书面裁决 ｜ **轮次**：M0 ｜ **上游**：任务书 §3、ADR-001/002/006、GAP-01/02/13
> **实施轮**：M1（org 归属）/ M2（注册入口初始角色） ｜ **本 ADR 零代码改动**

## 1. 三层模型（正交裁决的落地形态）

```
第 1 层  平台权限：users.role ∈ {admin, project_lead, fde_engineer, viewer}   ——不动（ADR-001）
第 2 层  商业分层：commercial_entitlements.commercial_role ∈ {R1,R2,R3,R4,NULL} ——G1 已落库，权威承载已存在
第 3 层  主体归属：users.org_id（可空，M1 落）+ 各自身份表（fde_profiles / regional_partners / 企业主体键）
```

- 三层互不推导（ADR-001/006）；对外 L0–L4 仅经映射表**派生展示**（ADR-006，GAP-03 的映射入口由 G 线落，M 线只消费）。
- 真实代码基线：`commercial_entitlements`（user_id PK，`commercial_role`/四权益列）已随 G1 合并；`fde_profiles`/`fde_level_evidence` 在 dispatch 域（`dispatch/models.py:244,322`）——衡量**人**的交付能力等级，与商业分层不可互推（任务书红线 6）。

## 2. 四类主体 × 现有代码 × 目标语义矩阵

| 主体 | 数据归属 | 注册初始 `users.role` | 商业承载（**已在库**，M 线零新建） | org 关系（M1/M2 落） | 现测证据 |
|---|---|---|---|---|---|
| 企业客户 | org（企业空间=org，项目挂 org，成员进 org） | `project_lead`（org 内） | `enterprise_quota_subjects`（USCC 主键）+ `enterprise_free_quota` + `enterprise_triage_decisions` + `enterprise_paid_option_choices`（G6 全套在位） | 建号即建 org（`org_type=enterprise`，`subject_key` 挂钩）；成员 `users.org_id` 指向它 | `commercial/routes.py::register_enterprise_route`（免鉴权自助注册在位）；ADR-010 |
| 创业者 | 个人主体；模拟 run 与脱敏案例，**不进任何企业 org** | `viewer` + 模拟授权 | `FREE_TRIAL_ENTRIES['founder']`（G2 三入口注册表在位）；GAP-06 两档上限（`EXPERIENCE_LIMITS` 保守占位已落）；V3.2 simulation 域只读消费 | `org_id=NULL`（个人主体，无 org 行） | `commercial/models.py FREE_TRIAL_ENTRIES` + `assert_entry_scope_allows`；simulation 9 表无 project_id（V3.2 红线） |
| 交付者 | 个人主体 + 派单项目**临时成员** | 注册后 `viewer`；**进供给池审核通过后**才授 `fde_engineer`（v1.1 修正：绕过供给池审核与 G 线冲突） | `fde_profiles`（供给池生命周期）+ `fde_level_evidence`（GAP-01 证据链）+ `commercial_entitlements`（席位/权益，G1/G3） | `org_id=NULL`；接单经 `add_project_member` 落为项目成员（不因接单改 org） | `dispatch/models.py:244,322`；G3 扣费闸在位 |
| 区域服务商 | 个人/机构主体 + 报备商机记录 | `viewer` + 商机面授权 | `regional_partners`（四阶段闭集）+ `regional_sale_gate`（售卖默认关）+ `commercial_opportunities`（G4/G5 全套在位） | `org_id=NULL`（机构主体待 M2 定是否建 `org_type=enterprise` 行——**留待 M2 细化**，本期按个人主体+机构字段处理） | `commercial/regional_service.py`；ADR-005 |
| （平台侧）交付咨询 | 跨企业 | `admin`（本期）或新增运营角色 | GAP-14 三档分流判定留痕（`enterprise_triage_decisions.decided_by_user_id`） | `org_id=NULL`（平台身份） | **M0 留给 OWNER 的口子**：新增运营角色是 M3b 白名单面变宽的来源，本期默认 admin，M5 前按需再拍 |

## 3. 注册入口与现有代码的映射（ADR-M4 的输入）

任务书 §11-3 拍板「企业客户与创业者自助激活；交付者与区域服务商审核」。现有自助面：G6 企业自助注册（免鉴权路由 + IP 限流 `commercial:register:{ip}` + `viewer` 档自选密码，ADR-010 修正③）；G5 城市观察伙伴申请（当事人自证）；G2 三入口隔离闸（`assert_entry_scope_allows`）。**M2 的增量是把四入口收拢为统一注册面 + 邮箱验证 + 状态机**（详见 ADR-M4），不是从零建注册。

## 4. `org_id=NULL` 语义（拍板 §11-8 的工程展开）

1. NULL = 平台级身份，**不受 org 限制**：可跨 org 读写在语义上合法，但**每次跨 org 动作须留痕**。
2. 留痕形态：`operation_events.org_id = NULL`（事件本身是平台级动作）+ 事件 `metadata_json` 携带 `target_org_id`（对象归属可推导）——复用既有事件体系，零新表（红线：不建第二套审计事件体系）。
3. M3b 默认拒绝的端点对平台身份**显式白名单放行**（装饰器参数或服务层显式分支），禁止隐式旁路；白名单本身是审计对象（代码评审可见）。
4. 存量回归面：现测 2716 收集 / 102 个测试文件直接构造 `User(...)`——NULL 语义使这些夹具**零改动**；新增隔离用例一律双 org fixture。
5. guest01–03（W0 演示账号）**不迁移**（任务书 §3、N7）。

## 5. 被否决的映射方案（留档）

| 方案 | 否决理由 |
|---|---|
| `users` 加 `commercial_role` 列承载 R1–R4 | 污染 ROLE_RANK 比较与 AI 档位默认映射（GAP-01 既有结论）；且 G1 已选独立权益表方案落库，翻案须重新过 ADR-001 |
| org 成员资格直接当权限用（org_id 相同即可读） | 破坏「项目级最小可见性」：企业 A 的成员不应因同 org 就能读 org 内**所有**项目——可见性仍由 `project_members` 决定，org 只管归属与推导（§3 of ADR-M1） |
| 每主体新建一套身份表 | 交付者/区域服务商身份表已存在（fde_profiles/regional_partners），新建即平行体系（红线 8） |

## 6. 留给 OWNER / 后续轮的决策点

| # | 决策点 | 建议默认 | 时机 |
|---|---|---|---|
| 1 | 交付咨询是否新增运营角色（而非复用 admin） | 本期 admin；M5 判据设计时按权限矩阵再评估 | M5 前 |
| 2 | 区域服务商机构主体是否落 `orgs` 行（org_type 扩 `partner`？） | 本期个人主体+机构字段；若落 org 行需 M1 迁移里预留 CHECK 值域 | M2 细化 |
| 3 | 创业者模拟授权的承载（GAP-06 既有 `EXPERIENCE_LIMITS` 两档占位 vs 新授权表） | 消费既有占位结构，M5/M6 接线时判定 | M5 |
