# Changelog

本文件记录 FDE Workbench 开源版本的主要变化。版本号遵循语义化版本规范；首次公开源码版本为 `v0.1.0`。

## [未发布] — goal-r1 派单引擎轮（2026-10-31）

### 派单引擎 P0 双闸门（对照派单设计文档 v1.0 §8.3）

- **P0-5 门禁验收分离**（§9.4，§8.8 开池四道闸之二）：`gates` 加 `submitted_by_user_id` / `decided_by_user_id` / `is_delivery_party` 三列（迁移 `d2f6b4c8a1e9`）；`decide_gate` 双 403 防线——① 拍板人=该门禁证据执行人 → `gate_decider_conflict`（代码强制、先于其余业务校验，不可绕过）；② 交付方执行的 G8/G9 非 admin 拍板 → `gate_decider_role_required`（§11.3 方案①过渡口径）。单租户时代「同一用户提交+拍板」从 200 变 403，是刻意的硬闸门。
- **P0-6 events 白名单**（§2.5 坑 1）：`projects/events.py` 注册 `delivery_package` / `dispatch_offer` 两类 OperationEvent 目标（offer 的 project_id 经交付包反查）；为此按 §8.2 DDL 级约束先行落 `server/src/fde_api/dispatch/` 包两张骨架表（`delivery_packages`：8 态派单状态机 + `Unique(package_code)` + `Unique(project_id, dispatch_round)` + 扩圈半径 Check(25/50/100/0=全城哨兵)；`dispatch_offers`：`Unique(package_id, dispatch_round, candidate_user_id)` + 6 态 Check + VersionedMixin 乐观锁位 + `match_breakdown` JSON）——**服务逻辑零预埋**，发布/快照/匹配随 P0-1/P1 轮落位。
- 测试：新增 `server/tests/test_dispatch_p0.py`（6 例：两类事件目标写入、执行人自拍 403、交付方 G8 平台拍板、服务层防绕过、乐观锁位）；`test_gates_api.py`（5 例）与两个冒烟脚本改双拍板人（执行人=lead、拍板人=admin），门禁冒烟加「执行人拍自己的门 403」钉子。
- 口径（goal-r1 实测）：78 张表、迁移头 `d2f6b4c8a1e9`（10 revision）、pytest 1345 passed + 6 skipped、桌面 654 用例零改动全绿。轮次报告 `docs/goal-r1-派单引擎.md`；台账新增第十三节。

## [未发布] — goal-r3 技能循环（2026-10-30）

### 仓库健康巡检（G10）

- dynamic-workflows 编排只读巡检：**4 个只读子代理并行**（测试覆盖地图新鲜度 / docs 与代码漂移 / 依赖与 TODO / 台账逐节对账）→ **独立复核员**逐条复核 → 结构化报告。43 条原始发现全部坐实（0 驳回 0 存疑），**P1=0 / P2=14 / P3=29**。全程零变更——落盘走本 PR。
- 新增 `docs/仓库健康巡检-G10.md`：四面逐条发现（每条带 file:line 证据与复核状态）+ 下一批 backlog 三批建议（文档新鲜度批 / 依赖卫生批 / 功能欠账批，优先级逐条写明）。
- 关键坐实项：覆盖地图计数漂移 948→1330 collected（桌面 496→512，且 496/api-ipc(7) 写作时即不准）；「SES 未建」两处失效（G9 已预建默认关闭）；变量与密钥缺 8 个 FDE_SES_*；权限矩阵缺 mailing/SNS 例外鉴权行；**ruff/mypy/pre-commit 未入 lock，CI 门禁裸装最新**；台账对账 24 条中 5 条确认已完成、19 条仍待办（含 4 条 P2：research 三态 UI、PATCH-confirm 分叉、analyzing 对账、README 初始化节）。
- 随本 PR 修正自家文档两处（巡检发现）：`docs/SES发信模块-G9.md` §五闸门顺序归因（发信域约束在 service 前置，不在 decide_send）与 §八测试分桶（9+5+12+1=27）。
- 台账新增第十二节（backlog 三批推进）。

