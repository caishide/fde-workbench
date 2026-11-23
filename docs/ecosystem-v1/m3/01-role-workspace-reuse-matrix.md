# Ecosystem OS M3 角色工作台复用矩阵（草案）

**状态**：**草案 —— 交蔡工定范围后再开工**（本轮只做只读盘点，不写任何业务代码）。
**依据**：任务书 V1.0 §8（统一入口：角色工作台 · 五类角色）+ §15 M3「角色工作台与伙伴自助运营」＋ V1.1 修订六（端策略决议＝伙伴端 web 优先，2026-11-22 拍板 Q3）＋ §16 第 7–8 周排期。
**方法**：沿 M0 收割式方法——**引用为主、只写增量**；每条结论带文件路径锚点或路由字面量；查不到的明确写「未查到」，不猜。
**盘点时点**：2026-11-24，代码基线 `5a0a0b41`（main＝fork/main）。
**上游回执**：M2 批次三 任务 E 节（`docs/ecosystem-v1/m2/PROGRESS.md`）。

---

## §0 前置事实：五类「生态角色」≠ 代码里的两套角色闭集

M3 要做的五类角色（V1.0 §8）在本仓**没有一一对应的角色实体**。代码里现役的是两套闭集：

| 闭集 | 取值 | 锚点 |
|---|---|---|
| 系统权限角色（4 值） | `admin` / `project_lead` / `fde_engineer` / `viewer` | `desktop/src/shared/contracts.ts:4` `USER_ROLES` |
| 商业角色分层（4＋NULL） | R1 企业 / R2 创业者 / R3 交付者 / R4 区域合作商 / NULL 未分层 | `server/src/fde_api/commercial/models.py:79-82`（`ck_commercial_entitlements_role`） |
| 注册四入口 | `enterprise` / `founder` / `deliverer` / `partner` | `server/src/fde_api/registration/models.py:40-45` `ENTRY_TYPES` |

**★「导师／行业专家」在本仓零命中**——`grep -rn "导师" server/src desktop/src` 实测 **0 条**；`mentor` 只出现在 `bootcamp_mentorship` 席位来源与 `mentor_sessions` 体验计数键（`commercial/ladder.py:24`、`commercial/models.py:60` 的 `TRAINING_ITEM_TYPES` 含 `mentoring`——那是**培训项类型**，不是角色）。

⇒ **M3 的角色工作台不能新建第二套角色体系**（仓库红线：跨企业隔离入口单一权威，org 只是归属维度不是授权维度）。可复用的角色载体只有两个：**R1–R4 商业分层**（`commercial_entitlements.commercial_role`）与 **`role_assignments` 兼任承载**（`commercial/role_assignment_service.py`：一人多角色＋生效区间＋书面依据）。「导师」若要落地，只能作为**商业分层上的一个兼任**或**培训项类型的一个视图**，不是新角色实体。

---

## §1 前端壳：伙伴 web 优先的三件套已就位（**零新增前端壳**）

| 环节 | 现状 | 锚点 |
|---|---|---|
| Web 入口 | `web-main.tsx` 先装 web 桥再装 `main`——**桌面与 Web 共用同一套 React UI** | `desktop/src/renderer/src/web-main.tsx` |
| Web 构建 | `vite.web.config.ts` 出 `desktop/web-dist`，`web.html` 改名 `index.html`（幂等） | `desktop/vite.web.config.ts`、`desktop/scripts/web-dist-entry.mjs` |
| Web 桥 | `window.fde` 浏览器实现，`API_BASE=""`（**同源 `/api`，服务端零 CORS 改动**）；会话只在模块内存，刷新回登录页 | `desktop/src/renderer/src/fde-web-bridge.ts:1-47` |
| 桥安全对齐 | web 桥与桌面 `main/api-ipc.ts` 消费**同一份** `desktop/src/shared/api-safety.ts`（method 白名单／auth 排除／编码双查／multipart 严格拒绝／响应信封） | 同上 |
| 静态托管 | **不在本仓**——`desktop/web-dist` 是纯静态产物，仓内零静态服务代码；由宿主 Nginx 托管（`location /` 静态、`location /api/` 反代活体） | 仓外事实留痕：`docs/deployment/对外试用部署方案-v2.md:43,92` |
| 已上线实证 | 网页端（Chromium 走 `desktop/web-dist` + `/api` 反代活体）门禁提交 200、人工核验 200、事实批审 200 | `docs/design/ux-p0/隔离验收记录-2026-11-18.md:137` |

