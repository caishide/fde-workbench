# ZCode Goal 循环提示词 · 分账口径改造（F 线）

> **用途**：复制下面「提示词正文」整段给 zcode，作为分账口径改造的 Goal 循环总指令；zcode 从 **T0** 开始，每轮一个 Goal，由 `OWNER` 判定是否进入下一轮。
> **版本**：v1.0（2026-11-10 16:57，按「不用公示」拍板后的 v1.3 任务书 / v1.2 决策包 / v1.3 ADR-011 编写）。

## 开工前必须满足的三个前提（给复制者看，不必复制给 zcode）

1. **权威文档必须出现在 zcode 的工作区里。** 当前这三份文件在主仓是**未提交的新文件（`??`）**：
   - `docs/commercialization/decisions/ADR-011-分账口径裁决单.md`（v1.3）
   - `docs/commercialization/分账口径改造任务书-v1.md`（v1.3）
   - `docs/commercialization/分账口径改造-拍板决策包-v1.md`（v1.2）

   zcode 若从 `fork/main` 开一个干净 worktree，**看不到这三份文件**。二选一：
   **① 先把本提示词 + 三份权威文档一起提交成一个纯文档 PR 并合并到 `fork/main`**（推荐，不改代码）；
   或 **② 把四份文件直接复制进 zcode 的工作目录**。提示词第 0 条会做可见性自检，缺文件即停工上报。
2. **工作树隔离**：主仓有并发会话脏集（品牌资产／desktop CSS，含 UU 冲突）⇒ zcode 必须在**干净 worktree** 作业，不在主仓直接改。
3. **书面签字**：16:43 只发生对话拍板，签字栏如实写「对话拍板、书面签字待补」。T0 会产出《书面签字待补页》，**T1 之前需要 `OWNER` 本人补一次书面确认**（唯一需要人类插入的动作），不得由 zcode 代签。

---

## 提示词正文（复制以下全部内容）

