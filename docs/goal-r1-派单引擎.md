# goal-r1 · 派单引擎轮次报告（2026-10-31）

> 首轮冷启动。输入：设计文档 v1.0 补齐版（2026-10-31，文末版本记录已核）+ BP v3.0 + 规则表 v1.0 + 代码实测。
> 本轮 Goal（阶段 1，依提示词建议顺序取簇①）：**把两项开池硬闸门 P0-5（门禁验收分离）与 P0-6（events 白名单）各落一个可判定用例，并同步 AGENTS.md 口径漂移。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | B6·P0-5 门禁验收分离 | Gate 加 `decided_by_user_id` + `is_delivery_party`；`decide_gate` 校验「拍板人 ≠ 该门禁执行人」403 不可绕过（§8.3 P0-5 / §9.4 / §8.8 开池闸②） | `workbench/models.py:550-594` Gate 无执行人/拍板人列；`gate_service.py` `decide_gate`（:301 起）只查 `can_manage`，admin/leader 可自拍任意门 | **P0（阻塞开池）** | 三列 + 双 403 防线 + 双拍板人改造 |
| 2 | B3·P0-6 events 白名单 | `_TARGET_TYPES` 加 `delivery_package` / `dispatch_offer` 两类；`record_event` 两类目标写入用例（§8.3 P0-6 / §2.5 坑 1） | `projects/events.py:53-69` 15 类目标零派单；派单模型全库零存在（附录 A-2 末行） | **P0** | dispatch 包骨架两表 + 白名单注册 |
| 3 | H5 口径漂移 | AGENTS.md 口径=实测（附录 A-⑤） | AGENTS.md 写 74 表 / 8 revision / head `f3c8d2b7a1e5`（2026-10-28 口径）；本轮前实测已漂移为 76 表 / 9 revision / head `a9c3f1d8e2b4` | 口径修订 | 随本 PR 同步（含本轮新增后数字） |

**A 组存量防回退抽查（3 项）**：A3 收款 7 里程碑 + D+7/15/30/60 催款（`payment_service.py:9,45`，本轮零改动 ✓）；A5 门禁 G1–G9 证据链 pointer+sha256（`gate_service.py` `_normalize_submission_items` 校验 64 位 hex，本轮零改动 ✓）；A8 集成桥（`scripts/bridge-poll.mjs` 只读纪律，本轮零改动 ✓）。

