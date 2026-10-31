# goal-d3 · S1 表簇 + capability +4 + 沙箱基座

> 第三轮，输入：goal-d2 报告 + PRD §4 F3/§6 + 技术实施方案 §2/§4/§9 + goal 循环提示词 v1.0（goal-d3 节）+ 架构方案 §9/§6.4 + 自动交付 §5.1。

## 一、差距清单（逐项对齐循环提示词 goal-d3）

| # | 差距 | 现状 | 动作 |
|---|---|---|---|
| 1 | 5 新表 `agent_registry`/`agent_runs`/`agent_artifacts`/`agent_tool_calls`/`agent_credentials` | 不存在；d2 仅 `source_json.kind="skeleton"` 占位溯源 | 新建 `fde_api/agents/` 模块 models.py，逐列对齐架构方案 §9 + 自动交付 §5.1 增量 |
| 2 | `solution_review_checkpoints` | 不存在 | 同上（template/rule/knowledge/signoff 四类，E5 人工闸门） |
| 3 | `ProjectSolution` 增 4 列 generated_by/agent_run_id/template_id/confidence | 列不存在；骨架溯源藏在 source_json | 列级 ALTER（非新表，技术文档 §2 明示）；迁移回填：`source_json->>'industry_template_version_id'` → `template_id`（generated_by 保持 'human'——骨架是 AI 不参与内容生成的人工草稿） |
| 4 | `CAPABILITY_REQUIREMENTS` +4 | 18 项无 agent.* | +`agent.plan.generate`(≤project_operator)/`agent.code.write`(≤project_manager)/`agent.system.tool`(=system_operator)/`agent.meeting.convene`(≤project_operator)；桌面 `aiCapabilityLabels` 补中文标签 |
| 5 | `sandbox/` 模块 + compose `sandbox-runner`（§4：network none/tmpfs/资源上限/凭据注入/egress 白名单） | 无任何沙箱代码；compose 只有 redis/api/worker/scheduler | `agents/sandbox.py`（SandboxProfile/SandboxHandle/后端可注入）+ compose sandbox-runner 服务（`profile: ["sandbox"]` 门控，试点前不随默认 up 启动）+ docker/sandbox 最小镜像 |
| 6 | V2 四断言 | 无 | 新建 `tests/test_sandbox_isolation.py`：①宿主机无凭据明文 ②只挂 run workspace ③egress deny ④销毁回收；+ compose 基线断言 |
| 7 | 迁移可逆 + 既有零回归 | head `c5d7e9f1a3b7`（15 revision） | 新迁移 down_revision=c5d7e9f1a3b7；`test_migrations.py` HEAD 常量同步；conftest 清理序按新 FK 展开 |

**明确不做（边界）**：agents REST 蓝图 7 路由与 zcode 适配器归 d4；review_meetings 三表归 d5；dispatch `agent_assisted` 标记归 d8；egress allowlist 的 per-run 网络 + iptables 白名单需要真实 docker daemon 联调，随 d4 适配器落地——d3 的 sandbox 模块对该档显式抛 `SandboxError("egress_allowlist_not_available")`，默认 deny 已实装。

## 二、逐列设计决议（架构方案 §9 原文 + 自动交付 §5.1 增量之外的本轮落地口径）

- `agent_registry.kind` Check ∈ (zcode, codex, claude_code, opencode, persona)——`persona` 依技术文档 §2「kind 枚举含 persona」；`allowed_tools` JSON 默认 `[]`（声明式白名单，自动交付 §5.1）。
- `agent_runs`：status Check ∈ (queued, running, completed, failed, timeout, budget_exceeded)；`degraded_reason` String(32)（对应异常分类 A–E）；`fallback_level` Check ∈ (L0, L1, L2, L3) 可空；`retry_of` 为 String(36) 软引用（**不设 FK**：幂等链允许指向将来被归档清理的 run，硬 RESTRICT 会制造清理死锁——偏离架构方案原文处，特此登记）；`idempotency_key` 非唯一 Index（重试行与原 run 同 key，唯一约束会封死重试链；幂等语义在 d4 服务层收敛）；`cost_owner_type` Check ∈ (project, seat, platform) 默认 project（归属口径 O-3 待 d7 拍板，先落枚举骨架）。
- `agent_artifacts.kind` Check ∈ (code, doc, diff, config)；`sha256` 加 char_length=64 Check（红线：指纹列必须是完整指纹）。
- `agent_credentials`：对齐 ModelPreference 既有加密先例（Fernet + `FDE_MODEL_CREDENTIAL_KEY` 派生），列名沿用 `credential_ciphertext`；**绝不回显**沿用 redact 纪律（解密仅发生在注入时刻，d4 接线）。
- `solution_review_checkpoints.required_level` Check 沿用 ACCESS_RANK 四档（disabled 无意义不入枚举）。
- ProjectSolution `generated_by` server_default 'human' + Check ∈ (human, agent)；`agent_run_id`/`template_id` FK 均可空 RESTRICT；`confidence` Float 可空（架构方案 §9 E3 原文）。
- 沙箱凭据注入：`docker exec -e` 经内存传递，`redacted_argv()` 供日志路径使用（值替换为 `***`）；宿主磁盘/日志零明文。
- compose `sandbox-runner` 用 compose `profiles: ["sandbox"]`：默认 `docker compose up -d` 不启动它（试点 d6 才开），镜像构建与基线配置已就位——技术文档 §4 的 network_mode: none / privileged: false / tmpfs /workspace:size=512m 全部落进 compose 事实。

