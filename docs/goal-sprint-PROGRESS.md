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

### r2 收口回执

（CI/合并后回填）
