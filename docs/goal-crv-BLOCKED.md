# goal-crv BLOCKED（待裁决与留痕清单）

> 任务书 §2：拿不准的写这里，跳过继续做别的，随交付提交。收口轮随收口 PR 提交（空的写「无」）。

## 1 部分覆盖域留痕（§6：部分覆盖域全循环 ≤2 且须 BLOCKED 留痕）

### 1.1 r7 桌面端＝部分覆盖（登记于 2026-11-13）

- **事实**：`desktop/src` 共 190 文件 / 40,361 行——单域逐行读档远超 CreateWorkflow 上界（4 片×12 文件）与主会话直审容量；任务书 §3 r7 行审读面为「入口锚点，非穷举」且以 Electron 安全面为核心。
- **裁定（执行者按任务书裁量）**：r7 主读面收缩为「主进程安全面＋shared 契约面＋安全关键 renderer 面」＝**19 文件逐行读档**（main/ 全部 10＋shared/ 全部 3＋fde-web-bridge＋PublicDiagnosticPage＋AgentsConsole 等）——Electron 安全边界（CSP/preload/contextIsolation/协议注册/spawn/auth-ipc/api-ipc 双桥/consent 硬闸/终审队列）100% 逐行覆盖；**renderer 业务页面（~169 文件：research/help/projects/templates/dispatch 表单页等）降为抽查档**，未逐行读。
- **影响**：r7 覆盖声明将如实列三档（逐行读 19＋抽查若干＋没读＝业务页面），本域记「部分覆盖」1/2 名额；收口轮误报率与核锚照常覆盖已登记发现。
- **消解条件**：若蔡工裁定 renderer 业务页面须逐行审查，另立 r7b 增补轮（预计 2-3 轮工作流）。

## 2 needs-decision 清单（随各轮登记汇总）

| # | 来源 | 事项 |
|---|---|---|
| 1 | QR-041（r3） | 留资联系方式口径二选一：留资行存明文（mask_pii 开关）vs 库存占位符（改两处书面声明＋回访取号替代方案） |
| 2 | QR-042（r3） | 个保法 30 天留存期执行方案（懒检查/后台处置/挂账改 docstring）——若属 D-3 轻部署运维待办可降 P2 |
| 3 | QR-067（r4） | admin 蓝图四个 GET 读面：补 admin 门 vs 成文「有意公开」＋钉（M3b R1 红线角度判级存疑） |
| 4 | QR-073（r5） | 宿主通道盘符逃逸暴露面：部署态 host_channel vs host_poll 形态核证（须读部署态 server/.env 两键——禁区，留蔡工） |
| 5 | r6 §5-1 | SNS 回调关闭态 403 vs 仓库 404 纪律（机器对机器语义等价；收口须换代 test_sns_route_disabled_403 钉） |
| 6 | QR-133（r8） | redaction_review 事件账携带企业名明文（词典确证命中名＋疑似名原文）vs 红线「数据库只存代号」：复核闸功能需要名字 vs 红线字面——指纹化复核清单（UI 经本地词典反解）or 红线例外登记（测试钉现断言 name 在场＝既有设计，换代须随拍板） |
| 7 | QR-134（r8） | T-A2 脱敏面覆盖不对称：presurvey 录入卡自由文本零脱敏（models docstring 豁免声明「不触碰 S0–S2 红线」vs 同类别 translator 三道闸）＋update_analysis 人工编辑不复扫（已脱敏草稿可经编辑重引入真名，confirm 闸只看 AI 阶段清单）——录入卡豁免成立则登记 AGENTS；编辑面至少补输出端扫描 |

## 3 结构性挂账引用（不立 QR，引用既有编号）

CR-006（DSH 记账 needs-decision）／CR-016（outbox failure hooks 4 类——r6 现核确认精确吻合）／storage-migrate-layout 生产执行待 OWNER／M7 ADR §7 三问／split_rules 填数待 OWNER／D-5 免费漏斗／三道业务闸未激活＝授权层。
