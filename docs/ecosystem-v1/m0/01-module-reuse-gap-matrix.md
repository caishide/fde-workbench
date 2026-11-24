# M0 十三域复用与缺口矩阵

以 V1.0 §15 M0.2 为准，将 `registration/users/orgs` 拆为「注册」及「主体与组织」，得到十三域。§13.1 的详细数据、路由及界面映射另见 [05](05-api-data-model-inventory.md)。收割源为 [商业阶段状态](../../commercialization/phase-status.md)、[路由清单](../../audit/v3-route-inventory.csv)、[表清单](../../audit/v3-database-inventory.csv)和 Workbench `72347900` 源码。下表测试文件为复核指针，历史工程回执按原日期使用。

| 域 | 裁决 | 复用证据和验证锚点 | 扩展或新增边界 |
|---|---|---|---|
| 商业化 | `partial` | `commercial/billing_service.py:409`，商业阶段状态 G1–G6，`test_commercial_entitlements.py` | 地区售卖及首单分账待决。课程目录、学习进度及作业见 M4 |
| 注册 | `partial` | `registration/routes.py:121`，`test_registration_surface.py` | 复用发信验证和审核。分角色登记当期部署闸态与网页可达性 |
| 用户／组织 | `implemented` | `orgs/models.py:50`、`test_visibility_parity.py`、`test_cross_tenant_isolation.py` | 企业与伙伴团队映射先审查既有组织模型 |
| 派单 | `implemented` | `dispatch/routes.py:136`、`:605`，`test_dispatch_p0.py`、`test_dispatch_five_seat_baseline.py` | 复用供给池、派单、接单和结算。业务披露经 DIFF-09 对齐 |
| 诊断／引导／访谈 | `partial` | `diagnostics/routes.py:65`、`diagnostics/lead_routes.py:82`、`discovery/service.py:87`，`test_diagnostics_mvp.py` | 统一业务口径下的渠道测量和真实经营聚合待证 |
| 模拟训练 | `implemented` | `simulation/models.py:99`、`test_simulation_e2e.py`、V3.2 G8 与 G9 文件 | 模拟评估作为学习和认证输入。导师、作业与课程更新另审 |
| Agent／Workflow／Jobs | `implemented` | `workflows/definition_service.py:133`、`agents/service.py:975`、`test_workflow_runs.py` | M2 复用运行时、事件和定时任务挂岗位卡。涉联网按 04 |
| 项目／方案／计划／质检 | `implemented` | `workbench/models.py:74`、`solutions/models.py:12`、`plans/models.py:31`、`quality/service.py:75`，11-17 贯通回执 | M1 样单核验报价、授权签约、回款和验收证据 |
| 证据／门禁／封包 | `implemented` | `evidence/routes.py:24`、`handover/models.py:36`、`test_handover_packages.py`，贯通报告 §7 | 复用原件指针、指纹和人工裁决。试点补真实验收 |
| 发信 | `partial` | `mailing/channel.py`、`test_mailing_smtp.py`、`test_mailing_policy.py` | 复用审批、退订和通道。实际邮件与法务证据在授权场次登记 |
| 指标 | `partial` | `metrics/service.py:68`、`test_metrics_report.py`、R4 离线规格 | 企业询盘、首笔收入、逐单经济性与复跑需要真实数据，R4b 场次见优化 E-04 |
| Ontology／双仓集成 | `partial` | `integrations/ontology_client.py`、`ontology_mock.py`、`test_m5_wp2_client_mock_parity.py`、[05 双仓契约](05-api-data-model-inventory.md) | 试点环境和完整双仓证据待核 |
| 桌面角色入口 | `partial` | `desktop/src/renderer/src/App.tsx`、`CommercialOpsPage.tsx`、`EnterpriseSpacePage.tsx`、`MySettlementsPage.tsx` | 复用桌面与 web 代理。M3 核对伙伴待办、角色自助和手机适配 |

`implemented` 表示基线有相应实现及已有验证入口。`partial` 表示目标覆盖仍有缺口。以下候选以 `documented-only`、`blocked`、`not-found` 或 `in-progress` 登记具体边界。

## §13.2 候选预审

| 候选 | 状态 | 复用判断及待证条件 |
|---|---|---|
| `partner_applications` | `blocked` | 先用 `user_registrations` 和商业审核验申请旅程，确认现有模型无法表达的状态 |
| `learning_courses`／`learning_modules`／`learning_enrollments` | `not-found` | 基线定向检查未发现课程、章节、学习路径、学员进度的模型、迁移、API 或页面。`commercial/models.py:169` 的培训权益可作为准入条件 |
| `learning_assignments`／`learning_reviews` | `documented-only` | 先验证既有任务和 SimulationLab 能否承载作业及反馈 |
| `mentor_assignments` | `documented-only` | 先证明持续匹配、可见性和责任记录的业务需求 |
| `partner_team_memberships` | `blocked` | 先审查 org 对区域团队、跨区成员和权限关系的覆盖 |
| `regional_operating_plans` | `documented-only` | 先以既有项目与任务试行区域计划 |
| 两种 Paperclip 外部映射／派发候选 | `blocked` | M2 稳定后进行独立栈 P0。评估现有 Outbox 状态承载能力 |
| `partner_activity_events` | `documented-only` | 先用 `operation_events` 验证主体、审计和聚合 |
| 跨仓 Golden Scenario 全链回执 | `in-progress` | 已检查双方契约测试定义，试点场次尚待回执 |

新增表评审的十项预答统一见下列准入条件。现阶段各候选均无建表授权。

1. 现有表不足须附失败场景和复用路径，当前优先验证上述候选。
2. 租户沿用已有 org 边界。课程目录是否平台级须由产品确认。
3. 主体关联须复用已有组织、用户或项目主键，并核对删除语义。
4. 状态机由业务确认允许迁移及终态，随后给出契约。
5. 幂等键按同主体、同业务动作定域，须验重复提交行为。
6. 审计沿用事件记录路径，明确 actor、目标、org 及时间。
7. 保留期由合规决定，真实原件遵守本地真相层边界。
8. 删除或归档须明确历史证据与结算记录的保留方式。
9. 权限复用服务端权威，覆盖跨组织和越权负例。
10. 迁移须有向后兼容、回滚和数据校验依据，再进入单独实施评审。
