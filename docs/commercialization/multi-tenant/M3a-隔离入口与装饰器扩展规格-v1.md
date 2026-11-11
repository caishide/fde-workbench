# M3a 隔离入口与装饰器扩展规格 v1

> **轮次**：多客户工作平台 M 线 M3a（统一隔离入口）＋ M3c（越权套件骨架）
> **依据**：任务书 §7-M3、§11-1/§11-8 拍板、ADR-M1（租户模型）、ADR-M2（主体-角色映射）、ADR-M3 §2（施工规格要求）、《全局面盘点表》（M3b 唯一施工清单）
> **地位**：**规格先行件**——ADR-M3 §2.4 要求「装饰器批量扩展行为规格先行」，本文件入库后方可动 M3a 代码；M3b 每批 PR 必须引用本文件
> **状态**：v1（2026-11-11）｜**留痕可推翻**：OWNER 拍板后可改版本，M3b 各批须同步

## 0. 一句话语义

**企业只见本企业**：可见性由「成员关系」授权、由「org 归属」**收敛**——企业身份用户看不到别的企业 org 下的项目；平台身份（`org_id=NULL`）不受 org 限制但**跨 org 动作必须留痕**。

## 1. org 语义三态（单一权威：`fde_api/orgs/isolation.py`）

| 态 | 判定 | org 可见范围 | 说明 |
|---|---|---|---|
| **平台身份** | `users.org_id IS NULL` | 不限（跨 org 可见） | admin／交付咨询／交付者／创始人——**存量用户全部落在这一态**（M1 拍板 §11-8「存量用户不回填」⇒ 存量回归面零变化） |
| **企业身份** | `users.org_id = X` | `{X}` ＋ `{INTERNAL_ORG_ID}` ＋ 项目 `org_id IS NULL` 的平台级行 | 企业自有账号（M2 企业注册入口建号即建 org，M2 轮拍板①） |
| **平台内部 org** | `orgs.org_type='internal'` | — | **平台自有的项目归属桶**：平台身份立项的项目落此处（`org_scope.py` 归属戳兜底），是「平台立项 → 企业账号作 viewer 成员」既有通路（G6 ADR-010）的落点，**不在企业间隔离边界内** |

**边界为什么是「企业 org 之间」而不是「一切 org 之间」**：G6 既有交付链路是「staff 立项（平台身份 ⇒ 项目落 internal org）→ 企业账号经既有 `add_project_member` 加为 viewer 成员」。若把 internal org 排除在企业身份可见范围外，该链路当场断（G6 企业空间的交付项目清单为空）。internal org 桶内**可能混装多家企业**——这是已知缺口，本轮**不掩盖**：登记进《全局面盘点表》「待 M0 补充」节，消解路径＝M5 企业空间把企业自建项目归属从 internal 迁到企业 org（不靠本轮猜改）。

## 2. 统一入口的权威判定（SQL 下推）

**唯一权威**：`fde_api/projects/permissions.py`

```
visible(user, p)  ⇔  user.is_active
                   ∧ ( p.leader_user_id = user.id ∧ role_at_least(user.role,'project_lead')
                      ∨ ∃ member(p, user) )
                   ∧ org_scope_allows(user, p.org_id)
```

`org_scope_allows(user, org_id)`：

| actor | 判定 |
|---|---|
| `user.role == 'admin'` | 恒真（平台能力，沿用既有语义） |
| `user.org_id IS NULL` | 恒真（平台身份不受 org 限制，§11-8 拍板） |
| 企业身份（`user.org_id = X`） | `org_id IS NULL`（平台级行）∨ `org_id = X`（本企业）∨ `org_id = INTERNAL_ORG_ID`（平台立项桶） |

**SQL 下推要求**（红线 10「不在 SQL 后再加一层 Python 过滤」）：

