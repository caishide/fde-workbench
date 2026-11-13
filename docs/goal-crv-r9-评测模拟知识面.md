# goal-crv r9 轮记录：评测·模拟·知识面（终稿）

> 循环：goal-crv ｜ 轮：r9 ｜ 域：评测·模拟·知识面（工作流 45 文件逐行＝simulation 23＋research 13＋discovery 9；直审 19 文件＝translator 6＋research/models＋seeds 11＋bridge-poll.mjs；guidance 9 归 r8 主域补审）｜ 审查时点基点：`35ffbea`（各片核验 git diff 基点零差异）
> 审读方式：CreateWorkflow 四片（run `dwfrun-16ce5af5`，18 条 E1）＋主会话直审
> **结论一句话**：模拟隔离红线（九表零 project_id/三视图装载断言/执行器物理不读 reference_json/种子无 TLD 圆点）、污染隔离七钉域、L2 诚实语义（unavailable 不编造/insufficient 显式）、N6 接线（simulation 两 entry 全接线）、CR-031 演练排除——五条域纪律全部回归在位；真实缺陷集中在**工具失败归因链整体不可达**（FA-05 死分支×handler 异常零留痕复合）、**过拟合闸承诺零执行点**、**discovery 幂等键碰撞与状态盲写**、**export 事务内外呼＋撞名 500**——P2×7／P3×3（合并 16 锚），零 P0 零 P1。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：64 文件**＝工作流四片 45＋主会话直审 19（translator 6＝service 228＋jobs 310＋models 45＋routes 77＋ai_prompt 43＋__init__ 2；research/models.py 660；seeds 11 静态三查；bridge-poll.mjs 233 行）。
- **抽查：0**（佐证读——ai_server_client.py Idempotency-Key 面/templates 发布闸/transcripts 不可变性/测试钉 grep——在 ShardReport notes 如实标注）｜**没读：0**。
- 四片合规声明在案（零执行/零写/未触禁区/基点零差异核验至 `281734a`）；E0＝P2×7 锚点逐一重读全实证（failure_analyzer:260-265／environment:92-103,215-224／regression_runner:8-16＋overfit grep 闭集／export_service:78-96,108-118,156-216／chunking:105-120＋jobs:195-201／discovery jobs:248-260,373-380,420-432,450-460）＋trace.py:47 tool_call 类型佐证＋P3 归并入族。

## 2 QR 台账（r9 增量 · 单一真身在总报告附录）

**本轮新增 QR-135～144（10 条）**：

### P2（7 条，E0 锚点逐一重读确认）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-135 | simulation/failure_analyzer.py:260-265 | FA-05 工具失败归因分支死代码——对 dict 形态 tool_call（trace.py:47 签名）迭代出键字符串，`isinstance(call, dict)` 恒 False ⇒ tool_errors 恒 []；G5「工具异常⇒接口/权限根因」专用归因永不触发，生产唯一调用方 improvement_service.py:165 传 dict 形态实证 |
| QR-136 | simulation/environment.py:97-101,220 | handler 内抛出的 SimulationToolError 零留痕——except 直接重抛跳过 `_record_call`；六案例种子均无 documents 命名空间 ⇒ mock 空参调 sim.fs.read_document 必抛且无痕，**每个默认 mock run 必现**；cost_json.tool_failures 系统性失真（与「调用全留痕」docstring 矛盾） |
| QR-137 | simulation/regression_runner.py:12-13＋regression_service.py:262-267 | 「过拟合 ⇒ 提案不得进入发布审批」承诺零执行点——release_channel 四闸（admin/密码/approved/regression_plan 非空）无任何 RegressionResult/overfit 消费（grep 闭集）；overfit_risk=True 的 approved 提案可直接发布（判级存疑：落库 note 明文陈述规则故按 P2） |
| QR-138 | research/export_service.py:158-216 | worker 导出全链（DeepSeek 同步外呼最坏 ~180s＋DOCX 渲染＋put_stream）全程持有未提交 DB 事务（首 scalar :160→首 commit :216）——QR-123 同族新锚（documents/generator 已报，本面未报） |
| QR-139 | research/export_service.py:92-93,113-115 | 调研结果 ProjectFile 撞 uq_project_files_project_category_name ⇒ IntegrityError 未映射恒 500——跨类型同名合法（imports.py:1291 背书）＋命名不含类型消歧 ⇒ 撞后 `_find` 永 None 重试恒 500 无自愈；QR-118 同族新锚（判级存疑：无卡死态可改名绕过，取 P2） |
| QR-140 | discovery/chunking.py:112,118＋jobs.py:198 | 自适应二分两半片共用父片 index ⇒ execution_id `c{index}d{depth}:{attempts}` 逐字节相同 ⇒ 同一 Idempotency-Key 绑两个不同输入外呼（ai_server_client.py:400 直传）——最坏 DSH 回放首响应＝静默错数据、最好审计归因折叠（判级存疑：DSH 回放语义仓外不可读；同深度兄弟碰撞零测试覆盖） |
| QR-141 | discovery/jobs.py:251-259,377,453-459 | 抽取行状态推进 check-then-act 无行锁——running 态 pass-through「继续走」＋并发双跑撞唯一约束后通用 except 无条件把成功批打成 failed；:377 无守卫盲写 review_required 可翻转 worker-loss 的 failed（QR-088/094/101 家族续注；判级存疑：单 worker 部署收窄窗口，P2 依赖 QR-100 心跳误判家族成立） |