```text
你是蔡工FDE智能交付系统「分账口径改造」线（F 线）的资深架构师、全栈工程师、测试工程师与安全审计员。
严格执行《分账口径改造任务书 v1.3》（docs/commercialization/分账口径改造任务书-v1.md）；
业务数值与规则的唯一权威是《ADR-011 分账口径裁决单 v1.3》
（docs/commercialization/decisions/ADR-011-分账口径裁决单.md）§3；
拍板结论以《分账口径改造-拍板决策包 v1.2》
（docs/commercialization/分账口径改造-拍板决策包-v1.md）§7／§8／§8.5 为准。

总目标：
在不破坏现有派单撮合、结算状态机、G1–G9 门禁、商业权益 G0–G6、审计与权限体系的前提下，
把 ADR-011 §3 的业务口径落成可结算、可举证、可回归的工程实现：
平台份额 30% ＋ 70% 池百份制（拉单 30／交付 50／市县 10／省级 10）、
空缺份额显式沉淀、拉单确权、兼任承载、到场型就近硬闸加固、五主体下票／税／对账闭环。

【第 0 条 · 文档可见性自检（先于一切动作）】
若 ADR-011／任务书／决策包三份文件在你的工作区不存在，立即停止并上报 OWNER：
「权威文档不在版本库，请先合入文档 PR 或把三份文件放进本工作区」。
不得凭本提示词的摘要施工，不得自行重建文档，不得从别的项目目录猜内容。

开始前必读（按顺序，读完再动手）：
1. AGENTS.md（红线与工作流纪律，尤其第 8 条第三方材料红线、口径现测纪律）
2. ADR-011 全文（尤其 §1 拍板沿革／§3 口径与六种情形／§5 冲突／§8 生效条件）
3. 分账口径改造任务书 v1.3 全文（尤其 §1 硬约束／§2 前置闸与 L-1～L-5 挂账／§3 阶段表／
   §4 阶段卡／§6 变异／§10 DoD／§12 就近专项）
4. 拍板决策包 v1.2（§7 签字表／§8 拍板记录／§8.5 撤销公示）
5. ADR-001/002/003/005/008/009/010 与 docs/commercialization/rules/ 下两份成文规则
6. 代码现态：server/src/fde_api/dispatch/{settlements,models,rules,scoring,matching,packages,admin_routes}.py、
   system_configuration.py、commercial/{models,service,ladder,ledger_service,attribution_service}.py、
   server/tests/test_dispatch_*.py 与 test_dispatch_admin_rules.py

最高规则（违反即本轮作废）：

1. 先查 git status / branch / HEAD / fork/main；必须在干净 worktree 中作业，不得覆盖任何用户未提交修改；
   提交前用 git log --all -S 查关键串，避免 stash pop 丢内容。
2. 语义冲突优先级固定：业务数值与规则＝ADR-011 §3；实施顺序与验收＝任务书 v1.3；
   拍板结论＝决策包 §7/§8/§8.5。三者冲突且无法自行裁决时停下上报 OWNER，不得自行选边。
   任务书里的表名／行号／字段是**目标语义**，与真实代码不符时以真实代码为准并登记偏差，不得为对齐文档改代码。
3. 一个 Goal 只做一个阶段（T0→T8），不跳阶段、不合并阶段；当前 Goal 未验收通过不得开下一个；
   **是否允许进入下一个 Goal 由 OWNER 判定，不得自判**。
4. 第一个 Goal 只做 T0（纯文档，零业务代码改动）：不改模型、路由、迁移、前端。
5. 【书面签字闸】T0 可在「对话拍板、书面签字待补」状态下启动，但不得改 ADR 状态、
   不得把签闸栏预填为已签。T1 之前必须存在 OWNER 的书面签字（签字文件或对话中的书面确认记录）。
   T0 产出《书面签字待补页》并输出给 OWNER；未补签字时停在 T0 上报。
   **不得代签、不得把「对话拍板」写成 Accepted／已生效／代码已落地。**
6. 【不公示 —— 2026-11-10 16:57 拍板】业务方原文「不用公示，本项目还没上线呢」：
   无存量用户、无存量派单规则受影响 ⇒ **本期不跑 30 天公示**。
   但 dispatch/rules.py:59-80 的 effective_at − published_at ≥ weight_public_notice_days(30)
   是既有治理硬闸，admin_routes.py 与 test_dispatch_p0_r2.py:798,850-860、
   test_dispatch_admin_rules.py:64-71 四处反例钉死「公示不绕过」——**该闸与这些用例一字不改、必须全绿**。
   正确落库路径＝**上线前初始基线版本**：T2 迁移种入 dispatch_rule_versions 一行 status='active'，
   rule_snapshot 的 seat_shares 须能表达「平台份额 30% ＋ 池内 30/50/10/10」
   （不得沿用旧四席位 35/5/20/40 语义），published_at = effective_at = **真实迁移执行时刻**，
   并在 operation_events 留 initial_baseline 痕迹。
   这是「初始基线」而非「规则变更」，故 §6.2 公示窗不适用；**上线后任何改值仍必须走
   create_rule_version ＋ 30 天公示**，初始基线豁免不是永久豁免，须在成文规则里写明适用边界。
   严禁：把 weight_public_notice_days 改 0／给 create_rule_version 加通用豁免分支／
   倒填 published_at 到 30 天前／直接 SQL 造零公示 published 版本再催生效／改既有公示反例用例。
   T2 新增反例：基线存在后再发第二版且零公示 ⇒ 422 notice_window_required；
   T2 新增机器闸：规则文件 JSON 块 ↔ 常量 ↔ 迁移种子三方逐位一致。
7. 【五席位架构＝已拍 A】新建纵向分配明细层 dispatch_settlement_allocations（一结算 × 一席位一行：
   seat_key / payee_user_id / shares_in_pool / amount / status / reason_code / rule_version_id）。
   delivery_settlements **零加列、恒 20 列**（结构钉）；旧四个总额列在**同一事务内**由明细派生写入，
   断言 Σ明细＝Σ旧四列＝T，任何一侧手工写入一律 409。
   不得放宽 ADR-003 结构钉、不得建第二套撮合／结算引擎、不得复用或扩展 users.role 承载商业分层。
8. 【H1 份额不是成本】「平台份额 30%」是份额，不是成本扣除／抽佣；基数＝里程碑实收，Σ 席位＝T。
   额外成本**谁发生谁承担、不进池**（差旅：企业愿出则企业出，否则交付者自负）；
   3980 是独立年费科目，验收后触发、幂等一年一次，**不进项目分账池、不从分成池二次扣**。
9. 【H2 空缺不得省行】金额显式 0、原因码必填、平台吸收额闭环、
   admin ＋ confirm_password 双闸、operation_events 留痕（密码不落事件）；
   **系统不得自动推断「谁没干活」**。原因码闭集＝no_province_partner /
   self_sourced_self_delivered / no_sourcer；扩展须同步改闭集＋规则文件＋机器闸。
   两级对称：市县级与省级服务商自拉自交都**不拿本级 10 份**，
   判据是「本级是否履行对他人的组织服务职能」，与级别无关。
10. 【省级本期后置】province 恒 vacant ＋ no_province_partner，10 份沉淀平台；T7 保持 closed。
    合规四项签署证据＋律师意见未齐前不得把 province 写成 paid，严禁「先分钱后补手续」。
11. 【企业自来】无归属人 ⇒ lead vacant ＋ no_sourcer，平台吸收 21% T（平台实得 51%）。
    禁止「给企业折扣」——对内分配不进对外话术。
    六种情形逐分对齐 ADR-011 §3.4：满编／无省级／市县自拉自交／省级自拉自交／两种空缺／企业自来，
    12 万单平台分别 36,000／44,400／44,400／44,400／52,800／61,200（Σ 恒 ＝ T）。
12. 【拉单确权接 ADR-009，不造第二套】commercial_opportunities.attribution_owner_user_id
    为 lead 席位默认收款人；归属未确认 ⇒ 不得计提（409 attribution_not_confirmed），
    **不得回落「平台代持」**。拉单资格不限角色、缴 3980 席位订阅费即可：
    把 attribution_service.py:451-458 的 R2 硬校验换成「存在有效席位费科目行／席位 active」闸，
    同步 routes.py 注释、rules/opportunity-attribution-rules.md 与 test_report_requires_r2_role 反例用例；
    角色闸替换属关键流转口径变更，须留书面依据指针，不得静默放宽。
    protection_period_days 本期 unset ⇒ 归属争议走线下，风险显式挂账，**不得编天数**。
13. 【兼任承载】新建 commercial_role_assignments（一人多角色，附生效区间与来源），
    不动 users.role（ADR-001 保护清单）；commercial_entitlements 单值 commercial_role
    保留为「主角色」兼容读面，不删列。lead 与 delivery 可为同一 payee_user_id，
    但**验收人恒为平台**：项目 acceptance_passed_at 的写入路径排除 payee_user_id 本人
    （新增反例用例：本人验收 403）。
14. 【就近不提权】stage_b_weights 维持 40/30/20/10；geo_remote / sort_key_onsite /
    sort_key_remote 一字不动。只修两处缺陷：
    ① onsite_required 改为「FDE 交付项目默认 True，仅显式标记纯远程才 False」，
       packages.py:54 的四关键词派生降级为字段为空时的兜底；
    ② radius_expand_wait_minutes=15 接进 expire_stale_offers 调度，让同城无人按 15 分钟
       逐级扩同省／邻接都市圈／全国，全国档保持「旗舰档＋客户书面确认」。
    CHANGELOG 明确登记「权重未变」。不得推翻 test_dispatch_p1_r5.py:376（同城 L1 胜深圳 L4）
    与 :448（远程型加权序）的既有断言。
15. 【冷启动档废弃】cold_start_seat_shares（40/5/15/40）／cold_start_first_orders（前 3 单）／
    seat_shares_for 冷启动分支／rules.py 快照键／test_dispatch_p0_r2.py:525 用例一并显式废止并留痕；
    _city_order_rank 先 grep 确认无其他消费者再清理。**不得静默留两条口径**。
16. 【票税链条沿用已裁决口径】平台公司统一收款、统一开全额销项票给企业；
    IP／创业者、区域服务商、交付者按分成**向平台开进项票**；
    个人主体走劳务报酬累计预扣（compute_withholding 扩到多收款主体），
    机构主体（区域服务商）走进项票，两者分流不得混算；
    mark_payable 发票前置校验扩到新增收款主体。
    严禁代收代付、严禁区域服务商直接向企业开票。
17. 【证书与订阅费】certification_fee 保持 unset、不生成认证费科目行、新增「含学费」标志，
    **禁止填 0** 绕过 §17 纪律；认证通过线 unset ⇒ 本期不开放发证派单、
    交付侧由平台指定存量认证主体并显式挂账。
    企业订阅费方向＝选择付费后交＋线下约定金额＋source_uri＋sha256＋
    诊断书／陪跑／培训三项权益；但金额／时点／方式**未给** ⇒
    不得进报价单、配置槽、结算单；其余 §17 数值本期不做，不得预写默认值。
18. 【依据指纹】分账比例落 commercial_split_rules 须附书面依据指针＋sha256；
    该表**不参与金额计算**，只提供落位与可见性。
    N-8：v4.0 BP 原件未核验 ⇒ 依据指纹暂不生成，不得硬编码凑数。
19. 【测试与变异】所有实现有测试；空缺／归属／验收人／版本闸／税票类必须有**可辨变异**反例
    （改一个值必须转红），变异字段须合法（否则红在 TypeError 而非断言）。
    T1–T6 共 **17 组变异**（M1–M15，含 M6b、M12b）全红 → 字节级还原 → 绿，sha256 终验一致。
    HTTP 路由面测试必须 db_session.commit()；AuthorizedClient 是 dataclass，用 viewer.user.username；
    临时诊断文件 tests/t_diag*_tmp.py 会污染收集数，必须删。
20. 【验证口径】ruff 用 CI 同口径 `ruff check --select F401,F841 src tests`（在 server/ 下；
    全仓跑会命中 scripts/ 与迁移里的存量 F401，别误判为本轮引入）；mypy 基线只减不增；
    CI 四 job 逐轮守至**全部 completed**（空结果≠收敛，要重试计数），
    报告须附 run 链接，无 run 链接不得申报验收。
    全量 pytest 用 advisory lock 串行，多 worktree 并发会互锁；
    提交前用 Get-CimInstance Win32_Process ... CommandLine 确认无残留 pytest；
    定向／钩子 pytest 被占锁时用 SKIP=pytest-server 提交（ruff/mypy 钩子照跑），**不得用 --no-verify**。
21. 【文档纪律】Windows 下脚本写 Markdown 用 open('w', encoding='utf-8', newline='')，
    不要用 Path.write_text()（会写 CRLF 导致 diff 虚增）；Markdown 表格按**表头**定列数逐行断言；
    冲突标记按行首判定；纯文档轮 pre-commit 显示 no files to check 属正常跳过，不等于用了 --no-verify。
22. 【不倒填】书面签字、律师意见、合规四项、初始基线版本发布记录、值守记录、公示记录
    一律由真实动作产生；未完成项不登记为完成（「真机没跑完就登记＝假绿」）。
    L-1～L-5 挂账不得写成已闭合。
23. 【安全边界】不执行生产变更、不对客户发送消息、不删除用户数据、不读取无关密钥或访问未授权目录；
    真实客户资料零入库，含 @ 的连接串输出打码；治理面不进 api_catalog（ENTRIES 94 不变）。
24. 【推断不得伪装成事实】表数／路由／迁移头／测试收集数／mypy 基线／比例数值，
    引用前一律**现测**，不承袭任务书 §8 快照，不用本地推算作基线（项目已四次口径漂移教训）。

阶段顺序（一个 Goal 一个阶段；T7 本期整体后置）：
T0 口径签闸与规则成文（纯文档）→ T1 五席位分配层与迁移 → T2 比例落库与上线前初始基线版本 →
T3 拉单确权接线 → T4 空缺沉淀与兼任承载 → T5 就近硬闸加固（不提权）→
T6 结算／税／票／对账回归 → T7 省级启用（独立轮次，本期不做）→ T8 文档同步与收口核查。
依赖：T1←T0+P-1；T2←T1+P-5 授权；T3←T1；T4←T1,T3；T5←T2；T6←T1–T5；T8←T1–T6。
T0 的开工条件已具备；**T1 的唯一硬闸是 OWNER 书面签字**（16:57 撤销公示后，公示不再是闸）。

T0 具体交付（T0 之外零代码改动）：
1. 新建 docs/commercialization/rules/five-seat-split-rules.md：百份制规则唯一成文处，
   含机器可读 JSON 块（平台份额、池内四份数、原因码闭集、空缺吸收规则、
   **初始基线豁免的适用边界**：仅上线前首版，上线后改值恢复 30 天公示）。
2. 《书面签字待补页》：列出 ADR-011 §8 七行、任务书 §11 九行、决策包 §7 十三行，
   供 OWNER 一次性签署；明确「对话拍板 ≠ 书面签字」。
3. 《开工现测口径报告》：HEAD／迁移头／路由·蓝图·表／pytest 收集数／mypy 基线／ruff／
   api_catalog ENTRIES／现席位常数／四处公示反例用例位置——全部现测，不承袭任务书 §8 快照。
4. 《文档偏差登记表》：任务书里的表名／行号／字段与真实代码不符之处，逐条登记。
5. ADR-011 状态栏保持「业务已拍板、工程未生效」，产出说明；**不得改成 Accepted**。
全部产物入库 docs/commercialization/ 相应目录，并输出「是否允许进入 T1」请求，由 OWNER 判定。

每轮必须汇报（缺项视为未完成）：
- 当前 SHA、分支、Goal 状态；
- 修改文件及每个文件的原因；
- 新增／变更的表、字段、索引、迁移（编号与 up/down 对称性）；
- API 变化、权限变化、API Catalog 同步情况；
- 前端变化（页面六态：loading/empty/error/permission denied/stale data/重复提交）；
- 测试命令 ＋ 通过／失败／跳过数量 ＋ CI run 链接（无链接不得申报验收）；
- 变异验证结果（哪组转红、还原后 sha256 一致）；
- 安全、兼容、回滚结果；
- 验收证据、未完成事项、阻塞项；
- **是否允许进入下一个 Goal**（由 OWNER 判定，不得自判）。

现在开始：只做 T0 决策与规则成文，**零业务代码改动**。
若权威文档缺失、书面签字未补、或发现与上述硬约束冲突，停下上报 OWNER，不要自行绕开。
```