## 三、验证结论（全部本包实测）

- [x] 新迁移 up/down 可逆：`test_migrations.py` 15/15（含 downgrade c5d7e9f1a3b7 → upgrade head roundtrip 与骨架回填专测）；`alembic check` 零差（env.py 补 `agents.models` 注册——否则 `project_solutions.agent_run_id` 的字符串 FK 解析不到表）
- [x] V2 四断言 + compose 基线：`test_sandbox_isolation.py` 5 例全绿（凭据仅 env 内存管道/argv 零明文、恰一个 workspace 挂载 + 真相层拒挂、--network none + 资源上限 + compose 断网基线、rm -f 销毁 + 幂等 + 销毁后拒绝操作、DockerBackend 失败归一 A 类不外抛 stderr）
- [x] 基础断言：`test_goal_d3_s1_foundation.py` 11 例全绿（六表约束/默认值、RESTRICT 链、generated_by 列化、回填三态、capability 档位、agent.system.tool 系统级、agent.code.write 实时鉴权）
- [x] 变异闭环 M1–M4：--network none→bridge / kill 跳过 rm / agent.code.write 降档 / 拒挂标记去 .env——各「变异→红→还原→绿」，无 mutbak 残留
- [x] 桌面：typecheck 零错误；vitest **667/667**（零改动，accessLabels 纯增量）
- [x] ruff All checks passed；mypy d3 触碰文件零错（基线噪音均为传递依赖既有项）
- [x] 全量服务端 pytest：见 §四
- [ ] capability +4 对既有用例的适配：**零适配**（既有能力清单断言均为子集/成员断言，非全量冻结）

## 四、全量回归数字（本包实测 2026-10-31）

| 项 | 结果 |
|---|---|
| 全量服务端 | **1480 passed / 6 skipped / 0 failed**（16:39，安静窗口单跑；fork/main 基线 1464 + 本轮 16 新用例） |
| capability +4 冲击 | 零适配——受影响 4 文件（test_ai_api_actions / test_ai_file_delivery / test_extension_management / test_lcsc_capability_gate）38 例全绿 |
| 桌面 | typecheck 零错误；vitest **667/667**（零改动） |
| ruff / mypy | All checks passed / d3 触碰文件零错（基线噪音均为传递依赖既有项） |
| 迁移 | head `d9c3e7f1a5b8`（16 revision）；down/up roundtrip + 回填专测全绿；`alembic check` 零差 |

## 五、新增文件与触点清单

- 新增：`server/src/fde_api/agents/`（models.py + sandbox.py）、`server/migrations/versions/d9c3e7f1a5b8_s1_agent_tables.py`、`docker/sandbox/Dockerfile`、`server/tests/test_sandbox_isolation.py`（V2×5）、`server/tests/test_goal_d3_s1_foundation.py`（×11）
- 修改：`solutions/models.py`（+4 列）、`control/access.py`（+4 能力 + agent.system.tool 系统级规则）、`config.py`（sandbox_* 7 字段）、`migrations/env.py`（agents.models 注册）、`tests/conftest.py`（清理序）、`tests/test_migrations.py`（HEAD 常量）、`compose.yaml`（sandbox-runner）、`desktop/src/renderer/src/ai/accessLabels.ts`（+4 标签）、AGENTS.md、台账节二十五、技术文档 §0

## 六、行为变更声明

**零既有路由/契约行为变更**：本轮零新路由、零 api_catalog 条目（agents 蓝图归 d4）；`authorize_ai_capability` 仅新增 `agent.system.tool` 系统级分支（新能力名，无既有调用方）；`/users/{id}/ai-access` 能力清单对持有相应档位的账号多出 agent.* 条目（纯增量展示）；compose 默认 `up -d` 不启动 sandbox-runner（profiles 门控）。
