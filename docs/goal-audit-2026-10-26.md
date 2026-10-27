# Goal 循环评审会审计报告（party mode · 五官并行实证）

| 项 | 值 |
| --- | --- |
| 日期 | 2026-10-26 |
| 评审对象 | goal 循环 WP00–WP16 全队列：本地 15 提交（455dfac→4b0ca19）+ CI 修复 3 提交（05a0c7f→7ceec5b），PR #1/#2 已合并 |
| main | ac2101e |
| CI | run 40388246187 三 job 全绿（server-tests / desktop / pseudonymization）——**首绿** |
| 方式 | 5 名专家 agent 并行独立审计，三态判级（红=必须修 / 黄=有账要还 / 绿=通过） |
| 本机基线 | server 1185 passed / 6 skipped；desktop 609/609；tsc 0 error；ruff 通过；mypy 基线无新增 |

## 总评：**黄 —— 可交付，有账要还**（1 绿 4 黄 0 红）

没有任何角色判红：无造假绿、无泄漏、无不可复现的声明。但四份黄灯各自指出了会随时间发酵的债。

---

## 0. CI 首绿之路（PR #2，三次迭代，每层都被前一层掩盖）

| 批次 | 根因 | 修复 |
| --- | --- | --- |
| 第一批（run 40376170323：server 4 + desktop 1） | ① `test_quote_first_order_concurrency` 自行构造 `Settings(database_url=…)`，`redis_url`/`jwt_secret` 靠本机 `server/.env` 兜底；② minimax 测试隐式依赖 `.env` 的 `FDE_DEEPSEEK_API_KEY`；③ desktop 断言硬编码 `2026/8/28 10:30:00` 而 fixture 带 `+08:00` 偏移，组件按机器时区渲染 | ① 复用 conftest `test_settings`；② monkeypatch 注入合成 key；③ 期望值与组件同表达式动态计算 |
| 第二批（pseudonymization 首次真正运行） | `check-pseudonymization.sh` blob 是 CRLF，Linux bash 语法错误 | 字节归一化 LF + `.gitattributes`（`*.sh text eol=lf`） |
| 第三批 | `run_wsl` 非 WSL 分支只会 `wsl.exe`——Linux 宿主无此命令（pg_dump 127） | 三分支 `run_host`：WSL 直跑 / Windows 走 wsl.exe / Linux 直跑 docker |
| 第三批副产物 | 黑名单提取 `grep -oE '[一-龥]…'` 三环境三行为：UTF-8 locale「Invalid collation character」匹配 0 个（黑名单静默失效，哨兵自测发现不了）、C locale 按字节碰巧能跑、MSYS 另一套 | 改 `perl -Mutf8 -CSD` 按码位区间提取，locale 无关 |

> 教训：pseudonymization job 此前一直被 server-tests 失败连带 skip——**从未真正运行过的检查等于没有检查**；连续被掩盖的三个环境假设（CRLF、wsl、locale）全靠"首次真跑"才暴露。

---

## 1. CI 环境官：**黄**

失败 run 根因归类复核完整（TOCTOU 断言失败确认为 Settings 校验错误的级联，非独立竞态）。无"必红"确定雷。残留：

| # | 位置 | 风险 | 建议 |
| --- | --- | --- | --- |
| 1 | `.github/workflows/ci.yml:56` | CI `pip install -e ".[test,dev]"` 按区间解析，**不消费 `requirements.lock`**——传递依赖发版即可零改动翻红，本机冻结 venv 仍绿 | 安装叠加 `-r requirements.lock` 或 `--constraint` |
| 2 | `ci.yml:17,73,107` | `ubuntu-latest` 已于 2026-10-19 起迁移 Ubuntu 26（绿 run 即在新镜像通过，兼容已实证），但后续不 announce 的镜像变更不可控 | 钉 `ubuntu-24.04`（或 26.04）三 job 一致 |
| 3 | `ci.yml:97` | `docker ps --filter ancestor=postgres:16` 可能抓错同名镜像容器 | 加 `--filter name=` 双重过滤（低概率） |
| 4 | 改善项 | 无 pip/npm 缓存、无 `timeout-mininutes`、无 concurrency 组 | 提速/止损，不影响正确性 |

CRLF blob 判级：13 个文件（py/json/tsx/env 示例），Linux 下均无执行语义，**无致命**；唯一致命类（.sh）已修。

## 2. 验证官：**黄 → 裁定后实质绿**

五个抽样工作包全部复现，全量数字精确复现：

