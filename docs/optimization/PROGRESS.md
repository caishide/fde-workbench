# goal-optimize 实际进度

更新于 2026-11-23。材料、工具、本机验证、CI、合并、活体与用户验收分别记账。

## 2026-11-23 R1c 冻结水位核对

- 合成回归复现了旧判据接受落后水位。计划须提供冻结回执中的预期水位，恢复后的水位须精确匹配。测试覆盖高于或低于预期、非法计划值及多组等值正例。WSL 部署工具全套 88 例通过。
- R1c-2b 等待专用恢复环境。已查询本机 Compose 项目，共享 Docker 上运行着现有工作台与其他服务。数据库冻结和实机验收条件见 [R1c 规格](R1c-固定产物与隔离恢复验收规格.md)。

## 2026-11-23 R5 类型与异常观测

- 甘特图的日期和依赖集合补齐类型注解。mypy 基线由 277 条收缩到 274 条，实测 274 条且零新增。
- 立项遇到意外异常时，应用日志记录 `project_creation_failed` 及异常类别。基于合成 SQL 和绑定参数的测试验证了完整异常日志的泄露风险，修正后分类日志、固定 503 契约、甘特、热点预算及 QR 回归切片共 17 例通过。QR004/QR018 偶发 503 的根因待复现。
- #571 已合并为 `4682e048`，本地 `main` 已同步。PR 首跑在 30 分钟时限处取消，复跑四项通过。同一提交的 push 流水线四项通过，服务端 pytest 为 4930 passed、123 skipped。
- [R5 实施规格](R5-类型与异常观测收敛规格.md)

## 2026-11-22 R4 容量观测准备

- 四条用户链分别统计请求、排队、执行和人工等待，单列失败、恢复、未完成、缺测和未经过阶段。既有 metrics CI 自动发现新增合成用例。见 [容量基线与离线汇总规格](R4-容量基线与离线汇总规格.md)。
- R4b 待隔离栈和实测场次确认。R4c 以该基线为前提。场次环境和证据要求见 [待裁决](BLOCKED.md) E-04。
- 交付完成：PR #569 四项 CI 通过并 squash 合并（commit 72347900），本地 main 已快进、分支已删、codegraph 已 sync。R4b/R4c 仍受 E-04 约束，不以离线工具冒充容量实测。
- CI 假红处置：push run 首次 QR018 假红，同日 main 独立出现 QR004/QR018 同族 create_project 503；PR run 与失败 job 重跑均全绿，目标测试本地复跑 2 passed。R5 补充立项异常分类日志。

## 2026-11-21 R3离线工具续跑

- R1c-2b 与 R2 真实验收仍待专用环境/OWNER前提，不重复施工。按顺序转入 R3 可独立面：新增观察记录闭合 JSON 离线汇总器，输出完成率、独立完成率、首次验收通过率、人工投入、返工、总历时和模型费用；未知分母保留，不做总体推广。
- 本地合成验证 20 例通过；两条变异（尝试未知进入已尝试分母、未知AI费用仍算验收成本）分别真红后还原复绿。工具不接生产库、不折算人工单价、不采集数据。
- 交付完成：PR #566 四项 CI 通过并 squash 合并（commit 2a5559c5），本地 main 已快进、分支已删、codegraph 已 sync。R3真实净收益与人工基线仍为外部前提。
- 2026-11-22 提交闸实录：pre-commit 全套 4805 过/56 假红/121 跳，根因为本地 `server/.env`（11-20 起含宿主通道键）被测试 Settings 暗读，agent 路由面集体改道；conftest `_env_file=None` 封闭化后失败家族切片 28 例全绿，随本轮 PR 一并交付。

## 2026-11-21 续跑

- R1c-1 已由 #555 合入 `main`（`2e31ef76`）。R1c-2a 在 `feat/goal-optimize-r1c-restore` 落地离线编排和证据报告。计划与清单中的镜像 ID 不符、端口冲突及非法输入在回调前拒绝，报告只保留核验后的允许字段。
- WSL 全部署工具套件 85 例通过。Windows 同套件 84 例通过，1 例因宿主无法创建目录符号链接而跳过，该用例在 WSL 通过。恢复验收待 R1c-2b 的隔离实机证据，包括冻结窗口、数据恢复以及 RTO/RPO 测量。

## 2026-11-19 续跑（优先于历史回执）

