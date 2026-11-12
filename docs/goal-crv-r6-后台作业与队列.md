# goal-crv r6 轮记录：后台作业与队列（终稿）

> 循环：goal-crv ｜ 轮：r6 ｜ 域：后台作业与队列（jobs 9＋mailing 6＋bridge 5＋cli/expirations/extensions/wsgi 3＝23 文件 3.5K 行）｜ 审查时点基点：`35ffbea`
> 审读方式：CreateWorkflow 三片（23 文件逐行读档，run `dwfrun-7e5e6760`）——全域入工作流无直审余量；主会话横扫（subject_org keyword-only 全量 26 调用点 ✓＋CR-016 现核）＋P2 载重锚点 7 条逐一重读
> **结论一句话**：subject_org 机械闸全量成立、outbox 失败方向安全有钉、reconcile 窗口数学自洽、mailing policy 24 钉一致、CR-016 现核与台账精确吻合（无第 5 类悬空）——队列核心纪律扎实；缺陷集中在**进程存活面**（worker 循环零隔离/心跳误判）、**mailing 并发面**与**bridge 锁覆盖面**——P2×7／P3×3（合并 11 锚），零 P0 零 P1。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：23 文件（全域闭合）**＝工作流三片（jobs 队列域 9／mailing 外发面 6／bridge 采集与 CLI 面 8）＋主会话横扫（subject_org 调用点全集 grep＋CR-016 handlers 现核）。
- **抽查：0**（佐证读——heartbeat.py/compose.yaml/bridge-poll.mjs fail() 语义/测试钉 grep——在 ShardReport notes 如实标注，不计逐行档）｜**没读：0**。
- 三片合规声明在案；CLI 域 storage-migrate-layout 之外命令面经 shard 1 循环段逐行＋shard 3 全文 482 行覆盖。

## 2 QR 台账（r6 增量 · 单一真身在总报告附录）

**本轮新增 QR-099～108（10 条）**：

### P2（7 条，E0 载重锚点逐一重读确认）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-099 | cli.py:190/198/204 | worker 循环三处零异常隔离——Redis/DB 一次抖动即整进程退出（try/finally 无 except 实证；QR-015 同族新锚：调度循环已报、worker 循环新面；本地裸跑无监督静默死亡） |
| QR-100 | cli.py:185＋worker.py:75-82 | 心跳把 >180s 合法长作业误判卡死——beat 只在循环顶部，handler 期间必 unhealthy（判级存疑：接 autoheal 即 P1；修法＝续租线程顺带 beat） |
| QR-101 | mailing/service.py:98-148 | 发送路径 check-then-act——幂等/限额先查后写、SES 外呼先行：并发同键实发两封＋后写撞唯一约束 500＋台账缺行 |
| QR-102 | bridge/sync.py:182/255-285 | advisory lock 只覆盖段①——注释声称已关的 reproject 覆盖窗口仍在（读在锁外）＋②③标 ok/retention 清理锁外新 session 并发互删 run 行致 AttributeError 500 |
| QR-103 | bridge/sync.py:58 | 缺轨/空轨快照判成功（ok=True）——存活集空集→投影全场 vanished 误报＋delete_projection「仍存活即拒绝删」守卫失效（判级存疑：现役采集器 fail()-exit 可达性低） |
| QR-104 | bridge/runner.py:131 | captured_at 格式校验只在 sync 层——客户端输入错误报成 500 sync_failed 且不落 failed-run 行 |
| QR-105 | cli.py:398 | storage-migrate-layout --limit 提前 return 跳过汇总与 fail-loud——分窗推进失败窗口以 exit 0 收场（违背自身「不一致⇒记账不静默」契约） |

### P3（3 条合并 11 锚——§5 规矩 5）
- **QR-106 jobs/worker 卫生族**（4 锚）：worker.py:174/222 last_error 无截断（outbox 注释宣称 2000 字同宽口径 job 侧不存在）｜worker.py:139 租约 token (pid, job_id[:8]) 跨进程碰撞（同 pid 双 worker 守卫失效；当前单 worker 潜伏）｜admin_routes.py:112 queue_depth 对 Redis 故障未降级→整面 500｜cli.py:168 worker --once help「单作业」实为 drain 全队列（文案漂移）
- **QR-107 mailing 卫生族**（3 锚）：service.py:233/291 SNS 证书/订阅 URL fetch 网络失败未归入校验失败——500 而非自契约 403｜service.py:127 本地事件 event_key 缺 attempt 维度（同键重试轨迹被折叠，与 models 注释漂移）｜service.py:152-164 抑制判定零归一（大小写漂移漏抑制；现役调用链已归一收敛，判级从严 P3）
- **QR-108 bridge 与投影卫生族**（4 锚）：runner.py:34 桥入站面（令牌门/白名单/错误契约/DELETE 翻译）零测试覆盖｜bridge/__init__.py:5 采集节奏口径自相矛盾（15 min vs sync.py 4h——差 16 倍）｜runner.py:92 status 键值零校验原样入库＋全仓无 MAX_CONTENT_LENGTH（体积纵深）｜expirations.py:99 api_confirmation 投影按「最近 500 条」截尾——最旧未决确认最先消失（方向与用途相反，应 NOT EXISTS）

## 3 清白亮点（供总报告引用）

- **subject_org keyword-only 闸全量成立**：主会话 grep＋shard 独立核对双证——26 调用点全部显式传参（含显式 None=平台级三处），ensure_background_job 唯一调用点无旁路；静态钉 test_m4_batch3_queue_subject.py:180 在位。
- **CR-016 现核**：14 个 handler 类型中无 failure hook 恰为台账原文四类（file.scan/file.preview/document.generate/ai.execute），无第 5 类业务行悬空——挂账精确吻合；automation/discovery 两类已接线注册。
- outbox enqueue 先 rpush 后 commit 失败方向安全（幻影条目无害有钉）；RECOVERABLE 重试幂等（T-J1 中间重试保持 dispatched 红线有钉）；reconcile due/orphan 窗口数学自洽（任何退避 ≤900s 必落入补投窗）。
- mailing policy 六组纯函数与 24 钉一致；发信域约束「主域不发信」三层落实（policy 归一＋pydantic 启动 fail-fast＋钉）；ses_client 三类 ClientError 映射完整。
- expirations admin-only 403/due 边界/CONFIRMATION_WINDOW 单一权威/零写纪律四钉；create_admin 幂等八钉。

## 4 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 5 备注

1. 关闭态口径裁决项（shard 2 移交）：mailing SNS 回调在 SES 关闭时 403 mailing_disabled（有钉）vs 仓库「公网免注册写面关闭=404」纪律——消费者是 AWS SNS 机器对机器、403/404 语义等价；若按纪律收口须同步换代 test_sns_route_disabled_403 钉——**needs-decision**。
2. policy.retry_allows/next_retry_delay 退避契约全仓零生产消费点（throttle 重试未实现）——接线时消费或显式放弃。
3. models.py:44-47 active_key 生成列 MySQL `||` 歧义（裁剪候选）——部署 PG-only 纯潜伏，文档勘误随修复批。
4. registration/commercial 在 HTTP 请求内同步调 SES（分钟级最坏阻塞）——r3 已审 registration 面，此处备注不立条。
