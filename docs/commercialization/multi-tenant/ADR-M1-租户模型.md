# ADR-M1 多租户模型（甲路线：组织级隔离，复用既有成员模型）

> **状态**：已拍板（任务书 v1.2 §11-1/§11-2，2026-11-10 OWNER 签署）→ 本 ADR 将拍板落成书面裁决与实施语义 ｜ **轮次**：M0 ｜ **上游**：任务书 §4 / 评估文档 §2.B、§5
> **实施轮**：M1 ｜ **本 ADR 零代码改动**

## 1. 裁决

采用**甲路线**：`orgs` 独立表（类型 `enterprise`/`internal`）+ `projects.org_id` 推导 + 复用 `project_members`（成员可见性即隔离边界）+ 应用层统一访问入口。**不启用 PG RLS**。乙路线（全量 tenant_id + RLS）保留为规模化演进，触发条件见 §6。

## 2. 真实代码基线（M0 现测，06c1dd5）

| 事实 | 证据 |
|---|---|
| 全仓零租户概念：无 `org`/`tenant`/RLS/`CREATE POLICY` 生产代码 | 全 src grep 零命中（评估文档同结论，复测确认） |
| `users` 10 列，无归属维度 | `auth/models.py:80`（id/username/display_name/role/password_hash/must_change_password/is_active/auth_version/created_at/updated_at） |
| 可见性过滤是 Python 全表扫描，仅覆盖 `Project` | `projects/permissions.py`（55 行，`select(Project)` 后逐条判；`visible_project_ids` 精确消费 5 域） |
| JWT 7 claim 无租户维度 | `auth/tokens.py:14-22` |
| 企业空间已复用 projects 权限模型（G6 先例） | `commercial/enterprise_service.py`（`add_project_member` 路径 + viewer 成员），ADR-010 §1-8② |
| 企业主体键已存在（PK=规范化 USCC） | `enterprise_quota_subjects`（ADR-004 §1.1，mod-31 校验位） |
| 存量演示数据：1 开发库（2 演示项目） | 活库现测（见容量实测报告 §3） |

## 3. 目标数据模型（M1 实施语义，非本轮代码）

```
orgs（新表）
  id            uuid pk
  org_type      ∈ {enterprise, internal}        -- internal=平台自有（承载存量回填与平台侧项目）
  name          varchar unique                  -- 企业代号化名（客户真实名称不入库，红线 2）
  subject_key   varchar null unique             -- 可选挂 G6 企业主体键（USCC），1 org : 1 subject_key
  created_at / updated_at / created_by_user_id

users.org_id        uuid null fk→orgs           -- NULL=平台身份（ADR-M2 §4）
projects.org_id     uuid null fk→orgs           -- 存量回填到 internal org 后收 NOT NULL（评估后再定；
                                                   先 nullable + 回填，避免一次迁移两步语义）
operation_events.org_id  uuid null fk→orgs      -- NULL=平台级事件（与既有 nullable project_id 同构：
                                                   operation_events.project_id 本就可空）
```

- **零新建平行权限表**（G6 红线复述）：企业成员进项目仍走 `add_project_member`；org 只是**归属与推导维度**，不是第二套 ACL。
- **项目域 83 张表**（50 直连 + 33 传递，口径见盘点表维度 1）不逐表加列——经 `projects.org_id` 推导。
- **迁移纪律**：additive 单迁移、up/down 对称；回填幂等（`UPDATE projects SET org_id=(internal org) WHERE org_id IS NULL`）；`cli.py` 种子补 internal org；`test_migrations` HEAD 断言 +61→62 rev。
- **推导语义**：`org_of(project) = projects.org_id`；`orgs_of(user) = [users.org_id] + org_ids_of(membership)`——成员可见性仍由 `project_members` 决定，org 仅决定**归属命名空间**与统计口径，不单独授权（防第二权限体系）。

## 4. org_id=NULL 语义（拍板 §11-8 复述）

NULL = **平台级身份不受 org 限制**（admin/交付咨询）。跨 org 读取/写入**须留痕**（operation_events org_id=NULL 但 target 归属 org 可从对象推导）。存量回归面最小化是本拍板的直接动因（现测收集 2716 用例，102 个测试文件直接构造 `User(...)`——先验 2333 用例的现测修正值）。M3b 端点默认拒绝时对平台身份**显式白名单放行并留痕**，不做隐式旁路。

## 5. 被否决的备选（留档防重提）

| 备选 | 否决理由 |
|---|---|
| 乙：全量 tenant_id + PG RLS | 评估文档 15～30× / 660+ 判断点；RLS 与连接池、并行跑测（每 worker 独立库/schema）的兼容成本未评估；甲路线数据结构是其直接前置，不白做 |
| A：每客户独立 compose 栈 | O(n) 证书/值守/备份运维面；商用平台目标是单实例多主体，物理隔离路线已被拍板排除 |
| A′：共享容器 + 每租户独立 database | 请求级 session 路由改造 ≈ B 的复杂度换 A 的一半资源（评估文档 §2.A′），风险最高 |
| `users.role` 承载商业分层 | ADR-001 正交裁决（红线 6）；`commercial_entitlements.commercial_role` 已是 R1–R4 权威承载（G1 已落） |

## 6. 乙路线演进触发条件（任务书 §4.2 复述，满足其一即启动乙升级设计）

1. 付费企业 > 20 家；
2. 出现合规级隔离要求（客户合同要求数据物理/行级隔离）；
3. 单实例查询性能因跨 org 扫描劣化（容量实测报告 §5 的监控指标持续恶化）。

触发时按评估文档 §2.B 的 660+ 点位清单执行；`orgs`/`org_id`/归属数据全部直接复用。

## 7. 对下游的硬约束（承接任务书 §11-1 列）

- M1 建 `orgs`；M3a 把 `projects/permissions.py` 改为**带 org 维度的 SQL 下推**（禁止再加一层 Python 过滤——红线 10）；M3b 逐端点加 org 校验（以盘点表为唯一清单）。
- **热点闸**：隔离逻辑不得写进 `projects/service.py`（现测 1945 行，闸 1946 只许变小）；建议落点 = `projects/` 包内新模块（如 `orgs/` 或 `projects/org_scope.py`），M1 实施时定名并保持单一入口。
- 现服务器不扩容先试点（拍板 §11-5）；W0 演示服务器零改动（拍板 §11-6、红线 R8）。
