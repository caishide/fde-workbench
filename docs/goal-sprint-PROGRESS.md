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
- [ ] ★核对并发线 `feat/e8-fallback-e11-credentials`（E8/E11 落地线，2026-11-13 现测已在主树检出、基点 `35ffbea`）——若 E8 已实施合并：r6「条件轮」降级为「验收＋收口轮」，吸收条款照扫其改动面；两线同碰 `agents/` 域时按插队纪律处置

### r1 收口回执（2026-11-13）

- PR **#411** squash 合并 `5a3f276`；CI 四 job 全绿（权威 run **43291551524**：server-tests 12m20s／desktop 2m26s／pseudonymization 58s／secrets-scan 9s）。
- main 追平 fork/main＝`5a3f276`（主树被并发线检出 feat 分支 ⇒ 用 `git fetch fork main:main` 只推 ref 不动检出——共享树 HEAD 争用面新配方）；`goal-sprint-r1` 分支本地（树 diff 空＝squash 零漂移证明）＋远端均已删；sprint worktree 现 detached @ `5a3f276` 待 r2。
- r1 遗留：蔡工发起首个 run（窗口 11-19 止）后补证据 sha256 登记；未发起则窗口关闭如实登记转 r2。

## r2 · P2′ 服务端咬合面收口（2026-11-13，生产代码轮）

### 开工前检查单（吸收条款执行记录）

- [x] `git fetch fork` 对齐：基点 **`86722e6`**（#417 crv r5 合并轮）；在途 PR 仅 #6/#7（quickflying 10 月旧件，非活跃轮，不阻塞）。
- [x] 扫 goal-crv QR 台账（**已出 5 域章 98 行**，`docs/audit/全面代码审查报告-2026-11-13.md`）——与本轮改动面（agents 领取/回执/状态机）相交：**QR-073（P1）必吸**＋同函数 P2 两连 **QR-088/089 吸收**；QR-090（容器面 receipt ask）/086/087（retry）/091/092/094/095（spawn 段＝r3 面）**相邻不吸收**，照常走 QR→修复批轮。
- [x] ★核对并发线 `feat/e8-fallback-e11-credentials`：**已合并＝#414**（E8 只读降级层＋E11 凭据管理面，`8cbb21b`）⇒ **r6「条件轮」降级为「验收＋收口轮」**（吸收条款照扫其改动面）；本轮已核其改动（agents/credentials.py＋control/automation_*）与 P2′ 咬合面无交集冲突。
- [x] 建 `D:/test/fde-wt-sprint` 分支 `goal-sprint-r2`（从 `86722e6`）。

### 范围现测校正（重要）

P2′① 咬合半**已于 #204/#215（2026-11-08）落地**（迁移 `f6d3a9c1e7b2`：status CHECK＋`host_running`＋`execution_provider`/`host_claimed_at`/`host_token_hash`/`host_receipt_at`/`host_lost_at`；三路由 `GET /agents/host/status`／`POST /agents/host/claim`〔FIFO+skip_locked+幂等重领〕／`POST /agents/host/runs/{id}/receipt`；发起侧 202；`mark_host_lost` H4 只标记；config 默认全关）。**r2 不重造**——实际工作面＝crv 吸收＋N2 两事实接线＋§11.3 六约束核对（核对结论：约束①③④⑤⑥既有实现全部在场；②的幂等/鉴权在场但行锁有 QR-088 缺口，本轮补）。

### r2 变更面

