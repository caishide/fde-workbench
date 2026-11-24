# M0 安全与授权矩阵

收割源为 [AGENTS.md](../../../AGENTS.md)、[多客户商业化进度与验收](../../commercialization/phase-status.md)、[商业化缺口登记](../../commercialization/00-gap-register.md)、任务书 §14 及现有测试。表中测试用于定位既有防御性回归。本轮核对文本与配置约束，实际试点执行由对应负责人授权。

| 边界 | 允许方与限制 | 测试与检查入口 | 遗留 |
|---|---|---|---|
| 跨企业项目可见性 | 项目成员及既有角色规则决定授权，列表和详情共用权威。企业身份按服务端当前归属验权 | `projects/permissions.py`、`test_visibility_parity.py`、`test_cross_tenant_isolation.py` | M1 回读角色组合和跨视角事件 |
| 平台管理写入 | 平台归属与 AI 能力分别判断，授权人员操作。跨企业写入按事件纪律留痕 | `control/access.py`、`test_m3b_batch1a_control_plane.py`、`test_m3b_batch2_commercial.py` | 伙伴团队和区域权限逐一核验 |
| 企业客户名单 | 企业确认前禁止区域伙伴导出，平台按书面授权托管 | M7-1 阶段验收、`test_commercial_regional_partners.py` | 确认同企业边界与区域归属变更 |
| 公网注册、诊断写面 | 部署闸关闭时返回 404。验证令牌只存指纹。诊断限流默认 fail-closed，注册要求公网部署显式设 `FDE_REGISTRATION_RATE_FAIL_CLOSED=1` | `test_registration_surface.py`、`test_diagnostics_mvp.py`、AGENTS 红线 | 只读提取选定环境的闸态及限流配置证据 |
| 发信与机器回调 | SMTP 和 SES 互斥。机器回调的关闭态语义沿既有登记。真实邮件服从发信批准及退订规则 | `test_mailing_ses.py`、`test_mailing_smtp.py`、`test_mailing_policy.py` | 真实 SMTP、退订与合规覆盖须登记 |
| 宿主通道与出站 | 仅限已授权的单个 run 和代号化数据。生产白名单扩张由蔡工批准 | `test_host_egress_proxy.py`、`test_agent_traceability.py`、AGENTS 出站红线 | M2 逐项登记用途、目的域、数据与责任人 |
| 证据、门禁和封包 | 原件本地保管，登记指针和 sha256。人工验收，受控变更及留痕 | `test_handover_packages.py`、贯通报告及桌面写安全验收 | 真单需取得人工裁定和回款证据 |
| 诊断评测污染 | 答案与生成器、检索和知识种子隔离，展示例外须标记并隔离路径 | `test_diagnostic_eval_contamination.py` | M2 接线前确认语料边界和数据留存 |
| 正式签约、扣费与结算 | 业务、财务及法务分别按既有闸审批。收款回填和已付销账只证明记录状态，实际资金动作以逐笔授权与凭证为准 | `test_dispatch_five_seat_baseline.py`、`test_f_line_t6_tax_invoice_reconciliation.py`、[ADR-007](../../commercialization/decisions/ADR-007-human-confirmation-default.md)、ADR-011、GAP-12 | 签约前对齐 DIFF-09，区域正式售卖前补签并批准开闸 |
| AI run 发起和外部影响 | 人提交并确认受控动作，AI 仅提议与生成候选 | `test_ai_run_proposal.py`、`control/api_catalog.py` | M2 新岗位逐项审查 API、数据范围、预算与权限 |

## M2 外部接触预审

- 增长、招生和行业调研先提交来源及目的域清单。收录用途和保留期须经负责人确认。
- 客户运营和区域触达由人审定具体收件人与内容。外部发送量、退订、渠道合法性纳入审批。
- 交付和技术运营使用既有权限、队列与审计。任何跨租户、白名单、模型或第三方凭据扩张均需独立裁决。
- 岗位卡逐项记录调用对象、可见数据、权限、费用上限、人工复核环节和审批人。相关前置见 [06 决策登记](06-owner-legal-decision-register.md)。
