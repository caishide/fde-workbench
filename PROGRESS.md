# PROGRESS — 翻译器×企业自诊融合设计稿包

- 会话断线续接说明：本文件是本包唯一进度账；每做完一项立刻更新。

## 理解的目标／顺序／最大风险（任务 0 收尾，2026-11-12）

- 目标：翻译器（内部售前面）×企业自诊（公网获客面）是同一条「客户诉求→结构化理解」链的两段；领导已拍板方向＝统一诉求理解内核＋双门面＋认领续翻（不硬合一）。本包**只出融合设计稿**（§0–§6，落 docs/audit/），供领导拍板后拆轮实施；纯文档零代码零迁移零路由零桌面。
- 顺序：任务 0 现状逐条核对 →（已完：12 项吻合、2 项偏差，证据见 BLOCKED.md 最上面，只做不受影响部分）→ 任务 1 锚点 ≥12 条现测（已完：24 条，全部本次打开文件实测）→ 任务 2 写设计稿 → 任务 3 feature 分支 push fork 开 PR（保持待审不合并）。
- 最大风险：①两模块 AI 通道不同源（translator＝DeepSeekClient 直连、diagnostics＝execute_ai_prompt）——评分移植方案必须显式处理通道差异，否则 §4 落地即返工；②诊断答案材料不进 server/src 的污染隔离纪律，约束评分夹具只能放评测脚本侧（scripts/diagnostic_eval/ 域）；③T-11 认领闸未实施，续翻链路只能设计为依赖 T-11 的后置轮。

## 已完成

- [x] 认领前查在途 PR（fork 开放 PR #351–#355，无本线分支/PR，无撞车）
- [x] feature 分支 `docs/translator-diagnostics-fusion` 自 fork/main `e05f1d6` 建立
- [x] 任务 0 现状核对（2026-11-12 现测；偏差 2 条记 BLOCKED.md）
- [x] 任务 1 锚点 28 条（translator 9／diagnostics 10／共享面 8＋表内引用，全部现测；稿内行号复核终扫过）
- [x] BLOCKED.md 建立
- [x] 任务 2 设计稿 §0–§7 完成（`docs/audit/翻译器与企业自诊融合设计稿-2026-11-12.md`；§0–§6 必备节全齐＋§7 红线自证；稿内引用行号二次复核修正 2 处）
- [ ] 任务 3 push fork + 开 PR（不自动合并，领导亲自拍板）
- [ ] 完成条件核验（diff docs-only + CI 四绿）

## 建议改走（「建议」条款留痕）

- 无改道；唯一偏差是任务书两条现状数字（见 BLOCKED.md），均按「证据留痕＋设计稿用现测值」处置，未改变任何「只允许」路径。

## 事故与修复记录（2026-11-12）

- **事故**：共享工作树 HEAD 被并发会话切回其分支（`docs/case-learning-ledger-backfill`），本包首个 commit（原 `e3efa0f`）落在**他人分支**上（其远端已在 `ca83924`，若其继续 push 即污染 PR #354）。
- **修复**：①独立 worktree（`D:/test/fde-wt-fusion`）内 cherry-pick 搬运（→`e9b1a6a`）＋rebase 到当时 fork/main `c97eedf`（→`27cc354`）；②他人本地分支 `git reset --mixed ca83924` 复位到其 push 原状（mixed 不碰工作树文件，其未提交改动零影响）；③rebase 后现测 fork/main 两笔新提交（#349/#353）与本稿 28 锚点涉及文件域零触碰（`git diff e05f1d6..c97eedf --stat -- <锚点文件域>` 无输出）。
- **教训**：共享主树的 HEAD 是跨会话争用面——本包后续所有 git 写操作一律在独立 worktree 内执行；commit 后必须核对 `[分支名 sha]` 输出与预期分支一致。

## 终态（2026-11-12）

- PR **#358** 已开（保持待审不合并，领导亲自拍板设计稿）：https://github.com/caishide/fde-workbench/pull/358
- **CI 四 job 全绿**：run `43056579134` conclusion=success——desktop ✓／secrets-scan ✓／server-tests ✓／pseudonymization ✓（check-runs API 全读，非 gh pr checks 摘要）。
- 硬指标 2 实证：`git diff fork/main...HEAD --stat`＝恰 3 新文件（BLOCKED.md 22 行／PROGRESS.md 30 行／设计稿 281 行，共 333 insertions），server/·desktop/·migrations/ 零触碰。
- 分支 tip＝`812785f`（27cc354 设计稿＋812785f 事故记录），基于 fork/main `c97eedf`。