⇒ **M3 新增角色工作台不需要新写前端壳**：加 renderer 路由 + 组件即可在 web 与桌面双形态生效；要动的只是仓外 Nginx vhost 与 `desktop/web-dist` 重建。

---

## §2 可见性：必须复用三层既有权威，不新写角色过滤

| 权威 | 语义 | 锚点 |
|---|---|---|
| 项目可见性（单一权威） | 列表谓词 `visible_project_filter()` ＋ 对象级 `project_access()` 必须同源（否则「列表可见、详情无权」的幽灵行），由 `test_visibility_parity.py` 钉死 | `server/src/fde_api/projects/permissions.py:25-101` |
| org 维度隔离 | 三态：平台身份不受限／企业身份见「本 org ＋ 平台内部桶 ＋ 平台级行」；纯领域判定、零 flask 零环境读取 | `server/src/fde_api/orgs/isolation.py:34-101` |
| 商业域读面 org 归属 | 商业域行**不含 org_id**，经关联账号 FK → `users.org_id` 推导；对象级四态 `self / same_org / cross_enterprise / other`（跨企业 404 不确认存在） | `server/src/fde_api/commercial/org_read_scope.py:64-128` |
| 派单域第三语义 | `PackageAccess`（role ∈ lead/seller/delivery/**audit**）独立于 `project_access` 与 admin；包 SQL 禁 join quotes/payments/contracts | `server/src/fde_api/dispatch/access.py:1-49` |
| 三入口隔离闸 | 企业入口＝真实业务问题／创业者＝模拟体验／交付者＝脱敏模拟项目考核；非企业入口取用 `real_business` 即 403 | `server/src/fde_api/commercial/quota_service.py:294-315` |

**已接线、可直接复用的消费方**：任务中心列表 `control/service.py:338-358`、任务看板 `control/task_board.py:25-73`、纪要列表 `meetings/service.py:61,1002`、企业空间 `commercial/routes.py:500-511`（**绑定账号本人或 admin**，CR-062 拍板，刻意不改为 org 维度）、商机列表 `commercial/routes.py:250-273`、区域伙伴列表 `commercial/routes.py:347-363`、能力档案 `dispatch/routes.py:495-550`、线索池按区可见 `diagnostics/lead_routes.py:60-80`。

---

## §3 五类角色 × 现有工作台复用矩阵

### §3.1 现有页面（桌面端 `desktop/src/renderer/src/`）

| 角色 | 路由 hash | 页面文件 | 标题 | 访问门 |
|---|---|---|---|---|
| ① 创业者 | `#leads` | `leads/LeadPoolPage.tsx` | 线索池 | 登录即可 |
| ① 创业者 | `#diagnostics`（`/sample`、`/share/<token>`） | `diagnostics/PublicDiagnosticPage.tsx` 等 | 免注册诊断 | **公开面** |
| ① 创业者 | `#translator` | `translator/TranslatorPortalPage.tsx` | 翻译器门户 | 登录即可 |
| ② 交付者 | `#dispatch/mine` | `dispatch/MyOffersPage.tsx` | 我的接单 | 登录即可 |
| ② 交付者 | `#dispatch/settlements` | `dispatch/MySettlementsPage.tsx` | 我的结算 | 登录即可 |
| ② 交付者 | `#dispatch/profiles` | `dispatch/CapabilityProfilesPage.tsx` | 能力档案与产能看板 | 登录即可 |
| ② 交付者 | `#dispatch`（tab=pool） | `dispatch/DispatchPoolPage.tsx` | 派单池 | 登录即可 |
| ② 交付者 | `#simulation` | `SimulationLab/SimulationLabPage.tsx` | 模拟训练场 | admin／project_lead／fde_engineer |
| ③ 企业客户 | `#enterprise-register` | `commercial/EnterpriseRegisterPage.tsx` | 企业注册 | **公开面** |
| ③ 企业客户 | `#enterprise-space` | `commercial/EnterpriseSpacePage.tsx` | 企业空间 | 登录即可 |
| ④ 区县服务商 | `#leads`（`CLAIMANT_KINDS` 含 `r4_partner`） | `leads/LeadPoolPage.tsx` | 线索池 | 登录即可（按区可见） |
| ④ 区县服务商 | `#dispatch/settlements`（区域合伙人席位行） | `dispatch/MySettlementsPage.tsx` | 我的结算 | 登录即可 |
| ④ 区县服务商 | `#commercial-ops` | `commercial/CommercialOpsPage.tsx` | 商业化运维（含区域售卖闸） | **admin-only** |
| ⑤ 导师／行业专家 | — | **未查到任何页面** | — | — |
| 平台侧（共享） | `#projects` / `#projects/<id>`（13 tab） / `#task-center` / `#system-configuration` / `#dispatch/console` 等 | `projects/ProjectsPage.tsx` 等 | — | 见 `routing/useHashRoute.ts:200-231` |

### §3.2 现有 API 面（服务端）

| 蓝图 | 前缀 | 对 M3 最有用的端点 | 门 |
|---|---|---|---|
| `dispatch.routes` | `/api/v1/dispatch` | `GET /packages`・`GET /offers/mine`・`GET /settlements/mine`・`GET /profiles/me` | `/profiles` 列表对非 admin 403；`/offers/mine` 只返回本人候选 |
| `dispatch.admin_routes` | `/api/v1/admin/dispatch` | `POST /profiles`・`/profiles/<user_id>/enable`・结算四闸 | **admin-only** |
| `commercial.routes` | `/api/v1/commercial` | `GET/POST /opportunities`・`GET /regional-partners`・`POST /regional-partners`・`GET /enterprise-spaces/<key>`・`GET /entitlements/<uid>`・`GET /certification-records/<uid>`・`POST/GET /orgs/<org_id>/invitations` | 读面自判「本人/admin/org」 |
| `commercial.admin_routes` | `/api/v1/admin/commercial` | 培训／认证／席位激活／交付资格写面・`GET /regional-sale-gate`・`POST /opportunities/<id>/{enterprise-confirm,attribution,presales,match,customer-choice,settlement}` | **admin-only** |
| `diagnostics.lead_routes` | `/api/v1/diagnostics/leads` | `GET ""`（按区可见）・`POST /<sid>/claims`・`POST /claims/<id>/{accept,reject}` | accept/reject ＝ admin |
| `registration.routes` | `/api/v1/auth` | `POST /register/<entry>`（四入口）・`POST /registrations/{verify,resend}` | 审核簿记面 admin-only |
| `simulation.routes` | `/api/v1/simulation` | 场景 CRUD・`POST /runs/<id>/execute`・`POST /runs/<id>/evaluation/human`・`GET/POST /findings` | 交付侧口径 |
| `ops_todos.blueprint` | `/api/v1/ops` | `GET /todos`・`POST /briefs/generate` | **admin-only**（M2 WP-2/WP-3 已建件） |
| `projects.routes` / `meetings.routes` / `control.routes` | — | 项目主干、纪要面、任务中心 | 项目成员／逐路由鉴权 |

**★培训／认证没有独立蓝图**——只有 `commercial` 域内两个 admin 写面（`POST /api/v1/admin/commercial/users/<uid>/training`、`/certification`）＋ 一个自读端点（`GET /api/v1/commercial/certification-records/<uid>`）。**没有队列、没有认领、没有排期面**。

---

## §4 缺口清单（每条注明「现有代码里最接近的东西」）

### ① 创业者

| # | 缺口 | 最接近的现有件 |
|---|---|---|
| 1 | **缺「我的商机」工作台**：桌面端**无任何商机页**（`grep "opportunities"` 在 renderer 的命中全是诊断报告的政策建议，与商业商机无关） | `commercial/routes.py:250-273` 的 `GET /api/v1/commercial/opportunities`（已按「admin 全量／本人只见自己报备·归属·售前」过滤）＋ `leads/LeadPoolPage.tsx` 的认领状态机 UI 范式 |
| 2 | **缺「线索→项目」转化视图**：认领只落 pending，页面注释明写「服务端尚无认领→项目转化端点，本页不臆造」 | `diagnostics/lead_routes.py` 的 claims 三面 ＋ `ops_todos.py` 的 admin-only 漏斗计数 |
| 3 | **缺学员侧训练入口**：`#simulation` 限 `fde_engineer` 及以上，创业者被回落 | `SimulationLab/SimulationLabPage.tsx` ＋ `simulation/routes.py` ＋ `commercial/models.py:267` `FREE_TRIAL_ENTRIES["founder"]`（3 次模拟 ＋ 1 次导师陪跑体验档） |

### ② 交付者

| # | 缺口 | 最接近的现有件 |
|---|---|---|
| 1 | **缺真正的「派单收件箱」语义**：`GET /dispatch/offers/mine` 是 API 级收件箱，但 UI 侧 `#dispatch/mine` 与 `#dispatch` 派单池**平级 tab**，没有「未响应／临期／已过期」分流，deadline 语义散在服务端 `offer_deadline()` | `dispatch/routes.py:335-385`（含 deadline 现算）＋ `MyOffersPage.tsx` |
| 2 | **缺「派单→接单→项目」跨域交接视图**：接单后靠 `add_project_member` 落回项目内鉴权，交付者看不到「我接的包 → 我参与的项目」 | `dispatch/access.py` §9.3 交接链 ＋ `DispatchPoolPage.tsx` 的包字段 ＋ `projects/ProjectsPage.tsx`（列表已按 `visible_project_filter` 收敛） |
| 3 | **缺交付者侧聚合视图**：结算按 `seat_key` 分散，无统一「我的交付物／结算明细」视角 | `GET /dispatch/settlements/mine`（五席 `FIVE_SEAT_KEYS`）＋ `MySettlementsPage.tsx` |

### ③ 企业客户

| # | 缺口 | 最接近的现有件 |
|---|---|---|
| 1 | **缺登录后落点**：企业注册页是**公开页**，注册完没有「跳到我的企业空间」引导；`#enterprise-space` 需手填 `subject_key` | `EnterpriseSpacePage.tsx` ＋ `registration/routes.py:121` 四入口返回体 |
| 2 | **缺客户视角项目进度页**：企业空间里的「交付项目」是嵌入卡，不是独立视图 | `ProjectDetailPage.tsx` 13 tab（但含门禁证据／执行事实／术语表等内部口径，不适合客户）＋ `projects/permissions.py:25-52`（企业账号在项目里是 viewer 成员） |
| 3 | **缺成员/席位自助页**：邀请 API 已有，桌面端只在企业空间里内嵌调用，无独立页 | `EnterpriseSpacePage.tsx:159-181`（邀请＋接受已就位）＋ `commercial/routes.py:535-590` |

### ④ 区县服务商

| # | 缺口 | 最接近的现有件 |
|---|---|---|
| 1 | **缺「伙伴自助运营面」**：`GET/POST /commercial/regional-partners` 在桌面端**零消费**（`grep "regional-partners" desktop/src` 实测 0 条）——申请、阶段、阶梯、区域售卖闸全部只有 API | `CommercialOpsPage.tsx:182` 区域售卖闸卡（**admin-only 且只读** `GET /admin/commercial/readiness`）＋ `commercial/regional_service.py`（阶梯/售卖闸/按项目结算服务层已就位） |
| 2 | **缺区域转化漏斗视图**：线索池有区域筛选，但「认领→成交→结算」漏斗只在 `ops_todos.py` 里以 **admin-only 计数**存在 | `ops_todos.py:264-300` ＋ `LeadPoolPage.tsx:322-353`（认领身份＋区域筛选 UI 已就位） |
| 3 | **缺「我的区域服务结算」独立页**：混在 `#dispatch/settlements` 的席位行里，无「按区域/按项目」聚合 | `commercial/regional_service.py`（区域结算引用 G3 科目层 `project_share`，一单一结）＋ `GET /dispatch/settlements/mine` |

### ⑤ 导师／行业专家

| # | 缺口 | 最接近的现有件 |
|---|---|---|
| 1 | **缺角色实体本身**：零命中「导师」；`users.role` 只 4 值、商业分层只 R1–R4、注册入口只 4 个——**导师无处安放** | `commercial/models.py:60` `TRAINING_ITEM_TYPES`（含 `mentoring`）＋ `commercial/role_assignment_service.py`（兼任承载机制） |
| 2 | **缺训练队列页**：培训/认证只有 **admin 写面**＋一个自读端点，**无队列、无认领、无排期** | `SimulationLab/SimulationLabPage.tsx`（现成的「训练」产品形态）＋ `simulation/routes.py` ＋ `dispatch/routes.py:809-928`（争议处理＝现成的「人工裁定队列」范式） |
| 3 | **缺「教学案例 ↔ 真实包」对齐面**：导师默认无任何包授权 | `DispatchPoolPage.tsx` 的十二项白名单字段可直接复用为教学案例视图 ＋ `dispatch/access.py:35-49` `grant_package_access(role="audit")`（**已有 audit 席位语义可承载导师只读授权**） |

---

## §5 增量候选（只写增量——供蔡工定范围用，非开工清单）

按「先补零页面的洞、再补分流语义、最后才动角色体系」排序：

| 序 | 候选 | 性质 | 复用面 | 新增量（估） |
|---|---|---|---|---|
| 1 | **④ 区域伙伴自助运营页**（`#partner/operations`） | **零角色新增**——R4 已在商业分层；页面消费既有 `GET /commercial/regional-partners` ＋ `GET /ops/todos`（**后者现为 admin-only，需开一个「按伙伴主体收敛」的只读变体**，否则越权） | `commercial/regional_service.py` 服务层已就位 | 1 个 renderer 页 ＋ 1 个只读端点（主体收敛） |
| 2 | **② 派单收件箱分流**（未响应／临期／已过期三态） | 纯前端分流——`GET /dispatch/offers/mine` 已现算 deadline | `MyOffersPage.tsx` ＋ `dispatch/routes.py` | 1 个前端分组（服务端零改动） |
| 3 | **③ 企业侧登录后落点**（注册→企业空间跳转 ＋ 免手填 `subject_key`） | 纯前端引导 ＋ 1 个「我的企业空间」查询端点 | `registration/routes.py` 返回体 ＋ `EnterpriseSpacePage.tsx` | 1 个前端跳转 ＋ 1 个只读端点 |
| 4 | **① 创业者「我的商机」页** | 纯前端——`GET /commercial/opportunities` 已按主体过滤 | `commercial/routes.py:250-273` ＋ `LeadPoolPage.tsx` 范式 | 1 个 renderer 页（服务端零改动） |
| 5 | **⑤ 导师训练队列页** | **需先解决角色载体**：候选＝在 R1–R4 之上加兼任（`role_assignments`）＋ 复用 `simulation` 场景面 ＋ `package_access(role="audit")` 只读授权；**必须先拍板角色落法，否则不得开工** | `simulation/routes.py` ＋ `dispatch/access.py` | 角色落法定后再估 |
| 6 | **学员侧训练入口**（创业者进 `#simulation`） | 权限口径放宽（现限 `fde_engineer` 及以上） | `useHashRoute.ts:200-231` ＋ `simulation/routes.py` | 1 处角色门调整 ＋ 鉴权面核对 |

---

## §6 「未查到」清单（诚实登记，不猜）

| # | 未查到 | 核验方式 |
|---|---|---|
| 1 | 独立的 `training` / `certification` 蓝图 | 蓝图注册唯一权威 `server/src/fde_api/app.py::_BLUEPRINT_SPECS` 无此两项 |
| 2 | 「导师」角色实体（页面／路由／API／枚举） | `grep -rn "导师" server/src desktop/src` ＝ 0 |
| 3 | 桌面端对 `regional-partners` 端点的任何消费 | `grep -rn "regional-partners" desktop/src` ＝ 0 |
| 4 | 仓内托管 `desktop/web-dist` 的静态服务器代码 | `server/src/fde_api/` 与 `desktop/src/main/` 无 `send_from_directory` / `static_folder` / `registerProtocol` |
| 5 | V1.0 §8 角色工作台的规格文档 | `docs/ecosystem-v1/` 下只有 `m1/`、`m2/`，无 `m3/`；`grep "角色工作台"` 全仓零命中 |
| 6 | 商业商机的前端页面 | `grep "opportunities"` 在 renderer 的命中全属诊断报告政策建议域 |

---

## §7 待蔡工拍板（**本轮不开工**）

| # | 事项 | 建议 |
|---|---|---|
| 1 | **M3 本轮切片范围**（§5 候选 1–6 选哪些） | 建议取候选 1 ＋ 2（均为「零角色新增、零新角色体系」的纯增量），先验证伙伴 web 优先路径 |
| 2 | **「导师」角色落法** | 建议复用 R1–R4 商业分层 ＋ `role_assignments` 兼任 ＋ `package_access(role="audit")` 只读；**不新增角色枚举**（红线 8） |
| 3 | **运营待办/简报能否开「伙伴主体收敛」只读变体** | 候选 1 的前置（现 `GET /api/v1/ops/todos` 为 admin-only；开变体须走既有可见性单一权威，不新建过滤体系） |
| 4 | **web 优先的仓外 Nginx 变更归属** | 仓内零静态托管代码 ⇒ vhost 变更属宿主动作，须与部署负责人对齐后再动 |
