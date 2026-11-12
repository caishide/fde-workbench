# goal-crv r5 轮记录：dispatch、workflow 与 agents 编排执行域（终稿）

> 循环：goal-crv ｜ 轮：r5 ｜ 域：编排执行（dispatch 21＋workflows 14＋agents 28＋solutions 5＋handover 4＝72 文件，全仓最大域 ~20K 行）｜ 审查时点基点：`35ffbea`
> 审读方式：CreateWorkflow 四片（45 文件逐行读档，run `dwfrun-ac1770b7`）＋主会话直审 27 文件（agents 卫星面 16＋workflows draft_ai＋solutions 4＋handover 4＋constants 等）
> **结论一句话**：goal-c8 冻结区（8 态机终态不可逆/match·match-ai 双来源闸唯一/offers 落库闸）复扫维持清白、workflows CR 旧修面（CR-013/014/019/020/022/B#1）逐点回归在位、solutions 三承诺（organize 零落库/SOW 冻结/弃用密码闸）钉在位、handover 状态机 CHECK 完整；真实缺陷集中在**资金侧预扣链**（QR-071 税务义务缺口）、**编译产物契约断裂**（QR-072）、**宿主通道产物路径盘符逃逸**（QR-073）与并发/授权一致性面——P1×3／P2×22／P3×3（合并 24 锚），零 P0。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：72 文件（全域闭合，无一遗漏）**＝工作流四片 45＋主会话直审 27。agents/service.py 1763 行单批全读；attribution 级大件均分段覆盖。
- **抽查：0**｜**没读：0**。
- 四片合规声明在案（零执行/零写/未触禁区）；分片审读员对多条发现内嵌二次锚点重读（nailCheck 载明）；主会话 E0＝P1×3 双证据重读＋P2 载重锚点 12 条逐一重读（settlements:98/packages:464/rules:113/wf-dispatch:263/def-svc:569/svc:1254/host_channel:156/context:169/adapter:212/host_receipt:91＋grep promote_user/revoke_package_access 调用点闭集）＋其余锚点收口轮批量核锚兜底。

## 2 QR 台账（r5 增量 · 单一真身在总报告附录）

**本轮新增 QR-071～098（28 条）**。P1×3 见总报告 §5；P2×22／P3×3 摘要：

**P2（22）**：QR-074 seat_shares_for 对形状不合规快照 KeyError→收款事务 500＋scoring 静默 0 权（同根；三种消费行为不一致）｜QR-075 accept 主事务提交后 handover 失败 500 无补偿——offer 已 accepted 而成员未加，重试 409 死锁｜QR-076 offer 终态盲写（decline/expire 无包行锁，并发覆盖 accepted；判级存疑可 P3）｜QR-077 accept_package 绕 accept_offer 三道闸＋平台代接单不校验候选∈本轮 offer（张冠李戴 dispatch 侧；两片同报合并）｜QR-078 包授权只授不撤——revoke_package_access 全仓零调用＋撤销零留痕（白名单含方案/报价/席位金额；两片同报合并）｜QR-079 rules 并发激活可双 active（无 partial unique/无行锁）→ 撮合与分账口径漂移｜QR-080 project_lead 包写/读倒挂（能撤回看不见的包）｜QR-081 供给池入池与等级核验全链零生产调用方——Stage A 池恒空（CR-027 同型；判级存疑可 P1）｜QR-082 L0 对账应计聚合无 status 过滤（draft/disputed 计入，与 docstring 口径漂移）｜QR-083 workflows _dispatch_skill 跨 namespace 取行＋scope.desc() public 压 personal——pinned 显式版本承诺被打破｜QR-084 start_run context 无大小上限（DB 膨胀＋AI 成本无界）｜QR-085 定义 update/publish 无锁——并发交错产生「published 版本行缺失」→ run 恒 409｜QR-086 retry 授权读发起时旧档、执行记当前档——调档窗口授权与能力脱钩｜QR-087 retry 不复查包准入（agent_assisted_required/O-4）与 T6 门——预算/pilot 都复了、这两个漏了｜QR-088 claim_host_run 带 run_id 无行锁无条件赋值——并发双领取双执行｜QR-089 claim 载荷 allowed_tools 实时读 registry——「随 run 冻结」契约失守（无快照列）｜QR-090 receipt ask run_id=None 使联合唯一失效——并发双审批单（CR-045 同族续注）｜QR-091 host_channel「exit 0 但汇总不可解析」落 failed 可重跑族——与 B#2 不对称（判级存疑）｜QR-092 host_channel env=dict(os.environ) 全量继承——平台密钥族进 run 进程（判级存疑）｜QR-093 context severity/module 渲染未过 _clean——盘符/密钥模式原文进沙箱｜QR-094 adapter done 分支无 break——终态可被同批后续事件翻转（completed→budget_exceeded 产物丢弃）｜QR-095 host_receipt exit_code 缺省按 0＝缺省即成功（与容器面保守语义反向；判级存疑）

