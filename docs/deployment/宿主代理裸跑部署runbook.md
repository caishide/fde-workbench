# 宿主代理（host_poll）裸跑部署 Runbook（路线 B · Windows 原生）

> 适用场景：在 **Windows 宿主原生** 跑服务端 + 宿主代理，用 `ZCode.exe` 在本机真实执行智能体 run，
> 产物原件留在 Windows 工作区，服务端只收 `host:` 指针 + sha256（红线 §6.6）。
> 本 runbook 已用 **pilot-001** 真实跑通验证（run `b647945e-4b6e-4010-a8da-e4913fe7430b`，
> `execution_provider=host_poll` → `completed`，3 个产物落库）。
>
> 路线 A（容器）的工作区在容器内，宿主侧读不到，所以 **host_poll 只能在路线 B 裸跑态使用**。

---

## 0. 前置依赖（一次性确认）

| 依赖 | 裸跑态要求 | 验证命令 |
| --- | --- | --- |
| PostgreSQL | 从 Windows 可达（`127.0.0.1:15432` 上的 `fde_workbench`） | `（端口探测）(exec 3<>/dev/tcp/127.0.0.1/15432)` 或 `psql` 连得上 |
| Redis | 从 Windows 可达（`127.0.0.1:6379`） | `redis-cli -h 127.0.0.1 -p 6379 ping` → `PONG` |
| ZCode 二进制 | `ZCode.exe` 全路径存在 | `ls D:/software/zcode/ZCode.exe` |
| zcode.cjs | `resources/glm/zcode.cjs` 存在 | `ls D:/software/zcode/resources/glm/zcode.cjs` |
| 工作区根目录 | Windows 路径，服务端和代理**必须一致** | `ls D:/test/agent-workspaces` |

> ⚠️ **docker 别名陷阱**：`server/.env` 默认的 `FDE_DATABASE_URL=...@twenty-db:5432/...`、
> `FDE_REDIS_URL=redis://redis:6379/0` 是容器网络内部地址，Windows 原生服务端**连不上**。
> 裸跑态必须改成 Windows 可达地址（见 §1），或显式用进程环境变量覆盖。

Redis 若没有 Windows 可达实例，可临时起一个发布到 `127.0.0.1:6379` 的容器：
```bash
wsl -e bash -lc "docker run -d --name fde-redis-win -p 127.0.0.1:6379:6379 redis:7.4-alpine"
```

---

## 1. 启动裸跑服务端（8011）

进入 `server/` 目录，用 **显式进程环境变量** 覆盖 `.env` 的 docker 别名与默认值，再用 Flask 开发服务器启动：

```bash
cd D:/test/fde-workbench/server

export FDE_DATABASE_URL="postgresql+psycopg://fde:<DB密码>@127.0.0.1:15432/fde_workbench"
export FDE_REDIS_URL="redis://127.0.0.1:6379/0"
export FDE_API_PORT=8011
export FDE_AGENT_HOST_POLL_ENABLED=1
export FDE_AGENT_WORKSPACE_ROOT="D:/test/agent-workspaces"
export PYTHONPATH=src

.venv/Scripts/python.exe -c "from fde_api.wsgi import app; app.run(host='0.0.0.0', port=8011, threaded=True, use_reloader=False)"
```

> 说明：
> - `<DB密码>` 取 `server/.env` 里 `FDE_DATABASE_URL` 的密码；若 `.env` 已改为 Windows 可达地址，前两个 `export` 可省略。
> - **不要**用 `gunicorn` 启动：gunicorn 23.x 在 Windows 原生会 `ModuleNotFoundError: No module named 'fcntl'`，必须用 Flask 内置 `app.run()`（跨平台）。
> - `FDE_AGENT_HOST_POLL_ENABLED=1` 与 `FDE_AGENT_WORKSPACE_ROOT` 也可直接写进 `.env`（本机已写），显式 export 只是确保万无一失。
> - 后台运行：命令末尾加 `> srv8011.log 2>&1 &`（Git Bash），或用工具后台启动。

### 1.1 验证 host_poll 已开

`FDE_AGENT_HOST_POLL_TOKEN` 取 `server/.env` 里的同一个值。带令牌访问状态面：

```bash
TOKEN="<server/.env 的 FDE_AGENT_HOST_POLL_TOKEN>"
curl -s -H "X-Host-Poll-Token: $TOKEN" http://127.0.0.1:8011/api/v1/agents/host/status
# 期望：{"data":{"lost_marked":0,"pending":0},"error":null}  HTTP 200
# 不带令牌期望 403 host_poll_token_missing
```

---

