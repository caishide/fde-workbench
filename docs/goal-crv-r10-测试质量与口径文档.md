# goal-crv r10 轮记录：测试质量与口径文档（终稿 · 主会话轮）

> 循环：goal-crv ｜ 轮：r10 ｜ 域：测试质量与口径文档（server/tests 关键钉判别力评估 6 钉三段链＋AGENTS/README/CHANGELOG 口径 vs 现测＋全循环 CI 口径链终审）｜ 审查时点基点：`35ffbea`（测试文件零生产 diff 轮，基点即现树）
> 审读方式：主会话直审（无 fde_api 生产条目；判别力评估＝静态推演「变异会否转红」，不执行被审测试）
> **结论一句话**：机械闸钉族（keyword-only 编译闸＋全仓静态扫描＋指纹耦合＋允许名单污染闸）判别力 A 级扎实；安全隔离钉断言方向判别力足够但**宽容形态（403/404 双接受）弱化「不确认存在性」语义**；**test_ai_run_proposal 审计链钉 CI 稳定性 C 级**（本循环窗口 5 run 3 红阻断 docs-only 轮合并 3 次）——P2×1／P3×2，零 P0 零 P1。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：6 钉测试文件**（test_cross_tenant_isolation 308 行全读／test_m4_batch3_queue_subject 214 行关键段＋静态钉全读／test_visibility_parity 54 行全读／README 口径段 grep 现测／污染钉与 prompt_registry 钉按既有轮实测引用）＋全循环 CI run 链终审（#412~#423 的 run 号与失败测试名）。
- **抽查：CHANGELOG 最近节／test_ledger_sync_nail**（静态确认分类器钉在场，未逐行）｜**没读：desktop/tests 主体**（r7 已按片定点核对）。
- 判别力评估方法：三段链＝①钉断言内容（读源）→②变异推演（改动哪条生产码会让它红——静态论证）→③评级。

## 2 关键钉判别力评估（6 钉）

| 钉 | 断言面 | 变异推演（红路径） | 评级 |
|---|---|---|---|
| test_cross_tenant_isolation（9 例） | 7 域跨企业访问 403/404/列表不含＋cross_org_ 留痕 | 移除 visible_project_filter org 收敛 ⇒ 列表钉红；移除对象级 project_access ⇒ 详情族钉红；**关键场景＝跨企业成员关系**（docstring 自述「素不相识不构成判别力」）——fixture 直建越界成员 | **A**；弱点见 QR-147 |
| test_visibility_parity（1 例对账钉） | list_projects SQL 预过滤 ⊆ visible_project_ids 四 actor 全量比对 | 任一写路径放宽产幽灵行 ⇒ 对账钉先红（CR-063 单一权威语义） | A- |
| test_m4_batch3_queue_subject（6 例） | metering admin 闸＋分组零编造＋**全仓静态扫描**（enqueue_outbox 调用点 12 行窗口须 subject_org=）＋dispatch 复制断言 | 删任一调用点 subject_org ⇒ offenders 非空红；编译期 keyword-only 双保险（M4-C 机械闸） | **A** |
| test_diagnostic_eval_contamination（7 例） | 七钉：fixtures 键名/生成器可见面/seeds 面/形状/指纹一致/真相层 skip 显式/同步脚本允许名单 | 禁名单可改名绕（家族性已知）但 ⑦**允许名单**绕不过；r9 全域 grep 回归零命中 | A- |
| test_prompt_registry（15 例） | 指纹耦合「改正文不升版本⇒红」＋AST 全常量双向 ≡＋fail-safe 矩阵＋链序源钉 | N6 轮变异四连真红实证（历史） | A |
| test_ai_run_proposal（16 例） | propose→密码确认→落 run＋审计链三事件序＋零密码字段 | 行为面判别力 A；**CI 稳定性 C**（QR-145）——断言对事件落库时序敏感 | 行为 A／稳定 C |

## 3 口径文档审计（vs 现测）

