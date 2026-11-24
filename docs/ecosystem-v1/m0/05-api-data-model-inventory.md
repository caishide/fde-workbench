# M0 API 与数据模型盘点

## 结构现测

Workbench 基线 `723479009d1b1f0c63744790ad3be3ed02bebbe1`，现测日 2026-11-23（UTC+8）。收割源为 [结构 JSON](../../audit/v3-workbench-inventory.json)、[路由 CSV](../../audit/v3-route-inventory.csv)、[数据表 CSV](../../audit/v3-database-inventory.csv)、[蓝图注册表](../../../server/src/fde_api/app.py#L29) 和 [API Catalog](../../../server/src/fde_api/control/api_catalog.py)。

| 结构面 | 数量或版本 | 当日检查 |
|---|---|---|
| 路由 | 563 | 同提交路由 CSV 解析后的数据行数，排除表头 |
| 蓝图 | 58 | AST 数 `_BLUEPRINT_SPECS` 元素，与 JSON 一致 |
| 表 | 172 | 同提交表 CSV 解析后的数据行数，排除表头 |
| 迁移 | 101，代码单头 `f2a4b6c8d0e2`，单根 `ebb003a5c3a8` | AST 读取 revision 与全部 down_revision，做集合差，无缺失父节点 |
| API Catalog | 98 | AST 数 `ENTRIES` 元素。Catalog 供受控工具消费，路由盘点见独立 CSV |
| 架构图 | 6 张候选 | `python -I -X utf8 scripts/audit/check_archify_diagram_freshness.py` 退出 0 |
| 本机活库迁移头 | `e2b4d6f8a0c2` | PostgreSQL `SELECT version_num FROM alembic_version`，`transaction_read_only=on` |

代码头至活库版本之间包含 `a3f5e7c9d1b3`（仓库绑定）、`b3e8c7d1a9f4`（Action 任务运行）、`c9e1f3a5b7d9`（补丁）、`e0c2e4a6b8d0`（仓库 CI 运行）及 `f2a4b6c8d0e2`（修正）。直接读取 Alembic 版本表完成活库头核对，容器内 `alembic current` 与活体部署三验未执行。M1 若需这些已合并能力，由部署负责人为选定环境核验并登记对应版本。

## §13.1 逐项映射

面向完整逐端点清单，按蓝图、模型路径和测试列筛选上列 CSV。下表给出服务、UI 和权限盘点的主要入口。状态以 [01 复用与缺口矩阵](01-module-reuse-gap-matrix.md) 及 [04 安全与授权](04-security-and-authorization-matrix.md) 为准。

| §13.1 项 | 数据、服务与 API 入口 | UI、权限和缺口 |
|---|---|---|
| 用户与组织 | `users`、`orgs`，`auth/`、`orgs/`、`users` 蓝图 | 登录及成员管理。服务端项目可见性与对象访问同源 |
| 商业角色和权益 | `commercial/models.py`、`commercial/routes.py` | 商业运营页，平台 admin 授予。M1 对账角色、权益、认证与资格 |
| 注册与审核 | `user_registrations`、`registration/routes.py` | 企业注册入口、验证与审核；伙伴端覆盖待核 |
| 企业主体和空间 | `commercial/` 企业空间服务 | `EnterpriseSpacePage`，绑定账号本人或 admin |
| 免费额度和诊断 | `commercial/` 配额、`lead_diagnostic_sessions`，`diagnostics/routes.py` | `PublicDiagnosticPage`、企业空间；配额和匿名诊断各自按业务口径审计 |
| 商机归属和保护 | 商机及归属服务在 `commercial/`，诊断认领在 `diagnostics/lead_routes.py` | `LeadPoolPage`、`CommercialOpsPage`；跨入口撞单规则待业务裁定 |
| 区域伙伴与售卖 | `commercial/` 区域伙伴及售卖闸 | 运营可见，正式签约依 GAP-12 |
| 科目与结算 | `delivery_settlements`、`dispatch_settlement_allocations`、`dispatch_rule_versions`，`dispatch/settlements.py`、`commercial/ledger_service.py` | `MySettlementsPage` 显示本人。空缺与兼任沿已有模型，DIFF-09 约束首签 |
| 课程和培训 | 商业培训记录与费用可复用 | 完整课程、进度和作业能力见 01 |
| 模拟和认证 | `simulation/` 与 `commercial/` 认证记录 | `SimulationLabPage`；认证及资格由授权人员落地 |
| 供给池及派单 | `dispatch/models.py`、`dispatch/routes.py`、`dispatch/admin_routes.py` | 供给池与接单控制台，指派、接受、可见性分别授权 |
| 项目、报价、合同和支付 | `projects/`、`solutions/`、`plans/`、`commercial/`、`dispatch/` | 项目商业面。真实签约、实收与支付链按 M1 样单验证 |
| Agent、Workflow、Jobs | `agents/`、`workflows/`、`jobs/`，取 `control/api_catalog.py` | Agent Console、Workflow Console，发起与外效经既有确认链 |
| Evidence、Gate、Handover | 证据、项目门禁与 `handover/`；存储证据指针与指纹 | 项目证据页与封包。采纳、裁定和登记由人工驱动 |
| 指标与审计 | `metrics/`、`operation_events` | `MetricsReportPage`；M0 经营指标以核实的聚合与证据为准 |
| Ontology 双仓 | `integrations/ontology_client.py`、`ontology_mock.py`、`integrations/routes.py` | 绑定及交付 TrustBoard，服务间身份与版本锁定见下节 |
| Paperclip 映射 | v1.1a 修订三约定 P0 后置 | 独立栈验证价值后再评审外部映射与派发状态 |

## 双仓契约

Fde-Ontology `73e6d9ccc40407b33c71633e65fd8bfbfab23290`，主检出干净并与远端一致。`CURRENT.md` §2 负责阶段和契约指针，版本以该提交 `docs/v3.3/m1/ontology-api-spec.yaml` 的 `info.version` 为准，实读为 `1.3.8-af2`（OpenAPI 3.1.0）。`CURRENT.md` §2 的 `v1.3.6-af0` 属较早记录。

| 契约维度 | 已查文本证据 | 当前覆盖边界 |
|---|---|---|
| 客户端、Mock 与服务 | Workbench `integrations/ontology_client.py`、`ontology_mock.py`、`server/tests/test_m5_wp2_client_mock_parity.py`；Ontology `ontology-service/tests/test_m4_1_contract_parity.py` | 前者核查影响分析、治理摘要与对账形状。后者检查路由双向一致及错误码映射，测试定义已查阅 |
| 版本与 ETag | Ontology OpenAPI、Workbench `server/tests/test_ontology_client.py`、`test_ontology_bindings.py` | 选定试点环境的实际版本需随部署验证登记 |
| 错误码和幂等 | OpenAPI 头部声明签名上下文、幂等头和 trace。客户端/Mock 套件含对账请求幂等键、透传字段及治理查询参数 | 跨仓 Golden Scenario 全链回执待补，见 [BLOCKED](BLOCKED.md) |

对照阅读了现有测试，M0 无活体部署验证，也无双仓端到端新回执。