- **QR-073（P1，吸收）**：NEW `workspace_files.is_unsafe_artifact_path()` 单一真身（盘符/反斜杠/根锚三形态）替换 `service._finalize`＋`host_receipt` 两处弱判定；且 unsafe 路径**不读文件不进 prepared＋回执面不落 AgentArtifact 行**（原实现只要 digest 形状合法就落行——Windows 裸跑态 `workspace/output/<盘符路径>` 的 Path 连接会替换基座直读宿主任意文件）。
- **QR-088（P2，吸收）**：claim 带 `run_id` 重领路径补 `with_for_update()`（等锁后重读最新状态判 403/幂等；FIFO 面保持 skip_locked）。
- **QR-089（P2，吸收）**：`agent_runs` 加可空 `frozen_tools` JSON 列（**迁移 `c8e2a6f0b9d4`，73→74 单头**）；`start_run` 落发起时刻三重交集快照；领取载荷（含续领分支）读快照，旧行 NULL 回落 registry 读（行为兼容）。
- **N2 两实测事实接线**：NEW `agents/host_preflight.py`（唯一真身，r3 宿主代理复用）——①provider 覆盖开关成对校验；②`defaultModelSelection` 键在场校验。接线点＝`run_host_channel` spawn 前（出站闸之前）；失败→既有 HostChannelError→L2 明确失败映射（零 spawn 零计费，重试由人 H4，不静默重试）。config 新键 `FDE_AGENT_HOST_ZCODE_CLI_CONFIG`。
- 测试：test_host_poll +6 例（参数化展开 10 项：rival 提交重读 403／frozen 快照／旧行回落／五形态路径零行×5／202 受理快照落库）、test_host_channel +5 例（参数化展开 10 项：preflight 正负例＋校验先于出站闸）；既有 host 三件套补 preflight 注入点（临时 CLI 配置＋env 开关清理）。
- **变异五连全红→字节级还原→绿**（M1 去行锁／M2 快照退实时／M3 路径退旧判定／M4 模型键短路／M5 成对短路）。★教训：M1 首版判别力不足——持锁者**未提交**时无锁实现的 UPDATE 同样阻塞在行锁上，测试假绿；改「rival **提交**后等锁重读判 403」形态才杀灭（判别力本身要验收的家族教训再现）。
- 验证：定向 155+ 例绿；ruff 绿；mypy **277/102 基线不变**；inventory 重提取（revision_count 73→74；路由 488/蓝图 52/表 153 不变）；防陈旧闸绿（图纸无迁移数声明，M4 纯迁移轮先例不重生 archify）；全量 pytest（见收口回执）。
- 环境注记：sprint worktree 新建独立 `server/.venv`（xdist worker 全新解释器不带 `-c` 前导 sys.path，主 venv editable 指向主树——每工作树一份环境纪律）。★教训：venv 必须按 CI 配方 `pip install -r requirements.lock -e ".[test,dev]"` 安装——裸 `pip install -e` 拉到 SQLAlchemy 2.1.8/新 pydantic，mypy 基线检查假红 9 条（全在未触碰文件）；且 `scripts/check-python-types.py` **优先用树内 server/.venv**（存在即用），同一命令在树内有/无 venv 时走不同解释器。
- ★CI 首轮红例与修复（run 43337413266 server-tests 1 failed）：`test_agent_execution_grant_wiring.py::test_host_channel_run_records_authorization_fingerprint`——该测试的 `_host_settings` 未带 `agent_host_zcode_cli_config`，CI（无 ~/.zcode/cli/config.json）撞本轮新增 spawn 前置校验 ⇒ run 落 L2 而非 completed。修复＝与 test_host_channel_service 同款注入（`c6a060f`）；全仓 `agent_host_zcode_bin` 构造点闭集复扫＝2 处均已注入。★教训：新增机械闸后，测试面的构造点闭集扫描要按 **settings 键名**（`agent_host_zcode_bin`）而非类名（`HostChannelSettings(`）——前者抓到了后者漏掉的 service 级构造点。

### r2 收口回执（2026-11-13）

