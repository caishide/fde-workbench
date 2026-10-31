# goal-d4 · S1 适配器 + 溯源 + 成本（轮次报告）

> 输入：goal-d3 报告 + 《交付工作台升级 PRD v1.0 定稿》§4 F3 + 《技术实施方案-智能体交付工作台》§3.1/§5/§8 + 自动交付设计 §7.1 V 判据 + goal 循环提示词 v1.0（goal-d4 节）+ 代码实测。
> 基线（开工预检实测 2026-10-31，fork/main `c4f7f14`，B1+D3 联合口径）：91 业务表 / head `d9c3e7f1a5b8`（16 revision）/ 蓝图路由 233 / ENTRIES 73 / pytest 1493 收集（1487 通过 + 6 跳过）/ vitest 676。

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，d3 末） | 定级 | 本轮行动 |
|---|---|---|---|---|---|
| G1 | AgentAdapter + zcode 适配器 | 技术文档 §5：spawn/监听/回收三段；V1 | `agents/` 只有 models/sandbox，零适配器 | P0 | `agents/adapter.py`：`ZcodeAdapter` 三段 + `AgentRunContext`/`AgentRunResult` + 事件/产物扫描可注入 |
| G2 | agents 蓝图 7 路由 | 技术文档 §3.1 agents 段 | 零路由（d3 零路由收口） | P0 | `agents/routes.py`：GET /agents（含不可用原因）/ POST run / GET runs{id} 溯源 / handoff / retry / tool-calls / cost |
| G3 | run 生命周期 | 循环提示词 d4：幂等键、重试≤2 指数退避、ai_manual_handoff、超时/预算熔断 | 表齐（d3）语义空 | P0 | `agents/service.py`：幂等去重（服务层收敛）、retry 链 ≤2 + 指数退避、L3 handoff（E-2）、超时（B-1）/单 run 预算（B-2）/月度预算（`FDE_AGENT_MONTHLY_BUDGET`）熔断 |
| G4 | 上下文脱敏渲染器 + CI 断言 | 技术文档 §5 红线段 | 无渲染器；ProblemItem 直读会带原文风险 | P0 | `agents/context.py`：代号+confirmed ProblemItem+模板骨架+知识片段；盘符路径/PEM/令牌自动遮蔽 + `agent_forbidden_terms` fail-closed；毒化输入零命中断言 |
| G5 | egress allowlist 实装 | 技术文档 §4：per-run 网络 + iptables 白名单（d3 显式拒绝挂起） | `SandboxError("egress_allowlist_not_available")` | P0 | `sandbox.py`：`EgressPlan`（per-run 网络/子网 + iptables ACCEPT 白名单 + REJECT 兜底 + kill 回收），argv 事实层 CI 可测，真实 iptables 联调归试点 |
| G6 | 沙箱降级链 L2 接线 | 自动交付 §3.2 A-1 / 技术文档 §4 降级段 | sandbox.py 注释「调用方（d4）」 | P0 | service 捕 `SandboxError` → run 落 `fallback_level=L2` + 零计费 + `agent_unavailable` 503 |
| G7 | denied 留痕（V3 前半） | D-1：越权调用落 `agent_tool_calls` + run 标 degraded | 表齐无写入方 | P1 | 适配器监听段 tool_call 事件 → 白名单判定 → denied 落表 + `degraded_reason="tool_denied"` |
| G8 | 产物校验（C-1）与 handoff 终审（V7/E-2） | 自动交付 §7.1 V6/V7 | `solution_review_checkpoints` 表无业务写入方 | P1 | manifest source_refs 校验：缺/未知引用 → run failed + 产物 `reviewed=False` 不进终审；handoff 建 pending signoff checkpoint（project_manager） |

**本轮明确不做**（沿循环提示词边界）：codex/claude_code/opencode 适配器（只有 zcode，其余注册项在 GET /agents 报 `adapter_missing`）；V3 后半三重交集与工具面 `meeting_convene`（d5/d6）；V4 全链手动触发与 V11 degraded UI 标注（d6）；V12 插件 disable 同步（d6，本轮只有 `disabled`/`adapter_missing`/`credential_missing` 三类静态不可用原因）；solutions 段 `generate-agent` 路由（技术文档 §3.1 solutions 段，随 d6 降级链收口）；O-3 额度/seat 归集口径（d7，本轮 `cost_owner_id` 先记 project_id）。

## 二、行动说明

- 分支 `feat/delivery-d4-adapters`（基于 fork/main `c4f7f14`，隔离 worktree + junction 配方）；**零迁移、零新表**（head 仍 `d9c3e7f1a5b8`，16 revision）；新文件 12（agents 模块 4：adapter/context/service/routes + 测试 7 + 本报告）+ 修改 8（sandbox.py/app.py/config.py/api_catalog.py/两份 .env.example/Dockerfile/test_sandbox_isolation.py）。
- **偏离架构方案原文一处（登记）**：§6.2 `AgentAdapter.run` 为 async 签名——本仓库服务端为同步 Flask 栈，按同步 `run` 实装，接口形态（ctx + sandbox → result）不变；async 化留待 worker 化时评估。
- **设计决议（本轮）**：① 幂等键不设唯一（d3 已登记）在服务层落地为三态——completed 复用、在途复用、终态失败强制显式 retry；重试链共享幂等键，家族大小即尝试数（≤3 run），退避 `base·2^(已重试次数)`。② egress 子网按 run_id 哈希确定性派生（`17231.x.0/24`），避免并发 run 抢网；iptables 规则只作用于本 run 子网，不碰宿主其他转发。③ C-1 产物「先落账再抛错」：能取指纹的产物留痕（`reviewed=False` 永不进终审），缺文件的产物无指纹不落行（storage_ref+sha256 必须成对完整——红线）。④ api_catalog 只收 agents 只读四条；run/handoff/retry 属人工授权写路径不收（沿门禁三路由先例）。
- **行为变更**：无（既有路由/契约零改动；d3 测试「allowlist 未实装」断言随实装升级为实装断言，属 d3→d4 演进）。
- **影响面与回滚**：agents 蓝图整体可下线（app.py 单注册点）；`FDE_AGENT_*` 全部有安全默认（预算 0=不限额、egress 空=deny 基线、禁区词空=只走模式遮蔽）。