## 2. 启动宿主代理 daemon（repo 根目录）

> ⚠️ **脚本位置陷阱**：`host_agent.py` 在 **仓库根** `scripts/agents/`（不是 `server/scripts/`），
> 且必须从**仓库根**启动——脚本靠自身路径推导 `SERVER_ROOT`，再拼接 `server/src` 进 `sys.path`。

```bash
cd D:/test/fde-workbench

export FDE_AGENT_HOST_POLL_TOKEN="<与 server/.env 相同的 FDE_AGENT_HOST_POLL_TOKEN>"
export FDE_AGENT_HOST_ZCODE_BIN="D:/software/zcode/ZCode.exe"
export FDE_AGENT_HOST_ZCODE_CJS="D:/software/zcode/resources/glm/zcode.cjs"
export FDE_AGENT_WORKSPACE_ROOT="D:/test/agent-workspaces"   # 必须与 §1 服务端完全一致
export FDE_API_BASE_URL="http://127.0.0.1:8011"
export PYTHONPATH=server/src

server/.venv/Scripts/python.exe scripts/agents/host_agent.py
```

正常输出（每 15s 轮询一次）：
```
[2026-11-13 11:46:32] 宿主代理启动 base=http://127.0.0.1:8011 interval=15.0s once=False run_id=None
[2026-11-13 11:46:32] 无待领取 run
```

> 后台运行：末尾加 `> host_agent.log 2>&1 &`。
> 调试单次：`python scripts/agents/host_agent.py --once`（轮询+执行一轮后退出）。

---

## 3. 发起 pilot-001 run

`D:/test/launch_pilot_run.py`（本机运维脚本）用已知 `FDE_JWT_SECRET` 铸造 admin JWT，
解析 `pilot-001` 项目与可用 agent，发起 run。它已指向 `BASE=http://127.0.0.1:8011`。

```bash
cd D:/test/fde-workbench/server
.venv/Scripts/python.exe /d/test/launch_pilot_run.py
```

期望输出（关键行）：
```
start_run HTTP 202: {"data": {"detail": "宿主轮询通道已受理：run 等待宿主代理领取。",
  "execution_provider": "host_poll", "id": "b647945e-...", "status": "queued"}, ...}
RUN_ID=b647945e-...
```

> ⚠️ **幂等键碰撞陷阱（最重要）**：`8010`（容器，路线 A）与 `8011`（裸跑，路线 B）
> **共享同一个数据库** `127.0.0.1:15432/fde_workbench`。若某个 `idempotency_key` 已被 8010
> 以 `sandbox` + 默认 `agent-workspaces/` 根创建过，8011 复用同一键会**直接返回那条旧 run**，
> 而不是新建 host_poll run —— 表现为「`/host/status` 说已开，但 run 却是 sandbox」。
> 因此路线 B 每次发起请用**全新 idempotency_key**（脚本里现为 `pilot-001-hostpoll-run-001`）。
>
> 已误建的 sandbox 幽灵 run（典型：`execution_provider='sandbox'`、`context_ref` 以默认
> `agent-workspaces/` 开头、`status='queued'`、从未被任何 worker 领取执行）若占用着你打算复用的
> 幂等键，必须清掉才能让 host_poll 服务端新建 run。清理流程见 **§7.1**（按共享库纪律，
> 清理须**显式指定 run id / 幂等键**并先确认无子行，不得批量裸删）。
> 示例：本仓库已知的幽灵 `0ef28514-216b-4b42-8747-85b4b2dae38e`（键 `pilot-001-first-run-001`）
> 已于 **2026-11-13** 经确认后删除，旧键已释放。

---

## 4. 验证 run 落地为 host_poll + 正确工作区根

```bash
cd D:/test/fde-workbench/server
.venv/Scripts/python.exe - <<'PY'
import psycopg
DB="postgresql://fde:<DB密码>@127.0.0.1:15432/fde_workbench"
c=psycopg.connect(DB)
with c.cursor() as cur:
    cur.execute("select status, execution_provider, context_ref from agent_runs where id='<RUN_ID>'")
    print(cur.fetchone())   # 期望 ('queued','host_poll','D:/test/agent-workspaces/platform/<RUN_ID>/context.md')
c.close()
PY
```

`context_ref` 必须以 `D:/test/agent-workspaces` 开头（不是默认的 `agent-workspaces/`）。

---

## 5. 监视：领取 → 执行 → 回执 → 完成

宿主代理每 15s 轮询，发现 `pending>0` 即 `claim` → 状态变 `host_running` → 拉起 `ZCode.exe`
→ 扫产物 → 回执 → 状态变 `completed`。观察 `host_agent.log`：