### SES 发信模块预建（G9｜WP-E）

- 新增 `server/src/fde_api/mailing/`：**默认整体关闭**（`FDE_SES_ENABLED=false` 时发送路径落 `drop_disabled`、SNS 回调端点一律 403，默认部署零行为影响、零 AWS 依赖——boto3 延迟导入，未启用时不 import AWS 栈）。SES 生产批复下来**只需改配置启用**，不改代码。
- 发送路径 `send_email`（service 函数，**不设 HTTP 路由**——避免未批复时出现可打的发信口）：闸门顺序固定 = 开关 → 发信域约束 → 幂等键 → 收件人抑制 → 当日限额（只数 UTC 当日）→ 打 SESv2；throttle 记事件并返 503（可重试）、拒收返 502（不可重试），失败不占发送台账。
- SNS 回调端点 `POST /api/v1/mailing/sns/events`：**签名即鉴权**（SNS 带不了工作台 JWT）——校验 Signature v1（RSA-SHA256，字段序按 AWS 固定顺序）+ `SigningCertURL` 限 `sns.*.amazonaws.com`（校验不过则**不发起任何外联**）+ `SubscribeURL` 同域限制 + `TopicArn` 白名单；退信/投诉只落地址 + 分类 + 通知 sha256 指纹，**不落通知原文**。
- 新增两表（迁移 `a9c3f1d8e2b4`）：`mailing_sends`（幂等键唯一）、`mailing_events`（`event_key` 唯一——SNS 是 at-least-once 投递，重放不重复计）。bounce/complaint = 地址级死刑（进抑制名单），delivery 不影响地址。
- 发信域口径落到配置校验器：FROM 必须落在 `FDE_SES_SEND_SUBDOMAIN` 子域内，主域 `somwyn.com` 启动即失败（`ses_sender_domain_forbidden`）。DKIM/SPF/DMARC 写 `docs/SES发信模块-G9.md` 不写死代码——**子域**加 SPF，**主域 SPF 不加 SES include**（否则扩大主域邮件面）。
- SNS 主题策略须带 `aws:SourceArn`（配置集 ARN）+ `aws:SourceAccount`——缺 `SourceArn` 即 confused-deputy 洞（任账号 SES 都能往我们主题灌事件）。AWS 凭证走 boto3 默认凭证链，不配进本模块、不进仓库。
- 新增 `server/tests/test_mailing_ses.py`（27 例，**零真实邮件**）：假客户端 + botocore Stubber + 自签证书验签；覆盖闸门顺序、bounce/complaint 抑制、幂等重放、坏签名/错主题/非法 JSON 拒绝、text/plain 报文解析、配置校验器。
- 依赖：`boto3>=1.36,<2`（pyproject + `requirements.lock` 钉 1.43.122/botocore 1.43.122/s3transfer 0.19.3）。

### 后台作业死亡后对账重排队（台账 §八 第 1 条落地，2026-10-30 晚）