### P3（3 条合并 16 锚——§5 规矩 5）
- **QR-142 评估/回归判定语义族**（6 锚）：evaluator.py:217-223 重评遇 provider 故障清零既有有效模型行（违反 unavailable=无分数态排除）｜model_evaluation.py:374-379＋routes.py:242 未知 model_mode 直通 500｜evaluator.py:136-165＋regression_service.py:230-268 并发首评撞唯一约束 500｜regression_runner.py:131-140 improved/regressed 维度阈值不对称 5 倍（TOTAL_* 常量用于维度口径）｜:180-190 blind 缺席时过拟合判定基于合成零值（note 断言不存在的盲测结论）｜regression_service.py:219-238 先跑全量两组再指纹查重（run-then-discard 孤儿 run 累积）
- **QR-143 simulation 输入校验与归档/幂等族**（5 锚）：run_service.py:104-106＋runner.py:154,176 config 数值键未校验 int() 抛 ValueError → run 恒 queued 无 error_json｜evaluation_rules.py:336 structured 闸读顶层键（生产组装在相位体）恒 True 死开关｜improvement_service.py:252-267 confirmed+hypothesis 混装进提案（与「likely/hypothesis 不自动变改进项」docstring 矛盾）｜service.py:402 归档守卫是行级非分支有效态——PATCH 旧版本行 id 可无声复活已归档场景｜run_service.py:131 等 6 处 check-then-insert 无 IntegrityError 兜底（TOCTOU 500，幂等语义并发窗口失效）
- **QR-144 research/discovery 卫生族**（5 锚）：export_service.py:228-242 全量 .all() 拉 document 文件 Python 侧过滤（QR-129 同族新锚）｜form_service.py:862-887 _condition_matches 零调用死代码（活身 :819-859 带循环守卫——双胞胎漂移风险）｜discovery/merge.py:48-53 行号回基无上界校验（模型谎报片内行号直达审阅面 provenance）｜discovery/jobs.py:435-438 requirement_suffix 死双参＋8-hex 随机键（32bit 碰撞撞唯一约束整批 failed）｜research/definitions.py:240,373-377 定义校验不对称（table 缺/空 columns 过发布闸而作答面恒 400；date 选项不校验 ISO 与 min≤max 序——定义错误报成答案错误）

## 3 清白亮点（供总报告引用）

- **模拟隔离红线全绿**：九表零 project_id（models 逐列核验）；loader 三视图递归泄漏自检（ScenarioLeakError）；执行器物理不读 reference_json（runner.py:98-101 `reference = None`）；种子 6 案例零 TLD 圆点零答案键（grep 闭集）；边界闸网关前缀裁决＋越界 failed_hard。
- **污染隔离七钉域回归确认**：FORBIDDEN_KEYS/PATH_TOKENS 于 server/src＋seeds＋本域 45 文件 grep 全零命中；lessons.json SOP-only 维持；seeds/enterprise-names.txt 合成示例 3 行（主会话实测）。
- **L2 诚实语义消费点一致**：unavailable=无分数态（model_evaluation 四态全落 unavailable 不编造）；evaluator 两层分歧计算排除 unavailable；重评幂等更新不插行；G6 调参纪律（train 集 findings 才能 create_proposal 409）；textmatch 确定性 0.25 可解释常量。
- **N6 接线**：simulation.evaluation/simulation.diagnostic_judge 两 entry 在位；diagnostic_judge/evaluation_prompt/model_evaluation purpose+prompt_version 全接线；discovery PROMPT_VERSION 走 version_of 单点（derived_of 双 key 注册）。
- **CR-031 演练排除回归在位**（pilot/metrics 双面 notlike）；release_channel N4 三闸逐行复核（密码 verify_password 参数序正确/回滚恢复 approved/事件 project_id 恒 None）。
- **imports.py 外部解析攻击面四闸齐备**（对照 QR-127 同型缺口在本面不存在）：10MiB 输入闸 413／defusedxml 全解析点（xml.etree 零命中）／zip 容器五闸（成员数/单成员/总量/压缩比/加密位）＋路径穿越闸＋关系目标闭集／CSV 编码闭集+field_size_limit；公式注入不适用（唯一去向 DOCX 纯文本 run）。
- **research models 层**（直审 660 行）：subject link 同项目组合 FK＋set/before_insert 双监听同步；merge 不变量 CHECK；revision 不可变；_PARENT_TYPES 严格 DAG 论证排除合并自环。
- **bridge-poll.mjs**（直审 233 行）：slug 白名单前置于命令拼接；只读命令白名单；8MB/90s/50 files 有界；token 走头不入 argv。
- **translator 主干**：AI 调用在事务外（running 先 commit——QR-123 的正确对照先例）；actor ContextVar 复位防 worker 线程串扰；采纳闸序 404 不泄露＋IntegrityError 409。

## 4 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 5 备注

1. 判级存疑 4 处如实标注（QR-137 落库 note 构成规则陈述故 P2／QR-139 家族内取 P2／QR-140 DSH 语义仓外不可读／QR-141 依赖 QR-100 家族）。
2. **export_service.py:267-270 purpose="research_export" 绕过 execute_ai_prompt 单一入口**（内联提示词＋无 prompt_version＋N6 注册表无该键）——r2 QR-040（research_export 未注册 purpose）已登记同面，引用续注不重报；收口轮修复批统一接线。
3. environment.py:54 两个 U+FFFD 源码注释损伤（od -c 实证）——零行为影响，随下次触碰顺手修复。
4. simulation 迁移/种子引导：seeds.py docstring 称「播种只在迁移/引导路径调用」与实际（仅 tests/scripts 调用）不符——文档过claim 登记不立案（生产库种子靠手动脚本，运维面）。
5. 遗留小项（不占 P3 名额）：瞬时重试与契约重试共用 request_id（审计歧义 P4）／get_evaluation_report 多模型行 next() 任取（P4）／routes limit=0 被 or 吞成默认（毛刺）。