**rebase 备注（2026-11-01，两轮）**：CI 期间并发会话相继合并 PR #49（B2 调度台）与 PR #51（B3ops 运维页），本轮回两次重放：第一轮基于 `3de6c2c`（B2 基底），第二轮基于 `fc64be1`（B3ops 基底：路由 239/ENTRIES 79/pytest 1507/vitest 695）。最终合并口径=路由 246 / ENTRIES 83（实测）/ pytest 1541 收集 / vitest 695；api_catalog 双侧条目合并（B3ops 5 条 + d4 4 条）且目录完整性测试双绿。本报告 §三 的全量数字为 d4 轮在 c4f7f14 基线上的实测（1527 收集），最终以 CI 在 rebase 头上的全量绿为准。

## 三、验证结论

| 判据 | 结果 | 证据 |
|---|---|---|
| V1 | ✅ | zcode 注册 + GET /agents 可见；disabled/adapter_missing/credential_missing 三因各得其报（test_agents_adapter.py） |
| V5 | ✅ | B-1 timeout + 产物不入库 + kill argv；B-2 budget_exceeded + 成本停在阈值内；月度闸 409（test_agent_budget.py） |
| V6 | ✅ | C-1 三类失败 422 失败码可见 + reviewed=False；校正后 retry 回退补录闭环（test_solution_validation.py） |
| V7 | ✅ | handoff → 接管人 + L3 + pending signoff（project_manager）；重复接管/completed 接管 409（test_solution_validation.py） |
| V8 | ✅ | I-1 同键 201→200 run 数=1；失败显式 retry；上限 2 次 + 指数退避 409→放行（test_agent_idempotency.py） |
| V9 | ✅ | T-1 反查链 solution(agent_run_id)→run→产物 sha256→context 文件→source_refs（test_agent_traceability.py） |
| V10 | ✅ | M-1 明细+月度汇总一致；scope 权限 403/404/400 收口（test_agent_budget.py） |
| V3 前半 | ✅ | D-1 denied 落 `agent_tool_calls` + run degraded（tool_denied），run 继续（test_agents_adapter.py） |
| A-1 接线 | ✅ | SandboxError → 503 agent_unavailable + run 落 L2 + token_cost=0（test_agents_adapter.py） |
| CI 脱敏断言 | ✅ | 毒化输入渲染产物：盘符×2/令牌/PEM 零命中 + 占位符在位；禁区词单元 fail-closed + 服务闸 422 E2E 零 run 落库（test_agent_context_sanitization.py） |
| 反假绿灯四条 | ✅ | ①声明=断言（+34 用例逐条对 V/用例编号）；②变异 M1–M5 各「变异→红→还原→绿」（M1 deny/allowlist 矛盾检查拆除、M2 退避公式清零、M3 预算越界入账、M4' 超时放行为 completed、M5 禁区词熔断拆除）；③真执行（sandbox allowlist 断言目标 argv 序列非空、脱敏断言目标字符串集合非空）；④数字实测（下表） |

**全量数字（实测 2026-11-01 收口）**：

| 项 | 结果 |
|---|---|
| 服务端 pytest | 全量 `1527 收集`：**1521 passed / 6 skipped / 0 failed**（基线 1493 + 本轮 +34；修复 catalog 两条目后复测）|
| 桌面 vitest | 676/676（零改动）；typecheck 零错误 |
| ruff | `F401,F841` src+tests All checks passed；agents 模块全规则 All checks passed |
| mypy 基线 | OK：no new type errors（顺带消化基线旧账 10 处） |
| 迁移 | 零新迁移；`alembic check` 语义不适用（无模型变更） |

（M4 首版变异「deadline 检查拆除」导致假时钟循环不终止而非变红——已停任务还原，改用 fail-fast 变异「超时放行为 completed」完成闭环；此教训登记 §四。）

## 四、下一轮建议 + 新登记差距（进台账二十七）

1. **d5（T2 lite 评审会）**：review_meetings 三表 + meetings 6 路由 + `meeting_convene`/`meeting_get_minutes` 工具面 + 纪要封存 + worker 状态机 T2 强制钩子（`review_gate_open`）。
2. **d6 收口清单（本轮挂账顺延）**：solutions 段 `generate-agent` 路由 + `solution.agent_run_id` 自动接线（本轮 T-1 用 ORM 直设锚验证链路）；V4 全链手动触发 + V11 degraded 全链标注；V3 后半三重交集 + V12 插件 disable 同步；run 卡死恢复（同步执行中 crash 留 running 态——本轮已知边界）；真实 iptables 生效性 + 沙箱镜像内 zcode CLI 版本钉定（试点前人工联调，镜像已装 iptables）。
3. **d7**：O-3 额度 seat 归集口径（本轮 cost_owner_id 暂记 project_id）+ 加油包 + UI 透明化。
4. **工程教训（变异纪律补丁）**：拆「循环出口」类变异会让测试挂死而非变红——变异设计必须保持终止性（fail-fast 变异：改终态语义而非删出口）。
5. 遗留观察项沿 d3：manifest mtime 卫生（P3）、健康分编辑态展示（桌面轮次处理）。