**实施中对设计文档的两处留注（冲突裁决顺序=代码为准）**：
- **留注①（P0-5 列集）**：设计 §9.4 列 2 列（`decided_by_user_id` + `is_delivery_party`），但「拍板人 ≠ 执行人」的判定需要执行人身份可查，故实增 3 列（多 `submitted_by_user_id`）。设计的 2 列语义完整保留，无冲突，属必要支撑列。
- **留注②（P0-6 范围）**：提示词称 P0-6「不依赖新表」，但 `record_event` 的目标必须是 ORM 实例（`_TARGET_TYPES` 按类查找），两类目标无模型即无从验证。故本轮把 §8.2 对 `delivery_packages` / `dispatch_offers` 的 DDL 级约束**先行落表**（服务逻辑不预埋），P0-1 的服务层判据（快照不可变、8 态迁移用例）仍留待后续轮。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p0-gate-separation`，1 个迁移 + 8 个文件）：

1. `server/src/fde_api/workbench/models.py`：`Gate` 加 `submitted_by_user_id` / `decided_by_user_id`（FK users，SET NULL）+ `is_delivery_party`（Boolean，默认 false）。
2. `server/src/fde_api/projects/gate_service.py`：
   - `submit_gate_evidence` 落执行人（`submitted_by_user_id=actor.id`）；`is_delivery_party` 按「提交人是否为 ProjectMember(role='member')」推导（派单池上线前管理位提交恒 False，写入路径随 §9.3 接单交接生效）；
   - `decide_gate` 双 403 防线，置于状态检查之后、其余业务校验之前（不可绕过）：① `gate_decider_conflict`——拍板人=执行人；② `gate_decider_role_required`——交付方执行的 G8/G9 须 admin 拍板（§9.4 方案② + §11.3 方案①过渡口径）；
   - 拍板时落 `decided_by_user_id` 并入事件 changes；`_serialize_gate` 增三项输出。
3. `server/src/fde_api/dispatch/`（新包，§8.6 落位）：`models.py` 含 `DeliveryPackage`（§2.2 新增字段 + §8.2 全部 DDL 约束：`Unique(package_code)`、`Unique(project_id, dispatch_round)`、dispatch_mode/dispatch_status 8 态/redispatch_radius_km(25,50,100,0=全城哨兵)/sow_type/required_level 各 Check）与 `DispatchOffer`（`Unique(package_id, dispatch_round, candidate_user_id)`、status 6 态 Check、`VersionedMixin` 乐观锁位、`match_breakdown` JSON）。**服务逻辑零预埋**。
4. `server/src/fde_api/projects/events.py`：`EventTarget` 联合类型与 `_TARGET_TYPES` 注册两类派单目标；`_project_id_for_target` 支持 `DeliveryPackage`（直取）与 `DispatchOffer`（经包反查）。
5. `server/migrations/versions/d2f6b4c8a1e9_dispatch_p0_gate_separation.py`：gates 三列 + 两新表，接链 `a9c3f1d8e2b4`；`migrations/env.py` 注册 dispatch models。
6. 测试：新增 `server/tests/test_dispatch_p0.py`（6 用例）；改造 `test_gates_api.py`（拍板统一走 leader_client，执行人=admin——5 用例全部适配双拍板人）、`test_ai_server_chat_mcp.py`（提交=lead、拍板=admin，1 处）、`test_migrations.py`（HEAD_REVISION 常量 → `d2f6b4c8a1e9`）与两个冒烟脚本（`scripts/gate-engine-smoke.py` / `scripts/commercial-smoke.py`：新增临时 lead 执行人，全部证据提交走 lead、拍板走 admin；门禁冒烟加「执行人拍自己的门 403」钉子）。
7. `AGENTS.md`：口径同步（见下表）+ 登记派单设计文档为施工准绳入口。

**席位口径辨析（防后续轮踩坑）**：`delivery_packages` 四席位 = **执行席位** `seat_lead/delivery/consult/qa`（§2.4「包 × 角色」），与 `delivery_settlements` 商务四席位 `platform/region/city/delivery`（§7.2）不同名不同义——本轮只落前者。

**影响面与回滚**：纯增量（3 列 + 2 表 + 白名单注册），无既有字段语义变化；唯一行为变化 = 同一用户对同一门禁「先提交后拍板」从 200 变 403（这正是 P0-5 的目的）。回滚 = `alembic downgrade d2f6b4c8a1e9`（丢两表与三列，无数据迁移）+ revert PR。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.3 P0-5 判据「执行方拍自己的门 → 403」 | ✅ `test_executor_cannot_decide_own_gate`（API 全链路：admin 提交→admin 拍板 403 `gate_decider_conflict`→leader 拍板 200，`decided_by_user_id`/`submitted_by_user_id` 落库断言）+ `test_decide_gate_service_level_conflict_guard`（服务层直调同拦，防绕过） |
| §9.4/§11.3 交付方门禁平台拍板 | ✅ `test_delivery_party_gate_g8_requires_platform_decider`（leader 403 `gate_decider_role_required` / admin 放行；`is_delivery_party` 场景按列语义构造，API 写入路径随 §9.3 后续轮） |
| §8.3 P0-6 判据「record_event 两类目标写入」 | ✅ `test_record_event_supports_delivery_package_target` / `test_record_event_supports_dispatch_offer_target`（target_type、target_id、project_id 归属全断言；offer 的 project 经包反查） |
| §8.2 乐观锁位 | ✅ `test_dispatch_offer_optimistic_lock_column_present`（本仓惯例=服务层显式 +1，offer_service P1-1 沿用） |
| 既有门禁回归（A1 钉子等） | ✅ `test_gates_api.py` 5 用例双拍板人后全绿；`test_ai_server_chat_mcp.py` 43 用例全绿 |
| 全量 `npm run test:server` | ✅ **1345 passed / 6 skipped / 0 failed**（11:43；含迁移链全量 up/down 往返） |
| `npm run test:desktop` / `npm run typecheck` | ✅ typecheck 零错误；vitest **654/654**（桌面端本轮零改动） |
| 迁移链 | ✅ 测试库（fde_workbench_test）随测试套件反复 upgrade/downgrade 验证 DDL；正式库升级见下 |

**口径数字重测（H5，本轮后 vs 设计文档附录 A 快照）**：

| 口径 | 附录 A 快照（2026-10-31） | 本轮实测（改动后） | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **78**（+delivery_packages/dispatch_offers） | 本轮净增 2，与 §8.1「新增 8 张」进度 2/8 一致 |
| 迁移 revision | 9 / head `a9c3f1d8e2b4` | **10 / head `d2f6b4c8a1e9`**（接链正确） | 派单迁移第 1/6–8 个 |
| 蓝图路由 | 212 | 212（本轮零新路由，routes 随 P1-3） | 无漂移 |
| api_catalog ENTRIES | 54 | 54（同上） | 无漂移 |
| 服务端 pytest | 1210+（AGENTS 旧口径） | **1345 passed + 6 skipped**（+6 派单用例；含 3 处首轮失败的修复复验） | — |
| `stale_version` 引用 | 19 文件 42 处 | 未重测（本轮不新增引用） | 下轮顺测 |

**镜像与正式库**：合并后于本地 main 重建镜像 + 容器 recreate + `alembic upgrade head`（红线纪律），结果补记于 PR。

**失败与未完成项（如实）**：首轮全量 pytest 出现 **3 处失败**（`test_migrations.py` HEAD_REVISION 常量滞后 + 两个冒烟脚本仍是单拍板人流程），均已修复并复跑通过（冒烟 5/5、migrations 20/20）；终轮全量结果见上表。P0-5/P0-6 的验收判据本身已全过，但两项改造的**完整闭环**仍开放（见第四节）。

## 四、下一轮建议

1. **优先（簇②表建设，依 §8.3 依赖序）**：P0-3 `fde_profiles`（+ `fde_level_evidence`）→ P0-8 `dispatch_rule_versions`（版本切换判据需要它）→ P0-1 `delivery_packages` 服务层（快照 canonical_json 冻结、发布/撤回、8 态迁移用例——表已就位，本轮铺路）→ P0-2 `package_access`（§9.5 隔离基线四条测试从这轮起建）。
2. **顺手项**：P0-4（Payment 加 `acceptance_passed_at` + `dispatch/settlements.py`）可与 P0-2 同 PR（同为 S 档）；P0-7（system_configuration PUBLIC_FIELDS + §6.2 时间常数）独立 S 档。
3. **风险**：① 桌面端 GateBoard 对 403 新错误码无专门文案（回落通用「门禁操作失败」，可接受的降级，P2-1 时随 dispatch UI 一起补）；② `is_delivery_party` 目前仅测试可置位——接单交接（§9.3）落地前，规则②防线处于「列已立、写入路径未通」状态，报告如实登记。
4. **待拍板（附录 B）**：本轮未触发阻塞项①②（claim/权重公示未动）；B-②资金托管边界在 P0-4 开工前需确认按默认口径（对公收款+四席位内部分账）施工——已按「默认口径施工+标注待签字」纪律处理，不停工。
5. **文档修订建议（附录 A 时效）**：本轮净增 2 表 + 1 迁移 + 迁移头变更，属「重大漂移」——建议设计文档下轮修订时把附录 A-⑤ 更新为 10 revision / head `d2f6b4c8a1e9`、A-③ 表数 78；另登记**新发现的命名冲突**：本台账二节 D11 草案的 `delivery_package`（结项打包，draft→sealed→delivered）与派单 `delivery_packages`（8 态派单机）同名不同义，D11 若日后实施须改名（建议 `handover_packages`）。