- R0/R1a/R2a：#530 合流后 WSL 44 例通过、零 skip。新头 `490e1ff0` 的 PR 与 push 两组 CI 均四项成功，合并为 `d0b9aaa8`，本地 `main` 已快进。9 个同名旧副本已备份并逐个核对 SHA-256。未部署。
- R1b：[部署协调规格](R1b-部署协调协议与验收规格.md) 采用单宿主统一占用槽。两条定时备份仅核元数据，尚未核目标和一致性窗口。
- R1b-2：新增离线协调器。审查发现 Windows 查询句柄妨碍更新及释放，实测允许共享删除仍不够；改用固定短时进程锁保护状态 I/O。补齐更新前所有权复核、`SystemExit` 归类、部分释放与精确调用序列断言。独立文本复审无实现级阻断，提出两处断言加固，均已补：真正解析坏记录，以及发布与释放两阶段均收到内核锁争用信号。最终 Windows 协调器 13 例（3.337 秒）、WSL 全部署工具 57 例（14.148 秒），exit 0 零 skip；空槽和验证失败两份隔离变异分别 exit 1。
- R1b-3：正式 Windows 入口、固定生产目标、定时备份和旁路仍待核。不改生产、不宣称跨宿主互斥；隔离实现独立投递，不计为 #530 内容。

## 目标／顺序／最大风险

1. 让交付稳定、用户可独立完成任务、AI净收益可测；保持技术栈。
2. R0文档→R1a候选核验→R1b部署协调→R1c固定产物/恢复，再推进R2–R5；OWNER项独立备料。
3. 共享部署覆盖与历史证据冒充现测是主要风险；本轮不部署、不改生产配置。
4. 候选通过不等于镜像、数据库或用户任务通过；真实凭据/用户/生产AI授权不从本Goal推定。

## 续跑位置

- R1c 开发树为 `D:/test/fde-workbench`，分支 `feat/goal-optimize-r1c-manifest`，原起点为 #544 合并提交；本线提交前于 2026-11-20 07:42 快进合流 `fork/main` 至 `cc636b9f`（#546，docs-only）。
- PR #555 四项 CI 全绿后 `fork/main` 前进至 211a61b9；已合入本分支，冲突仅 CHANGELOG，按「本线完整节在前＋上游完整节在后」保留双节。合流后 Windows 13 例（4.633s）与 WSL 部署工具 70 例（20.224s）通过。
- 原始提交 `212f26b2` 的 ruff、mypy 和完整服务端 pytest 钩子均通过。测试使用独立的临时 PostgreSQL 和 Redis 实例，两容器已清理。
- R1b 以 `f0f16f4b` 为合流基线，`372e2a8f` 的 push 和 PR 两组 CI 均四项通过。#544 squash 合并为 `a8786f78`，本地 `main` 已快进至同一提交。合流后 Windows 协调器 13 例及 WSL 部署工具 57 例通过。
- R1b-3 的生产前提和 R1c 的恢复验收分别见 BLOCKED 与 leader 任务书。
- R1c-1 修复证据：独立只读审查发现空路径和父分量路径可能误批准；新增拒绝用例先红后绿。Windows 13 例与 WSL 部署工具 70 例在 `cc636b9f` 复测通过。原起点 `a8786f78` 的预检隔离 PG/Redis 环境中 ruff 通过、mypy 277 处零新增、服务端全量 4312 passed / 85 skipped / exit0，用时 5700.44s；正式提交钩子已在当前基线复用同款隔离服务。
- cc636b9f 首次提交钩子：ruff/mypy 通过，服务端全量 4514 passed / 1 failed / 85 skipped / exit1，用时 4110.70s。红例为 #538 冻结 JSON 的 Windows checkout CRLF 字节锚错位；仅将工作树恢复为 HEAD blob 的 LF 原字节后定向 1 passed，未改断言、未 skip，随后复跑提交钩子。

## 分轮状态

| 轮次 | 实现/材料 | 验证 | 交付 |
|---|---|---|---|
| R0 | 建议、leader、进度、待决、观察模板已落盘 | 文档独立审查P2已关闭；leader 2823字符/6节；本地链接核验通过 | 随R1a提交 |
| R1a | 只读CLI与44例测试；CI/README/AGENTS/CHANGELOG已接线 | WSL 44通过、零skip；兼容补丁及合流独立复审通过 | #530 四项 CI 通过并已合并 |
| R1b | 隔离协调器与协议 | Windows 13 例、WSL 部署工具 57 例通过 | #544 已合并，生产接线另行确认 |
| R1c | R1c-1 固定包校验，R1c-2a 离线恢复编排 | 合成正反例覆盖阶段顺序、提前停止及报告边界。实机恢复待 R1c-2b | R1c-1 #555、R1c-2a #562 已合并，冻结水位补丁随轮交付 |
| R2 | 观察模板已备；R2a清单示例已校正并独立审查通过 | 真实用户与真发信未验 | OWNER前提见BLOCKED |
| R3 | 离线观察汇总器与口径规格已落地 | 合成20例；两条变异红→绿；真实净收益未测量 | #566 已合并（2a5559c5） |
| R4 | 离线汇总器、采集口径、场次验收条件 | 合成验证通过，容量基线待 R4b | R4a #569 已合并，R4b/R4c 见 E-04 |
| R5 | 甘特集合注解与立项异常分类 | mypy 基线收缩 3 条，503 日志隐私回归通过 | #571 已合并（`4682e048`） |