- 可见集：`SELECT projects.id WHERE (leader 谓词 OR EXISTS(project_members …)) AND (org 谓词)`；
- **org 谓词恒可下推为 SQL**（`projects.org_id` 列存在，索引 `ix_projects_org_id` 在位）⇒ 不得写成「先取全量再 Python 过滤」；
- 对象级入口 `project_access(user, project)` 与列表级 `visible_project_ids(session, user)` **必须同语义**（否则详情 403 / 列表可见的幽灵行——`test_visibility_parity.py` 对账钉的老坑复发）。

**兼容面**：`visible_project_ids` 有 5 个消费域（agents／handover／meetings／transcripts／projects）＋ `project_access` 广布 38 个文件——**函数签名与调用形态零改动**（消费方不改一行代码即通过＝改造成功的验收判据）。

## 3. 装饰器扩展规格（ADR-M3 §2.4 强制六项）

### 3.1 org 校验发生在哪一层：**服务层**（不在装饰器）

理由：org 归属是**被作用资源**的属性，装饰器在进入视图前不知道资源属于哪个 org；把 org 判定塞进装饰器要么猜（按 URL 前缀猜 org，错），要么让装饰器去查库（每个装饰器一次额外查询＋把资源解析责任劈成两半）。故：

- **装饰器层**只做：身份解析（既有 `require_auth`）＋ **org 上下文注入**（`g.current_user_org_id`）＋ 平台身份的**显式白名单声明**（既有 `require_role('admin')` 即平台白名单形态）；
- **服务层**做：解析资源 → 取 `resource.org_id`（或经项目推导）→ 调 `isolation.org_scope_allows(...)` → 不通过则抛域错误。

### 3.2 默认拒绝语义：**fail-closed**

- 新改造（M3b）的端点：**默认拒绝**跨 org 访问——不写「放行」就是拒绝；
- org 判定失败**不得**退化为「按老逻辑放行」；
- **存量端点在本轮零改动**（盘点表未登记的面不得擅改——红线 4）；M3b 逐端点销号时才切换到 org 校验。

### 3.3 平台身份白名单的**显式形态**

| 形态 | 表达 | 语义 |
|---|---|---|
| 角色白名单 | `require_role('admin')` | 平台管理面——既有语义不变（admin 恒可见全部项目） |
| 身份白名单 | `user.org_id IS NULL`（`isolation.is_platform_identity`） | 平台身份不受 org 限制——**白名单是「不设限」而非「额外授权」**，不制造第二套权限体系（红线 8） |
| 显式代操作 | M3b 端点内的「admin 代他人操作」分支 | 必须写明代操作对象＋留痕（见 §3.4），**不得**退化为「admin 全通过」 |

### 3.4 跨 org 动作留痕点

跨 org 的**写动作**（含 admin 代操作、成员跨企业授予、配置位代改）必须落 `operation_events`，且：

- `operation_events.org_id` 取**被作用资源的 org**（M1 已实现：事件维度从 project 推导；平台级事件为 NULL）；
- 事件 `operation` 名带 `cross_org_` 前缀（批次销号时逐端点登记，**闭集见 §3.5**）；
- **只存代号与指纹**（客户真实资料不入事件——红线 2）。

### 3.5 失败码闭集

跨 org 拒绝**只用这两个码**，不得自造：

| 码 | HTTP | 语义 |
|---|---|---|
| `forbidden` | 403 | 资源在 actor 可见域内但无权操作（沿用既有项目域语义） |
| `not_found` | 404 | 资源不存在**或**跨 org 不可见——**不确认面存在**（与部署闸 fail-closed 404 同款纪律） |

**默认口径**：跨 org 命中 ⇒ **404 `not_found`**（不确认资源存在）；同 org 无权操作 ⇒ 403 `forbidden`（沿用既有语义，避免推翻既有断言）。既有项目域行为**本轮不变**——跨 org 判定只在 M3b 销号的端点上生效。

### 3.6 逐批验证方法（变异用例先红后绿）

每批 M3b 必须同时交付：

1. **该批越权用例**（企业 A 令牌打企业 B 资源 ⇒ 404/403）——**与端点改造同一 PR**（红线 3）；
2. **摘除式变异验证**：把该批新增的 org 判定摘掉 ⇒ 该批越权用例**必须转红** ⇒ 还原 ⇒ 复绿（判别力验收——测例本身要验收，家族教训）；
3. 越权用例**进 CI**；未进 CI 不得申报该批销号。

