# AGENTS.md — fde-workbench

FDE（前端部署工程师）交付工作台：Flask + SQLAlchemy API（`server/`）+ Electron·Vite·React 桌面端（`desktop/`），当前 v0.2.0。部署、命令全集、迁移与换机迁移清单以 **README.md** 为唯一权威，本文件只放 Agent 不看就会犯错的边界。

## 红线（违反即事故）

- 客户真实资料永不进 git 历史与远端：仓库和数据库只存代号（如 somwyn）；真实姓名、扫描件、回款凭证只留在本地 fdeops/openfde 工作目录（`D:\test\FDE\…`）。
- 密钥不入 VCS：`.env`、`server/.env`（承载 FDE_DB_PASSWORD / FDE_JWT_SECRET / FDE_BRIDGE_TOKEN）永不提交，仓库只有 `*.env.example`；FDE_JWT_SECRET 是本地密钥加密根，换机迁移必须原样携带。
- 门禁证据只存 `source_uri` 指针 + sha256 指纹；证据原件永远留在项目工作目录，不进仓库、不进数据库。
- `scripts/bridge-poll.mjs` 只读纪律：只调 openfde 只读 CLI + 读文件，绝不写真相层；采集只能在 Windows 宿主跑，Docker 容器内跑不了。
- 远端分工：`origin` 是上游（gxfde），**永不 push**；工作远端是 `fork`（caishide/fde-workbench），tag 也只打在 fork。

## 常用命令

- 桌面端：`npm run typecheck`、`npm run test:desktop`（620+ 用例）；服务端：`npm run test:server`。
- 服务端代码烤进镜像：改 `server/` 后必须 `docker compose build && docker compose up -d`，再执行 `alembic upgrade head`（只跑 up -d 无效）。
- 集成桥手动采集：`schtasks //Run //TN "FDE-Bridge-Poll"`（Git Bash 下双斜杠），或桌面端集成桥页「立即采集」按钮（同一代码路径）。
- 桌面改动交付：重打包便携版并做 asar 字节验证（README「打包桌面端」节）。

## 工作流与陷阱

- 变更走 feature 分支 → push fork → PR → 4 个 CI job 全绿（desktop / server-tests / gitleaks / pseudonymization）→ 合并 → ff 本地 main → 删分支。
- CI 跑 Ubuntu：Windows-only 代码路径（schtasks、wsl、盘符）必须做成可注入/可 mock，测试显式传 platform。
- 本机 Windows/Git Bash；docker 经 `wsl -d Ubuntu-24.04 -- docker …`（配 `MSYS_NO_PATHCONV=1`）。
- 代码检索优先用 CodeGraph：本仓库已索引（`.codegraph/` 是本地 SQLite，已 gitignore，勿提交）；`codegraph explore "<问题或符号>"`，大规模改码后 `codegraph sync` 重建增量。

## 当前状态（2026-10-31）

- v0.2.0：门禁 G1–G9、报价/收款/合同、集成桥（宿主 4h 采集 + 手动采集按钮）、内嵌使用帮助；本地 main == fork/main。
- 版本号按发布列车同步 `desktop/package.json` 与 `server/pyproject.toml`，tag 打在 fork。
- 待办台账：`docs/后续需求台账-F5与D11.md`；历史审计存档：`docs/goal-audit-2026-10-26.md`；派单引擎 goal 循环报告：`docs/goal-r<N>-派单引擎.md`。
- 口径数字（实测 2026-11-01，派单运维页簇 B3/B5/B6 + B2 + B1 + goal-d3 S1 联合口径）：服务端 **91 张业务表**（不含 alembic_version；d3 +6）、迁移头 `d9c3e7f1a5b8`（**16 个 revision**，d3；B1/B2/B3ops 零迁移）、蓝图路由 **239**（B1 +3 mine 路由；B2 +1 packages/{id}/offers 留痕；B3ops +5：disputes 列表/打开/裁决 + simulator/replay + claim-gates 看板）、api_catalog ENTRIES **79**（B1 +3、B2 +1、B3ops +5）、服务端 pytest **1507 收集**（d3 +16、B1 +7、B2 +6、B3ops +8）、桌面端 vitest **695 用例**（B1 +9、B2 +10、B3ops +9）。B3/B5/B6 运维页簇：三个平台侧 tab——争议处理（L0–L3 全量留痕、对账单只透出 source_uri 指针红线、L1 ≤¥50,000 上限 422、裁决 100% 人工 §6.6）、仿真对比（只读回放=当前池×当前规则版本画像，全链路仿真留 CLI 沙箱库不经 HTTP 写库，口径=仿真不作真实成绩）、开闸运维（§6.4 三条件+种子开关逐城明细，只读不翻转）——台账二十八节。B2 调度台操作面：平台侧第 6 子页（admin/project_lead 可见，动作权限服务端复核）——供给池候选勾选器 + 包全景生命周期按钮（等级覆盖 §4.5 / 发布携候选 / 重派 round+1 / 执行撮合（可解释结果面板）/ 指派 offer / 撤回 / 代接单）+ 包侧 offer 留痕面板——台账二十六节。B1 接单工作台：交付工程师专区（设计 §1.4 授权可见+offer 流形态；企业需求方专区被 §1.4-3 明确排除不做）——我的 offer 收件箱（§6.2 窗口 deadline 服务端现算）/接单拒单（乐观锁+原因枚举）/我的席位结算（他席金额零出现）/我的档案（404 无档案）/派单池 claim 抢单按钮（开闸判定在服务端）——台账二十六节。goal-d3：agent_registry/agent_runs/agent_artifacts/agent_tool_calls/agent_credentials 五表 + solution_review_checkpoints + project_solutions 生成来源四列 + CAPABILITY_REQUIREMENTS `agent.*` 四能力 + `agents/sandbox.py` 沙箱基座（V2 四断言）+ compose `sandbox-runner`（profiles=["sandbox"] 门控，试点 d6 启用）——详见 `docs/goal-d3-交付工作台.md`。goal-d2：S0-3 确认流三缺陷修复（cancelled 显式文案/start 透传 failure_message/PATCH 即 setDraft）+ S0-4 方案骨架（confirmed 指引 409 闸）与健康分 v0（120 分制）+ S0-5 `sow_contract_linked` 串联审计 + S0-6 行业模板种子 ×3（`seed_workbench` 幂等装载，模板总数 1→4）+ P0 四指标埋点 + 售前录入卡桌面入口——详见 `docs/goal-d2-交付工作台.md`。派单 goal-r9/r10/r11（P2-4 私单封堵/撮合仿真器/C7 混合转换）：**派单 goal 循环已终止（§八八项全成立）**，唯一凭证=`docs/goal-r11-派单引擎收口.md`；剩余事项全外部输入。
- goal-d2 口径存档（2026-10-31）：85 表 / head `c5d7e9f1a3b7`（15 revision）/ 路由 230 / ENTRIES 70 / pytest 1448 收集 / vitest 667；S0 全收口——详见 `docs/goal-d2-交付工作台.md`。
- 派单引擎施工准绳：`D:\test\FDE\蔡工FDE工作台_文档中心\06_派单引擎\蔡工FDE工作台_派单撮合引擎产品与技术设计_v1.0.md`（2026-10-31 补齐版，冲突裁决顺序=代码实测 > 设计文档 > 规则表 > BP）。