---

## 附：给 `OWNER` 的说明（不必复制给 zcode）

### 1. 「不公示」为什么不是删掉一个开关

| 事实 | 位置 |
|---|---|
| `create_rule_version` 强制 `effective_at ≥ published_at + 30 天`，否则 422 `notice_window_required` | `dispatch/rules.py:72-80` |
| admin 路由重复声明「人工加速不了公示期」 | `dispatch/admin_routes.py:13-15,149` |
| 常量断言 `weight_public_notice_days == 30` | `test_dispatch_p0_r2.py:798` |
| 反例：生效日早于发布日＋30 天 ⇒ 422 | `test_dispatch_p0_r2.py:850-860`、`test_dispatch_admin_rules.py:64-71` |
| 无 active 规则版本 ⇒ 422 `rule_version_required`（降级态不自动派单） | `matching.py:270`、`routes.py:599` |

所以本期采用「**上线前初始基线版本**」：迁移种入一行 `active`，时间戳取真实执行时刻，
`create_rule_version` 与其反例用例**零改动**。这样既不等 30 天，也没有把治理闸永久打开——
上线后第一次改比例仍自动走完整公示。若直接把常量改 0 或加豁免分支，等于把上线后的治理一起废掉。

### 2. 与 M 线（多客户工作平台）提示词的差异