| 包 | 核验 | 结果 |
| --- | --- | --- |
| WP01 会话锁 | 双 pytest 并发 + `pg_stat_activity` 现场抓到第二会话 `wait_event='advisory'` 等锁 | ✅ 复现 |
| WP05 B3 首单闸 | `pg_advisory_xact_lock` 确在 `quote_service.py` 生产代码；并发测试连跑 3/3 绿 | ✅ 复现 |
| WP08 E7 预算审计 | 审计无 key/提示词字段；fail-open 语义有专门测试钉住 | ✅ 复现 |
| WP11 CI/mypy | `no new type errors (baseline 104, current 103)`；ruff 通过 | ✅ 复现（基线文件登记 104 条，其中 1 条已解决） |
| WP13 bridge stale | openfde/fdeops 双轨独立判定互不兜底 | ✅ 复现 |

**全量首跑 4 failed（`test_ai_eval_opportunity.py::test_golden_case` 引文剔除类）裁定：评审会自身交叉污染，非仓库 flake。** 证据链：① 失败签名与并行运行的变异测试 M3（临时删除 `ai_opportunity_service.py` 的 `quoted()` 过滤）语义完全吻合；② 时间窗覆盖（变异窗口落在首跑 350s 内）；③ 干净树当日 3 次全量 1185 + 失败文件定向 26/26 + 复跑 31/31（0.06s）全绿，独立 flake 证据为零。**教训（记入方法论）：变异测试与全量回归不得并行调度。** 彻底封口建议：后续任一次全量跑挂掉时先查有无并行进程改文件，再怀疑 flake。

## 3. 测试质量官：**黄（钉子本体 6/6 有效）**

| # | 变异（破坏生产代码） | 测试 | 结果 |
| --- | --- | --- | --- |
| 1 | B3 advisory lock → `SELECT 1` | 首单并发 | 🔴 红（抓住 TOCTOU） |
| 2 | E7 `budget_exceeded` 恒 False | 预算闸 | 🔴 红 |
| 3 | E3 删 `quoted()` 证据过滤 | 金标准评测 | 🔴 红（4F，含"编造厂商名→剔除"） |
| 4 | D5 draft 409 拦截 → pass | 版本下载门 | 🔴 红（2F） |
| 5 | C2 Gate 勾选全不勾→全勾 | gate-board | 🔴 红 |
| 6 | C1 `mutate(async () =>`→`() =>` | commercial-board | ⚪ 字面存活 |

M6 存活分析：`mutate` 的 try/catch 包住 `await run()`，同步 thunk 抛错同样被 catch——**async 关键字不是承重墙**。补测真实回归形态（parsePositive 逃出 try 作用域）正主用例击红，证明钉子钉住的不变量（parsePositive 必须在 mutate try 作用域内求值）有真实防护力。若把 async 语义本身视为修复本体，则该语义无钉（记录为 P3）。

## 4. 安全官：**绿**

- **Secret**：goal 循环全部提交 diff + 全历史补扫，原始命中 3 组全部误报（合成测试值，且其中一组反向断言"密钥不落审计"）。疑似真值：无。
- **隔离防线**：conftest 断言**先于** `downgrade("base")` 执行；`twenty` 在禁止清单；纯库名校验不校验主机（远端 `*_test` 不拦——理论弱点，P2 加固项）。
- **审计链**：`ai_call_audits` 12 个元数据列，无 key/prompt/上下文；失败仅 warning 不打断业务。
- **客户数据**：黑名单 fixture 三个名字纯合成；哨兵值仅存在于测试与自测代码；`.env`/日志/`.artifacts`/`release` 均未被跟踪。

## 5. 交付官：**黄**

worker/scheduler **全绿可起**：import 链零报错，handler 注册表 8 项齐全，compose 与 cli 命令名一致，alembic head `e5b8a1c9d3f7` 与口径一致。矛盾集中在文档/脚本残留：

| 位置 | 文档说 | 现实 | 判级 |
| --- | --- | --- | --- |
| `scripts/run-e2e.mjs:13-15,85-91` | `FDE_E2E_DATABASE_URL` 只收 `mysql+pymysql://` | 全仓 PG/psycopg，无 pymysql | **P1：e2e 脚本必败 + `tests/e2e/` 无 playwright.config（僵尸验收手段）** |
| `server/.env.example:4` | `FDE_ENV=dev` | Literal 只收 development/test/production | **P1：照抄即 ValidationError** |
| 根 `.env.example` | —— | compose `${FDE_DB_PASSWORD:?}` 强制要求该键 | **P1：缺键 compose 拒绝启动** |
| `README.md:74` | `docker compose up -d twenty-db redis` | compose 服务仅 redis/api/worker/scheduler | P1：照敲报 no such service |
| README 测试段 / `docs/后续需求台账` | —— | 与 package.json、conftest、路由现状一致 | ✅ 无矛盾 |

`.env.example` 必填项覆盖合格（database_url/redis_url/jwt_secret≥32 字符均含）；desktop 打包资源（icns/ico/png）全部存在。

---

## 6. 跟进清单