- **结构口径 485 路由/52 蓝图/153 表/73 rev**：权威真身 `docs/audit/v3-workbench-inventory.json`（@3f9a9ce）↔ AGENTS「当前状态」历史节逐位一致；README 无结构口径行（部署/命令权威，无第二真身冲突面）✓；本循环 r1–r10 全部零生产 diff 轮，口径无漂移 ✓。
- **pytest 口径链**：AGENTS 历史节 3473+8（N5 时点 @35ffbea）→ 本循环现测 **3508 passed + 8 skipped**（#414 +35 后的合并树 CI 实测：#418 run 43321731962 重跑绿／#421 tip run 43337038375 同值）——历史节按「每轮自报」惯例不重写，PROGRESS/总报告已按 CI 现测记录，无冲突 ✓。
- **vitest**：96 文件/1100 例（run 43269972808）维持；★**口径校正登记**：任务书与早前轮引「等价性静态钉 45 样本」为 r9 时点值，T-14a 增 HEADER_SAMPLES 18 条后现测 **63 样本（25 路径＋9 method＋11 body＋18 header）**（r7 分片实测，README/AGENTS 均未载该数，无文档漂移面——仅任务书历史文本，随本条留痕即可）。
- **CHANGELOG**：本循环十域轮零生产 diff 全不落 ✓（§4 纪律）；test_ledger_sync_nail 分类器与 backlog 状态钉静态确认在场。

## 4 QR 台账（r10 增量 · 单一真身在总报告附录）

**本轮新增 QR-145～147（3 条）**：

### P2（1 条）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-145 | server/tests/test_ai_run_proposal.py:158-159 | 审计链钉 CI 稳定性缺陷——`assert [e.event_type for e in events] == ["ai.api.requested","ai.api.started","ai.api.finished"]` 对事件落库时序/可见性敏感：goal-crv 循环窗口内 **5 run 3 红**（#418 run 43321721570 与 43321731962 首跑＋r5 合并 main run 43321496287——同测试同失败形态「缺 ai.api.requested」；另有 #421 旧 run 撞他枚 flake），docs-only 轮被迫重跑 3 次方合并。缺失形态指向两可能：①confirm 链 requested 事件与 started/finished 非同事务落库的真实竞态（生产审计链完整性问题）；②断言读 db_session 的时序窗口。**须专项定位**——若是①则为生产级审计链缺口，是②则为测试时序钉。修复方向：requested 事件落库事务核查＋断言改集合包含/排序无关＋CI 重试策略登记 |

### P3（2 条）
- **QR-146 已知 flake 续注**：`test_delivery_plans.py::test_task_decomposition_preview_commit_idempotent`——#364 评论留证「4 run 2红2绿」50% flake 挂账专项未动；本循环窗口再红 1 次（#418 run 43321721570）。与 QR-145 同窗活跃提示 **CI 时段敏感族**（22:10–23:30Z 窗口集中发作；18a4337e main run 与第 4 次重跑均绿＝窗口外恢复）——两钉专项可合并为「CI 稳定性专项」一项挂账。
- **QR-147 隔离钉宽容形态**：test_cross_tenant_isolation 13 处断言取 `in (403, 404)` 双接受——「不确认存在性」（M3a §3.5：无权 ⇒ 404 不泄露存在性）与「确认但拒绝」（403）语义漂移不会被该钉抓住；现有实现面经 r1/r3/r9 审读确认走 404 语义，但钉层无法防御未来漂移为 403。建议按域分档锁定预期码（或至少对「读单对象」族锁 404）。

## 5 清白亮点

- 机械闸家族判别力 A 级：keyword-only 编译闸＋静态扫描窗口＋指纹耦合＋允许名单污染闸——四类「绕不过」形态齐备（与夜审方法论「禁名单可绕、允许名单绕不过」教训一致）。
- 口径链全循环零漂移：十域轮零生产 diff，485/52/153/73 十次轮记录逐位一致；CI run 号全程落账可溯。
- M3c 套件「先于改造入库＋xfail(strict) 机械销号」模式是判别力工程范本（XPASS 判红强制摘标记）。

## 6 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 7 备注

1. QR-145 判级说明：测试质量域 P2（不直接判生产缺陷——缺失形态的根因〔生产竞态 vs 测试时序〕须专项定位后升/降级；若定位为生产审计链缺口则升 P1 修复候选）。
2. 全循环审查自身产出统计（供收口轮）：QR-001~147 十域 147 条；P1×18／P0×0；needs-decision 7 项（BLOCKED）。
3. 号段连续化说明：本轮初稿预留号位 148~150（起草期按疑似独立发现计数），收口前终扫发现台账断号（145~147 空置）——重编号 148~150→145~147 三文件同步，台账连号 001~147 无缺无重（E0 终扫闭集 grep 实证）。