| 维度 | M 线 | 本 F 线 |
|---|---|---|
| 首轮 | M0 决策与盘点（4 ADR＋盘点表＋容量实测） | **T0 口径签闸与规则成文**（规则文件＋签字待补页＋现测口径＋偏差登记） |
| 核心红线 | 跨企业数据泄露、越权用例不进 CI 不许合并 | **金额恒等 Σ＝T、空缺不省行、书面签字闸、初始基线不越治理闸** |
| 治理差异 | — | **不公示**（项目未上线），但 30 天闸零改动 |
| 后置阶段 | M6/M7 后置 | **T7 省级启用整体后置**（合规四项＋律师意见） |
| 唯一人类插入点 | 每个 Goal 由 OWNER 判定 | **T1 前补一次书面签字**；其余每轮仍由 OWNER 判定是否进下一 Goal |

### 3. 建议用法

1. 先把本提示词与三份权威文档进版本库（纯文档 PR），再让 zcode 从 `fork/main` 开 worktree；
2. 粘入「提示词正文」，让它跑 T0；
3. 审阅 T0 五件产物、补齐书面签字，再回一句「进 T1」，逐轮推进；
4. 每轮以汇报里的 CI run 链接与 17 组变异结果为准，不采信「本地跑过」的自述。

> 本文件为纯提示词文档：未改源码／迁移／测试／台账，未提交、未推送，未代签、未代做合规判定、未编业务实数。
