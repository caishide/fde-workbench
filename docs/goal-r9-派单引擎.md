# goal-r9 · 派单引擎轮：P2-4 私单封堵 + 撮合仿真器（H2/H3 内测/仿真回填）

- 日期：2026-10-31
- 分支：`feat/dispatch-r9-p24-sim`（自 fork/main `77fc03c`，goal-r8 收口之后）
- 输入：完成判定 verifier 指出的两项登记差距——收口报告 §七-1（P2-4，L 级）与 §七-3（撮合仿真器，留注⑳，H2/H3 回填前置）
- 迁移：**零迁移**（本轮全部为服务层钩子与纯代码模块；head 仍 `c5d7e9f1a3b7`）

## 一、差距清单

| 能力项 | 目标口径（出处） | 现状（代码证据，轮前） | 定级 | 对应行动 |
|---|---|---|---|---|
| B8 / P2-4 私下接单封堵 | 设计 §8.5：「服务层校验钩子：派单池外成交的技术封堵」；规则表 P2-4「禁止私下接单的技术执行」；收口 §七-1 建议与 FDE_DISPATCH 立项入口同轮 | ① `create_project`（projects/service.py:91）不接受 business_line——Project 默认 `'FDE'`（models.py:245 CHECK r7 已放行 `'FDE_DISPATCH'` 但**全仓无人写入**，FDE_DISPATCH 立项入口缺失）；② `create_package`（dispatch/packages.py:164）不校验项目成交渠道——直签项目可入池；③ 池内企业可被直签线再次立项/报价，无任何拦截 | P2（L 档，§八条件 2 的明示例外） | channel_guard 三钩子（H1/H2/H3，见行动说明） |
| G / 留注⑳ 撮合仿真器 | 收口报告 §七-3：「历史包回放打分——H2/H3 指标回填的前置工具」；BP §11 闸门：P3「生态交付 G9 一次通过率 ≥70%」、P4「平台方工时占比 ≤25%；毛利率 ≥70%」（内测/仿真数据口径） | 零匹配（`grep -rn simulator server/src` 无结果）；H2/H3 无任何数据支撑（r8 按诚实例外处理） | P1（§八条件 3 的明示例外） | `dispatch/simulator.py`：只读回放 + 种子化全链路仿真 + H2/H3 报告 + CLI |
| H5 口径漂移（常设） | 每轮重测口径数字 | r8 记 86 表；本轮实测 **85 张业务表**（`__tablename__` 85 处；物理库 85 张不含 `alembic_version`、含则 86——r8 口径疑把 `alembic_version` 计入，本轮起按业务表口径并注） | 常设 | 口径重测（见验证结论）+ AGENTS.md 更新 |

存量防回退抽查（A 组）：`test_projects_api` / `test_project_members_api` / `test_quote_first_order_concurrency` 等在本轮全量套件内全绿（直签立项缺省行为不变有专属用例 `test_direct_entry_default_unchanged` 守护）。

## 二、行动说明

### 1. P2-4 私单封堵——`server/src/fde_api/dispatch/channel_guard.py`（新）

「派单池外成交」的技术封堵，三条服务层校验钩子（错误码原样转译各服务错误类型，路由零改动）：

- **H1 立项入口**：`business_line='FDE_DISPATCH'` 只能平台侧（admin/project_lead）立项，fde_engineer/viewer → `403 dispatch_project_platform_only`（钩子先于通用鉴权，给出专属码；API 层 `require_minimum_role("project_lead")` 仍先行兜底）。入口在 `projects/service.py`：`_normalize_create_input` 新增 business_line 归一（枚举封闭，越界 `400 invalid_business_line`）+ `Project(business_line=…)` 落库；`routes.py` CREATE_FIELDS 放行该字段；序列化 DTO r7 已含，零改。
- **H2 池内企业直签封堵**：企业已进过派单池（任一交付包挂在同企业项目上，不限包状态）后，再以 `'FDE'` 直签线**立项或报价** → `422 private_deal_blocked`（复购走池正是 §3.3 复购判据口径；派单线同企业复购放行）。钩子在 create_project 与 create_quote 双入口（后者是存量直签项目的防御纵深）。
- **H3 渠道正交**：交付包只能建在 `'FDE_DISPATCH'` 项目上，否则 `422 dispatch_line_required`（直签项目不得入池洗渠道；accept_package 不另立项目，派单线项目是池内成交唯一载体）。