```
[11:47:02] run=b647945e-... 工作区=D:\test\agent-workspaces\platform\b647945e-... 开始执行
[11:50:07] run=b647945e-... 回执完成 status=completed artifacts=3 resp={...'status':'completed'}
```

DB 侧核对：
```sql
select status, execution_provider, host_claimed_at, host_receipt_at
from agent_runs where id='<RUN_ID>';
-- 期望 status='completed', execution_provider='host_poll', 两个时间戳非空
```

执行耗时约 3 分钟（真实 LLM 调用），受 `agent_registry.max_duration_ms`（缺省回落 `settings.agent_max_duration_ms`）上限约束。

---

## 5.5 运行之后：产物的下游消费旅程（桌面端同款接口）

run 跑完不是终点——产物要能被**预览 → 复核 → 采纳为方案 → 计入成本**。以下 4 步均已实测通过：

| 步骤 | 接口 | 实测结果 |
| --- | --- | --- |
| ① 预览产物内容 | `GET /api/v1/agents/runs/<RUN_ID>/artifacts/<AID>/content` | 200，返回 `content_base64`（服务端逐字节 sha256 对库行指纹自证，不符即 503） |
| ② 人工复核 | `PATCH /api/v1/agents/runs/<RUN_ID>/artifacts/<AID>` `{"reviewed": true}` | 200，落 `agent_artifact_reviewed` 事件 |
| ③ 采纳为方案 | `POST /api/v1/agents/runs/<RUN_ID>/artifacts/<AID>/adopt-solution` | 200，新建方案（`generated_by='agent'`、`agent_run_id` 回链、产物回写 `linked_solution_id`）；重复调用返回 `duplicate=true` 不重复建 |
| ④ 成本核算 | `GET /api/v1/agents/cost?scope=project&project_id=<PID>` | 200，run 级明细 + 月度汇总 |

> **注意**：`/cost?scope=project` **必须带 `project_id`**，否则 400。
>
> **②③ 需要 `can_manage`**（与产物复核动作同尺），普通 viewer 会得 403。
>
> **③ 的两种模式**：不传 `target_solution_id` ⇒ 新建方案；传了 ⇒ 把产物挂到人工已建的方案上
> （同项目、状态 active、且未绑定其它 run，否则 409）。
>
> **一 run 一方案**：同一个 run 的第二个产物再采纳会得 409 `artifact_already_adopted`
> ——先归档既有方案再采纳。

---

## 6. 验证证据

### 6.1 产物落库（指针 + sha256，原件不进库）
```sql
select kind, storage_ref, char_length(sha256) as sha_len
from agent_artifacts where run_id='<RUN_ID>' order by storage_ref;
```
期望 3 行，`storage_ref` 形如 `host:<RUN_ID>/output/presales-proposal-draft.md`，
`sha_len=64`。`host:` 前缀即红线：**服务端只存指针+指纹，原件留在 Windows 工作区**。

### 6.2 磁盘原件（代理读的就是这份）
```
D:/test/agent-workspaces/platform/<RUN_ID>/
├── AGENTS.md          # 服务端 _write_workspace 写入
├── context.md         # 服务端写入（context_ref 指针指向它）
├── task.md            # 服务端写入
└── output/
    ├── manifest.json                      # 代理扫描依据
    ├── presales-proposal-draft.md         # 真实产物（~17KB）
    └── requirement-clarification.md
```

### 6.3 回执里的非致命校验
本次回执 `failures` 含 `missing_source_refs`（产物未带 `source_refs` 溯源指针）——这是输出扫描器的
**提示性校验**，不阻断 `completed`。属正常现象，不代表管道失败。

---

## 7. 收尾

- 停服务端：结束 §1 的进程（后台任务 / `Ctrl+C`）。
- 停代理：结束 §2 的进程。
- 如需复用同一项目再跑，务必换新的 `idempotency_key`（改 `launch_pilot_run.py` 顶部常量）。

### 7.1 清理误建的 sandbox 幽灵 run

> **适用场景**：某个 `idempotency_key` 被 8010（路线 A）误建成 `sandbox` + 默认 `agent-workspaces/` 根，
> 且你要在 8011（路线 B）复用该键。不清理 → 8011 返回旧 run，host_poll 永远建不起来。
>
> **纪律**：共享库（`127.0.0.1:15432/fde_workbench`）不擅自改在途/他人记录。清理须**显式指定
> run id 或幂等键**，并先确认该 run 无子行、无 worker 领取。下面脚本默认**只列候选、不删**；
> 把 `DRY_RUN` 改成 `False` 才执行删除（删除前会自动再校验子行为 0）。