- 问题：worker 被杀（OOM/部署/重启）时，它从 redis 队列弹走的作业 id 随进程一起消失——outbox 事件已 `dispatched`（派发器不再看它），`BackgroundJob.max_attempts`/`available_at`/`locked_until` 无人消费，于是作业永远停在 `running`，业务行（指引分析 `analyzing`、会话 turn `running`）永远停在中间态，前端每 2 秒轮询到天荒地老，唯一解法是手工 `RPUSH fde-jobs <id>`。这正是 10-30 登录事故里那笔孤儿作业的成因。
- 修复一（`jobs/worker.py`）：`run_job` 把「认领 + 执行 + 落终态」从**一个事务**拆成三段——认领（`status=running` + 租约 + `attempts+1`）先单独提交，执行期间由守护线程**续租**（默认 60s 一次，租约 5min），终态再单独写回。三个后果：① 在跑的作业对其他进程**可见**（此前全程只有 pending，对账无从分辨「有人在做」与「做的人死了」）；② 行锁只存在于认领那几毫秒，不再被 handler 全程占着（长任务钉着连接正是 10-30 锁雪崩的形状）；③ 租约过期从此是**死亡信号**而非「慢任务」信号。返回语义（not_found / already_terminal / leased / no_handler / failed / succeeded）保持不变。
- 修复二（`jobs/reconcile.py` 新增）：对账扫描捞两种无主作业——① `running` 且租约已过期（worker 死了）；② `pending`/`queued` 且超过 5 分钟无人认领（队列项丢了）。捞到之后：**可恢复类型重排队**（受 `max_attempts` 与 `available_at` 约束，入队前先提交库事务，队列项丢失下一轮按宽限期再捞），否则**落 failed** 并调用业务行收尾钩子，把业务行推到终态（前端停止轮询，用户看到「进程中断，请重试」）。
- 可恢复性按类型显式登记（不默认重跑）：`project.presurvey.analyze`/`ai.chat`/`ai.execute`/`file.scan`/`file.preview`/`document.generate`/`research.export` 可重排队——它们的 handler 都已跳过终态业务行，重跑不会覆盖已有结论；**`automation.execute` 不可重跑**（有对外副作用：发信、MCP 调用），死亡即落 failed 交人工重触发。
- 业务行收尾钩子（`jobs/handlers.py` 注册表 + 四处实现）：指引分析 → `analysis_worker_lost`；AI 会话 turn → `failed`（卡住的 turn 会让整个会话永久 `chat_busy`）；调研导出 → `failed`；自动化 run → `failed`。终态业务行（`ready`/`completed`/`succeeded`）一律不动——对账不许覆盖已有结果。
- 接线：worker 循环每 60s 扫一次（扫不出东西时零 DB 写）；另给运维留了手工口子 `flask reconcile-jobs`（容器被杀后可立即补投，不必等下一个周期）。
- 回归钉子：`tests/test_job_reconcile.py` 新增 15 例——租约过期重排队 / 活租约不动 / **被活 worker 行锁占住的作业被跳过（`FOR UPDATE SKIP LOCKED`）** / 孤儿 pending 重排队 / 新鲜 pending 不动 / 重排队后不热循环 / 次数用尽落 failed / 不可恢复类型落 failed / 指引分析与会话 turn 的收尾与「终态不被覆盖」/ 端到端（孤儿作业经对账后真的跑完）/ **认领状态对其他会话可见** / **执行期租约被续期**。

### AI 工具循环锁泄漏修复（生产事故回补，2026-10-30 晚）

- 事故：worker 跑 AI 聊天时工具调用撞 DB 连接断线，`_run_tools` 兜底吞掉异常继续循环，但共享会话带着未决事务与 `users` 表行锁停在 idle-in-transaction 十余分钟；登录路径的 `FOR UPDATE` 全体排队，gunicorn 超时杀 worker 又留下新的半死连接，锁滚雪球致登录 500。
- 修复：`server/src/fde_api/control/ai_tool_loop.py` 两处——① `_run_tools` except 分支立即 `session.rollback()`，工具异常不再让会话持锁过夜；② 主循环每轮工具执行完也 `db_session.rollback()`——工具循环工具全只读，回滚零损失，却保证下一次 provider 调用（最长 `timeout_seconds` 300 秒、零 DB 流量）不会骑在一个仍持有行锁的 idle-in-transaction 连接上（事故里 13 分钟的持锁窗口正是这个形态）。
- 回归钉子：`tests/test_ai_tool_loop.py` 新增 1 例（`OperationalError` 抛出时 `db.session()` 返回的会话在 with 块内恰被 rollback 两次：崩溃处理器一次 + 主循环每轮清理一次；17 例全绿）。
- 运维侧另两笔（无代码）：`pg_terminate_backend` 清锁 + worker 重启解堵；孤儿 pending 作业（outbox 已 dispatched、redis 队列项随重启丢失）手工 `RPUSH fde-jobs <id>` 补投。关联既有待办：台账 §八 第 1 条（进程死亡后无对账重排队）——已由本文件上一节的「后台作业死亡后对账重排队」落地，手工补投不再是唯一解法。

