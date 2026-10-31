# goal-r5 · 派单引擎轮次报告（2026-10-31）

> 第五轮，输入：goal-r4 报告 + 设计文档 §4/§5 + 规则表 A-6 + 代码实测。
> 本轮 Goal（阶段 1，P1 主战役）：**P1-2 撮合核心（Stage A 五资格门 + 场景裁决 + Stage B + match_breakdown）+ 负面清单 A-6 七条逐条反例（=§8.8 开池四道闸之闸③）+ P1-4 options 枚举，各落可判定用例。**

## 一、差距清单（本轮覆盖项）

| # | 能力项 | 目标（出处） | 现状（代码证据，改动前） | 定级 | 对应行动 |
|---|---|---|---|---|---|
| 1 | C1–C3·P1-2 Stage A + 场景裁决 | 五资格门硬过滤；A 字典序/B 加权/C 不自动派（§8.4 P1-2 / §4.2–4.4） | 撮合零代码：`required_level` 无推导、无候选评估、无排序 | **P1（L 级主战役）** | `dispatch/matching.py` + `dispatch/scoring.py` |
| 2 | C2·Stage B 权重版本化 | 权重唯一来源=版本快照，不硬编码（§4.3） | 快照表 r2 已落但无消费者 | **P1** | 加权分从 active 版本取；无版本 → 422 `rule_version_required`（降级态语义） |
| 3 | C6·match_breakdown | Top3 + 结构化明细 + 对被派方释明（§4.8/§5.4） | offer 可建但 breakdown 无契约 | **P1** | §4.8 schema 逐键落位 + 释明文案 |
| 4 | C4·required_level 推导 | Quote 系数推导 + 人工覆盖留痕（§4.5） | 列在但恒空 | **P1** | `derive_required_level` + `override_required_level`（draft-only + reason 事件） |
| 5 | D2/D3·负面清单 7 条 | 每条一个反例/结构性防护（§8.8 闸③ / 规则表 A-6） | 零覆盖 | **P0 级闸门** | 七条反例测试（见验证表） |
| 6 | B8·P1-4 options | 席位分配/场景类型/匹配模式/拒单原因枚举（§8.4 P1-4） | options 无派单组 | **P1** | 四组枚举随 options 下发 |
| 7 | H5 口径 | AGENTS.md=实测 | 本轮后路由 226 / ENTRIES 66（83 表 / 12 rev 不变） | 口径修订 | 随本 PR 同步 |

**A 组存量防回退抽查（3 项）**：A1 报价（`_quote_with` 复用 Quote 列口径；quotes 相关全量回归 ✓）；A5 门禁（本轮零触碰，r1 钉子回归 ✓）；A3 收款（零触碰 ✓）。

**实施中的留注（默认口径施工）**：
- **留注⑫（SLA 承诺未建模）**：§4.3 服务时限维度需要候选档期承诺字段——`fde_profiles` 无此字段，一期统一按「可协商=50」（全员同值 → 排序影响中性）；档期字段随 P2 落位后接真实判定。
- **留注⑬（自动撮合前置=公示版本）**：无 published/active 规则版本时撮合 422 `rule_version_required`——正是 §11.1「备案未完成只跑 Stage A + 人工排序」的代码化；备案编号公示（§5.1）后此代理即真。
- **留注⑭（行业大类映射缺位）**：§4.3 行业分「大类命中 60」档需行业分类树——行业模板库 A7 未建，一期只有精确 100/未命中 0 两档。
- **留注⑮（全国档书面确认）**：geo_tier 3（全国）仅旗舰档必要条件已实现（quote.tier='flagship'），「客户书面确认件 source_uri 指针」二期落位。

## 二、行动说明

**动了什么**（feature 分支 `feat/dispatch-p1-matching`，零迁移 + 7 个文件）：

