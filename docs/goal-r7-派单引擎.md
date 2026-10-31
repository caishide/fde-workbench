# goal-r7 · 派单引擎轮次报告（2026-10-31）

> 第七轮，输入：goal-r6 报告 + 设计文档 §8.5 + 桌面端惯例实测。
> 本轮 Goal（阶段 1，P2 批次）：**P2-1 桌面派单页簇（含服务端支撑路由）+ P2-3 business_line 放行 + P2-6 cities 扩字段钉子——P2 六项除「P2-5 组织实体暂缓」与「P2-2 待拍板」外落地。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | B8·P2-1 桌面页簇 | 派单池/交付包详情/能力档案/权重配置（含仿真对比）/产能看板（§8.5 P2-1） | 桌面端零派单触点；档案/版本无读路由 | **P2** | dispatch/ 三页 + nav/route + 服务端 GET profiles/rules |
| 2 | B8·P2-3 business_line | `'FDE'` → `('FDE','FDE_DISPATCH')`（§8.5 P2-3 / §11.1 预留） | CHECK 只有 'FDE' | **P2** | 迁移 `c5d7e9f1a3b7` 约束互换 |
| 3 | B8·P2-6 cities 扩字段 | subsidy_scheme 选填 + metro_group（§8.5 P2-6） | r4 种子 schema 已含两键，无 P2-6 语义钉 | **P2** | 断言钉子（null 允许 + 必备键） |
| 4 | B8·P2-2 Project.status | 状态枚举扩展（§8.5 P2-2） | — | **P2（待拍板）** | 设计/规则表/BP 均无目标状态集——**不发明**，台账留注待拍板 |
| 5 | H5 口径 | AGENTS.md=实测 | 本轮后路由 228 / ENTRIES 68 / 桌面 660 / head `c5d7e9f1a3b7` | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A1 报价（`business_line` 迁移只动 CHECK，quote 路径零触碰 ✓）；A2 合同（零触碰 ✓）；A4 项目/任务（projects 全量回归 ✓）。