- PR **#422** squash 合并 **`3dc07fe`**；PR CI 两轮（首轮 server-tests 1 红＝授权票据测试缺 preflight 注入点，`c6a060f` 修复）⇒ tip run **43340038319** 四 job 全绿（desktop/server-tests/secrets-scan/pseudonymization；另一同 sha run 43340030857 亦四绿）。合并树权威 main run **43342235002** 被并发合并取消（家族行为）⇒ 以 tip run **43343183487**（`979eeed`＝`3dc07fe`＋docs-only #423）为 superset 权威。
- main 追平：`git fetch fork main:main`（并发线 #418/#420/#421/#423 四 PR 插队窗口内落地）；`goal-sprint-r2` 远端已删、本地分支在 r3 分支建后删除；合并树 CHANGELOG 结构终扫零丢失（我方 r2 节＋节体逐字在场；插队方本就无 CHANGELOG 节）。
- 活体部署三验全绿（从本树 `-p fde-workbench` 接管）：**alembic 真实升级 `b5d9e2f4a7c1 → c8e2a6f0b9d4 (head)`**（frozen_tools 列上活库）／url_map **488** non-static ＝ 口径／三镜像逐位一致 api `33eff9e990a7`／worker `36c3e692e176`／scheduler `b949caac6a02`／ready 200。★部署配方坑：worktree 部署必须 `docker compose -p fde-workbench build/up`（不带 `-p` 落目录名项目，撞活体 8010 端口Bind 失败＋镜像 tag 错项目——首次 up 失败即发现，`-p fde-wt-sprint down` 清场后正名重build 接管）。
- 本地全量 pytest（lock 对齐前 sqlalchemy 2.1.8 环境）：3530 收集＝3527 passed＋8 skipped 内含 3 迁移口径钉红（`HEAD_REVISION` 常量＋`known==73` 双钉漏同步，当场修复复绿——新增迁移必同步两处口径钉入教训）＋1 zcode teardown 环境 ERROR（复跑绿）；CI 锁定环境为权威。mypy **277/102 基线不变**（lock 对齐 venv 复核；裸装 2.1.8 时假红 9 条已甄别为环境漂移）。
- r2 遗留移交 r3：宿主代理进程本体（轮询循环→spawn zcode→回执）；`adapter_missing` 解除回执落台账 §12（①实装＋N2 签核两项已齐，待 r3 真机验收）；crv 台账已 134 行（#423 r8 出 P1×2 迁移存储域）——r3 开工吸收扫描按新台账重扫。

## r3 · 端到端真机验收（2026-11-13，宿主代理进程本体轮）

### 开工前检查单（吸收条款执行记录）

- [x] `git fetch fork` 对齐：开工基点 **`876f7cc`**（#426）；r2 收口回执 `7fc37ff` 随分支首提交入库。★fork/main 在本轮窗口内又进 4 提交（#429 crv 收口/#427 crv r10/#430 首个 run 发起/#431 crv fixup/#428 回填）⇒ 收口前 rebase。
- [x] QR 台账重扫（147 行终态，#427 r10 闭合）：与本轮 agents 改动面**零新增相交**（QR-117/118＝富文本键名/上传 IntegrityError，前端域）；r2 扫描时挂给 r3 的 **QR-092/094/095 本轮吸收**（spawn/env 族），QR-086/087/090/091 相邻不吸收照走 QR→修复批轮。
- [x] ★并发线核对：#430「一键发起 agent run＋工作区根修复（首个 run 真机落库）」＝`scripts/agents/start-run.py` **人直调**既有 API（AI 不代发起红线合规——发起动作归人）、run `0ef28514` queued 落库、零生产代码改动。r3 不碰其面；N1 链的宿主消费半正是本轮宿主代理本体（生产 run 的自然领取在部署后，工程验收不碰生产 run）。
- [x] 分支 `goal-sprint-r3`（从 `876f7cc`＋r2 回执提交）。

### 范围定稿（五项，2026-11-13）

