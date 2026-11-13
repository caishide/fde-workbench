# goal-crv r2 轮记录：AI 链路与起草域（终稿）

> 循环：goal-crv ｜ 轮：r2 ｜ 域：AI 链路与起草 ｜ 审查时点基点：`35ffbea`（fork/main 顶 #410；合并前插队 #411 goal-sprint 与本线零交叠，PR 基于 #412 后的 `45bfaf9`）
> 审读方式：CreateWorkflow 四片（73 文件逐行读档，run `dwfrun-3feef00f`）＋主会话横扫（execute_ai_prompt 调用点全集／J-1 白名单／预算闸真身／输出端脱敏时序）
> **结论一句话**：purpose 归因纪律执行到位（9 调用点全显式传参）、prompt_registry/model_routing 闸体与钉自洽、ontology 治理面约束完备；真实缺陷集中在**计量链路**（流式 usage 恒零＝预算闸系统性失效、fallback 丢用量、请求期零记账）与**一条脱敏时序红线违背**（presurvey DOCX 脱敏前上传供应商）——P1×2／P2×12／P3×3（合并族），零 P0。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：73 文件**（分配表 r2 主域 4 条目 `ai/quality/plans/ontology` 全闭合）＝工作流四片（AI供应商与执行链 9 被审＋14 验证读；AI业务起草面 9 被审＋9 链路证据读＋12 钉核查；质量与方案AI起草 10；本体治理面 4——ontology/service.py 2103 行六段连续 Read 全覆盖）＋主会话横扫（调用点 grep 全集 10 处、J-1 白名单 test_prompt_hygiene_jseries.py、预算闸 auditing.py:136、脱敏链 project_draft.py/kimi.py 时序）。
- **抽查：部分验证读已在 ShardReport files 中如实分档标注**（抽查档＝跨文件语义验证与钉核查，非被审主面）｜**没读：0**（主读面全集逐行闭合）。
- 四片合规声明在案：零执行、零写、未触禁区、摘录零密钥；关键排除项与「防复核者重走弯路」注记（record_audit 独立短事务疑点否定等）留档。

## 2 QR 台账（r2 增量 · 单一真身在总报告附录）

**本轮新增 QR-024～040**。摘要：

### P1（2 条，E0 双证据过闸）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-024 | ai/deepseek.py:507 | 直连腿流式路径 usage 恒采集失败（三重机理 E0 逐点重读：SSE body `.json()` 必抛→恒 None＋请求体无 `stream_options:{"include_usage":true}`＋usage chunk 空 choices 被 `["choices"][0]` IndexError 丢弃）⇒ DSH 关闭（出厂默认）下 executions 后台主路径 token 计量恒零，预算闸计量-拦截语义系统性失效、admin 月度读数系统性低估。修法：流式解析 usage chunk 或诚实置 None（对齐 kimi 知情设计）＋补流式假体钉 |
| QR-025 | ai/kimi.py:74 | 预调研 DOCX 原件脱敏前上传供应商——上传腿（:74-81，默认 `kimi_local_docx_extract=False` 即走此腿）先于 `redact_text`（project_draft.py:72，build_messages 内）执行；E4 凭据闸（`SensitiveCredentialDetected→400`）与 A2 代号化红线被时序架构（project_draft.py:59 注释自decl「不把原文送出去」与实现直接背离＝intended-vs-implemented）。判级 P1（红线违反），P0 复核注：若按「未脱敏敏感原件外发第三方＝安全洞」口径可升 P0 留蔡工裁定。修法：上传前本地预检（凭据 400/词典故障 503）或废弃上传腿统一本地提取；test_kimi_client.py:54 上传正例钉须同步换代（**2026-11-13 修复批 B CLOSED：QR-024 流式 usage 修复＋QR-025 随批裁定升 P0 废弃 `/files` 原件上传腿统一本地提取，旧上传钉已换代留痕**） |