**P1（误导新人/假验收，建议尽快）**
1. `run-e2e.mjs` 改 PG 或移除 `test:e2e` 僵尸脚本；补 playwright.config 或删 `tests/e2e/`
2. `server/.env.example` 的 `FDE_ENV=dev` → `development`；根 `.env.example` 补 `FDE_DB_PASSWORD`
3. `README.md:74` compose 启动命令改为可直接执行版本

**P2（漂移与防线加固）**
4. CI 安装叠加 `requirements.lock` 约束；`runs-on` 钉版本；`docker ps` 双重过滤
5. conftest 增加主机校验（拒绝远端 `*_test`）
6. `check-pseudonymization.sh --self-test` 在非 `fde_workbench*` 目标库拒绝建哨兵表

**P3（打磨）**
7. `INITIAL_PASSWORD` 收敛到 conftest 单点（现散落 10+ 测试文件，持续制造扫描噪声）
8. 审计 blob 断言扩展 `purpose`/`status` 字段；CI 落地 gitleaks
9. C1 async 语义若视为修复本体则补钉；mypy 基线 `--update` 收缩（104→103）

## 7. 评审会遗留物说明

评审窗口内工作区 `scripts/` 出现两个**未跟踪**文件：`backup-pipeline.sh`、`install-backup-pipeline-task.ps1`（内容为「AI 外贸获客系统」n8n/Mautic/openoutfind 备份，与 fde-workbench 无关）。五个评审 agent 均无此产出职责，来源存疑。已按纪律不删不提交，待人工确认归属。

> **归属已确认（2026-10-27，悬案关闭）**：两者即仓库主人并行会话的备份管道工作，以 2f90484 随 PR #4 入库，后续 671eba1 继续加固 backup-all.sh。评审纪律（不删不提交、待确认）按预期生效。

---

## 8. 跟进清偿记录（2026-10-26 当日）

§6 清单 9 项全部清偿，12 个提交：

| 项 | 处置 | 提交 |
| --- | --- | --- |
| P1-1 僵尸 E2E | 删除 `tests/e2e/` + `run-e2e.mjs` + `test:e2e` 入口——spec 断言的是 MySQL 时代 readiness 契约（`{"mysql":"ok"}`，现契约为 `{"database":...}`）+ POSIX venv 路径，三重过时不可达；4 个 helper 脚本因有 `tests/operations` 独立单测保留 | 2f36a7a |
| P1-2 环境样例 | `server/.env.example` `FDE_ENV=development`；根样例补 `FDE_DB_PASSWORD`（compose 三处 `:?` 插值实测缺键 rc=1 / 带键 rc=0） | e6c432b |
| P1-3 README compose | 命令改 `docker compose up -d redis` + 幂等建 external 网络；合并重复段落 | f2df841 |
| P2-4 CI 加固 | `-r requirements.lock` 叠加安装（`-c` 不可行：lock 含 `psycopg[binary]`，pip 拒绝带 extras 约束）；三 job 钉 `ubuntu-24.04`；service 容器加 `POSTGRES_DB` 环境指纹二次确认（`--filter name=` 因 GHA 命名无文档保证弃用，本机同镜像 Twenty 容器实测被正确拒绝） | 4c8ad17 |
| P2-5 conftest 主机校验 | host 必须回环（127.0.0.1/localhost/::1）；新增 `test_conftest_safety.py` 把 driver/库名/主机契约钉成 9 条直接断言 | fed1a92 |
| P2-6 哨兵表护栏 | `--self-test` 非 `fde_workbench*` 目标库块首拒绝（拒绝路径零 SQL 触达，twenty 库实测零残留） | 56ad095 |
| P3-7 口令收敛 | 全仓 30 处字面量收敛 conftest 单点（14 模块常量 + 16 内联/别名）；附带修复 7ac6300 误入的 CRLF（eb009e1 全仓 renormalize + `* text=auto`）与 367185e 的多行 import 插入位（056408b） | 7ac6300 / 367185e / eb009e1 / 056408b |
| P3-8 审计 + gitleaks | blob 断言扩至全部字符串列（+purpose/status）；CI 新增 secrets-scan job（gitleaks 全历史基线本机实测 46 commits 无泄漏） | 91467df |
| P3-9 C1 裁定 + mypy | 裁定 async 关键字非修复本体（mutate 的 try/catch 包住 `await run()`，同步抛错同样被捕获；承重不变量已被 C1 用例钉住），裁定落档测试注释；mypy 基线 `--update` 收缩 104→103 | 7986588 |

**验证基线（本机 2026-10-26）**：server 1194 passed / 6 skipped（1185 基线 + 9 条新契约断言）；desktop 609/609；tsc 0 error；ruff 绿；mypy baseline 103 = current 103；pseudonymization 自测 PASS；gitleaks 全历史 no leaks。