**P3（3 条合并 24 锚）**：QR-096 dispatch 并发 500 与状态死角族（offer 查重竞态/幽灵 id 500/allocate_five_seats 并发/disputed 死巷/rules due 无 order_by）｜QR-097 真身与呈现族（replay 无规则版 0.0/match-ai decision sha 不绑生成事件/capacity 公式三处/_rank_readonly 第二实现/promote 无锁/models 注释引不存在符号/wf context 覆盖默认键/_begin_node KeyError 冒泡/条目标题花括号 422）｜QR-098 agents 卫生族（retry 骨架丢失/succeeded_but_receipt_invalid 指引矛盾/handoff 事件 fallback_level 硬编码/recover 漏标/receipt DSL 四函数零接线/sandbox 子网碰撞＋失败无 teardown/routes docstring 11≠17/host_receipt docstring 与实现矛盾/超长 path 截断撞唯一索引永久 500/AgentCredential.name 无唯一约束）

## 3 清白亮点（供总报告引用）

- **goal-c8 冻结区维持清白**：8 态机终态不可逆（TRANSITIONS accepted 无出边）＋withdraw offer_in_flight 闸；match/match-ai 并列双来源闸唯一（AI 腿零 dispatch_offers 落库、decision 纯事件端点、场景 C 零烧费）；offers 落库闸（乐观锁＋时限＋包行锁＋同轮互斥＋sibling 释放，并发单赢家有钉）。
- **workflows CR 旧修面回归全绿**：CR-013/014/019/020/022/B#1 hops 熔断逐点在场；recovery 断链收敛闭环；models 四表约束与查询面匹配。
- **solutions 三承诺**：organize 零落库（saved:False 钉）／SOW 导出冻结方案版本（同版本唯一约束＋TOCTOU 闭合）／弃用密码确认（403 钉）；review-trail 隐私纪律（排除个人备注）。
- **handover**：draft→sealed→delivered 状态机一致性 CHECK 四条＋manifest 规范化哈希＋跨项目封包拒绝＋delivered admin 专属不可逆。
- **agents 卫星面全清白**：execution_grants（域分离派生＋最小动作集＋指纹不落本体）／execution_authorization（HMAC 闭集＋compare_digest＋TTL 钳制）／execution_policy（resolve 防逃逸＋拒绝清单＋命令锚定）／artifact_content（指纹自证 503＋413 不截断＋防穿越）／credentials（平台闸＋Fernet＋名字白名单）／host_egress_proxy（⑦出站闸白名单审在 DNS 前＋CONNECT 403＋审计只记域名）／pilot 闸／lessons（污染阀＋软失败）／review_signals（只元数据）／seeds（PM-2 前缀）／signoff（advisory lock 幂等）。

## 4 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 5 备注

1. **CR-028 续注**：QR-071 为 settlements.py compute_withholding 调用侧守卫新角度（CR-028 原条＝UTC 年/调用时月两处实算误差）——按规矩 4 引用续注。
2. QR-072 缓解面：compile_delivery_preview 当前零生产调用方（grep 闭集）——接线前修复即可；已采纳落库的存量定义同批受害。
3. QR-073 暴露面判据：AGENTS ⑦出站闸两键仅被 host_channel 分支消费——部署态若仅 host_poll（指纹直录不回读）可降 P2；按禁区未读 server/.env 不猜，留蔡工核证。
4. 判级存疑 7 处如实标注（QR-073/076/078/081/091/092/095）；结构性零调用方事实（mark_payable/mark_paid/allocate_five_seats/dispatch mark_disputed/transition assign 均零生产调用＝结构就绪·待授权态）已按授权层口径处理，不虚报为运行缺陷。