**封堵留痕（独立事务）**：封堵发生写 `OperationEvent`（`private_deal_blocked` / `dispatch_project_entry_blocked`，target=actor/project）。留痕走独立事务——被封堵的主事务必然回滚，留痕必须独立存活；留痕失败只降级不阻断封堵。

**实施留注（bug 与修复）**：首版钩子放在 leader `SELECT … FOR UPDATE` 之后，封堵留痕的独立事务 INSERT `operation_events` 触发外键 `FOR KEY SHARE` 检查，与外层对**同一 user 行**（actor==leader）的 FOR UPDATE 互斥 → 自死锁（共享测试库上实测复现）。修复：**钩子先于任何行锁语句执行**（create_project/create_quote 均已如此），并在 channel_guard 文档字符串写明该约束。教训入库：服务层「第二连接」钩子必须在主事务持锁前运行。

**拍板项（新）**：封堵是绝对技术动作、无运行时开关。若业务将来要给池内客户开直签（例如战略大客户），属设计变更拍板项，不是配置项——已登记台账。

### 2. 撮合仿真器——`server/src/fde_api/dispatch/simulator.py`（新）

- **`replay_scoring(session)` 历史包只读回放**：对库内已进入撮合流程的交付包（published/offered/assigned/accepted），按**当前**供给池与 active 规则版本重跑 Stage A/B——与 `match_package` 同管线但**不落 offer、不迁状态、不写事件**（只读性有专属用例：前后 offer 数与包状态逐项相等）。这是 P2-1 权重配置「仿真对比」视图的数据源（权重调整前后各跑一次即对照）。
- **`run_simulation(session, scenarios, seed, params)` 全链路仿真**：建包→发布→撮合→接单（含拒单/超时→expired→重派→场景 C 人工回退）全部走**真实服务函数与真实引擎**（create_package/publish_package/match_package/accept_offer/decline_offer/expire_stale_offers/seat_shares_for + DISPATCH_CONSTANTS + active 规则版本）；人工环节按**显式假设表**采样（接单意愿按 Top3 顺位衰减、G9 一次通过率按「候选等级−需求等级」差额表、平台工时=编排+质检、场景 C ×3）。
- **诚实纪律（报告 meta 逐字回显）**：口径=simulation，不冒充真实数据；假设集中 `DEFAULT_ASSUMPTIONS` 可覆盖且全量回显；H2 附「随机派单基线」（同一假设表、池内等级混合、观测需求分布求期望——回答的是「引擎挑人把首过率抬了多少」）；随机性=random.Random(seed) 单流，报告不含 uuid/墙钟，同 seed 可复现（有逐字段相等用例）。
- **CLI**：`python -m fde_api.dispatch.simulator --scenarios N --seed S [--with-replay] [--output f.json]`；**拒绝非沙箱库**（FDE_DATABASE_URL 库名必须 `_sim`/`_test` 结尾，防误写业务库）。
- **留注（新）**：回放对池状态敏感——A4 在途占用计入资格门，刚被大量接单后的饱和池会大量落场景 C（本轮工件实测 23 包回放 20 场景 C）。权重对照用法应在池空闲态跑；这本身是产能规划信号而非缺陷。

### 3. 影响面与回滚

- 影响面：直签立项缺省行为不变（存量调用零感知——不传 business_line 即 FDE，已有专属回归用例）；交付包创建新增渠道校验（既有派单测试夹具显式 `business_line="FDE_DISPATCH"`，3 个测试文件各 1 行）；simulator/channel_guard 为新增独立模块，不触碰存量路径。
- 回滚方式：revert 单提交即可；无迁移、无数据回填、无配置变更。

## 三、验证结论