① **providerId 真机事实吸收**：2026-11-13 实测 zcode 0.17.1 schema strict——`defaultModelSelection={providerId,modelId}`，写 `providerKey` 被**整键丢弃**静默回退内置默认；r2 校验器查 providerKey 会对合法配置误拒 ⇒ 校验换 providerId（`host_preflight.py` docstring 带实测更正框）；`v3-backlog.md` N2 事实行的 providerKey 表述归并发线（a95af5a 族）修，r3 不碰避免冲突。② **宿主代理进程本体** NEW `agents/host_agent.py`＋**服务端 context 读取面** NEW 路由。③ **adapter.py spawn 段整体重划**（`adapter.py:93` 定向警示清偿，不得只换 argv）＋QR-094。④ QR-092/095 吸收。⑤ **真机验收＝工程级**（不创建生产 AgentRun＝H4 边界不碰；N1 首个生产 run 仍归蔡工亲手，窗口 11-19 止）。

### r3 变更面

- **宿主代理本体** NEW `server/src/fde_api/agents/host_agent.py`：`HostAgentConfig.from_env`（五必需 env 键＋闸开白名单空 fail-closed）／`HttpHostTransport`（协议：200 拆 `{data}` 信封／非 200 回完整信封读 error 码）／`preflight`（复用 host_preflight 同一对校验器，**fail-fast 于 claim 前**——部署半态不领取，避免 run 白挂 host_running）／`materialize_workspace`（run_id 形状钉＋根锚＋拒绝清单；空 task.md 不 spawn）／`build_receipt_payload`（产物 sha256 宿主侧现算＋`egress_audit` 有界摘要上行）／`run_once`（一次生命周期；spawn 失败如实回执 failed 不悬挂）／`main`（env 驱动，退出码 0/2/3/4/5）。生命周期红线（通道例外⑤）：**一次进程＝至多一次 claim→执行→receipt，run 终态即回收**；零凭据注入；spawn 真身＝`run_host_channel`（preflight＋契约 argv＋超时熔断＋⑦闸全复用）；真相层零接触。
- **服务端 context 读取面**：NEW `agents/host_context.py`（状态闸族：404 不存在／409 非 host_poll·未领取·已回执／403 令牌与领取不符／413 超 4MB；context_ref 前缀剥除重新 join 当前 Settings 根＋根锚校验；三面料逐字回传）＋第四条宿主路由 `GET /agents/host/runs/<run_id>/context`（**488→489**；独立路由非 claim 内联＝可幂等重取＋有界语义）。面料设计定稿：**服务端渲染一次、宿主逐字落盘**（不两侧各渲染——漂移温床）。
- **adapter.py spawn 段整体重划**：删虚构容器契约与 TODO 警示；`spawn_argv`＝契约层 `zc.build_cli_argv(prompt=zc.task_prompt(workspace), cwd=…)`（prompt 文字面并入契约层单一真身）；`ZcodeAdapter(*, cli_command="zcode")`；`AgentRunResult.summary_payload` 字段（`--json` 汇总随 result 回传回执保真）；QR-094 done 终态立即终止批内遍历（completed 不得被同批尾随越界 cost 翻成 budget_exceeded 丢产物）；`ManifestOutputScanner` 自 service 机械搬入（`_MANIFEST_FILE` 收归 workspace_files 单一真身，service 顶部再导出引用不变；热点预算只减不增）。
- **QR-092（宿主进程 env 白名单继承）**：`host_channel_env` 白名单前缀集（node 运行时＋Windows 定位＋`ZCODE_` provider 注入面＋代理透传）＋拒绝清单双层（`FDE_`/TOKEN/PASSWORD/SECRET/API_KEY/PRIVATE_KEY 子串即使命中允许前缀也剔除）。
- **QR-095（回执 exit_code 语义）**：缺/非 int ⇒ None（**不缺省 0**）；`status=completed` 而 exit≠0 ⇒ 降档 failed——服务端不认无凭据的「成功」。
- **pilot.py 警示换代**（真身清偿）：「执行契约已实装（宿主代理通道 goal-sprint r3），但试点窗口内尚无真实完成的 run」——文本与实装态一致。
- **★真机首跑撞出生产缺陷→⑦闸回环豁免**（`host_egress_proxy.py`）：首跑 EXIT=1、产物零。隔离两腿定位：裸跑腿全过（marker 产物＋manifest 双件）／闸腿复现（`APICallError: Cannot connect to API`＋审计 `tunnel_blocked 127.0.0.1:18787`）。真相＝zcode 运行时经**桌面端本地 broker（127.0.0.1:18787）**回环 IPC 取凭据/会话，其客户端**无视 NO_PROXY** 把回环 CONNECT 推进代理，闸按白名单拦截 ⇒ broker 不可达 ⇒ API 调用取消。修复＝**闸侧回环豁免**：回环目标 CONNECT 一律转发、审计新类别 `tunnel_loopback`（`proxy_env` 的 NO_PROXY 本就声明回环直连语义，zcode 不认账由闸侧补齐；⑦ 管出站互联网面，回环不出机器）；明文 absolute-form 仍一律拒绝（未观测到回环明文面，不预设放宽）。测试钉两例（部署态白名单不含 127.0.0.1 下回环中继＋localhost 别名；blocked 原钉保持）。★部署事实：本机形态 zcode CLI 依赖桌面端在场（broker 18787）——裸跑形态的前提归部署 runbook 详述（并发线 runbook 承载）。
- **回执携 ⑦ 审计证据**：`build_receipt_payload` 增 `egress_audit`（`summarize_audit` 有界形状：计数＋去重域名 ≤20，只记域名不记路径/内容——红线同构）；宿主代理单发进程里这是审计留证唯一出口（服务端 `agent_egress_audit` 事件落库择机接线）。
- 测试：NEW `test_host_agent.py` 15 例（from_env 闭集/egress 白名单闸/preflight 复用/materialize 逐字＋坏 run_id＋空 task.md fail-closed/全链指纹逐位/零凭据注入/失败回执/receipt 拒/claim 拒/preflight 先于 claim/ghost digest/HTTP 传输形状）＋autouse 清场夹具（本机真实 `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` 泄入防护——r2 教训复现）；test_host_poll +7（QR-095 两例＋context 五例含**令牌轮换领取绑定钉**＋HTTP 路由接线）；test_host_channel +3（env 白名单三层）；test_agents_adapter pin 换代＋QR-094 一例；test_host_egress_proxy 回环豁免换代。★M8 完整性钉吸收（全量复跑撞出）：新 GET context 面未登记 ⇒ `_EXCLUSION_RECORDS` 增 `internal_service` 条目（宿主机器通道令牌闸面、JWT 不进鉴权：A/同角色 A/B 属主现测 403×3，claim/receipt 同族；条数基线 64→65）——M8 红队套件 43 passed 复绿。
- NEW `scripts/verify/host_agent_real_machine_check.py`：工程级验收器——进程内 `ThreadingHTTPServer` 存根（status/claim/context/receipt 四咬合面与真实路由形状逐字段同源）＋**真实传输**（HttpHostTransport over loopback HTTP）＋**真实 spawn**（run_host_channel 默认 spawner→真 zcode 非交互）＋**真实 ⑦ 闸**（部署态同款六域白名单）＋TEMP 一次性隔离工作区（绝不触碰真相层）。