```bash
cd D:/test/fde-workbench/server

# 1) 先列出候选幽灵（sandbox + 默认根 + 未领取 + 无子行）
.venv/Scripts/python.exe - <<'PY'
import psycopg
DB="postgresql://fde:<DB密码>@127.0.0.1:15432/fde_workbench"
DRY_RUN = True   # 改成 False 才真正删除

c = psycopg.connect(DB, connect_timeout=5)
with c.cursor() as cur:
    # 候选：sandbox、默认根、queued、从未被 host 领取
    cur.execute("""
        select id, idempotency_key, status, execution_provider, context_ref
        from agent_runs
        where execution_provider='sandbox'
          and context_ref like 'agent-workspaces/%'
          and status='queued'
          and host_claimed_at is null
        order by created_at
    """)
    cand = cur.fetchall()
    print(f"候选幽灵 run 数: {len(cand)}")
    for r in cand:
        rid = r[0]
        # 子行校验：agent_artifacts / agent_tool_calls / project_solutions
        cur.execute("""
            select (select count(*) from agent_artifacts where run_id=%s)
                 + (select count(*) from agent_tool_calls where run_id=%s)
                 + (select count(*) from project_solutions where agent_run_id=%s)
        """, (rid, rid, rid))
        child = cur.fetchone()[0]
        flag = "可删" if child == 0 else f"有{child}子行-跳过"
        print(f"  {rid}  key={r[1]}  child={child}  -> {flag}")
        if not DRY_RUN and child == 0:
            cur.execute("delete from agent_runs where id=%s", (rid,))
            print(f"    DELETED {rid}")
    if not DRY_RUN:
        c.commit()
c.close()
print("OK" if DRY_RUN else "DELETED")
PY
```

> 注：执行删除后，对应的 `idempotency_key` 立即释放，可在 8011 用同一键重新发起 host_poll run。
> 若不想冒险用原键，仍可在 `launch_pilot_run.py` 改新键（§3），两条路都通。

---

## 8. 故障排查速查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'fcntl'` | 用 gunicorn 在 Windows 原生启动 | 改用 Flask `app.run()` |
| `/host/status` 403 `host_poll_token_missing` | 没带令牌 | 加 `X-Host-Poll-Token` 头 |
| run 落 `sandbox` + `agent-workspaces/...` 默认根 | 幂等键被 8010 占用 / `.env` 未开 host_poll | 用全新 idempotency_key；确认 `.env` 或显式 env 开了 `FDE_AGENT_HOST_POLL_ENABLED=1` 且 `FDE_AGENT_WORKSPACE_ROOT` 为 Windows 路径；若要复用该键，先按 **§7.1** 清掉幽灵 run |
| 代理日志 `can't open file .../server/scripts/agents/host_agent.py` | 在 `server/` 下启动脚本 | 改到**仓库根** `scripts/agents/` 启动 |
| 代理 `缺少宿主代理环境变量` | 没 export 那 4 个变量 | 补 `FDE_AGENT_HOST_POLL_TOKEN/ZCODE_BIN/ZCODE_CJS/WORKSPACE_ROOT` |
| 代理 `ZCode 二进制不存在` / `zcode.cjs 不存在` | 路径错 | 核对 `D:/software/zcode/...` 实际路径 |
| run 一直 `host_running` 不回执 | zcode 执行中或卡住 | 看 `host_agent.log`；查 `tasklist | grep zcode`；超时由 `max_duration_ms` 兜底后自动转 `timeout` 回执 |
| DB 连不上 | `.env` 仍是 docker 别名 | 显式 export `FDE_DATABASE_URL` / `FDE_REDIS_URL` 为 `127.0.0.1` 地址 |
| 产物预览 404 `artifact_content_path_unsafe` | 指针带 `host:` 前缀（服务端版本早于本次修复） | 升级服务端到含 `host:` 剥前缀的版本；或确认 `agent_workspace_root` 与代理侧一致 |
| 产物预览 404 `artifact_content_unavailable` | 服务端读不到宿主工作区（容器部署态常态） | 裸跑态检查 `FDE_AGENT_WORKSPACE_ROOT` 与代理侧**完全一致**；容器态属预期降级 |
| 采纳产物 409 `artifact_already_adopted` | 同一 run 已有产物被采纳 | 先归档既有方案再采纳（一 run 一方案闸） |
| `/cost` 400 | `scope=project` 缺 `project_id` | 补 `&project_id=<项目ID>` |
| 采纳/预览 403 `project_forbidden` | 当前账号非 can_manage | 与产物复核动作同尺，换项目管理权限账号 |
