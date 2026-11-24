# M0 执行边界核对表

收割源为 [AGENTS.md](../../../AGENTS.md)、[CONTRIBUTING.md](../../../CONTRIBUTING.md)、[README.md](../../../README.md)、PartyMode 纪要 §二 E、任务书 §14/§19 和 [02 并发地图](02-git-worktree-concurrency-map.md)。M0 授权仅覆盖只读证据和本目录文档。

| 检查点 | 执行断言 | 证据或前置条件 |
|---|---|---|
| 远端 | `origin` 永不 push。工作远端与 tag 均为 `fork`。从已核实的 fork 主线建立独立树 | `git worktree list`、`gh pr list`、`git ls-remote fork refs/heads/main`。提交、推送、开 PR 依各自授权 |
| 在途保护 | 客户资料、密封件与指定树保持只读。其他会话未跟踪文件和 stash 保持原状。并发热点由单一写入方负责 | 02 具名清单及分支对照，冲突登记并暂停该写入 |
| 部署与接管 | 任何后续授权部署须先由负责人校验接管。服务端重建后执行授权迁移及三验 | `scripts/deploy/takeover_check.py`。三验为活体路由、容器内 Alembic 当前头、镜像 ID 与构建产物逐位一致 |
| 结构数字 | 同一时点记录仓库清单、迁移图与活库读数。迁移多父全部参加拓扑检查 | [05 结构盘点](05-api-data-model-inventory.md)。维护者在改结构时同步 inventory、CSV 与 archify |
| 台账同步 | 同轮同步交付轨迹、backlog、相关文档和桌面交付物。CHANGELOG 台账型节占比按仓内钉处理 | `test_ledger_sync_nail.py`。纯本目录审计登记一次，维护文件随授权 PR 处理 |
| 桌面交付 | 后续桌面改动须重打包便携版，证明新包命中特征、旧包不命中，并登记 r 序号 | `fde-package-verify` 和仓内 asar 验证流程 |
| 并行测试与 pre-commit | 使用每 worker 独立测试库或独立 schema。测试环境与生产隔绝。保留 warnings 捕获。以对应合并基线 CI 记录为正式测试证据 | `pytest -n 4 --dist loadfile` 依 README 环境执行。遵守全量 pre-commit 及仓内 CI 四检查纪律 |
| 证据与隔离 | 真实资料在本地真相层。证据只保留指针和 sha256。评测标准答案只有受控展示例外，生成和检索入口不消费 | `test_diagnostic_eval_contamination.py`、项目授权矩阵、保护清单 |
| 新增触达 | 发送、授权扩张、生产写入、收费、分账及最终验收由人工责任链处理。出站域变化须经蔡工批准 | [04 安全矩阵](04-security-and-authorization-matrix.md) 和 [06 决策登记](06-owner-legal-decision-register.md) |
| Paperclip P0 | 等 M2 稳定后使用独立 compose、数据库、镜像标签及挂载源。回调沿机器回调现有鉴权、限流和时序要求 | v1.1a 修订三；M5 补乱序、早到和重复回调的防御性验证 |

运营验收记录分别确认代码合并、部署、签约与收款授权、交付验收和真实到账。任何 M1、M2 或放量动作依 §16 的前置决策顺序执行。