### P2（12 条，E0 锚点全确认）
QR-026 executions.py:133 `ai_actor_id.set` 无 reset——worker 单线程跨 job 泄漏，后续 DSH 腿任务预算/审计归错主体（对照 translator/jobs.py:67,156 正确 set+reset 范式）｜QR-027 deepseek.py:133 直连腿后台 actor 双盲（`current_actor_id` 只读 g、worker 无 g；`ai_actor_id` 仅 DSH 腿消费；subject_budget_exceeded 对 None 恒放行）——两片独立同报，E0 合并为一条｜QR-028 deepseek.py:258 fallback 按次重置 `_last_usage`→主模型已计费 token 不入账（注释「主备不串」的设计意与记账后果脱节；修法=按尝试求和）｜QR-029 deepseek.py:353 `_read_stream` 循环零包裹——流中断/解码异常逃逸 DeepSeekError 包络：零审计、零降级、调用方裸 500（kimi.py:261-264 同构保护在场对照）｜QR-030 kimi.py:120 请求段在 inner try 外——超时/限流/认证失败零审计（:137 注释自称「失败也记账」实为部分段；判级存疑注：CR-006 相邻，可并口径域）｜QR-031 model_routing.py:48 路由命中描述符仅 {provider,model} 两键——直连腿消费要求 base_url/api_key（ai_server_client.py:215-227），or 链已短路偏好链 ⇒ 路由开启+降级腿=ai_model_not_configured 硬失败，fail-safe 承诺被消费契约打破（出厂默认关，判级存疑注：默认关闸下可辩 P3）｜QR-032 quality/draft.py:180＋plans/draft_ai.py:213 契约闸非 hashable TypeError 双胞胎（邻行 risk_level 即正确 isinstance 写法对照；500 绕过整批重试与 409 映射；两 twin 同 patch）｜QR-033 quality/draft.py:287＋plans/draft_ai.py:324 AI 调用+退避 sleep 在打开事务内双胞胎——idle in transaction 跨分钟级外呼（T-13′ 部署事故同类风险面；拆两段事务收口）｜QR-034 plans/service.py:329 任务分解 create_project_task 独立事务即时提交于外层 begin 内——外层回滚留孤儿任务＋零审计（extensions.py 裸 sessionmaker 机制双片交叉确认；并发双击触发唯一索引冲突即现）｜QR-035 plans/service.py:303 `item_ids: []` 过校验（any() 空真值）而 `_plan_items` falsy 不过滤——显式空选区静默变「全选」批量创建（判级存疑注：桌面端若存在清空选区提交路径则升 P1）｜QR-036 ontology/service.py:1322 **CR-021 续注**——跨变更集并发 confirm 物化竞态：指纹复核对在途事务不可见＋受影响术语行无行锁＋别名撞唯一静默跳过 ⇒ 名字域解析分裂（别名表指向 Y、canonical 指向 Z）；按任务书规矩 4 引用既有编号续注不立全新条｜QR-037 quality/draft.py:150 accepted 需求 >50 时 AI 起草契约不可满足——每次必先烧满 2 次供应商调用再 409（**E0 从严升档 P3→P2**：固定烧钱＋功能静默不可用且报错不指根因；先验拒绝同 no_approved_requirements 模式）