- **服务端全量**：`node scripts/run-server-tests.mjs tests -q` → **1448 passed / 6 skipped**（11m37s，含本轮新增 14 例）。
- **桌面端**：vitest **660 passed**（51 files）；`npm run typecheck` exit 0（桌面零改动，回归守护）。
- **静态**：ruff 全绿；mypy 基线检查 **OK no new type errors**（baseline 289 / current 288，基线反而消化 1 例）。
- **本轮新用例**：
  - `test_dispatch_p2_r9_p24.py`（10 例）：H1 平台侧立项 OK + API/服务层两级 403 语义、business_line 枚举封闭 400、直签缺省行为不变、H2 立项封堵 422、派单线复购放行、H2 报价封堵（存量直签项目）、H3 直签项目入池封堵 422、封堵留痕独立事务存活（rollback 后 OperationEvent 仍在）。
  - `test_dispatch_p1_r9_sim.py`（4 例）：漏斗守恒 + 指标数学自洽（H2 分母=已交付、H3=工时占比/毛利）、假设表回显与口径标注、全部需求挂派单线（P2-4 非干扰证据）、回放只读性（offer 数/包状态前后相等）、同种子两次运行报告逐字段一致、未知参数拒绝。
- **CLI 沙箱实跑**：`fde_r9_sim` 库（alembic upgrade head → load_seeds → CLI）：`docs/dispatch-sim-r9-seed42.json`。seed=42、24 需求：引擎接单 23 / 场景 C 0 / 未成交 1，平均重派轮次 1.09；**H2 G9 一次通过率 0.9565**（随机派单基线 0.9183，+3.8pp；BP P3 目标 ≥0.70 达标）；**H3 平台工时占比 0.0716 ≤0.25、毛利率 0.9717 ≥0.70**（BP P4 达标）。回放部分显示饱和池效应（23 包中 20 场景 C——A4 在途占满，见留注）。
- **失败与修复记录（不粉饰）**：①路由 CREATE_FIELDS 未放行 business_line → 首跑 400 invalid_request，已修；②Quote 夹具缺计算列（labor_cost 等 NOT NULL）→ 补齐；③钩子死锁（见行动说明）→ 先于行锁修复；④module_catalog 每用例被清 → 用例内重灌；⑤package_code 尾段冲突 → 项目编码尾段随机化；⑥拒单 reason 必须枚举内 → 改「档期冲突」；⑦`python -m` 直跑暴露 projects 包 __init__ 急切导入环 → record_event 延迟导入。全部修复后有终态全绿证据。
- **H5 口径数字（本轮实测，与 r8 对照）**：业务表 **85**（`__tablename__` 85 处；物理库 85/含 alembic_version 86——r8 的「86」按业务表口径修订为 85，漂移原因=口径非 schema）；迁移 **15 revision / head `c5d7e9f1a3b7`**（零迁移）；蓝图路由 **228**（不变）；api_catalog ENTRIES **68**（不变）；服务端 pytest **1448 通过 + 6 跳过**；桌面 vitest **660**。设计文档附录 A 修订建议：r8 修订稿的「表 86」重锚为「表 85（不含 alembic_version）」。

## 四、下一轮建议

1. **C7 混合模式自动转换 job**（收口 §七-2，唯一剩余工程侧 P2 项）：assign 24h 超时 → 转 claim；挂 dispatch.maintenance 24h 节流框架；前置=城市开闸（B-① 备案结论拍板）。
2. **仿真器校准**：以真实内测数据替换 `g9_first_pass_by_level_delta` 假设表与工时分布（首批 10 单生态交付到位后）；当前 0.9565/0.0716/0.9717 是**假设表下的合成值**，达标表述必须携带假设回显——不得摘出当真实成绩引用。
3. **外部拍板驱动项**（不变）：B-① 备案结论→开闸链路；B-③ 税率表法务确认→常量替换；B-④ 城市名单→种子更新；P2-2 状态集；新增：**池内客户直签豁免**是否需要业务开关（当前绝对封堵）。
4. **桌面交付纪律**：r7 三页 + 本轮零桌面改动的便携版重打包，按 README「打包桌面端」节执行（asar 字节验证）。
5. **附录 A 修订**：文档 owner 执行 r8 修订稿时，把表数口径改 85（含 alembic_version 则 86，建议明示口径）。