### 跨库只读验证脚本固化（G8）

- 新增 `scripts/verify/`（sql-queries 方法）：`run-verify.sh` + `verify-twenty-persons.sql` + `verify-n8n-executions.sql`——Twenty persons 总数/新增窗口/ICP 分布/去重命中，n8n 最近执行状态与耗时。连接参数全走环境变量（容器名/用户/库名，无口令：psql 在 db 容器内走本地 socket，脚本不读 .env）；每个会话显式 `BEGIN; SET TRANSACTION READ ONLY; … ROLLBACK;`；SQL 经 stdin 进容器（中文不走 argv）；输出仅计数不含客户明细。
- 口径：ICP 从笔记标题「冷邮件草稿 (ICP N)」提取每人最高分（≥70 培育 / 55–69 留档双层）；去重命中 = 同主邮箱挂多人（期望 0）。
- 宿主实跑一次并记录计数摘要到 `docs/验证脚本-G8.md`：persons 75（7d 新增 64，ICP 记分 9 全在 55–69 留档档）、重复邮箱 0（去重有效）、公共管道 4 成功（均值 27s）、QFhunterFeed01 2 成 3 败（运维信号，仅记录）。

### 意图差距审计（G7）

- 新增 `docs/意图差距审计-G7.md`：以 G2 七份意图文档 + AGENTS.md 红线为基线，逐边界核对代码执行点。**B1–B4 零差距**——门禁证据只收指针+64 位 hex sha256（`gate_service.py:520-548` + `workbench/models.py:544-547`，无 blob、无上传路由）；confirm 只能 canManage（`service.py:174-180` + `api_catalog` 零 guidance 条目，AI 无代拍板面）；bridge-poll 唯一进程出口是两个 openfde 只读子命令（`bridge-poll.mjs:68,101,110`，无写相 CLI、真相层零写面）；.env 不入 VCS 有可校验闭环（`.gitignore:1-5` + 全树仅两个 example 被跟踪 + gitleaks PASS 盲区规则）。
- F1 [P2→已处置]：「origin 永不 push」原本只有文档约束、无本地强制——本机已加 `git remote set-url --push origin FORBIDDEN-origin-is-upstream-use-fork`（push 必失败已实测，fetch 不变）；每台新克隆须重复，建议进 README 初始化节（台账十.1）。
- F2 [P3→已修]：G4 重写 `jobs.py` 使意图文档 4 处行号引用漂移、步骤 4 语义未反映自动重试——《系统意图-关键流程》《系统意图-自动化面》已同步更新。
- 台账新增第十节。

### 真实浏览器 UI 回归 harness（G6）

- 新增 `desktop/gui-harness/`：纯浏览器驱动 renderer 的回归 harness。dev-only Vite 配置（端口 5199）注入 `window.fde` 桥 shim（登录/刷新/`ApiResponse` 信封、deviceLabel→device_label 转换、401 刷新重试；`app.version` 返回裸字符串——三处契约此前只有 Electron 真机能验证），同源 `/api` 代理到 127.0.0.1:8010（浏览器有 CORS 而 Electron IPC 没有），并给生产 CSP 打 dev 补丁（`connect-src 'self'`、`style-src 'unsafe-inline'` 供 Vite 开发样式）。不引新依赖，不进打包产物。
- 新增 `desktop/gui-harness/regression.mjs`：仓库自带 playwright-core + 已装 Chromium 驱动两条链路 11 个断言点——①指引链：登录→项目→查看预调研分析→**只读 draft 态直接出现「确认并用于项目指引」按钮（R11 事故防线，浏览器实测通过）**→弹窗内编辑；②集成桥页：侧栏进入、状态文案、「立即采集」按钮在浏览器 harness 下被平台守卫拦为 `bridge_platform` 错误提示（与真机同代码路径）、采集反馈区可见；截图留本地（已 gitignore，含本机路径与项目代号）。
- 新增仓库技能 `.agents/skills/fde-gui-regression/SKILL.md`：harness 原理、启动/种子/运行命令、fixture 陷阱（enterprise_code 需两个「·」、module_keys 必须命中 ModuleCatalog）、断言口径与已知坑（hash 路由需点侧栏、Vite 单实例、中文经 `\uXXXX` 转义）。
- 回归报告 `docs/GUI回归-G6.md`：11/11 通过表、R11 防线结论、2 条 P3 finding（认领入口失败静默无提示——已记台账第九节；命名约定再次复核，与台账七.3 同源）。

