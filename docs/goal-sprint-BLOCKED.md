# goal-sprint BLOCKED / 待授权登记

> 任务书 §4：「拿不准的写 `docs/goal-sprint-BLOCKED.md`」；§8：「BLOCKED.md 随收口 PR 提交」。
> 本线 r1–r6 与收口终扫全程无 Agent 侧阻塞项；以下为**收口终扫现测发现的共享活体风险与待授权业务闸**，全部不属于本线改动面，处置归蔡工/运维层。

## 待授权（业务闸，Agent 不代拍）

1. **D7 阈值拍板**：四口径复审报告已于 r4 出齐（`docs/audit/D7-四口径运行证据复审报告-2026-11-13.md`），阈值拍板位维持「待蔡工拍板」（零预支，闸态变更=0）。
2. **G-B／G-C Go/No-Go 闸签署与试用账号发放**：部署方案 v1 §8 十三项技术判据已现测具备（2026-11-09 T6 组现测＋R-T6-1 PR #250 根治），但 `G-B`/`G-C` 未签 ⇒ 不得发放任何登录信息（原文纪律维持）。
3. **N1 试点窗口到期处置**：窗口 2026-11-12～2026-11-19；窗口内 2 条 `host_poll` run 全 `completed` 且 8/8 产物已人工复核（2026-11-14 现测），窗口 11-19 到期后的续期/关闭/回收决策归蔡工。

## 共享活体现测风险（收口终扫 2026-11-14 发现，处置待运维拍板）

4. **跨栈 Redis 服务别名冲突（DNS 轮询）**：`fde-workbench-*` 栈与 `fde-wt-deploy-diag-*` 栈（r5 T-14b 部署）共存于同一 Docker 网络 `automation_qiflow-net`，两栈 compose 服务别名同为 `redis` ⇒ Docker DNS 对名 `redis` 轮询解析。现测证据：`fde:health:worker` 键落在 `fde-workbench-redis-1`、`fde:health:scheduler` 键落在 `fde-wt-deploy-diag-redis-1`（跨栈串写）。影响面＝心跳观测分裂＋后台队列 `lpush/brpop` 理论上可被对栈 worker 消费（当前 `background_jobs` 无 running/queued 行，暂无实害）。处置选项（改 compose 网络别名唯一化或两栈分网）＝生产拓扑变更，超出收口轮零代码范围且涉另一栈 ⇒ 待蔡工拍板后单独立项。
5. **容器 healthcheck 探针 FAIL 不置非零退出码**：`python -m fde_api.health.heartbeat scheduler` 在键缺失时输出 `FAIL ...` 但 `exit=0`（2026-11-14 实测），⇒ healthcheck「healthy」对心跳缺失无判别力（#72 族）。修复（探针按 check 结果置 exit code）＝服务端生产代码改动 ⇒ 待单独立项，不混入收口 PR。
