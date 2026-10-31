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
- 口径数字（实测 2026-10-31，goal-r4 派单引擎轮 + goal-d1 交付工作台轮合并口径）：服务端 **84 张表**、迁移头 `a7f3c1e9d5b2`（**13 个 revision**，链条 `…→ f4b8c2d6e3a1 → a7f3c1e9d5b2`）、蓝图路由 **226**、api_catalog ENTRIES **64**（录入卡路由沿门禁先例不进目录）、服务端 pytest **1409+ 用例**、桌面端 vitest **654 用例**。goal-r4 落地 offer_service（§6.3 乐观锁 / §6.7 拒单权 / §6.4 开闸评估）+ P1-3 目录↔路由双向一致性测试 + P1-5 种子三处（dispatch_cities.json / acceptance_metrics.json / gates.json 加 applicable_industries），详见 `docs/goal-r4-派单引擎.md`；goal-d1 新增 `presurvey_intakes` 表（售前轻量录入卡，PRD F1/D16）+ guidance 蓝图 2 路由 + `key_business_problems` 条目 severity/module 可选键 + **G3 前置闸**（`set_presurvey_source`/`create_analysis` 需 G3 passed，409 `presurvey_s3_gate_open`——行为变更：存量项目未拍 G3 会被闸住，运营口径=补证据拍板）；goal-d 循环提示词与技术实施见文档中心 05_AI 方案与 `docs/技术实施方案-智能体交付工作台.md`；派单 goal-r1/r2/r3 详见 `docs/goal-r<N>-派单引擎.md`。
- 派单引擎施工准绳：`D:\test\FDE\蔡工FDE工作台_文档中心\06_派单引擎\蔡工FDE工作台_派单撮合引擎产品与技术设计_v1.0.md`（2026-10-31 补齐版，冲突裁决顺序=代码实测 > 设计文档 > 规则表 > BP）。
