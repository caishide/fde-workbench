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
- 口径数字（实测 2026-10-31，goal-r11 终止复核）：服务端 **85 张业务表**（不含 alembic_version；r8 的 86 为含其口径，§8.1 八表齐）、迁移头 `c5d7e9f1a3b7`（**15 个 revision**）、蓝图路由 **228**、api_catalog ENTRIES **68**、服务端 pytest **1456 通过 + 6 跳过**、桌面端 vitest **660 用例**。goal-r9/r10/r11：**P2-4 私单封堵**（channel_guard 三钩子）+ **撮合仿真器**（H2/H3 内测/仿真口径，工件 `docs/dispatch-sim-r9-seed42.json`）+ **C7 混合模式自动转换**（挂 dispatch.maintenance 节拍）——**goal 循环已终止（§八八项全成立）**，唯一凭证=`docs/goal-r11-派单引擎收口.md`（取代 r8 收口报告）；剩余事项全外部输入，清单见该报告第五节。
- 派单引擎施工准绳：`D:\test\FDE\蔡工FDE工作台_文档中心\06_派单引擎\蔡工FDE工作台_派单撮合引擎产品与技术设计_v1.0.md`（2026-10-31 补齐版，冲突裁决顺序=代码实测 > 设计文档 > 规则表 > BP）。