## R1a验证证据

- CLI全套：WSL `python3 -m unittest discover -s tests/deploy -p "test_*.py" -v`，**44 passed / 11.158s / exit0 / 零skip**。真实临时Git仓与子进程，不mock被测核心、不触碰活体。
- 早期Windows版本38例：37通过、1因本机符号链接创建权限不足skip（173.879s）；随后WSL38例全通过（11.958s），补齐循环路径。最新代码以44例WSL结果为准，不能把早期Windows结果冒称最新全套。
- 原有文档闸：`D:/test/fde-workbench/server/.venv/Scripts/python.exe -m pytest --noconftest -p no:cacheprovider server/tests/test_ledger_sync_nail.py server/tests/test_diagnostic_eval_contamination.py -q`，**9 passed / 9.10s / exit0**。两测试是独立纯文件检查，未载入服务端conftest或连库；不替代服务端全量CI。
- 本仓兼容性：只解析89份迁移AST，静态单头`b7f2d9e4c6a8`；现有alembic.ini受支持；未导入/执行迁移，不是数据库升级证据。
- 文档：13个本地链接逐项在场；leader 2823/4000字符；双份操作手册字节一致；git diff --check通过。

## 先红后绿与审查处置

- 工具缺失先红；filter执行反例先红后修，首轮23例通过。
- 独立审查指出Git对象替换、动态元数据、迁移枚举、partial clone、配置间接读文件、3.12循环路径异常和help契约。27例中条件重赋值/AugAssign两例误放行，修复后扩为38例。
- 自审补ignored迁移反例：旧工具误报candidate_consistent；增加目录文件名对账后39例通过。只枚举额外文件名，不读取内容。
- 复审补深缩进filter/include、3.12无值布尔项与Alembic忽略文件名：真实复现filter走到status、include进入Git、AttributeError泄stderr和伪合并误放行。修复为Git配置逐行去缩进后解析、固定错误转换，以及tracked/disk共用文件名选择函数；43例全过。
- 最初上述fixture误用重复core节/两个合并节点，提前触发其他检查；纠正fixture再复现，未把错误夹具计作漏洞关闭证据。
- Git/迁移解析只支持明确声明的本地可信仓静态范围；不自称恶意代码沙箱、原子快照或活体核验。
- 独立审查者只读源码/diff，不执行被审代码；实施者跑测试。最终独立复审确认3项遗留阻断全部关闭，无新增提交阻断；工具指纹0619068761d53525…、测试613593d0df12bcb1…与43例实跑版本一致。

## 技能关卡

已应用leader、fde-delivery-flow、strategy-red-team、tdd、code-review、requesting-code-review、verification-before-completion、neat-freak；桌面/服务端业务未改，不触发打包或生产部署。本轮不得把R1a本地通过等同总Goal完成。

## 实际提交与工作树自核

- 首提交`2642f64`已生成，原pre-commit ruff/mypy/完整server pytest三项均Passed。钩子只报告通过，不虚构用例数；此前缺venv失败已通过依赖junction和仅进程环境测试库URL解决，未跳过钩子、未复制凭据。
- 对真实managed worktree自核发现未启用的config.worktree遗留旧路径被误拒；Git未启用extensions.worktreeConfig时不读取它。新增关闭态/开启态反例先红后修，工具只检查实际启用的配置文件；44例WSL全绿。真实树修改后返回dirty_tree，证明已越过误拒且保留脏态闸。
- 该兼容补丁仍需独立复核与原提交钩子；首次全绿不是后续改动自动通过的凭证。干净提交自核、push和四CI继续推进。

## R1a 合流与全量复核（历史）

- 兼容补丁及合流独立复审通过，工具9638702cb5f5416f…、测试cfc35fed7b26db7d…；44例WSL实测已通过。
- 第二次提交钩子ruff/mypy通过，但服务端全量为4113 passed/1 failed/3 errors/7 skipped，1038.93s，exit1；提交未生成。失败四例单进程复跑4 passed（16.47s），尚不足以证明全量通过，不修改原断言。
- 期间在同一工作树编辑文档导致pre-commit另报文件变化；此后冻结被测树直到测试结束，独立备料放主树.artifacts。不得把该提示与真实失败混为一谈。
- 已保留stash `c6ace0d2ce82be83c6744a8663d8d633363101ae`，合入固定MERGE_HEAD `649a2609647c784f52d68f2f280c0635a9cb9f16`（含其他线#524–#528）；CHANGELOG按“本线完整节＋上游完整正文”解冲突，AGENTS保留上游现役口径与本线入口。合流后的完整测试待执行。
- R2a：docs/goal-regtrial-BLOCKED.md审核清单与发信子域示例已修正；小规格与独立审查回执齐。仅文档，不改变部署、DNS、真实发信或三项OWNER待办。

