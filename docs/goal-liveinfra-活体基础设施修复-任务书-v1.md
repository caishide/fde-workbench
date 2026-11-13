# goal-liveinfra · 活体基础设施修复任务书 v1

> **线名**：goal-liveinfra（活体基础设施修复）｜**立项依据**：goal-sprint 收口终扫 2026-11-14 两项现测发现（`docs/goal-sprint-BLOCKED.md` #4/#5）；**蔡工拍板**：2026-11-14 交互选择卡「单独立项一次修两项」。
> **性质**：部署拓扑＋服务端小 PR 联合轮；**一个 PR**（compose 拓扑变更与探针修复同轮交付，活体一次 recreate）。
> **边界**：不动 diag 栈归属与代码；不引入新监控面；不改任何业务行为。

## 1. 背景与问题定义

### R1 跨栈 Redis 服务别名 DNS 轮询（部署拓扑）
`fde-workbench-*` 栈与 `fde-wt-deploy-diag-*` 栈（r5 T-14b 部署的 D-3 独立轻部署）共存于同一 Docker 网络 `automation_qiflow-net`，两栈 compose 服务别名同为 `redis` ⇒ Docker DNS 对名 `redis` **轮询解析**。现测证据（2026-11-14）：`fde:health:worker` 键落在 `fde-workbench-redis-1`、`fde:health:scheduler` 键落在 `fde-wt-deploy-diag-redis-1`（跨栈串写）。影响面＝心跳观测分裂＋后台队列 `lpush/brpop` 理论上可被对栈 worker 消费（两栈各自有独立 DB，跨栈消费 job 会拿错库 run_id——当前无 running/queued 行，暂无实害，属埋雷）。

### R2 healthcheck 探针 FAIL 不置非零退出码（服务端）
compose healthcheck 命令 `python -m fde_api.health.heartbeat <name>` 在心跳键缺失时输出 `FAIL no heartbeat key` 但 **exit=0**（2026-11-14 实测）⇒ 容器「healthy」对心跳缺失无判别力（I4 心跳设计「卡住即 unhealthy」的语义被探针架空；worker 卡死事件 2026-11-14 实测发生、靠人工 restart 恢复）。

## 2. 修复方案

### R1 Redis 别名唯一化（择 A，B 备选）
- **A（推荐）**：`fde-workbench` 栈 compose 内将 redis 服务别名改为栈内唯一名（如 `redis` 保留服务名、network alias 增设 `fde-workbench-redis`，`FDE_REDIS_URL` host 同步改），diag 栈不动——本栈容器 recreate 后 DNS 不再与 diag 栈轮询。
- **B（备选，若 A 受网络插件限制）**：为本栈单建独立网络（`fde-workbench-net`），redis/api/worker/scheduler 全部迁入并从 `automation_qiflow-net` 摘除（注意：该网络同时承载其他跨栈 forward 容器，摘除前须核对 `fde-pg-forward`/`fde-redis-forward` 的依赖方向）。
- 涉及文件：`compose.yaml`（服务别名/网络/`FDE_REDIS_URL`）＋`.env.example` 相关注释；属部署配置面，零 Python 代码。

### R2 healthcheck 探针置 exit code
- `server/src/fde_api/health/heartbeat.py` 的 `__main__` 块：现单参模式语义核实后，改为 **check 语义**（healthcheck 场景）：键缺失/过期 ⇒ 打印 `FAIL ...` 并 `sys.exit(1)`；健康 ⇒ 打印 `OK ...` 并 `exit=0`。
- ⚠️ 先核实现网是否有其他调用方依赖「单参＝beat 写入」语义（`compose.yaml` 两处 healthcheck、值守脚本、文档）；若有，healthcheck 命令改调显式 `--check` 子命令，beat 语义保留——**调用面清查结论写进 PR 描述**。
- 测试：新增/改造用例钉住「键缺失 ⇒ exit 1」「键新鲜 ⇒ exit 0」；变异验证（删探针判别分支 ⇒ 红）。

## 3. 轮次与验收判据

| # | 内容 | 验收 |
|---|---|---|
| 单轮 | R1 compose 别名唯一化＋R2 探针 exit code，同 PR 交付 | ①两栈各自 redis 内心跳键归位（`docker exec <本栈redis> KEYS fde:health:*` 含 worker+scheduler 且 diag 栈不再新增本栈键，连续观测 ≥2 周期）；②探针变异验证：手删心跳键 ⇒ 下一探针周期容器转 `unhealthy`（先在隔离参数下验证，防误伤生产）；③活体三验（url_map/alembic current/镜像 ID）；④CI 四 job 绿；⑤diag 栈复核零扰动（其容器 healthy、其心跳键仍归其栈） |

## 4. 闸与红线

- **部署闸**：recreate 涉共享活体，执行前 `takeover_check.py --tree <部署树> --live`；与并发线部署窗口错峰；recreate 后三验＋心跳归位观测。
- **红线**：H1–H13/N1–N7 不变；不代拍部署窗口（recreate 时点如与并发线冲突，如实挂 BLOCKED 等窗口）；`FDE_REDIS_URL` 变更属部署态配置，`.env` 差异按 takeover 检查器口径登记。

## 5. 排期

**立项即排期待定**（不与并发线抢窗口）；实施授权＝本任务书在库＋蔡工对实施时点的显式令（排期≠实施授权惯例）。