### 代码评审门与回溯评审（G5）

- 新增 `docs/代码评审-G5.md`：PR #24 的参与者约定法评审报告（scope/dimensions/findings/coverage，含 9 条保留 finding 与 6 条驳斥成立的丢弃候选）、PR #17/#18 回溯评审、WP-B Serper 修复说明。
- 评审修复（随 PR #24 提交）：DSH 路径的裸 `JSONDecodeError`/`ControlServiceError` 逃出错误分类 → 结构化输出失败现在落 `ai_output_invalid`（可重试）/配置类不可重试，DSH 部署形态下重试能力不再静默失效；重试耗尽文案只在终态错误可重试时才劝「请重新发起分析」；存储对象缺失归入专用码 `source_object_missing`；限流/超时类瞬时错误重试前退避（契约失败不退避）；本地 DOCX 解析失败按确定性改为不可重试（存储读取 `OSError` 仍可重试，供应商侧提取失败不变）；重复投递不再对已终态分析二次调用 AI；每次尝试用独立请求号（上游去重不会挫败重试）；`python-docx` 声明下限提到 `>=1.2`（样本生成器用了 1.2.0 才有的 `add_comment`）。
- 新增回归钉子：重试语义 +7 例（请求号独立/退避双向/不可重试终态文案/存储缺失分类/终态守卫/任务仍为绿）、DSH 分类 +2 例。
- 回溯评审 PR #17/#18 发现 3 条（台账第七节）：PATCH 成功而 confirm 失败后前端版本与库态分叉致重试必 409（P2）、审核面板内无旧版源警示、认领命名约定无服务端保障。
- WP-B 修复交付（获客引擎 `AI_Find_Customer`，独立分支 `fix/serper-region-iso-codes`，commit 2c51e1a；其 origin 为上游仓库，不推送）：`_REGION_GEO` 由表自身 `gl` 值反查建 ISO-2 索引，ISO 码（US/CA/DE）不再落空致 Serper maps 400；键归一（下划线/连字符→空格）；命中失败打 warning（此前静默降级为全局搜索正是 400 无人察觉的原因）；引擎 +6 例，全量失败集合与改前逐条一致。

### 指引契约失败自动重试加固 + 对抗 DOCX 样本（G4）

- `server/src/fde_api/guidance/jobs.py`：预调研分析任务内自动重试——`GUIDANCE_ANALYSIS_RETRY_LIMIT = 1`（不含首次，测试钉死）。可重试失败（retryable=True 的 KimiError / GuidanceContractError 契约违反，即 MiniMax 概率性不守 JSON 合同的已知现象）先自动重试一次，仍失败才落 failed，failure_message 携带「已自动重试 N 次仍失败」的用户可见提示；不可重试（如 ai_service_not_configured）一次即败不消耗额度；source_missing 在构造 AI 客户端前拦截（零 AI 调用）；新增兜底分类 analysis_unexpected_error——未预期异常不再让分析卡在 analyzing（前端会无限轮询），且消息不携带异常串。每次尝试重新打开文件流。
- 对抗 DOCX 样本生成器 `server/tests/fixtures/presurvey/generate_fixtures.py`（9 种：空文档/空表格/合并单元格/批注/异常样式/缺失章节/超长段落/嵌套表格/非 ZIP 字节流；python-docx 1.2 程序化构建 + document.xml 最小注入），session 级构建到临时目录，二进制不入 git。
- 新增 `tests/test_guidance_adversarial_fixtures.py`（11 例）：两层解析（guidance 块抽取 / 本地全文提取 / Kimi 本地提取分类）对 9 样本的行为契约——畸形输入绝不崩溃、空内容失败为可分类错误（kimi_file_extract_failed retryable=True）、合并单元格全文层按 _tc 去重且块层按格位稳定引用、批注不泄漏进提取文本、异常样式不阻塞提取、嵌套表全文层递归可见（块层不可见，钉住两层差异）、超长段落整体提取。
- 新增 `tests/test_guidance_retry.py`（9 例）：重试语义钉子——契约失败重试一次后成功 / 耗尽后 failed 带 ai_output_invalid 与自动重试提示 / 调用次数恰为上限+1 / 不可重试一次即败 / 真实提取路径吃空表格样本落 kimi_file_extract_failed / source_missing 零 AI 调用 / 未预期异常落 analysis_unexpected_error 且消息无异常串 / 成功路径一遍 ready。
- conftest 清理清单补 `ProjectGuidanceAnalysis`/`ProjectPresurveySource`（此前测试库跨用例残留指引行会顶住 RESTRICT 外键清理）。