## 4. 令牌口径（JWT）

| 项 | 口径 |
|---|---|
| claim 数 | 7 → **8**，新增 `org_id`（可空；空 = 平台身份） |
| 解码校验 | **在场性**校验：`org_id` claim 必须**在场**（平台身份取 `null`，合法）；**缺该 claim 的旧令牌一律 401**（fail-closed 选择） |
| **实现坑（已踩）** | PyJWT 的 `options.require` 判定是「`payload.get(claim) is None` ⇒ 缺 claim」——平台身份的 `org_id` 合法值恰是 `null`，**放进 `require` 列表会把全部平台身份令牌判死**（本轮实测 74 例 401 误杀）。故 `org_id` **不进 require 列表**，改为解码后显式判「在场 ＋ 类型（None/str）」 |
| 上线代价 | 部署后存量会话**至多 15 分钟内自然失效**（`access_token_minutes=15`），用户需重新登录 |
| **授权权威** | org 判定**一律读库**（`users.org_id`）——**不信令牌里的 claim**。理由：令牌是 15 分钟快照，用户归属可在会话期内变更；拿 claim 当授权依据＝陈旧令牌越权。claim 只作**追溯/跨服务传递**用途 |
| 签发点 | `auth/tokens.py::issue_access_token`（登录、刷新、`control/api_actions.py` 的 API-action 票据同源） |

## 5. 本轮交付边界（M3a＋M3c）

| 项 | 本轮 | 后续 |
|---|---|---|
| org 语义单一入口（`orgs/isolation.py`） | ✅ | — |
| 可见性 SQL 下推＋org 谓词（列表级＋对象级） | ✅ | — |
| JWT `org_id` claim（8 claim fail-closed） | ✅ | — |
| 装饰器上下文注入（`g.current_user_org_id`） | ✅ | — |
| 越权套件骨架（双 org 夹具＋7 域用例） | ✅（未销号者 `xfail(strict=True)`） | M3b 逐批摘除 |
| 端点级 org 校验（写端点销号） | ❌ | M3b ①②③④ 四批 |
| 全局表读面收敛（63 表 R3 读过滤） | ❌ | M3b 批次内逐端点 |
| Redis／存储／队列／AI 预算主体维度 | ❌ | M4 |

**xfail(strict=True) 的用意**：套件骨架里「尚未改造」的越权用例挂 `xfail(strict=True)`——**改造完成即 XPASS ⇒ 严格模式判失败 ⇒ 强制摘标记**。这把「销号」从人工纪律变成机械闸（不进 CI 不许合并、红了不许合并、标记忘了摘也会红）。

## 6. 红线对照

| 红线 | 本轮落法 |
|---|---|
| 密钥/口令/客户真实资料不入库 | 事件只存代号与指纹；org 维度不含客户明文 |
| 不启用 PG RLS | 隔离在应用层 SQL 谓词，甲路线不变 |
| 不建第二套权限体系/审计体系 | org 只是**归属维度**；授权仍归 `project_members`＋既有角色尺；审计仍归 `operation_events` |
| 企业空间复用 `add_project_member` | 成员可见性单一权威不动；本轮只加 org 收敛谓词 |
| `org_id=NULL` 平台身份语义 | 原样承继（§11-8 拍板），不做「平台身份也入 internal org」的改写 |
| 热点文件预算闸 | 隔离逻辑**不进** `projects/service.py`（新增 `orgs/isolation.py`）；`projects/permissions.py` 改动面 ≤ 数十行 |
| mypy 279 只许减不许增 | 新模块零 `Any` 泄漏，官方闸复跑核对 |
| 盘点表未登记的面不得擅改 | 本轮只改盘点表**已登记**的统一入口面；端点级改造留 M3b |
| 不执行生产变更 | 部署动作＝本仓 compose 栈重建与复验，无生产环境变更 |