1. `dispatch/scoring.py`（纯函数，零 DB）：`level_rank/level_score`（映射分进快照）、`industry_score`（精确档，留注⑭）、`sla_score`（统一 50，留注⑫）、`geo_score`（三档）、`geo_tier`（§4.7 四档，city_index 来自 dispatch_cities.json）、`weighted_score`（权重全经参数注入）、`tie_break_seed`（sha256(package_id, round, version_no) 可复现）、`sort_key_onsite`（字典序）/`sort_key_remote`（加权 + 围栏优先 + 稳定尾键）。
2. `dispatch/matching.py`：`derive_required_level`（§4.5 伪代码逐行：基档 + data≥1.3/compliance≥1.2/integration≥1.4 触发最多上调一级 + 封顶 L4）；`override_required_level`（draft-only 409 + 必填 reason + `delivery_package_level_overridden` 事件）；`allowed_geo_tier`（round-1 封顶 3，全国档旗舰 necessary 条件）；`_stage_a`（五门逐门明细：A2 经 ModuleCatalog 把包侧 catalog_id 归一到档案侧 module_key——代码实测口径留注；A4 在途=offered/accepted 计数 vs floor(产能÷max(单均,1)) 自动算）；`match_package`（published + 本轮无 offer 守卫 → active 版本守卫（423→422）→ 五门 → 场景裁决 → Top3（top_n 常数）→ offer 落库 + 包 offer 迁移 + 逐人事件）；场景 C 事件带淘汰明细（人工回退诊断）。
3. `dispatch/packages.py`：create_package 接入 `derive_required_level`（C4 判据「推导落库」）；发布重推导 onsite（r3 语义不变）。
4. `dispatch/routes.py` +2：POST packages/{id}/match（平台侧）、packages/{id}/required-level（覆盖）；`api_catalog.py` ENTRIES 64→66。
5. `workbench/options.py`（P1-4）：`dispatch_seat_shares/dispatch_scenario_types/dispatch_match_modes/dispatch_decline_reasons` 四组随 options 下发。
6. 测试 `tests/test_dispatch_p1_r5.py` 12 例（见第三节）。

**影响面与回滚**：零迁移纯增量；既有 offer_service/结算/门禁零改动（67 例回归集全绿）。回滚=revert PR。

## 三、验证结论

| 验证项 | 结果 |
|---|---|
| §8.4 P1-2 判据「场景 A/B/C 全路径」 | ✅ `test_scenario_a_lexicographic_geo_beats_ability`（同城 L1 rank1 > 南京 L4 rank2；breakdown 无 weighted_score）+ `test_scenario_b_weighted_and_reproducible`（L4 加权胜同城；**权重改版翻转排序**证明取自快照）+ `test_scenario_c_no_auto_dispatch_and_event`（零 offer + manual_fallback 事件带淘汰明细） |
| §4.2 五资格门逐门反例 | ✅ `test_stage_a_gates_reject_individually`（A1 等级/A3 行业/A4 满负荷各自出局）+ `test_stage_a5_geo_fence_onsite_only`（首轮非同城出局→场景 C；远程型同候选入选） |
| §4.5 推导与覆盖（C4 判据） | ✅ `test_derive_required_level_matrix`（7 分支矩阵：基档/三触发因子/不叠加/封顶）+ `test_override_required_level_draft_only_with_reason`（覆盖留痕 + 发布后 409） |
| §4.8 契约 | ✅ `test_top3_cap_and_breakdown_schema`（Top3 封顶 + 键集逐项 + A4 明细结构 + 释明文案非空） |
| 降级态 | ✅ `test_match_requires_published_rule_version`（无公示版本 422） |
| **§8.8 闸③：负面清单 7 条** | ✅ `test_negative_list_protections`：①档案零软画像字段（schema）；②`weighted_score` 签名无历史参数 + 同分不同历史同分（3 条 declined 历史 vs 零历史 → weighted_score 相等）；③全包无轨迹语义（latitude/longitude/gps 静态零命中）；④到场字典序（独立用例）+ geo 分值仅 {0,50,100}；⑤settlements 零工时引用（avg/monthly_capacity 静态零命中）；⑥被拒者下一轮匹配仍入选（republish round+1 后入选 offers）；⑦全包零货运语义（freight/运费/货运静态零命中） |
| §8.4 P1-4 判据 | ✅ `test_options_payload_has_dispatch_enums`（四组枚举值集逐项） |
| 地理分档 | ✅ `test_city_index_from_seed`（同城 0/同省 1（无锡、南通）/跨省异圈 3/tier2 合成 index 钉规则/未知城 3） |
| 回归集 | ✅ r1–r4 全部 55 例 + 迁移链 15 例 = 67 例全绿；ruff/mypy 无新错 |
| 全量 | CI 门禁出具（本 PR server-tests job） |