### P3（3 条合并条目，15 锚点——§5 规矩 5）
- **QR-038 归因与计量口径族**（4 锚）：kimi.py:97 DSH 腿漏传 purpose→同业务审计随部署形态分裂（"structured" vs "kimi_docx"——E0 在 P1 读码中直接确认无 purpose= 实参）｜control/ai_server_client.py:563 DSH 腿 prompt_fingerprint 恒为固定包装语指纹（G-09 模板身份归因在 DSH 腿退化）｜ai_opportunity_service.py:128 等 5 处 `ai_budget_exceeded→503`（持久预算状态伪装可重试临时故障，全 AI 面一致）｜ai/executions.py:4-6 崩溃重放=整单重执行而非「续跑」，注释「幂等跳过不产生重复副作用」与重复计费现实漂移
- **QR-039 交互协议与呈现族**（4 锚）：ai/executions.py:189 LTRIM 环形缓冲与 offset 分页不变量冲突——>1200 事件后客户端增量事件流永久哑火（16k token 流式远超上限）｜ai/project_draft.py:83 `redacted[:120000]` 静默截断无诚实标注（V31-P1 诚实截断纪律家族漏网）｜quality/draft.py:259＋plans/draft_ai.py:294 词典替换 occurrences 恒记 1（复核台账低估密度；修复点 redaction.py 单一真身）
- **QR-040 测试缺口与声明漂移族**（7 锚）：ai_opportunity_service.py:232 E3 引文溯源校验零负例钉（删掉过滤 CI 不红）｜ai/routes.py:101 research-form 两路由+operation 零 API 级测试（权限/404/409/预算分支全裸奔）｜quality/routes.py:1 头注「6 路由」实为 7＋service.py「AI 通道为未来增强」已被 N3a 落地｜plans/__init__.py:8 声明面漂移四合一（「乐观锁」无机制——version_id_col 全仓零命中／fact_ids 闭集表述与双腿实现不符／「第二道=审阅闸」失准／PLAN_VERSION_MAX 死常量）｜plans/service.py:148 同行两次 `_next_version` 并发失配｜ai/opportunity_adjustment.py:52 N6 AST 钉形状盲区实锤（函数体内联提示词逃逸「全常量必注册」——8 个未注册 purpose 家族收编于此）｜ontology/service.py:1457 captured_from check-then-act 无唯一约束＋:527 端点元素上限 32 与类型码上限 60 自相矛盾（33-60 字符可注册不可引用）

## 3 主会话横扫结论（r2 专项）

1. **purpose 归因纪律**：execute_ai_prompt 全仓 10 处调用点（1 定义+9 外部）grep 全集——9 个外部调用点**全部显式传 purpose**；chat_assistant/workflow_skill 两点 prompt_version 留空＝N6「未登记版本者留空」合法态（G-16 静态钉 test_ai_call_audit_attribution.py:204-228 AST 强制在场）。
2. **J-1 白名单**：`server/tests/test_prompt_hygiene_jseries.py`——system 组装点形态白名单（变量名允许集＋已登记例外逐符号），域外新增即红；横扫未见绕过面。
3. **预算闸真身**：`ai/auditing.py:136 subject_budget_exceeded`（M4 主体级：企业 org 额度＋全员合计）；闸的计量输入端被 QR-024/027 系统性架空——缺陷在采集侧不在判定侧。
4. **输出端脱敏**：redact_text 本体实现正确（project_draft.py E4 注释与 T-A2 一致）；缺陷纯在 QR-025 的调用时序。

## 4 清白亮点（供总报告引用）

- prompt_registry.py 12 注册行/version_of fail-loud/AST 双向≡钉自洽；model_routing 四道闸与 test_prompt_registry fail-safe 矩阵逐条吻合；链序钉「override＞质量路由＞偏好」ai_server_client.py:344-348 原样在场＋源序钉互证。
- auditing.py：purpose 兜底 unattributed＋DB CHECK 拒空＋budget_blocked 计入已用量防重试绕过——钉族对齐。
- ontology/models.py+routes.py：UNIQUE 分表钉「一个名字一个概念」库级底线、partial unique 互补 NULL 语义、13 路由 manage 标志与 docstring 逐一对应、验收分离/全局另需 admin 闸实测在位。
- quality/models.py+plans/models.py：CR-053 部分唯一索引封并发双 approved、两段式 CHECK、append-only 执行史。

## 5 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 6 备注

1. 8 个未注册 prompt_registry 的 purpose（memo_merge/opportunity_discovery/opportunity_adjustment/document_ai_content/research_export/solution_organize/translator_translation/kimi_docx）prompt_version 留空＝auditing.py:18-19 允许态；形状问题收编 QR-040。
2. CR-006 口径域引用不立新条：deepseek.py:159-160/kimi.py:180-182 预算门 fail-open；ai_server_client.py:543-547 any-admin 回退；kimi.py:144-145 流式 token 记 None（知情设计，与 QR-024「假装采集必败」意图相区别）。
3. 预算闸 TOCTOU（check-then-act 无原子预留）＝审计汇总式闸「尽力而为」定位，docstring 自认，不立条。