### 验收场景矩阵与缺口补测（G3）

- 新增 `docs/验收场景矩阵-G3.md`：指引链 / 集成桥手动采集 / SES 发信策略三链场景表（目标/起始/角色/分步/预期），每条映射钉住它的测试。
- 指引链补测 `desktop/tests/renderer/guidance-chain-scenarios.test.tsx`（8 例）：分析中→ready 自动开审进编辑态、failed 面板 role=alert 可见且无确认按钮、start() 失败 inline 可见、cancelled/queued/extracting 参数化占位展示、confirmed 卡片摘要 + `source_is_stale` 旧版重分析横幅（ProjectGuidanceCard 此前零测试）；集成桥链核对后无缺口（既有 13 例已覆盖全回路，platform 显式注入 win32/linux）。
- SES 策略先行 `server/src/fde_api/mailing/policy.py` + `server/tests/test_mailing_policy.py`（27 例）：四态分类（仅 throttle 可重试）、幂等闸门（同 message_id 判 duplicate 且先于限额/抑制）、每日限额（沙盒默认 10 可配）、总开关（未启用一律 drop_disabled）、发信域约束（仅配置子域，主域 somwyn.com 拒绝）、指数退避封顶——纯逻辑零 AWS 依赖，G9 在其上接客户端与 SNS 回调。
- 发现并记台账：cancelled 终态在审核面板仍显示「分析正在后台继续」占位（文案缺陷）；start() 失败提示不透传 failure_message 明细。

### 系统意图文档基线（G2）

- 新增 7 份意图文档（`docs/系统意图-*.md`，shipping-artifacts 方法，README 仍是部署唯一权威、交叉引用不复制）：架构与信任边界（根文档）、关键流程（预调研指引链/门禁/报价收款三链含鉴权点与 deny 例）、权限矩阵（三套角色体系 × 15 资源域）、变量与密钥（变量名×来源×轮换×风险，只写名不写值）、测试覆盖地图（现有 948+496+14 用例 / 建议 / 缺口三段）、定时任务（worker/scheduler/宿主 FDE-Bridge-Poll）、自动化面（AI 助手工具面/预调研管道/集成桥/任务中心，App 拥有副作用原则）。全部条目引用代码位置，作为 G7 意图比对基线。

### 内置手册与 UI 帮助 parity（PR #19）

- `help_manual.md` 补收「实操示例：证据文件怎么写（somwyn 样板）」整节与 G↔S 阶段映射（此前只在桌面端 HelpPage，help_fetch 检索不到）；新增双手册主题 parity 测试与 G↔S 映射与 `seeds/gates.json` 一致性测试，防两份手册再次分叉。

### 仓库级操作技能（G1）