**口径数字重测（H5）**：

| 口径 | 附录 A 快照 | 本轮实测 | 判定 |
|---|---|---|---|
| `__tablename__` | 76 | **84**（rebase 后含 goal-d1 presurvey_intakes；派单口径 83，§8.1 进度 7/8 余 disputes） | 漂移含并行轮 |
| 迁移 revision | 9 | **13** / head `a7f3c1e9d5b2`（goal-d1；派单零新迁移） | 接链正确 |
| 蓝图路由 | 212 | **226**（rebase 后含 goal-d1 两路由；本分支净 +2） | 正向漂移 |
| api_catalog ENTRIES | 54 | **66**（+2） | 一致性测试（r4）双向钉死 |
| 服务端 pytest | — | **CI 出具（1398+，含 +12 r5 用例）** | — |

**撞车与 rebase（如实）**：goal-d1（PR #37，presurvey_intake + G3 前置闸）在本轮 CI 期间合并——rebase 到 `a7f3c1e9d5b2`，AGENTS.md 口径行冲突按联合口径手并；rebase 后回归集 74 例全绿（含 d1 的迁移链）。

**失败与未完成项（如实）**：r5 用例首轮 8 失败，逐一定位：① `_onsite_package` 未给项目挂 ProjectModule → required_modules 恒空使 A2 反例空转（补真实模块行 + ModuleCatalog 缺种自建）；② publish 重推导 onsite 使 remote 场景被翻回到场（测试侧清 schedule）；③ 多处测试构造撞「同包同轮同候选」唯一约束与「本轮已有 offer」守卫（改远端轮次/round+1）；④ `_profile` 漏 add user（幂等补 add）；⑤ 负面清单 #2 断言走错场景（远程路径才有 weighted_score）。全部为测试构造问题，撮合代码本体无返工。

## 四、下一轮建议

1. **P1 收官清点（goal-r6 建议）**：P1 七项现状 = P1-1✅ r4 / P1-2✅ 本轮 / P1-3✅ r4 / P1-4✅ 本轮 / P1-5✅ r4 / **P1-6 Quote.owner_user_id（S 档，报价归属过滤）待做** / **P1-7 留存策略（撮合流水 3 年、涉税 10 年归档任务，M 档）待做**。建议 goal-r6 = P1-6 + P1-7 + `disputes` 表（§8.1 第 8 张，随 §6.6 L0-L2 仲裁入口 + E5 T+30 对账差异草稿）——完成后 §8.4 P1 全过、§8.1 八表齐。
2. **P2 批次（goal-r7+）**：P2-1 桌面端 dispatch 页面簇 / P2-2 Project.status 枚举扩展 / P2-3 business_line 'FDE_DISPATCH' / P2-6 dispatch_cities 扩字段（S 档为主）；P2-4 私下接单封堵（L）与 P2-5 组织实体（暂缓）殿后。
3. **风险**：① 撮合的 sla/行业大类两维是代理口径（留注⑫⑭），P2 档期与行业树落位时需回归排序断言；② 扩圈链的「每级等待 15min」（§6.2 radius_expand_wait_minutes）尚无调度任务消费——P1-7 归档任务轮顺带挂 expire_stale_offers 调度；③ match 的并发守卫依赖「本轮已有 offer」预检 + 唯一约束兜底，真并发双撮合靠 offer 唯一约束回 500 而非 409——可接受（管理动作低频），如需精确 409 在 P2 补包行锁。
4. **待拍板（附录 B）**：无新增阻塞；留注⑫⑬⑭⑮并入收口报告待签字清单。
5. **文档修订建议（附录 A 时效）**：路由 226 / ENTRIES 66；§4.6 首版到场词表与实现一致（现场/到场/驻场/驻点）可回写设计文档；A-② 行号漂移再累积（models.py 持续增长），建议下轮文档修订统一重锚。
