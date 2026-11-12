# goal-crv r1 轮记录：权限、身份与平台控制（终稿）

> 循环：goal-crv ｜ 轮：r1 ｜ 域：权限·身份·平台控制 ｜ 审查时点基点：`35ffbea7861476e5ea197487623bd5fb75219b43`（fork/main 顶）
> 审读方式：CreateWorkflow 四片（60 文件逐行读档，run `dwfrun-86fc45b1`）＋主会话直审（39 文件逐行读档）
> **结论一句话**：权限/隔离核心面（permissions/events/orgs/decorators 可见性与越权闸）总体扎实、双层钉覆盖厚；真实缺陷集中在**身份周边闸的单点缺口**（登录限流键未归一化、change-password 状态闸缺口、渠道闸更新面漏挂、N5 绑定闸死代码）与**系统配置/调度面健壮性**——P1×4／P2×16／P3×3（合并 14 锚点），零 P0。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：99 文件**（分配表 r1 主域全部 14 条目闭合，无一遗漏）＝工作流四片 60 文件（四份 ShardReport files 清单在案：隔离与权限核心 12＋认证身份与健康面 13〔含 decorators 辅助＋9 个测试钉核查文件〕＋平台控制AI与自动化面 18〔含交叉核读与钉核查〕＋项目业务核心 8…按被审面计 51 源文件＋钉核查测试文件）＋主会话直审 39 文件（app.py/config.py/errors.py/control 杂项 21/workbench 5/modules 3/templates 3/root __init__/orgs·users·projects·modules·templates __init__ 等）。
- **抽查：0** ｜ **没读：0**（主读面全集逐行闭合；「逐行读档 ⊇ 分配表该域主读面全集」成立）。
- 分片审读员合规声明四份在案（工作流 run 记录）：零执行被审面、零写文件、未读 server/.env/.env/仓外真相层、摘录无密钥值；四片各附「已驳回候选」清单（隔离片 10 项、项目片 14 项），供复核免重查。

## 2 QR 台账（r1 增量 · 单一真身在总报告附录，此处为摘要指针）

**本轮新增 QR-001～023**（总报告「附录：QR 台账」为逐条真身）。摘要：

### P1（4 条，全部 E0 双证据过闸）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-001 | auth/routes.py:37 | 登录限流键用未归一化原始用户名——NFKC/大小写变体轮换绕过 5 次失败锁（双证据：键拼装代码＋服务层 normalize 对照＋钉核查 8 例全单形态） |
| QR-002 | auth/service.py:244 | 被停用（suspended）用户持活体令牌经 change-password 无限续签——`_issue_token_pair` 三调用点唯此处缺 `_registration_state_gate`（grep 闭集＋suspend_registration 不动 is_active 实证） |
| QR-003 | control/api_actions.py:196 | N5 票据绑定闸死代码——scoped 会话下 agents.run_start 在 `_authorized:124` 先一步 403，闸两分支皆不可达（判级存疑注：若「scoped agents 腿不可用」为有意语义则降 P2） |
| QR-004 | projects/service.py:380 | PATCH enterprise_code 绕过 H2 私单封堵与 G4 商机保护闸——`ensure_enterprise_channel` 全仓仅 create_project/create_quote 两调用点（grep 闭集），更新面零复跑 |

### P2（16 条，全部 E0 锚点确认）
QR-005 敏感键闸窄于审计侧超集（access.py:18，privatekey/sessionkey/accesskey 三族缺口；注：下划线形态两侧均不拦，分歧限于连写键）｜QR-006 automation once 过去时间创建即执行，与任务板 re-activate 409 口径矛盾（service.py:406；判级存疑注：若「创建即补跑」为有意语义降 P3，矛盾仍须闭合）｜QR-007 登录限流 INCR/EXPIRE 非原子→半途故障永久 429（routes.py:60）｜QR-008 confirm_throttle 零 Redis 故障处理→12+ 消费点 500（confirm_throttle.py:28）｜QR-009 system_configuration `_decrypt` 吞错→PUT 永久清空已存密钥（:94）｜QR-010 PUT gating 失败提交半初始化行（:197）｜QR-011 None 落库＋`_apply` 静默不生效（:141）｜QR-012 `completed` 不在 AI 确认敏感态集——项目终态可被 AI 无密码执行（api_actions.py:213；涉 C 款记账口径）｜QR-013 chat running 态重入双跑付费调用（chat.py:170；判级存疑注：DSH 侧幂等性独立部署无法核实）｜QR-014 ai_tool_loop 执行侧无只读白名单复查＋降级授权宽于任务授权集（ai_tool_loop.py:111；判级存疑注：可降 P3 口径漂移，三处书面契约与现实不符独立成立）｜QR-015 scheduler 毒丸任务每轮崩整批调度＋同拍治理作业全停（scheduler.py:92＋cli 调度循环零隔离）｜QR-016 单边变更证据字段→「新 uri×旧 hash」候选自动挂载（task_service.py:835）｜QR-017 单任务取消无下游依赖守卫，与 module 取消守卫不对称（task_service.py:330）｜QR-018 create_quote 的 H2 渠道闸在行锁前用未锁快照判定（quote_service.py:249；与 QR-004 同根因，修复须联动）｜QR-019 mark_acceptance_passed 排除闸冒泡把到账回填整体 403（payment_service.py:297；判级存疑注：若 payee 全排除系设计意图降 P3 补 docstring）｜QR-020 is_delivery_party 判据把 leader/admin 误标交付方——G8/G9 拍板被误收窄 admin-only（gate_service.py:314；**E0 从严升档 P3→P2**：行为与注释规格直接矛盾且注释自称「管理位视为平台侧」）