- 固化 3 个仓库级 Agent 技能到 `.agents/skills/`（skill-creator 规范，随仓库分发）：
  - `fde-package-verify`：便携版打包全流程——electron-builder 产物 → asar sha256 → 中文 marker 字节验证（防控制台编码假阴性）→ 换新目录命名 r N+1 交付。
  - `fde-bridge-capture`：集成桥手动采集 runbook——`schtasks //Run`（Git Bash 双斜杠）或桌面「立即采集」按钮（同一代码路径）、`logs/bridge-poll.log` 验证到站、改 server 必须重建镜像、采集器只读纪律。
  - `fde-delivery-flow`：标准交付流检查单——分支 → push fork（永不 origin）→ PR → 4 CI 全绿 → 合并 → ff 本地 main → 删分支，每步验证点与常见事故对照。

## [未发布] — goal-r2 第二轮（2026-10-28）

安全口子、假绿灯与跨机口径一轮。**版本号未升**（按发布列车统一处理）。

### 安全（批次 G）

- **清除已入库的明文数据库口令**：备份脚本里的三条口令字面量（两条不同口令）已从工作树删除。凭据随 `2f90484` 入库，**视为已泄露，需人工轮换**（见交接清单）。
- **范围外备份管道移出仓库**：与 FDE 交付线无关的 n8n/Mautic/openoutfind 备份脚本迁至 `D:\test\AI外贸获客\scripts\`（副本 sha256 校验一致，仓库内可由 `git show 2f90484:scripts/backup-pipeline.sh` 恢复）。
- **集成桥读接口收敛门禁**：`GET /bridge/engagements`、`GET /bridge/status` 此前只要求登录（任意用户可枚举全部项目名与企业代号），现与写接口同级要求 `project_lead`。
- **登录限流键改为「用户名 + 来源 IP」复合键**：此前单个 IP 连错 5 次即可定向锁死任意用户名（含 admin）。Redis 不可用时记 WARNING（可观测），并可用 `FDE_LOGIN_RATE_FAIL_CLOSED=1` 切为 fail-closed。
- **秘密扫描线自证有效**：实测默认 gitleaks 规则对 `*_PASS=` 形态**整体漏报**（历史口令与随机探针同形态却一个抓一个不抓），新增 `.gitleaks.toml` 兜底规则与 `scripts/check-secret-scan.sh`（含 `--self-test` 哨兵自测）。

### 假绿灯（批次 H）

- **mypy 基线改计数法并纳入 tests**：旧实现按「文件+错误码+归一化消息」去重，实测 45 条基线条目掩盖了 181 次同类新增。
- **代号化检查不再吞错**：grep 退出码 1（无命中）与 ≥2（错误）区分；邮箱策略真正读取 `FDE_PSEUDONYM_EMAIL_POLICY`（缺省 fail）；黑名单提取 0 条即 FAIL；psql 失败不再当 0 行；`projects` 表 0 行即 FAIL（空库扫描等于没扫）。
- **CI 代号化 job 先迁移灌数再扫描**（原为空库扫描）。
- **冒烟脚本补真实断言**：auth 冒烟新增跨用户名隔离断言，commercial 冒烟种子管理员 try/finally 清理并断言归零。

### 跨机口径与运维（批次 I）

- pre-commit 三个钩子改走跨平台 node 入口（不再写死 Windows venv 路径）；README 更正 `.env` 模板来源与 venv 跨平台表述；操作手册路径参数化。
- compose 四服务统一 `restart: unless-stopped`；api healthcheck 改走 `/api/v1/health/ready`（真正校验依赖）；worker/scheduler 新增基于 Redis 心跳的 healthcheck（进程还在 ≠ 还在干活）。

### 打磨（批次 J）

- 业务枚举（价格档位 / 门禁五态 / C 分支 / SOW / 业务阶段）改由服务端 `GET /api/v1/workbench/options` 下发，前端保留本地兜底；存库值一律不变（旧中文标签数据照常可读）。
- 门禁汇总徽标改为按实际状态遍历（此前硬编码五态，服务端新状态会被静默丢弃）。
- 新增交付审计专用表 `document_delivery_records`（+ 迁移 `f3c8d2b7a1e5`），交付记录可按项目维度检索。
- C 分支触发档位收敛为单一常量；B 层分上下界都夹；扩展中心路由加角色门禁；预调研与调研导出的轮询失败对用户可见且失败后继续下一轮。
- **项目指引审核入口补缺**：指引卡片挂载时自动认领「已上传但尚未确认」的预调研源——此前分析/审核入口只在本次会话内上传后才出现，服务端（定时任务/历史会话）跑出的待审核指引在界面上没有任何入口；空状态文案同步提示审核入口。
- **指引审核弹窗只读态可确认**：确认按钮此前只在编辑模式渲染，用户从「查看预调研分析」进入的只读预览没有确认入口（得自己发现右上角「编辑」才能确认）；现在只读草稿底部直接显示「确认并用于项目指引」。

### 智能助手知识（help_fetch）

- 智能助手此前只拿到会话历史，「使用帮助」栏内容它一无所知（手册只在桌面前端渲染，服务端镜像里没有）。本轮把 `docs/工作台操作使用手册.md` 随 `server/` 源码烘进镜像（`fde_api/control/bundled/help_manual.md`），新增只读工具 `help_fetch`（按章节检索手册原文，带目录与分页），任意 AI 级别可用；对话入口注入工作台式 system prompt，引导「先查手册再作答」；新增公共 Skill `workbench-help`（`flask seed-public-skills` 灌入）。桌面「使用帮助」页同步注明智能助手内置同一份手册。

### 口径

- 服务端数据表 **73 → 74**（本轮新增 `document_delivery_records`）；迁移头 `e5b8a1c9d3f7` → `f3c8d2b7a1e5`。

## [v0.2.0] - 2026-10-26

交付流程与安全加固版本；桌面端与服务端版本号同步升至 `0.2.0`。

- 新增**门禁引擎 G1–G9**：pending → evidence → passed/failed 状态机（G9 支持 conditional_pass）；证据仅保存 `source_uri` 指针与 sha256 指纹，真实文件留在项目工作目录；claimed 与 accepted 分离。
- 新增**报价 / 收款（里程碑）/ 合同**商务看板与标准 FDE 项目模板派生。
- 项目工作台新增「门禁」「报价收款」页签；新增集成桥（本地 openfde / fdeops 工作目录的只读投影）与任务中心。
- 集成桥页新增「立即采集」按钮：桌面端一键触发宿主计划任务（与 4 小时周期同一代码路径），新快照到站自动刷新，无需等下一个采集窗口。
- 桌面端新增内嵌「使用帮助」：各模块操作说明、门禁 G1–G9 流程、实操示例与故障排查。
- 安全加固：登录连续失败限流（Redis 计数）、refresh token 轮换与改密即失效、API 容器非 root 运行、门禁证据哈希校验、CI 常驻 gitleaks 秘密扫描。
- 工程卫生：CI 并发取消与四 job 超时上限、pip/npm 缓存、全仓 LF 归一化、测试口令字面量收敛单点。
- README 按当前功能与 Docker Compose 部署路径重写，新增换机迁移清单。

## [v0.1.0] - 2026-09-28

首个开源源码版本。

- 提供 Electron 桌面端、Flask API、数据库迁移、后台 worker 与 scheduler 的源码。
- 提供项目、任务、调研、AI 机会、方案、交付文档、文件和管理员配置等工作台功能。
- 清理历史业务数据、客户资料、运行日志、访问凭据、对象存储文件和发布备份；仓库只保留通用示例与模板。
- 移除客户端自更新功能。升级需由部署者自行部署后端、执行迁移并重新打包客户端。
- 提供 MIT 许可证、安装部署说明、贡献指南和安全报告说明。

当前仅配置 macOS Apple Silicon（arm64）DMG 构建；没有 Windows 客户端。此版本是源码发布，不附带已签名、公证的安装包。公开部署前请更换首次登录密码和所有示例密钥，并阅读 README 的生产部署与安全说明。

本产品采用 vibe coding 方式开发；商用或处理真实数据前，应由部署者独立完成代码、安全、合规及业务适用性核验。
