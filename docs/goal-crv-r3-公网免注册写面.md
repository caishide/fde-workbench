# goal-crv r3 轮记录：公网免注册写面（终稿）

> 循环：goal-crv ｜ 轮：r3 ｜ 域：公网免注册写面（diagnostics＋registration）｜ 审查时点基点：`35ffbea`
> 审读方式：CreateWorkflow 四片（17 文件逐行读档，run `dwfrun-4417d794`）＋主会话红线横扫（gate-first/404、令牌指纹、限流分立、零外键、consent——四片交叉核+主会话复核）
> **结论一句话**：红线 10 条专项逐条核对——**令牌只存 sha256／零外键指向 projects／consent 硬闸／认领四闸（串行）／claimed≠accepted／归因服务端推导／比例只在配置面／404-not-403 全部在位且有钉**；真实缺陷集中在**数据生命周期声明与执行脱节**（联系方式脱敏成占位符、30 天留存期零执行）与**可见性/并发边界**——P1×4／P2×7／P3×3（合并 9 锚），零 P0。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：17 文件**（分配表 r3 主域 2 条目 `diagnostics/registration` 全闭合）＝工作流四片（诊断核心服务 4／诊断报告与作业面 4／线索认领与渠道面 3／注册面与诊断路由 6）＋主会话红线横扫（grep 404 语义/零外键/consent/限流分立执行点——结果与四片交叉核一致）。
- **抽查：0**（验证性摘读在 ShardReport notes 如实标注，不计入逐行档）｜**没读：0**。
- 四片合规声明在案：零执行、零写、未触禁区（fde-ops 官网落地面不可证处已如实标注判级存疑）；「已核不报」与「设计态不报」清单留档（R2/R4 自报身份 P-6 拍板态、CLAIM_STATUSES withdrawn 预留、_bump 非原子当日残留）。

## 2 QR 台账（r3 增量 · 单一真身在总报告附录）

**本轮新增 QR-041～054**。摘要：

### P1（4 条，E0 双证据过闸；两片同报已合并）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-041 | diagnostics/service.py:490 | 留资联系方式被脱敏管线替换成占位符——手机/邮箱落库即变「[手机号已脱敏]」，明文全系统零落点；service.py:504 与 claim_service.py:28-31 **两处书面设计都声明「明文仍在留资行里」**＝intended-vs-implemented 直接矛盾，A/B 档转化闭环下游无可拨号码。修法：①留资行存明文（给 contact 单独替换路径 mask_pii=False）或②库存占位符是隐私拍板（改两处注释＋给回访取号替代方案）——**需蔡工拍板口径** |
| QR-042 | diagnostics/service.py:416 | expired 死状态：30 天个保法留存期写入 expires_at 后全链路零消费——`status="expired"` 全仓零置位方（E0 grep 实证仅 CHECK 常量）、写动作只查 status、无清扫 job；留存期数据无限期保留＋过期可写（判级存疑：若留存期执行属 D-3 轻部署运维拍板待办可降 P2，但状态机声明可达而无可达路径从严 P1） |
| QR-043 | registration/routes.py:129 | 部署闸关时限流先于闸——IP 超限后 429 代替 404 泄露面存在（红线①「不确认面存在」；legacy G6 同型，修复须三处同改；判级存疑：429 是否算「确认面存在」可辩 P2，从严 P1） |
| QR-044 | diagnostics/claim_service.py:606＋lead_routes.py:121 | get_claim 单读无归属/角色检查——任何登录用户可读任意认领单（含裁定理由 decision_note＋自认领信号＋台账行），与 list_claims 两段可见性同域不同语义＝M3a 幽灵行家族（两片独立同报，E0 合并） |

