# G6 浏览器 UI 回归报告

> 方法：web-gui-tester（纯黑盒 GUI 驱动 + 截图/只读 DOM 双证据）。
> 被测对象：真实 renderer（`desktop/src/renderer`）经 `desktop/gui-harness` 提供的
> dev-only 桥注入后，在真实 Chromium 里点真实交互；后端是 compose 里的真实服务。
> 运行方式与坑位见 `.agents/skills/fde-gui-regression/SKILL.md`。

## 环境准备（与正式测试分离）

1. 起 harness dev server（`127.0.0.1:5199`），注入 `window.fde` 等价桥 + 同源 `/api` 代理；
2. 后端 `127.0.0.1:8010` 已在跑（`/api/v1/health/ready` → database ok / redis ok）；
3. 播下**合成** fixture：用户 `gui.regression`、项目 `FDE-GUI-REGRESSION`、
   预调研文件 + available 版本、一条 `analysis_state=ready` / `status=draft` 的指引。
   客户真实项目（somwyn 等）全程未被写入或修改。

> 说明：fixture 项目通过真实服务层 `create_project` 建成——渲染层会校验
> `template_snapshot`，手写空快照会让页面直接判「项目详情加载失败」，那样测的就不是界面了。

## 正式测试结果：11/11 通过

| # | 测试点 | 结果 | 证据 |
|---|---|---|---|
| 1 | 登录（真实表单提交） | PASS | `02-after-login.png` |
| 2 | 进入项目详情 | PASS | `04-project-detail.png` |
| 3 | 指引链-挂载认领入口（「查看预调研分析」出现） | PASS | `05-guidance-card.png` |
| 4 | **指引链-只读 draft 态出现「确认并用于项目指引」**（R11 事故防线） | PASS | `06-guidance-review-readonly.png` / `07-confirm-button-in-readonly.png` |
| 5 | 只读态**没有**「保存修改」 | PASS | `08-readonly-no-save.png` |
| 6 | 编辑态才有「保存修改」（两态互斥） | PASS | `09-editing-mode.png` |
| 7 | 集成桥页可达 | PASS | `10-bridge-page.png` |
| 8 | 集成桥三按钮齐备（立即采集/刷新/重新投影） | PASS | `11-bridge-buttons.png` |
| 9 | 采集触发有用户可见反馈 | PASS | `12-bridge-after-capture.png` |
| 10 | 刷新无异常 | PASS | `13-bridge-after-refresh.png` |
| 11 | 无应用级控制台错误 | PASS | — |

截图证据在 `desktop/gui-harness/screenshots/`（本地留证，已 gitignore：画面含本机路径与项目代号）。

### 关键断言（PR #18 事故防线）

只读草稿态（`analysis_state=ready` + `status=draft` + 可管理）下，审核弹窗底部**直接**渲染
「确认并用于项目指引」，不需要先进编辑模式——这正是 PR #18 修的主路径，本轮浏览器实测通过。
反向也钉住了：只读态没有「保存修改」，只有点「编辑」后才出现（两态互斥，未串味）。

### 集成桥采集触发路径

点「立即采集」后页面出现明确提示：**「浏览器 harness 无宿主计划任务，无法手动采集。」**
——这正是桌面端在非 Windows / 无宿主任务时的既有错误路径，前端把它如实呈现给了用户
（截图 12 可见）。真实桌面端同一按钮走 `schtasks //Run //TN "FDE-Bridge-Poll"`，
见 `.agents/skills/fde-bridge-capture/SKILL.md`。桥页其余部分读到的是**真实投影**
（6 个 engagement、最近同步流水、项目指位审计），说明页面数据链路本身是通的。

## 发现的缺陷

**本轮两条链路未发现产品缺陷。** 但过程中撞出两条**已被记录的既有设计缺口**（非本轮引入）：

1. **[P3] 挂载认领的命名约定无服务端保障**（台账第七节第 3 条，本次再获实证）：
   认领要 `display_name=预调研表` **且** `business_category=预调研` 同时命中，
   缺任一个就认领不到、「查看预调研分析」入口消失——本次搭 fixture 时先只给了
   `display_name`，入口就是不出；补上 `business_category` 后立刻出现。
   真实事故同源（PR #17 当时靠 ORM 数据修正救回）。**建议**：`set_presurvey_source`
   时服务端归一化命名，或收敛为「预调研类目唯一文件」约束。
2. **[P3] 认领入口的失败是静默的**：文件命名不合规时，用户只看到卡片空状态里的一句
   「已有待审核的分析时，点『查看预调研分析』即可审核确认」，但按钮根本不出现——
   用户无法区分「没有待审核分析」和「有但认领不到」。**建议**：认领失败时在卡片上给出
   可行动提示（例如「预调研表已上传但未关联到项目，请检查文件归类」）。

## 回归步骤入技能

本轮的操作步骤、断言口径与坑位已写入仓库技能
`.agents/skills/fde-gui-regression/SKILL.md`（harness 原理、跑法、fixture 口径、
「编辑」按钮不唯一、SPA 改 hash 不重渲染、Git Bash→WSL→容器中文编码等坑）。

## 红线自查

- 客户真实数据零触碰：fixture 全合成（`gui.regression` / `FDE-GUI-REGRESSION`），
  截图含 somwyn 与本机路径故不入库（已 gitignore）。
- 无密钥、无门禁证据内容入库。
- 仓库内只写变量名与代码，不写任何口令值（fixture 口令是合成值且只在本地文档中说明用途）。