## R1a 最终本地交付回执（历史）

- 合流提交`108c28d349a3fd3eeddd7604307a4189f215f1e3`已生成，ruff/mypy/完整服务端pytest三钩子全部Passed（完整日志在主树.artifacts/goal-optimize/final-commit-hooks.log）。未跳过钩子、未改原测试；此前一次失败记录保留，不推断已定位其根因。
- 干净真实managed worktree自核：exit0、candidate_consistent、单头b7f2d9e4c6a8、live_status=not_checked。测试后template_manifest仅Git stat缓存陈旧，规范化内容与HEAD一致；刷新索引后无暂存内容差异，未提交产物变更。
- 独立最终合流审查通过：CHANGELOG无串节，AGENTS仅新增入口，CI仅追加3行，R2a三项OWNER待办保留。
- 当前待交付：push fork、PR与四CI、合并及主树同步。R1a/R2a本地完成不能代替远端交付；R1b协议草案另在主树docs/optimization，尚未纳入本PR。

## R1b 本地钩子失败定位与一次性环境修复（2026-11-19）

- 提交钩子曾报 server 全量 83 failed/4108 passed/8 skipped。定位＝部署态 `server/.env` 的默认闸键污染测试默认关闭断言（`FDE_AGENT_HOST_CHANNEL_ENABLED=1`/`FDE_AGENT_HOST_POLL_ENABLED=1`）；不改部署配置，仅用一次性进程环境覆盖复测，不写入任何文件。
- 代表用例覆盖后复测 3 passed（17.80s）：`test_execution_policy.py::test_host_channel_default_off`、`test_host_poll.py::test_disabled_by_default_403`、`test_t6_gate.py::test_t6_disabled_by_default`。失败面＝环境污染，非 R1b 回归；R1b 不触碰服务端代码。
- 本机环境两坑（与仓内代码无关，登记防复发）：①本机 Python 在 Windows 不再忽略 `os.mkdir(mode)`，pytest/tempfile 的 0o700 目录被沙箱令牌立即自拒——本地一次性插件归一化 mkdir 模式并钉 `tempfile.tempdir`，装在 `server/.venv/Lib/site-packages/fix_tmpdir_mode.py`（只动本地 venv，不进仓）；由此产生的 7 个不可读垃圾目录（`server/.tmp/bt-*`、`pytest-of-P1`）untracked，需管理员清理。②`run-server-tests.mjs` 固定覆写 `PYTHONPATH=src`，本地插件须经 `PYTEST_ADDOPTS` 从 venv site-packages 装载。③测试临时目录不得放 `D:\test\fde-workbench` 下——`agents/sandbox.py` 的 `FORBIDDEN_MOUNT_MARKERS` 含 `d:\test\fde` 子串，会误触发 `workspace_mount_forbidden`（本轮已实证）；改用用户 Temp 下唯一目录。
- CI 是干净环境的权威验证面；上述覆盖/插件不进仓、不放松断言、不 skip。

### R1b 环境隔离机制定稿（2026-11-19 补记）

- 逐键环境覆盖路线被证伪：Windows 环境变量不能为空串（PowerShell/cmd 赋空即删键），`SecretStr` 字段无法经 env 置 None，`FDE_DEEPSEEK_API_KEY`/`FDE_AI_SELFHOSTED_API_KEY` 无法blank掉；全局关闭 dotenv 又误伤 `test_config.py::test_shared_environment_template_ignores_desktop_only_keys`（该测试专门验证 Settings 读 cwd 下自建 .env 的机制）。
- 最终机制＝本地插件包装 `Settings.settings_customise_sources`：仅当 dotenv 解析路径＝部署面 `server/.env` 时剔除该源，其余 .env（含测试自建 tmp .env）原样保留——得到 CI 等价默认态且 dotenv 机制测试零误伤；部署 `.env` 一字未动。
- 定向复验 10/10 绿：channel/poll 默认关、T6 默认闸、selfhosted 三态、translator 回落/分类、test_config dotenv 机制（15.70s）。
- 并行噪声记录：`-n 4 --dist loadfile` 在本机高负载下出现 14 例 DB 争用类失败/错误（同集合串行全过）；串行另遇 3 例瞬态（test_solution_signoff/test_task_board_api/skill_readbefore，孤立复跑即过）。本地权威口径＝串行全量钩子；CI 以其自身环境为准，不把本机负载噪声归因代码。
- 专用测试服务上的首次串行全量为 4190 passed、7 skipped、2 failed，两例定向复验均通过。后续原始提交 `212f26b2` 的三个钩子全部通过。偶发失败尚无统一根因。