### r3 验证与真机验收回执

- **变异五连全数收口**（改→红→字节级还原→绿）：M1 env 拒绝层失效 2 红／M2 QR-094 1 红／M3 缺 exit_code 缺省 2 红／M4 preflight fail-fast 1 红／M5 领取绑定 1 红——★M5 判别力教训再现：单令牌设计下「他 token」在入口校验即 403，领取绑定检查**不可达**＝假绿；改**令牌轮换场景**（claim 后轮换服务端 token，原持有者读 context 必须撞绑定检查 403）才杀灭。★变异脚本三硬化（v3）：try/finally 强制还原（v2 曾 900s 超时崩溃残留生产变异一次——手工核验还原后补）；单趟 240s 超时如实报；**变异运行期间绝不并发编辑源码**。
- 定向套件 **171 passed**（9 文件＝r3 改动面测试文件全量，含回环豁免后复跑）；ruff 绿；mypy **277/102 基线不变**；inventory 重提取（route **488→489**／52 蓝图／153 表／74 rev 单头 `c8e2a6f0b9d4` 不变）＋route CSV＋archify 刷新（candidate.json 489＋finalize 四闸绿＋**整页实拍 preview 1440×2098**）。
- **★真机验收 VERIFY-R3 RESULT: PASS（判据六条全过）**：①一次生命周期收场回执 `status=completed`；②产物指纹字节级一致（receipt=`a34bc4d89fa48c40…`）；③真模型消耗 billable **195,582 tokens**（6 模型请求，GLM-5.3-Flash，zcode 0.17.1）；④context 咬合面被消费；⑤egress 审计全白名单域＋回环、**零 blocked**；⑥产物 marker（R3-VERIFY-OK）＋manifest 双件可校验。**工程级**：不创建生产 AgentRun（H4 不碰）；首个生产 run 的宿主消费在部署后自然发生（N1 链，#430 已 queued 落库）。
- ★环境窗口注记：本轮两次测试/变异超时窗口（M1/M2 v3 240s×2＋adapter 套件一次 39 ERROR setup 全红 454s）疑与并发会话共享 PG 对撞同族；单例复跑全绿（39 passed 15.7s／M1/M2 补验 3.9s＋4.7s）——环境假象如实登记，**CI 为权威**。
- **CI 首红清偿（2026-11-13）**：PR #433 首轮 server-tests 红＝`6 failed, 3588 passed, 8 skipped`（全集中 `tests/test_host_agent.py` 的 run_once 六例，错误原文＝`HostChannelError: zcode 默认模型未配置：/home/runner/.zcode/cli/config.json 缺少可用的 defaultModelSelection 键`）——根因＝单测未隔离 preflight 的默认模型配置路径，落 HOME 下 `~/.zcode/cli/config.json`（CI runner 无此文件⇒六例假红；本机真机态又使「缺键」负例不可达＝假绿家族）。**生产行为正确（fail-closed），只修测试隔离**：夹具在 tmp 内写合法 `defaultModelSelection` 配置（先 set、后 `payload.update(overrides)`⇒负例 override 仍生效）＋新增「缺省路径语义」钉（monkeypatch 桩 `default_cli_config_path` 并断言报错含该路径——不打桩则读真实 HOME＝环境依赖＝假绿家族）；CI-like 空 HOME 实测 `test_host_agent.py` 15 passed。★同款纪律已在 `test_host_channel.py` 落地（模块级 `_CLI_CONFIG_PATH` 写 tmp 合法配置）。
- **全量本地实测（首红清偿后重跑）**：`3596 passed + 7 skipped`（3297.63s／0:54:57，exit 0）＋定向 9 文件 `171 passed`（136.05s）。★并发取证：另一会话 `fde-wt-v33m2` 同窗跑 `pytest tests -q`＋`test_migrations.py`（独立库 `fde_workbench_v33m2_test`），主树 pre-commit pytest 抢同一 `fde_workbench_test` session advisory lock（实测 pid 186473 等锁 50min）⇒ 本地耗时不可作性能口径，**CI 为权威**。

### r3 待办（收口条件）

- [x] 台账 §12 `adapter_missing` 解除回执＋§4 P2-b 行收口＋§3 E10 解锁判定落记录
- [x] backlog T-Z1 状态行更新＋CHANGELOG r3 节＋AGENTS bullet
- [ ] rebase fork/main（#431/#432 插队窗，已 rebase 至 `a122f28`）→ 全量 pytest（本地 3596 passed + 7 skipped 绿）→ PR **#433** → CI 四绿 → squash 合并 → 部署三验（url_map **489**／alembic `c8e2a6f0b9d4` head 不变／三镜像逐位）→ 收口回执回填