### P2（7 条，E0 锚点全确认）
QR-045 report_contract.py:125 金额「X 万/亿」形态绕过数字闸——「万」不在 _UNIT_PATTERN ⇒ 处方层裸数字免检，与 v2 声明「金额与比例任何层必检」相悖（判级存疑：可辩 P1；补「节省 30 万」拒收钉）｜QR-046 service.py:479 name/region 自由文本绕过凭据扫描与企业名脱敏（与同端点 contact 不对称；region 原样给同区域 R4 看）｜QR-047 claim_service.py:190 「一线一线」闸并发洞——pending 检查与插入间无行锁无部分唯一索引，并发双 pending 可落库（accept 侧有锁有底）｜QR-048 claim_service.py:130 hash_ip 的 'unknown' 占位使无 IP 请求共享指纹参与自认领判定——跨主体误命中即强制 C 档零转化费（判级存疑：remote_addr 恒在场则降 P3）｜QR-049 registration/routes.py:66 incr/expire 非原子且键无日期后缀——expire 失败该 IP 永久 429（诊断面键含 :{day} 后缀同款后果弱化为当日残留——键设计差异是实质性的）｜QR-050 registration/service.py:298 enterprise 入口 display_name>160：org 先建后校验，DataError 不被 IntegrityError 兜底 → 500｜QR-051 registration/service.py:350 request_id 客户端可控无长度上限直落 operation_events（公网免鉴权＋无请求体上限＋无字段上限＝DB 膨胀纵深缺口）

### P3（3 条合并条目，9 锚点——§5 规矩 5）
- **QR-052 时效与口径漂移族**（4 锚）：policy_data.py:22 快照「超 30 天失效重核」无机械闸（2026-11-19 起超期静默继续供应陈旧政策口径）｜claim_service.py:432 台账「报备到期日」硬编码 90 魔法数未引用 CLAIM_WINDOW_DAYS｜service.py:217 enforce_session_quota getattr fallback=3 与 config 真默认 6 漂移｜claim_service.py:489 线索池 R4 区域过滤裸 == 与认领闸 _normalize 归一口径不一致（认得了的看不见）
- **QR-053 失败路径与令牌域族**（4 锚）：diagnostics/jobs.py:281 外层兜底复用失败事务态 session 无 rollback——report_unexpected_error 可能落不上（worker_lost 兜底缓解）｜channel_links.py:58 渠道链接 token 与匿名令牌共用指纹域（与 hash_share_token 自立「权限域不同⇒指纹域分开」纪律不一致）｜registration/service.py:383 验证链接明文令牌放 URL query 且本仓无 /verify-email 落地消费面（判级存疑：fde-ops 侧不可证）｜registration/service.py:391 寄信契约只覆盖 MailingServiceError——botocore 非 ClientError 穿透 → 注册已提交后 500
- **QR-054 死代码族**（1 锚）：registration/service.py:78 LOGIN_BLOCKED_STATES 死映射全仓零消费——与 auth/service.py REGISTRATION_LOGIN_BLOCKS 双源漂移风险

## 3 清白亮点（供总报告引用）

- **红线 10 条中 8 条全绿**（②令牌 sha256／⑤零外键／⑥consent／⑦认领四闸串行／⑧claimed≠accepted／⑨归因推导／⑩比例配置面／①404-语义在闸开时）——每条带钉；诊断面限流 fail-closed 与注册面 fail-open 分立无混用。
- accept_claim 并发正确性：claim+lead 双行锁＋accepted_other 复查＋同日序号唯一约束重试——锁序恒定无死锁面。
- 台账行代号化：build_ledger_row 零联系方式/姓名/真实企业名，十二列与 AGENTS 口径一致。
- report_contract 其余面清白：顶层键闭集/R-5 一一映射/R-2 政策层 fail-closed by construction/政策原文量值不作数字来源（D2 修复在场）/分享视图零原文零联系方式。

## 4 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 5 备注

1. 跨片移交项已收编：shard1 附加发现（expires_at 无执行）并入 QR-042；shard3/4 双报 get_claim 并入 QR-044；shard3 移交的 channel_ref >80 撞 varchar ⇒ 500 线索——**E0 裁定不立条**：诊断路由 channel_ref 双通道均限 80 字符（routes.py:58-61/:83-84，shard4 clean 项实证），create_session 服务层无校验但唯一调用面已闸，登记为纵深备注。
2. decision_note（员工侧输入）未过 _redact_text——非公网面，登记备注不立条。
3. 需蔡工拍板项：QR-041 修复口径（明文 vs 占位符）——二选一均需改书面声明或实现，needs-decision。
