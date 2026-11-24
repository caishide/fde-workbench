# M0.1 工作树与并发地图

2026-11-23（UTC+8）。回收来源为 `git worktree list --porcelain`、`git --no-optional-locks status --short --branch`、`git branch -vv --no-abbrev`、`git stash list`、`git rev-list --left-right --count`，以及 fork 的开放 PR 列表。

| 工作树 | 头与分支 | 基线左侧／分支右侧提交 | 扫描结果与归属 |
|---|---|---|---|
| Workbench 主检出 | `03ff8e94`，`docs/goal-optimize-r4-writeback` | `0 / 1` | R4 #570，未跟踪 `_edgetmp/`、`server/.tmp/`。仅记录目录名 |
| Codex 托管优化树（3177） | `490e1ff0`，`feat/goal-optimize-delivery` | `53 / 4` | Git 状态干净。按其他会话施工树处理 |
| 隔离部署树 `fde-wt-rubricv2-deploy` | `80563f13`，detached | `21 / 0` | Git 状态干净。按活体迁移挂载源保护 |
| 独立 M0 树 `fde-wt-ecosystem-m0` | `72347900`，`docs/ecosystem-m0` | `0 / 0` | 本次新建，基线为当时本地 `main`、`fork/main` 和 fork 远端 main 共同指向 |

计数基准为 `723479009d1b1f0c63744790ad3be3ed02bebbe1`。两条在途分支没有设置 upstream。AE2 评审本地分支 `bc4484a7` 对跟踪的 `fork/main` 落后 5 个提交，无独立注册树。AF1 的若干分支仍登记在 refs。工作树列表不能替代平台会话登记，归属无法证明的树一律按他人施工面保护。stash 检出 5 条，从新到旧属于优化交付、M5 治理、审查修复、Ontology 对接和上线冲刺，均保留原状态。

| 并发线 | 证据 | M0 重叠和动作 |
|---|---|---|
| goal-optimize R4 | #569 已合入基线，#570 由检查中转为 `CLEAN` 后才建立 M0 工作树。该时间点 #570 处于开放状态 | #570 仅修改 `docs/optimization/PROGRESS.md`。M0 文件全部在独立目录。发布前复核主线及开放 PR |
| goal-optimize 后续 | 托管树相对基线有提交。`docs/optimization/BLOCKED.md` E-04 登记 R4b/R4c 的隔离场次前提 | 可引用基线进度和阻塞说明。基线到托管树的提交差异未涉及 `docs/ecosystem-v1/` |
| AF3 / AE2 | #568、#565 已进入基线，启动盘点时无同线开放 PR | 使用已合并提交的文本证据。评测、Action、解决方案仓源码均在保护范围 |
| Fde-Ontology | `73e6d9c`，`main...origin/main`，主检出干净，远端 main 同 SHA | `git worktree list --porcelain` 登记 AM1 `9a3ad43f`、AM3 `50618499`、CASE-A 独立运行 `5a6c0a95` 和规划树 `a99b50ef`。其他工作树以注册元数据为准 |

## 具名保护清单

- `C:/Users/P1/af1-hidden-sealed/` 是密封件。仅记文档已登记的路径。
- `fde-wt-af1wp1`、`fde-wt-af1wp1b`、`fde-wt-af1wp4` 按工作令保护。本次 Workbench 注册表未列三树，维持保护。
- `fde-wt-rubricv2-deploy` 按活体迁移挂载源保护。`takeover_check.py` 属部署接管流程。
- `fdeops`、`openfde`、客户真实资料与诊断案例集均由本地真相层保存。M0 仅引用仓内代号和证据类型。
- 检查遇到 rebase 或路径冲突时登记 `skip` 并保留现场。清理、切换、重置、变基、stash 应用或接管由原负责人按独立授权执行。
