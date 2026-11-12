# goal-sprint PROGRESS

> 线：goal-sprint 上线冲刺（任务书＝`docs/goal-sprint-上线冲刺-任务书.md` v2）｜启动：2026-11-13（蔡工拍板「现在启动」）
> 断会话续接：读本文件接着做，别重做；每做完一项立刻更新。

## 开工回执（2026-11-13）

- **理解的目标**：把「对外受控试用就绪」剩余四闸（P2′ 实装／N1 试点闭环／D7 阈值／T-14b 收尾）串成 8 轮止损的有闸冲刺线；让步顺序＝**闸不代拍 > 窗口不失期 > 推得快**。
- **轮次顺序**：r1 N1 试点支持（进行中）→ r2 P2′ 服务端咬合面 → r3 端到端真机验收 → r4 D7 复审报告 → r5 T-14b 收尾 → r6 E8（条件轮，开工闸＝蔡工显式令）→ 收口终扫。
- **最大风险**：① N1 窗口 2026-11-19 截止，首个 run 迟迟不发起则 r1 空转（缓解：PROGRESS 明示发起入口，r2 起不空等）；② 与 goal-crv 并发的 PR 插队（缓解：隔离 worktree `D:/test/fde-wt-sprint`＋每轮开工 `git fetch fork` 对齐）；③ r2/r3 真机面依赖宿主环境（边界＝N2 已签核检查单两表 PASS 语义）。
- **拍板留痕**：蔡工 2026-11-13 选「现在启动」⇒ 任务书 v2 落「并行条款＋crv 吸收条款」，替代原「与 crv 串行、本线先行」默认。

## 任务 0 基线（2026-11-13 现测，每条带命令）

| 项 | 值 | 测法 |
|---|---|---|
| 基点 | fork/main `35ffbea`（#410 squash，2026-11-13 合并） | `git fetch fork && git rev-parse fork/main` |
| 在途 PR | **0** | `gh pr list --state open` |
| 施工树 | `D:/test/fde-wt-sprint`（分支 `goal-sprint-r1`，从基点建） | `git worktree add -b goal-sprint-r1 … fork/main` |
| pytest CI 基线 | **3473 passed + 8 skipped**（12m28s） | main run **43281011099**（#410 合并轮，四 job 绿）。本地不重跑全量的理由：docs 轮零代码增量＋并发会话共享 PG 对撞家族风险；CI 实测为权威口径 |
| mypy | **OK：baseline 277 occurrences / 102 distinct**（现测） | `server/.venv/Scripts/python.exe scripts/check-python-types.py`——★较 AGENTS 口径 279/104 漂移 −2，登记待收口轮核对（P3 文档漂移，本线不修） |
| typecheck | 绿（node+web 双 tsconfig 零错误） | `npm run typecheck` |
| 活库身份 | `fde_workbench` @ alembic **`b5d9e2f4a7c1`** ＝代码 head 逐位一致；PG 容器 `qiflow-twenty-db`（与 `verify-run-evidence.sql` 头注配方同源） | `psql -c "SELECT version_num FROM alembic_version;"` |
| T-14b 前置 | `diag.fde18.com` DNS 未配置（Non-existent domain） | `nslookup`（本会话 2026-11-13） |
| crv 吸收面 | **零域章**：goal-crv 总报告未出生；`docs/audit/全面代码审查报告-2026-11-10.md` 属 goal-review-fix 线（CR- 前缀，QR 计 0），非 crv 吸收对象 | `ls docs/audit/全面代码审查报告*` + `grep -c "QR-"` |
| 本地跑测配方 | venv 忽略 PYTHONPATH（教训⑭家族）：真路径 exe＋`sys.path.insert(0,'server/src')`＋`os.chdir(server)` | 本轮 r1 自测实证（三次试错定型） |

## r1 · N1 试点执行支持（进行中，窗口 2026-11-12~11-19）

### Agent 侧完成项（2026-11-13）

1. **四口径 SQL 采集实跑**（`scripts/verify/verify-run-evidence.sql`，只读 `BEGIN READ ONLY…ROLLBACK`，全四段合法执行）：
   - ★**证据闸翻转发现**：`approval_rows=2`（reviewed=2）——SQL 头注「活库当前 automation_approvals=0」已过时；`evidence_gate=HAS_RUN_EVIDENCE`。2 行均为 **2026-11-08 somwyn E2E 试点产物**（risk_level=4／workbench.write／workflow.human_approval，均 approved、否决率 0.0000、审批时效 p50=85.5s／p90=104.3s）。**含义**：D7「approval_rows=0 禁预支」的数据前提已松动——r4 复审报告有了极小样本数据源（n=2，且是 human_approval 语义、非 N1 zcode run 语义）；**阈值 N 仍归蔡工拍，本线不预支数值**。
   - **C 口径现出 2 行「执行落空」**（approved 超 1h 无 executed_at；id `df31cb16…`／`b789a318…`，均 11-08）——疑为 `workflow.human_approval` 能力下「审批即终点、无执行腿」的口径语义错配而非真脱节；**r4 报告轮须裁决该口径**（与 B 词表 `executed` 单列同源），登记不结论。
   - D 口径：确认失败锁事件 **0 行**。
2. **N1 窗口状态**：`agent_runs WHERE created_at>='2026-11-12'` ＝ **0**（历史总 12，均 somwyn 试点期）⇒ 蔡工尚未发起首个 run，符合「首个 run 亲手执行（H4）」待办。**发起入口（待蔡工）**：桌面端 AgentsConsole 发起 pilot-001 编码 run（N3 五问已拍：A 轨封闭集＝仅 pilot-001；产出物＝run 产物目录代码/diff/文档＋`--json` 汇总；确认人＝蔡工）。
3. **契约失败语义自测**：`server/tests/test_zcode_contract.py` **14 passed**（7.13s；含 `--json` 汇总形状／故障态明确失败码／版本钉 0.17.1／降级语义）。
4. **产物复核链路**：端点面由 N3c 已交付（artifacts content 读取面＋AgentsConsole 终审队列），r1 零新增代码；蔡工发起 run 后按既有复核流走，届时补 run 证据 sha256 登记。

### r1 待办（收口条件）

- [ ] 蔡工发起首个 run（窗口 11-19 止）→ 证据 sha256 登记 → 打勾「窗口内闭环」
- [ ] 或窗口关闭未跑成 → 如实登记「部分完成」转 r2（不阻塞 r2 开工）

### r1 变更面

- 本 PR：任务书 v2 落库＋本 PROGRESS＋CHANGELOG 节。**零生产代码零迁移零路由**（判定：`git diff <基点>..HEAD --stat -- server/src desktop/src server/migrations server/seeds` 应为空）。

### r2 开工前检查单（吸收条款执行记录位）

- [ ] `git fetch fork` 对齐＋查在途 PR
- [ ] 扫 goal-crv 已出域章 QR 台账（现测：零域章，2026-11-13）
- [ ] 建 `D:/test/fde-wt-sprint` 内新分支 `goal-sprint-r2`（从当时 fork/main）