### P3（3 条合并条目，14 锚点——§5 规矩 5 每域上限 3 条合并同类项）
- **QR-021 未捕获异常路径族**（3 锚）：system_configuration.py:198 并发首 PUT IntegrityError→500｜control/service.py:401 ZoneInfo 非归一化键 ValueError 绕过捕获→500｜control/chat.py:224 执行中删会话→写回 None 解引用 AttributeError（三处同族）
- **QR-022 口径与注释漂移族**（3 锚）：health/heartbeat.py:14 退出码契约漂移（docstring 承诺 2=Redis 断，实际恒 1）｜control/api_catalog.py:138 EXTERNAL_EFFECT_KEYS 注释宣称「不得无确认排队」但 4 成员中 2 个无确认｜projects/task_service.py:437 单任务取消不刷新项目/模块计划日期（与 refresh 自述口径矛盾）
- **QR-023 卫生与测试缺口族**（8 锚）：orgs/org_scope.py:60 归属戳 before_flush 内 session.get 解析不到 pending 对象（潜伏，当前调用面已有 flush 前置）｜control/task_board.py:90 与 control/service.py:355 双套清单实现无对账钉｜auth/routes.py:66 攻击者可控 username 未清洗入日志（换行注入）｜auth/service.py:294 RefreshSession 无任何 GC 路径（无界增长）｜projects/service.py:744 project_completion 死代码（仅测试调用）｜projects/service.py:1634 列表路径 N+1（依赖元数据结果被丢弃）｜control/extensions_service.py:806 重复 `except ControlServiceError` 死分支（直审发现并入）｜顺带：project_module_has_dependents 守卫零测试钉（并入 QR-017 修复）

## 3 清白声明与验证记录（E0 过程）

- **P1 四条双证据**：QR-001/002 锚点重读＋grep 调用点闭集；QR-003 闸函数体＋调用序重读；QR-004 全仓 grep 调用点闭集。P1 全部另附「既有钉缺口」grep 证据（钉核查面零变体/零状态/零 matched-scope/零 PATCH 用例）。
- **P2/P3 逐条锚点重读**：33 条发现全部主会话重读源码锚点在场（sed 区段实证），零剔除、零改判驳回；判级调整 1 处（QR-020 P3→P2 从严）。
- **分片清白亮点**（供总报告引用）：projects/permissions.py 双入口 parity 三轴一致有双层钉；auth/decorators require_auth 链完整（org claim 在场性 fail-closed、授权全读库）；orgs/isolation 三态 fail-closed 有钉；mcp_gateway/model_preferences SSRF 防线完整；dispatch 8 态机与 package_access 冻结区复扫零命中（goal-c8 冻结区维持清白）。
- **工作流**：run `dwfrun-86fc45b1-a8e5-4ad7-99d1-9755ff17b41b`，4 片并行（供应商限速下串行轮转完成），32 条 E1 → 主会话 E0 全量复核 → 23 条台账条目（P3 合并 + QR-020 升档）。

## 4 口径数字变化

零生产 diff 轮：路由 485／蓝图 52／表 153／rev 73 全不变。直审＋分片合计逐行读档 99 文件。

## 5 备注（不立 QR 的观察）

1. `DSHRuntimePool.execute`（dsh_runtime.py:201-209）app context＋enabled 分支走内部 `execute_ai_prompt`（purpose=dsh_runtime_execute）替代外部 DSH——分片 3 读 automation_jobs.py:101 调用面后定性为**开发替代形态**（内部路径带 purpose 归因与审计），维持备注不立 QR。
2. `decide_plugin_change` executor 外呼在 DB 事务内——代码以内联错误信息承认非原子，重试语义依赖 executor 幂等；设计接缝备注。
3. 基线跑测注记：本地全量 pytest（2026-11-13）collected 3481，跑至后段出现大量环境性 E/F（CI 同提交 server-tests 绿＝`43283859901` server-tests success）——归因环境非代码，详见总报告基线节与 PROGRESS.md 处置记录。
4. CI 归因：main run `43283859901` desktop job 红＝`ai-server-chat.test.tsx` 计时敏感单测 flake（同 run 其余三绿、提交为纯文档）——按 §7 归因闸不计连败。
