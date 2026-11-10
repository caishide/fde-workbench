# ADR-M4 注册审核策略（四入口隔离、审核状态机、邀请令牌语义）

> **状态**：按任务书 v1.2 §11-3 拍板落成书面裁决 ｜ **轮次**：M0 ｜ **上游**：任务书 §7-M2、sec 评审 6 项、红线 R7、GAP-13
> **实施轮**：M2 ｜ **本 ADR 零代码改动**

## 1. 四入口与审核制（拍板 §11-3）

| 入口 | 审核制 | 初始态 | 现有代码基础（M0 现测） | M2 增量 |
|---|---|---|---|---|
| 企业客户 | **自助激活** | `pending_email → active` | G6 企业自助注册**已在位**：`POST /api/v1/commercial/enterprise-registrations`（免鉴权、IP 限流 `commercial:register:{ip}`、同主体幂等、viewer 档自选密码） | 收拢进统一注册面 + 邮箱验证 + 建号同时建 org（ADR-M1/M2） |
| 创业者 | **自助激活** | `pending_email → active` | G2 `FREE_TRIAL_ENTRIES['founder']` 入口闸在位（`assert_entry_scope_allows`） | 同上；不建 org 行（个人主体） |
| 交付者 | **审核**（R 分层证据链 GAP-01） | `pending_email → pending_review → active/rejected` | 现状建号 admin-only（`users/routes.py:50`）；供给池表 `fde_profiles`/`fde_level_evidence` 在位 | 自助注册 + 材料申报（R 分层申请）+ admin 审核流；审核通过前不可接单（无 `fde_engineer` 角色） |
| 区域服务商 | **审核**（合规前置 GAP-12） | `pending_email → pending_review → active/rejected` | G5 `regional_partners` 申请（当事人自证，城市观察伙伴）在位；`regional_sale_gate` 默认关 | 自助注册落「待合规审查」态；**入口默认置后**（sec 评审：注册面可达性上把该入口排在最后/特性开关控制） |

**状态机**（M2 目标语义）：`pending_email → pending_review（仅交付者/区域）→ active / suspended`；`suspended` 可恢复（admin 动作留痕）；全流转落 `operation_events`（复用事件体系，零第二套审计）。

## 2. 邮箱验证

复用 **SES 发信模块**（`mailing/`，goal-r3 G9 预建，默认关，`FDE_SES_ENABLED` 启用）：验证链接一次性令牌（sha256 指纹入库、明文只出现一次在链接里——与诊断匿名令牌同形态）；`pending_email` 态不可登录业务面（登录仅可重发验证）。SES 未启用期的降级：注册面整体置于部署闸之后（与 `FDE_DIAGNOSTICS_ENABLED` 同款 fail-closed 形态，关=404），**不允许「无邮箱验证的静默放行」**——降级方案（管理员线下代验）须显式开关 + 留痕，OWNER 拍板后 M2 实施。

## 3. 反滥用三件（sec 评审，红线 R7）

1. **邀请/验证令牌一次性**：消费即失效；邀请令牌同形态（sha256 指纹存储）。
2. **同 IP 注册限流**：既有 `commercial:register:{ip}` 键族模式扩展为四入口统一注册限流（每 IP 每日上限为**配置位**，缺省保守值 + `experience_limits_placeholder` 同款「试点前须填实数」标注；M0 不定数——任务书红线 11）。
3. **区域入口默认置后**：注册面 UI 与 API 均最后暴露；`regional_sale_gate` 关闭态下申请仍可进（申请≠售卖），但售卖流零可达（G5 既有闸兜底）。

## 4. 邀请令牌语义（M5 企业空间成员邀请，sec 评审社工面）

- 邀请 = 邮件 + 一次性令牌；**被邀者身份对邀请人可见**（防误邀/冒名）；**成员变动通知全组织**（org 内成员可感知成员增减）。
- 邀请上限为配置位（不定数）；邀请动作落 `operation_events`（邀请人、目标邮箱 hash、org）。
- 成员入 org 仍走 `add_project_member` 项目级授权——**邀请≠授权**，两者分离（org 归属 vs 项目可见性，ADR-M1 §3）。

## 5. 越权与留痕验收（M2 验收清单的判定基线）

重复邮箱 / 已存在主体（同 USCC）/ 未验证邮箱登录 / 审核态越权接单（交付者 pending_review 时尝试进供给池或接单）/ 售卖开关关闭态下区域伙伴进入售卖流——**全部 4xx 且留痕**（事件带 request_id，无密码/令牌明文）。

## 6. 留给 OWNER 的决策点

| # | 决策点 | 建议默认 | 时机 |
|---|---|---|---|
| 1 | 邮箱验证在 SES 生产批复前的过渡形态（部署闸整体关闭 vs 管理员线下代验显式开关） | 部署闸关闭（fail-closed，与诊断线同形态） | M2 开工前 |
| 2 | 交付者审核的材料清单（R 分层申请表单字段） | GAP-01 证据链口径（fde_level_evidence 既有列形状），不新增字段语义 | M2 |
| 3 | 注册限流数值（每 IP 每日） | 保守占位缺省 + 「试点前填实数」标注（不定数纪律） | 试点前 |