**实施中的留注（默认口径施工）**：
- **留注⑳（仿真对比二期）**：P2-1 权重配置页设计含「仿真对比」——需要撮合仿真引擎（历史包回放打分），本轮实现为**版本取值对照视图**（新旧快照逐项并读），仿真引擎随收口轮后立项。
- **留注㉑（派单页可见性口径）**：nav 派单池入口**全角色**可见——交付方只看到被授权包（package_access 第三语义服务端已强制，前端只渲染响应体）；平台侧看全量。档案/权重两 tab 数据平台侧 only（服务端 403 守卫）。
- **留注㉒（P2-2 blocked）**：Project.status 扩展在设计/规则表/BP 三处均无目标状态集——按「不得自行增删业务范围」红线不发明，待拍板后一轮落地（S 档）。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p2-desktop`，1 个迁移 + 12 个文件）：

1. 服务端：`dispatch/routes.py` 增 GET `profiles`（档案+产能：四域分/标签/城市/在途计数/上限自动算——平台侧 403 守卫）、GET `rules`（版本快照列表 + DISPATCH_CONSTANTS 只读节）；`api_catalog.py` ENTRIES 66→68。
2. 迁移 `c5d7e9f1a3b7`：business_line CHECK 互换（downgrade 防御性回写 'FDE_DISPATCH'→'FDE'）。
3. 桌面：`dispatch/DispatchPage.tsx`（tab 容器，hash 路由承载）+ `DispatchPoolPage.tsx`（白名单视图 + 详情展开 + `formatSeatAmount`/`isPackageView` 纯函数）+ `CapabilityProfilesPage.tsx`（四域分 + 负载条）+ `RuleVersionsPage.tsx`（版本快照表 + 只读常数 + `snapshotValue`）；`useHashRoute.ts`（route 类型 + parse + routeHash 三处）；`App.tsx` 页面分支；`AppShell.tsx` nav；`styles.css` 派单样式块。
4. 测试：服务端 `test_dispatch_p2_r7.py` 4 例（FDE_DISPATCH 入库/非法值仍拒/cities 扩字段/profiles 路由形状+在途计数+403/rules 版本+常数）；桌面 `dispatch-page.test.tsx` 6 例（白名单渲染+敏感字段零出现、空态/错误路径、产能负载、权重快照、tab 回调、纯函数）。
5. `test_migrations.py` HEAD 常量 → `c5d7e9f1a3b7`；r6 的 head 钉子测试**泛化**（常量 ↔ 迁移文件互证，不再随轮次硬编码——本轮被它咬了一口的教训直接产品化）。

**影响面与回滚**：零数据迁移语义（CHECK 放行类）；桌面纯新增 feature 目录。回滚=`alembic downgrade b2c4d6e8f1a3`（先确认无 'FDE_DISPATCH' 行）+ revert PR。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| P2-3 判据 | ✅ `test_business_line_allows_dispatch_value`（'FDE_DISPATCH' 入库 + 'FDE' 不变 + 'LOGISTICS' 仍被 CHECK 拒） |
| P2-6 钉子 | ✅ `test_dispatch_cities_extended_fields`（六城逐行 subsidy_scheme/metro_group） |
| P2-1 服务端 | ✅ `test_profiles_route_admin_only_and_shape`（形状/在途计数/上限 10/非平台侧 403）+ `test_rules_route_lists_versions_and_constants`（版本快照 + 只读常数节） |
| P2-1 桌面 | ✅ `dispatch-page.test.tsx` 6 例——**白名单渲染且报价/收款字段零出现**（敏感字段断言延续 §9.5 基线②到桌面层）、空态/错误路径、产能负载 20%、权重快照、tab 回调、纯函数 |
| 回归 | ✅ r1–r6 派单 87 例 = **91 例全绿**（服务端）；桌面全量 **660/660**；typecheck 0；ruff/mypy 全树无新错 |
| 全量 | CI 门禁出具 |
| 迁移 | 测试库 up/down 往返 + `alembic check` 元数据等价 |

**口径数字重测（H5）**：

| 口径 | 附录 A 快照 | 本轮实测 | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **86**（零新表） | 八表齐维持 |
| 迁移 revision | 9 | **15** / head `c5d7e9f1a3b7` | P2-3 第 15 个 |
| 蓝图路由 | 212 | **228**（+2 只读路由） | 正向漂移 |
| api_catalog ENTRIES | 54 | **68**（+2） | 一致性测试钉死 |
| 服务端 pytest | — | **CI 出具（1431+）** | — |
| 桌面 vitest | — | **660**（+6） | — |

**失败与未完成项（如实）**：① r7 服务端用例直调 fixture（pytest 拒绝）→ 参数注入；② worktree 桌面依赖未挂全（workspaces 提升到根 node_modules——junction 需两处，且 npm run 会先建空目录导致 mklink 失败，须先 rmdir /s /q）；③ tsc 抓出 AppRoute 类型/parseHashRoute 未随 routeHash 同步（第一次补丁脚本中途断言失败未写盘——**补丁脚本必须逐段验证写盘成功**）；④ 桌面用例两处（fixture 文案与 dt 标签重名、rerender 不触发 load——改点「刷新」按钮）；⑤ r6 的 head 钉子测试被本轮 head 前移咬中 → 泛化为常量↔文件互证。全部为测试/工程脚手架问题，业务代码零返工。

## 四、下一轮建议

1. **goal-r8 = 收口轮（终局判定准备）**：① §8.8 闸④「商业模块测试覆盖率 ≥60%」分子分母出具（coverage 工具跑商业模块关键路径：quotes/payments/contracts/dispatch 结算与撮合）；② H1–H3 指标口径（G9 一次通过率/平台工时占比/毛利率——内测/仿真数据口径，BP 闸门）；③ 附录 B 待签字清单汇总（①备案定性 ②资金托管/开票主体 ③税率表确认 ④城市名单 + 留注①–㉒逐项）；⑤ 附录 A 修订稿（表 86/15 rev/head/路由 228/ENTRIES 68 + A-①–⑦ 重锚）；⑥ 最终收口报告（逐项能力项 → 代码位置 + 测试用例 + 文档章节指针）。
2. **P2 剩余**：P2-2 待拍板（无目标值不发明）；P2-4 私单封堵（L 级，服务层校验钩子）单独立项——若收口前不动，列入收口报告「已登记未立项」节。
3. **风险**：① 派单页簇的 profile/rules 路由是平台侧 read API，桌面 viewer/fde_engineer 角色在档案/权重 tab 会拿到 403——页面已有错误态，P2-1 的角色化菜单（隐藏 tab）随 GUI 回归轮细化；② 仿真对比（留注⑳）缺位使权重调整缺数据支撑——收口轮至少给出仿真器最小口径建议。
4. **待拍板（附录 B）**：P2-2 状态集加入待拍板清单；其余无新增。
