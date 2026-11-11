# 商业化阶段状态（按 Goal 轮次累积）

- 权威基线：**fork/main**——G0 合并 `28f55fd`（#216）／G1 合并 `f186342`（#217）；G2 合并 `b0fd5fc`（#228）／G3 合并 `f65f874`（#234）／G4 合并 `ffed2e2`（#241）／**G5 合并 `28285e5`（#251，基线 `5294a6e`，合并前两度 rebase 融合上游 #246/#247/#250/#249/#252/#254/#253 七笔）／**G6 合并 `4e3e0e0`（#262，基线 `212b5fb`，合并前两度 rebase 融合上游 #258/#259/#260/#261 四笔）**
- 工作树：`D:\test\fde-wt-g1`
- 当前阶段：**§16 最终验收清单核对（收尾核查轮）— 已完成（18/18 全过）；商业化 G1–G6 Goal 循环全部收口**
- 阶段纪律：**一个 Goal 只做一个阶段，不跳阶段**；每阶段按任务书 §14 总提示词逐项回报（SHA/分支/阶段、改动文件、迁移、API·权限·目录、前端、测试命令与通过·失败·跳过数、安全·兼容·回滚、验收证据、遗留、下一阶段是否可开）

---

## G6：企业空间与企业自助交付（T-06/T-08）— 已完成

- 分支：`feat/commercial-g6-enterprise-space`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `212b5fb`（G5 收口态）
- 状态：**completed**（PR #262 squash 合并 `4e3e0e0`；PR run 42655291432／main run 42657141489 server-tests 实测同值 2618 passed + 6 skipped（462.00s／619.95s），四 job 全绿；部署活体三项复验全绿，见下）

### 目标

任务书 §10：企业能**自己注册**、描述问题、完成诊断，并按三档分流；「企业客户」与「企业自助用户」为**同一主体两种状态**共享企业空间，不另立第三套计费口径；**完全自助是长期目标，不第一天承诺**。

### 设计决策及理由（含 ADR 编号）

- **ADR-010**（`decisions/ADR-010-enterprise-self-service-space.md`）八项裁决：①四类注册入口＝R1–R4 一一对应（`REGISTRATION_ENTRIES` 注册表机器闸）；②自助注册＝当事人自证（一事务四件全成全败）；③ADR-004「授予=admin」为边界澄清非推翻（admin 闸守 staff 路径，自助授予防滥用＝结构性保证）；④两状态派生不落列（paid_delivery＝现行选择行存在，**不是账**）；⑤三档分流人工判定留痕、系统零判定（tier 复用 G2 闭集；零阈值常量）；⑥付费选项派生 G2 权威＋跟进语（零金额零数值哨兵）；⑦企业自主选择不被取消＝append-only（admin 不可代选/取消/改选；源码扫描钉）；⑧企业空间复用既有权限模型（`add_project_member`＋`project_access`，零平行权限表）。

### 修改文件

```text
新增：
  docs/commercialization/decisions/ADR-010-enterprise-self-service-space.md
  server/src/fde_api/commercial/enterprise_service.py                      （NEW：注册/空间/分流/选择/顾问注记原语）
  server/migrations/versions/e8b3f7c2d9a5_commercial_g6_enterprise_space.py
  server/tests/test_commercial_enterprise_space.py                         （NEW：27 例）
修改：
  server/src/fde_api/commercial/models.py                                  （+2 表 + 常量 + subject.problem_description 列）
  server/src/fde_api/commercial/routes.py                                  （+3 读/自证路由）
  server/src/fde_api/commercial/admin_routes.py                            （+2 治理写路由）
  server/src/fde_api/commercial/quota_service.py                           （profile 读面增 registration_entries）
  server/src/fde_api/users/service.py                                      （NEW register_self_service_user 原语）
  server/tests/conftest.py                                                 （清理序：G6 两表先于 G2 额度两表）
  server/tests/test_migrations.py                                          （HEAD e8b3f7c2d9a5 + 全集 57）
  docs/audit/v3-{route,database}-inventory.csv + v3-workbench-inventory.json（重生成：441/49/145/57）
  docs/architecture/archify-diagrams/architecture/{candidate.json,system-architecture.html,preview.png}
  AGENTS.md / CHANGELOG.md / docs/commercialization/phase-status.md（本节）
```

### 数据库迁移

迁移 `e8b3f7c2d9a5`（56→57 rev，additive，单链单头）：`enterprise_triage_decisions`（三档分流人工判定留痕：tier CHECK＝G2 三档闭集＋basis 指针/指纹同有同无 CHECK）、`enterprise_paid_option_choices`（append-only 选择行：option CHECK＝同一闭集＋部分唯一索引〔一主体一份现行〕＋顾问注记三元组原子 CHECK）、`enterprise_quota_subjects.problem_description` 加列（可空＝兼容存量）。**零播种零金额零数值**（哨兵钉）。

### API / 权限 / API Catalog

- 读/自证面（3）：`POST /api/v1/commercial/enterprise-registrations`（**公开自证入口，无鉴权**——任务书验收「无需经招商人员」的直接要求）、`GET /api/v1/commercial/enterprise-spaces/<subject_key>`（绑定账号/admin；他人 403）、`POST …/paid-option-choices`（**只认绑定账号本人**）。
- 治理写面（2，admin＋`confirm_password` 双闸）：`POST /api/v1/admin/commercial/enterprise-spaces/<subject_key>/triage-decisions`（三档分流人工判定；前置闸＝诊断已完成）、`POST …/paid-option-choices/<choice_id>/advisor-note`（顾问跟进注记，只补三元组）。
- `free-diagnosis-profile` 读面增 `registration_entries` 节（payload 扩展，零新路由）。**全部不进 api_catalog**——ENTRIES **94** 不变。

### 前端变化

无（纯服务端轮，桌面便携版不重打包；企业空间桌面呈现面挂后续轮）。

### 测试命令与结果

- `pytest tests/test_commercial_enterprise_space.py -q` → **27 passed**。
- 全量 `pytest -q -n 4 --dist loadfile`（**CI 同命令**）→ **2624 收集 = 2618 passed + 6 skipped，0 failed**（EXIT=0 / 19m35s〔rebase 融合上游 #258/#259/#260 三笔后复跑〕；G5 轮基线 2596 收集 + 本轮 +27 + 上游 #258 +1 ＝ 2624）。
- **PR CI server-tests 实测（run 42655291432）：2618 passed + 6 skipped（462.00s）；main run 42657141489 同值（619.95s）——与本地实测（19m35s）三轮一致**。
- `python scripts/check-python-types.py` → **OK：baseline 279 occurrences / 104 distinct，current 279**（四实施期 Optional 收窄当场归零）。
- `ruff check`（全部改动文件）→ All checks passed。
- **变异六连全转红→还原→绿**（字节级备份还原，sha256 终验一致）：M1 派生态抹平（engagement_state 恒 self_service→付费态读面反例红）／M2 分流前置闸摘除（未完成诊断可分流→红）／M3 admin 代选放行（摘绑定账号校验→admin 越权用例红）／M4 supersede 摘除（旧行不退位→撞部分唯一索引 500→红）／M5 注册跳过额度落库（额度行缺失→DB 断言红）／M6 注记可重复（二条注记 409 摘除→红）。

### 安全检查

- 注册面公开自证＝任务书验收直接要求；防滥用＝结构性保证（USCC 一主体一份额度库层兜底＋七项不免费硬编码＋六项完成判据）；对外部署的注册面节流**已清偿**（挂账清偿轮 2：来源 IP 限流 10 次/小时＋fail-open/fail-closed 开关；本期仍以内网部署假设交付，ADR-010 §3-3 已回填）。
- 分流/顾问注记＝admin＋`confirm_password` 双闸；逐动作 `operation_events` 留痕（request_id，**密码不落事件**）。
- 企业自主选择不被取消＝append-only（admin 越权 403＋源码扫描钉＋路由方法集扫描钉）。
- 书面依据只存指针＋sha256；未读取无关密钥；`server/.env` 未入库；本轮零生产变更。

### 数据兼容与回滚

- additive 两表＋一列（可空），**零既有表改列语义**（科目层/G4/G5 表零触碰）。
- 回滚＝`alembic downgrade b3e8a6c2d4f7`（child-first：choices → triage → 加列回退）＋回滚镜像。
- 额度流程（G2 三态）零改动回归绿（quota 27 例全绿）；派单/项目/结算回归绿（全量套件）。

### 验收证据（任务书 §10 逐条）

| 验收项 | 证据 |
|---|---|
| 企业可独立注册并完成一次诊断，无需经招商人员或先行寻找 FDE 服务商 | 公开注册入口（无鉴权 200）＋自助授予额度＋start→complete（admin 登记）→confirm（绑定账号确认）全链用例；`test_self_registration_creates_account_identity_subject_quota`＋`_completed_subject` 链路 |
| 三档分流可留痕、可回看判定了哪一档；无量化阈值硬编码 | `enterprise_triage_decisions` 留痕＋空间读面回看用例 `test_triage_decisions_reviewable_in_space_view`；**零阈值常量零评分代码**＋哨兵 `test_paid_options_derive_from_g2_authority_and_carry_no_numbers`（载荷无数字）＋闭集复用 G2 权威 `test_triage_tier_closed_set_matches_g2_authority` |
| 复用既有权限模型，未新建平行权限表 | `test_enterprise_user_joins_delivery_project_via_existing_add_member`（既有 add_project_member＋project_members 既有表＋project_access 可读）＋元数据机器闸 `test_g6_metadata_adds_exactly_two_tables_and_no_permission_tables` |
| 四类注册入口齐备；两状态同一主体 | `test_registration_entries_cover_all_four_identities`（键集＝R1–R4↔注册表↔G2 体验入口）＋`engagement_state` 派生用例 |
| 换账号不重置（G2 硬不变量穿透自助路径） | `test_same_subject_second_registration_does_not_reset_quota`（额度行恒 1）＋`test_second_account_cannot_restart_bound_quota`（409）——M5 变异转红 |

### 遗留问题

1. 体验上限（ADR-004 §1.8）消费接线维持挂账——真实消费方在 V3.2 simulation 域（ADR-004 §1.9 不触碰），判定原语已在位。
2. 注册面节流（复用 #250 登录限流模式）——**已清偿**（挂账清偿轮 2：`feat/commercial-registration-throttle`，公开注册入口按来源 IP 限流＋fail-open/fail-closed 开关；本期仍为内网部署假设）。
3. 企业空间桌面呈现面（自助注册页/空间视图）挂后续桌面轮；GAP-15 埋点、ADR-004 §1.4 集团归并（法务）、规则/费率数值拍板（§17）仍开放。

### 部署活体验证（合并后，2026-11-10 实测）

- 三镜像 rebuild 自本工作树（合并态 `4e3e0e0` 干净树）＋`docker compose up -d --force-recreate`＋容器内 `alembic upgrade head`：**b3e8a6c2d4f7 → e8b3f7c2d9a5（head）** 活体落库。
- **复验①（活体路由与本轮口径一致）**：url_map＝**442 条**（441 口径路由＋1 静态；G4 同构 427→428）——enterprise 域 11 条规则串（本轮 5 新＋G2 额度面 4＋admin 授予/完成 2）全数在位；`/api/v1/health/live` 200、`/api/v1/health/ready` 200（database ok／redis ok），四容器 healthy。
- **复验②（容器内 alembic current ＝ 本轮 head）**：`e8b3f7c2d9a5 (head)`。
- **复验③（容器镜像 ID ＝ 本工作树构建产物）**：api `f64601987f8e`／worker `e73f45a36b96`／scheduler `1d2d42e4f46b` 逐枚一致（同一构建时戳 2026-11-10 00:56:13）。
- 活库只读断言：`enterprise_triage_decisions` **0 行**／`enterprise_paid_option_choices` **0 行**（业务动作行零预置）；`enterprise_quota_subjects.problem_description` 列在位；试运营数值零落库。

### 是否允许进入下一阶段

**G6 是任务书 §13/§16 的最后一个商业化阶段——收口完成**：PR #262 四绿（run 42655291432）＋合并态 main run 四绿（42657141489）＋部署活体绿（三项复验＋活库断言，见上）。**商业化 G1–G6 全阶段闭环；进入 §16 最终验收清单核对（收尾核查轮）**。

---

## G5：区域合作商能力建设（T-12a，不含 T-12b）— 已完成

- 分支：`feat/commercial-g5-regional-partners`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `2538a02`（G4 收口态）
- 状态：**completed**（PR #251 squash 合并 `28285e5`；PR run 42620729944／main run 42622618241 server-tests 实测同值 2590 passed + 6 skipped（593.29s／406.34s），四 job 全绿；部署活体三项复验全绿，见下）

### 目标

任务书 §9：建区域阶梯的**内部能力**，同时**不具备**对外收费签约能力（本期不做 T-12b）；四阶段可区分、前两阶段无独家权、城市服务伙伴按项目结算无固定年费、**售卖能力默认关闭**且开关绑定合规条件清单。

### 设计决策及理由（含 ADR 编号）

- **ADR-005**（`decisions/ADR-005-regional-commercialization-gate.md`，G5 成文）十项裁决：①四阶段闭集（city_observer/city_service/formal_partner/regional_agent），阶段注记读面派生；②**售卖开关单行默认 closed**，CHECK 结构性排除缺件开门；③「无任何代码路径可在开关未开启时对外收费签约」＝结构性保证（`require_sale_gate_open` 唯一闸门 + formal_partner 写点唯一源码扫描钉）；④合规条件四项**登记 ≠ 开启**（登记后仍 closed，开启须独立双闸动作）；⑤前两阶段不授予独家区域权（CHECK＋服务层双封）；⑥区域代理「暂不启用」＝**无写路径**（409 `regional_agent_not_enabled`），不是禁用状态列；⑦城市服务按项目结算引用既有 G3 `project_share` 科目行（不建第二套结算），正式档不得写按项目结算（两档收费形态互斥）；⑧试运营升级指标与首期金额**本期不定数**（哨兵钉死示例数值不落码）；⑨三档定价以 **BP v4.0 为唯一基准**（迁移播种＋代码 `REGIONAL_TIER_SEED` 同源）；⑩真实身份材料零入库（伙伴代号＋指针＋sha256）。
- 成文规则唯一处：`docs/commercialization/rules/regional-partner-program-rules.md`（§2 四阶段／§3 开关与合规清单／§4 三档定价＋机器可读块）；机器闸＝规则文件 JSON 块 ↔ 代码常量 ↔ 迁移种子**三方逐位一致**。

### 修改文件

```text
新增：
  docs/commercialization/rules/regional-partner-program-rules.md           （NEW：成文规则唯一处＋机器可读块）
  docs/commercialization/decisions/ADR-005-regional-commercialization-gate.md
  server/src/fde_api/commercial/regional_service.py                        （NEW：售卖闸＋四阶段＋按项目结算原语）
  server/migrations/versions/b3e8a6c2d4f7_commercial_g5_regional_partners.py
  server/tests/test_commercial_regional_partners.py                        （NEW：31 例）
修改：
  server/src/fde_api/commercial/models.py                                  （+4 表 + 常量）
  server/src/fde_api/commercial/routes.py                                  （+4 读/自证路由）
  server/src/fde_api/commercial/admin_routes.py                            （+5 治理写路由）
  server/tests/conftest.py                                                 （清理序：G5 四表先于 G4 两表）
  server/tests/test_migrations.py                                          （HEAD_REVISION b3e8a6c2d4f7 + 全集 56）
  docs/audit/v3-{route,database}-inventory.csv + v3-workbench-inventory.json（重生成：436/49/143/56）
  docs/architecture/archify-diagrams/architecture/{candidate.json,system-architecture.html,preview.png}
  AGENTS.md / CHANGELOG.md / docs/commercialization/phase-status.md（本节）
```

### 数据库迁移

迁移 `b3e8a6c2d4f7`（55→56 rev，additive 四表，单链单头）：`regional_partner_tiers`（三档定价目录，T1/T2/T3 CHECK＋金额>0＋席位形状 CHECK＋basis_reference 必填；**迁移播种三行**〔BP v4.0 基准〕）、`regional_partners`（伙伴主体：四阶段闭集＋申请自证戳＋升级书面依据三戳＋tier/exclusive；**五条 CHECK**：阶段闭集／前两阶段无独家权／观察档无升级留痕／服务档必有升级留痕／正式档须书面依据齐备；partner_code UNIQUE）、`regional_sale_gate`（**单行，播种 closed**：四条件各 uri+hash+signed_at＋开启人/时刻；三条 CHECK：状态闭集／条件原子性〔uri↔hash↔signed_at 同有同无〕／**opened ⇒ 四项齐备＋开启留痕非空**〔结构性排除缺件开门〕）、`regional_service_settlements`（一单一结关联行：FK 伙伴/项目/G3 科目行全 RESTRICT；ledger_entry_id UNIQUE 防重复计数）。**试运营数值零播种**（哨兵钉）。

### API / 权限 / API Catalog

- 读/自证面（4）：`POST /api/v1/commercial/regional-partners`（申请城市观察伙伴＝**当事人自证**，免费）、`GET /api/v1/commercial/regional-partners`（admin 全量／非 admin 只见本人）、`GET …/<id>`（含阶段注记派生——区域代理显示「暂不启用」；他人 404 不透 existence）、`GET /api/v1/commercial/regional-partner-tiers`（三档目录＋开关状态；**目录可见 ≠ 可签约**）。
- 治理写面（5，admin＋`confirm_password` 双闸）：`GET /api/v1/admin/commercial/regional-sale-gate`（开关读面：状态＋四条件登记态，只出指针）、`POST …/regional-sale-gate/conditions/<key>`（登记签署证据，**登记 ≠ 开启**）、`POST …/regional-sale-gate/open`（**关键流转**：四项齐备才可）、`POST …/regional-partners/<id>/promote`（阶段升级；**formal_partner 第一步过售卖闸**；regional_agent 显式拒绝）、`POST …/regional-partners/<id>/settlements`（按项目结算，引用 G3 科目行）。
- **全部不进 api_catalog**（商业治理面，AI 不可调用）——ENTRIES **94** 不变。

### 前端变化

无（纯服务端轮，桌面便携版不重打包；商业化桌面呈现面挂后续轮）。

### 测试命令与结果

- `pytest tests/test_commercial_regional_partners.py -q` → **31 passed**。
- 全量 `pytest -q -n 4 --dist loadfile`（**CI 同命令**）→ **2596 收集 = 2590 passed + 6 skipped，0 failed**（EXIT=0 / 16m13s；rebase 融合上游 #246/#247/#250/#249/#252/#254/#253 七笔（pytest 增量仅前三笔 +7／+12／+3，余四笔纯桌面或纯文档零 pytest 增量）；G4 基线 2543 收集 + V31-P1c +7 + N1 首跑补码 +12 + #250 +3 + 本轮 +31 ＝ 2596）。
- **PR CI server-tests 实测（run 42620729944）：2590 passed + 6 skipped（593.29s）；main run 42622618241 同值（406.34s）——与本地实测（16m13s）三轮一致**。
- `python scripts/check-python-types.py` → **OK：baseline 279 occurrences / 104 distinct，current 279**（本轮回退零新增；实施期两处 Optional 收窄当场归零）。
- `ruff check`（全部改动文件）→ All checks passed。
- **变异五连全转红→还原→绿**（字节级备份还原，sha256 终验一致）：M1 售卖闸直通（`require_sale_gate_open` 摘 closed 判定→正式档反例红）／M2 缺件开门（`open_sale_gate` 摘四项齐备校验→缺件用例红）／M3 区域代理放行（摘显式拒绝→不可进入用例红）／M4 前两阶段独家放行（摘 `exclusive_not_allowed`→独家拒绝用例红）／M5 结算张冠李戴放行（摘 `ledger_project_mismatch`→跨项目结算用例红；**首版变异 `False and X or Y` 运算符优先级让判定意外存活——加括号全判失效后转红**〔变异本身也要验真〕）。

### 安全检查

- 对外收费签约唯一闸门＝`require_sale_gate_open`（闸关 409 `regional_sale_gate_closed`，不回落不绕行）；源码扫描钉把「formal_partner 写点唯一且在过闸函数内」机械化（`test_no_signing_path_bypasses_gate_source_scan`）。
- 开闸/升级/条件登记/结算＝admin 门＋`confirm_password` 双闸（ADR-007 §2.1）；逐动作 `operation_events` 留痕（带 request_id，**密码不落事件**）。
- 申请城市观察伙伴＝当事人自证（免费，不走 admin 门）。
- 合规条件证据只存 `source_uri` 指针＋`content_hash` sha256 指纹＋签署时刻；伙伴真实身份材料零入库（只登伙伴代号＋区域名）。
- 「两店一年」是客观时间门槛，不可提前（其证据行即 qualification 条件；不预设「本模式是否构成特许经营」的法律结论——须律师意见）。
- 未读取无关密钥；`server/.env` 未入库；本轮零生产变更。

### 数据兼容与回滚

- additive 四表，**零既有表改列**（G4 两表/G3 科目层零触碰；opportunities 行零影响）。
- 回滚＝`alembic downgrade e7b2c4d9f1a3`（child-first：settlements → gate → partners → tiers）＋回滚镜像。
- 闸关闭态下区域模块读面/申请/升级（观察→服务）行为与既有商业面零交互；派单/项目/结算回归绿（ledger 26 例＋channel_guard 13 例＋G4 商机 23 例＋迁移全量 28 例）。

### 验收证据（任务书 §9 逐条）

| 验收项 | 证据 |
|---|---|
| 售卖能力默认关闭＋无代码路径可在开关未开启时对外收费签约（≥1 断言用例） | `test_gate_default_closed_lazy_seeded`＋`test_formal_partner_blocked_while_gate_closed`（409 `regional_sale_gate_closed`，含跳级路径）＋**源码扫描钉** `test_no_signing_path_bypasses_gate_source_scan`；变异 M1/M2 转红 |
| 四阶段与「暂不启用」标注正确落库 | `test_rule_document_slots_match_code_bidirectionally`（闭集双向闸＋agent.enabled=false＋note「暂不启用」）＋`test_regional_agent_is_not_enterable`（409）＋读面派生注记；变异 M3 转红 |
| 城市服务伙伴按项目结算，无固定年费 | `test_city_service_per_project_settlement`（一单一结＋重复 409）＋`test_tier_catalog_has_no_city_service_row`（目录只收 T1/T2/T3）＋`test_settlement_rejected_for_formal_stage`（两档互斥）＋`test_settlement_requires_matching_project`（张冠李戴 409）；变异 M5 转红 |
| 前两阶段不授予独家区域权 | `test_exclusive_territory_rejected_for_first_two_stages`（409）＋`test_db_check_first_two_stages_no_exclusive`（DB CHECK 在位）；变异 M4 转红 |
| 三档定价以 v4.0 为唯一基准 | `test_tier_seed_matches_rule_document`（文档块 ↔ `REGIONAL_TIER_SEED` ↔ 库行三方逐位）＋basis_reference 必填 CHECK |
| 试运营指标与首期金额本期不定数 | `test_trial_upgrade_metrics_unset`（规则槽显式 unset）＋`test_trial_example_numbers_absent_from_g5_code`（哨兵：示例数值不落 G5 域代码与迁移，数字边界正则防误伤档位金额） |
| 合规条件清单四项（备案/披露/冷静期/两店一年） | `test_opening_requires_all_four_conditions`（缺一 409 `gate_condition_missing`）＋`test_gate_opens_after_all_conditions`（齐备开闸＋重复开闸/开启后改条件 409）＋CHECK `ck_regional_sale_gate_opened_complete` |
| 高风险写双闸＋事件无密码 | `test_gate_condition_registration_requires_admin_and_password`＋`test_promotion_requires_evidence_and_admin_password`＋`test_gate_events_recorded_without_password`＋`test_promotion_event_carries_stage_transition` |
| 读面权限 | `test_partner_read_scopes`（本人/admin/他人 404/列表隔离）＋`test_partner_read_requires_auth`（401）＋`test_tier_catalog_visible_with_gate_status` |
| 治理面不进 api_catalog | `test_governance_face_not_in_api_catalog`＋路由审计 CSV（ENTRIES 94 不变） |
| 新增服务端逻辑有测试 | NEW `test_commercial_regional_partners.py` **31 例**＋变异五连全红→还原→绿 |

### 遗留问题

1. **T-12b（对外收费签约）本期不做**——闸关闭＋无签约服务原语；放行前置＝合规条件清单四项签署＋律师意见（「本模式是否构成特许经营」），留独立轮次。
2. 试运营升级指标与首期金额**待业务拍板**（任务书 §17 数值类）——配置槽显式 unset，成文后填实无需改结构。
3. 区域商业化桌面呈现面（伙伴列表/开关面板）挂后续桌面轮；GAP-15（AI 草稿采纳率埋点）与 ADR-004 §1.4 多子公司集团归并仍开放。

### 部署活体验证（合并后，2026-11-09 实测）

- 三镜像 rebuild 自本工作树（合并态 `28285e5` 干净树）＋`docker compose up -d --force-recreate`＋容器内 `alembic upgrade head`：**e7b2c4d9f1a3 → b3e8a6c2d4f7（head）** 活体落库。
- **复验①（活体路由与本轮口径一致）**：url_map＝**437 条**（436 口径路由＋1 静态；G4 同构 427→428）——regional 域 8 条规则串（9 路由中 POST/GET 共串）全数在位；`/api/v1/health/live` 200、`/api/v1/health/ready` 200（database ok／redis ok），四容器 healthy。
- **复验②（容器内 alembic current ＝ 本轮 head）**：`b3e8a6c2d4f7 (head)`。
- **复验③（容器镜像 ID ＝ 本工作树构建产物）**：api `1700cc82d4d8`／worker `697392faa3ac`／scheduler `87ce05aae023` 逐枚一致（同一构建时戳 2026-11-09 21:18:55）。
- 活库断言：`regional_partner_tiers` **3 行**（T1 29800.00/15 席/转赠 7、T2 59800.00/30 席/转赠 15、T3 98000.00/50 席/转赠 25，basis_reference＝「BP v4.0 附录 C（v4.0 终版，经蔡工拍板）」——与 `REGIONAL_TIER_SEED` 逐位一致）；`regional_sale_gate` **单行 closed**、四条件槽全空（登记 ≠ 开启）；`regional_partners` **0 行**／`regional_service_settlements` **0 行**；试运营指标零落库。

### 是否允许进入下一阶段

**允许进入 G6（企业空间与企业自助交付 T-06/T-08，任务书 §10）——前置已满足：PR #251 四绿（run 42620729944）＋合并态 main run 四绿（42622618241）＋部署活体绿（三项复验＋活库断言，见上）。**

---

## G4：商机归属与渠道保护（T-09）— 已完成

- 分支：`feat/commercial-g4-opportunity-attribution`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `9497b2c`（开工时）；合并前**两轮 rebase** 融合上游三笔——#240（AI 原生化 N2，迁移 `c4f7a2d9e1b6` 53→54 rev，+10 测试）、#239（V3.2 G9b 真机两闸轮，+4 测试）、#235（V31-P1b 大纪要分段抽取，+52 测试，零迁移零路由）⇒ 本轮迁移改挂 `c4f7a2d9e1b6` 之后，**55 rev 单链单头 `e7b2c4d9f1a3`**
- 状态：**completed**（PR #241 squash 合并 `ffed2e2`；PR run **42581664828** 四绿 ＋ **main run 42583246694 四绿**；**部署活体绿**——三镜像 rebuild 自本工作树 ＋ `alembic upgrade head` `c4f7a2d9e1b6`→`e7b2c4d9f1a3`，收口 PR：`feat/commercial-g4-closeout`）

### 目标

任务书 §8：立「报备→确认→保护→撮合→结算」七步链路，**规则数值本期不定数**（可配置结构＋缺省「未配置」，不留硬编码默认值）；已确认归属的商机企业后续直接注册**不得简单转移**；保护期**不得变成永久锁定企业**。

### 设计决策及理由（含 ADR 编号）

- **ADR-009**（`decisions/ADR-009-opportunity-attribution-and-channel-protection.md`，G4 成文）十项裁决：①七步状态机**引用既有** dispatch 交付包（⑥撮合）与 G3 科目层 `project_share` 行（⑦结算），不建第二套撮合/结算；②五个规则配置位（保护期长度／续期条件／客户自主选择权／争议处理机制／归属判定）迁移播种 **unset**＋机器闸（成文规则文件机器可读槽位块 ↔ 代码常量双向相等）；③保护期**三态可区分**（`unconfigured`/`active`/`expired`）且 `active` 必有到期时刻（CHECK 结构性排除永久锁定）；④保护期直签封堵＝**既有 `channel_guard` H1–H3 的扩展钩子**（惰性：无商机即 no-op／失败放行：查询异常不阻断立项／只认存储态 active 且未到期）；⑤归属不因企业自行注册而转移＝**结构性保证**（企业侧立项路径无商机行写路径）＋反例用例；⑥归属确认＝admin＋密码（关键流转），报备/撤回＝当事人自证（R2），企业确认＝admin＋线下书面依据（指针＋指纹）；⑦规则未配置 ⇒ **fail-closed**（409 `rule_not_configured`，不回落任何默认值）；⑧客户自主选择**不改归属**；⑨争议期间链路冻结（撮合/售前/结算 409 `opportunity_disputed`），争议处理机制未成文不可发起；⑩真实资料零入库（只登企业代号，材料只存指针＋sha256 指纹）。
- 成文规则唯一处：`docs/commercialization/rules/opportunity-attribution-rules.md`（§2 七步链路／§3 保护期三态／§8 配置位对照表＋机器可读槽位块）；承接 **ADR-007**（双闸与自证动作）与 G1 角色分层（报备人＝R2 创业者）。

### 修改文件

```text
新增：
  docs/commercialization/rules/opportunity-attribution-rules.md            （NEW：成文规则唯一处＋机器可读槽位块）
  docs/commercialization/decisions/ADR-009-opportunity-attribution-and-channel-protection.md
  server/src/fde_api/commercial/attribution_service.py                     （NEW：规则位＋七步链路写原语＋保护期读时派生）
  server/migrations/versions/e7b2c4d9f1a3_commercial_g4_opportunity_attribution.py
  server/tests/test_commercial_opportunity_attribution.py                  （NEW：23 例）
修改：
  server/src/fde_api/commercial/models.py                                  （+2 表 + 闭集常量）
  server/src/fde_api/commercial/routes.py                                  （+4 读/自证路由）
  server/src/fde_api/commercial/admin_routes.py                            （+12 治理写路由）
  server/src/fde_api/dispatch/channel_guard.py                             （+商机保护期直签封堵钩子，H1–H3 语义不变）
  server/tests/conftest.py                                                 （清理序：G4 两表先于 G3 五表/派单簇/users）
  server/tests/test_migrations.py                                          （HEAD_REVISION + 全集断言 54→55）
  docs/audit/v3-{route,database}-inventory.csv + v3-workbench-inventory.json（重生成）
  docs/architecture/archify-diagrams/architecture/*                        （口径数字同步 + preview 重出）
  AGENTS.md / CHANGELOG.md / docs/commercialization/phase-status.md（本节）
```

### 数据库迁移

迁移 `e7b2c4d9f1a3`（54→55 rev，additive 两表，单链单头）：`commercial_opportunity_rules`（五配置位：`protection_period_days`/`renewal_conditions`/`customer_choice`/`dispute_handling`/`attribution_criteria`；**迁移播种为 unset**，status ∈ unset/configured，days 与 criteria 互斥形状 CHECK）、`commercial_opportunities`（商机主体：status 八态闭集＋归属三戳（owner/by/at＋uri/hash）＋保护期五列（status/started/expires/renewal_count/renewed_at）＋撮合/客户选择/结算三引用（FK delivery_packages / commercial_revenue_ledger）＋争议/撤回留痕；**六条 CHECK**：状态闭集／保护期闭集／归属形状（owner⇔confirmed_at）／阶段需归属（presales·matched·settled ⇒ owner）／保护期窗口（active ⇒ started AND expires）／到期晚于起算）。rules 表先行（opportunities 的 rule 快照虽为 JSON 不引用，但 down 线 child-first 可逆）。

### API / 权限 / API Catalog

- 读/自证面（4）：`POST /api/v1/commercial/opportunities`（报备＝**R2 当事人自证**）、`GET /api/v1/commercial/opportunities`（admin 全量／本人只见报备·归属·售前相关）、`GET /api/v1/commercial/opportunities/<id>`（含保护期**派生态**与「企业是否已自助注册」**派生事实**）、`POST /api/v1/commercial/opportunities/<id>/withdraw`（报备人自证，settled 不可撤回）。
- 治理写面（12，admin＋`confirm_password` 双闸）：`GET/POST /api/v1/admin/commercial/opportunity-rules[/<key>]`（规则位读＋配置/清空，须书面依据）、`POST …/opportunities/<id>/enterprise-confirm`（企业确认，代录线下书面答复）、`/attribution`（归属确认）、`/attribution/reassign`（改派，**被 `attribution_criteria` 闸 fail-closed**）、`/protection`（设定保护期，长度取 `protection_period_days` 配置位）、`/protection/renew`（续期，被 `renewal_conditions` 闸）、`/presales`（售前，默认归属人）、`/match`（撮合，交付包须同企业代号）、`/customer-choice`（客户自主选择，被 `customer_choice` 闸、**不改归属**）、`/settlement`（结算，须引用 `project_share` 科目行且未作废）、`/dispute`（发起争议，被 `dispute_handling` 闸、争议中链路冻结）。
- **全部不进 api_catalog**（商业治理面，AI 不可调用）——ENTRIES **94** 不变。

### 前端变化

无（纯服务端轮，桌面便携版不重打包；商业化桌面呈现面挂后续轮）。

### 测试命令与结果

- `pytest tests/test_commercial_opportunity_attribution.py -q` → **23 passed**。
- 全量 `pytest -q -n 4 --dist loadfile`（**CI 同命令**）→ **2543 收集 = 2537 passed + 6 skipped，0 failed**（EXIT=0 / 8m39s；G3 轮基线 2454 收集 + AI 原生化 N2 +10 + #239 +4 + #235 +52 + 本轮 +23 ＝ 2543）。
- **PR CI server-tests 实测**（run 42581664828）：**2537 passed + 6 skipped**（522.82s）；**main run 收口**（合并态 `ffed2e2`，run 42583246694）：**2537 passed + 6 skipped**（568.87s）——与本地 CI 同命令实测逐位一致；desktop 82 文件 **966 passed**（见口径行 vitest 校正注记）。
- `python scripts/check-python-types.py` → **OK：baseline 279 occurrences / 104 distinct，current 279**（实施期补一处测试断言形状〔re.search Optional 收窄〕后归零，无新增）。
- `ruff check`（全部改动文件）→ All checks passed。
- **变异五连全转红→还原→绿**（字节级备份还原，sha256 终验一致）：M1 归属不自动易主失效（企业注册派生事实恒 False→反例用例红）／M2 保护期未配置也封堵（守卫放宽为任意非 revoked 态＋绕过到期派生→反例用例红）／M3 规则未配置仍放行（`require_rule_configured` 直通→规则闸用例红）／M4 争议不冻结（`_reject_when_disputed` 摘除→争议冻结用例红）／M5 归属可静默改写（`attribution_already_confirmed` 摘除→防改写用例红）。

### 安全检查

- 关键流转（企业确认/归属确认/改派/保护期/续期/售前/撮合/客户选择/结算/争议/规则配置）＝admin 门＋`confirm_password` 双闸（ADR-007 §2.1）；逐动作 `operation_events` 留痕（带 request_id，**密码不落事件**）。
- 报备/撤回＝当事人自证（ADR-007 §2.4；报备仅 R2）；撤回**不动归属事实**（审计可回查）。
- 证据只存 `source_uri` 指针＋`content_hash` sha256 指纹；真实企业名/联系人/凭证零入库（只登企业代号）。
- 归属改写无旁路：再确认 409 `attribution_already_confirmed`；转移唯一路径 `reassign` 且被 `attribution_criteria` 规则闸 fail-closed（本期不可用＝**本期无转移路径**）。
- 企业侧立项路径**无商机行写路径**（结构性保证）；保护期直签封堵**失败放行**（渠道秩序诉求，不是资金安全闸）；派单线（H1–H3）语义零变化。
- 未读取无关密钥；`server/.env` 未入库；本轮零生产变更。

### 数据兼容与回滚

- additive 两表，**零既有表改列**（`delivery_settlements` 列集合逐位比对，结构钉）。
- 回滚＝`alembic downgrade c4f7a2d9e1b6`（子表先行：opportunities → rules）＋回滚镜像。
- 保护期判定惰性（库内无商机行时行为逐位不变）；G1–G3 商业面与派单回归绿（commercial+dispatch+projects 组合 154 例通过）。

### 验收证据（任务书 §8 逐条）

| 验收项 | 证据 |
|---|---|
| 七步链路完整（§2 七步） | `test_seven_step_chain_completes`（报备→企业确认→归属→保护期→售前→撮合→结算全链 200）＋ `test_step_order_is_enforced`（跳步 409 `invalid_opportunity_state`） |
| 「归属确认后企业自行注册，商机不自动易主」反例 ≥1 | `test_attribution_not_transferred_when_enterprise_registers_directly`（保护期未配置 ⇒ 企业可直签立项；归属人/确认戳/状态/保护期逐项不变＋`enterprise_registered` 派生事实可见）；变异 M1/M2 转红 |
| 保护期为空＝「未配置」且三态可区分 | `test_protection_three_states_are_distinguishable`（unconfigured→直签放行／active→封堵／backdate 到期→读时派生 expired→放行）＋ `test_protection_status_values_are_closed` |
| 保护期 active 封堵直签立项（渠道保护落点） | `test_active_protection_blocks_direct_project_creation`（422 `opportunity_protection_active`＋审计事件 `opportunity_protection_blocked`）；直签封堵不得变永久锁定（CHECK active⇒expires） |
| 规则文件与代码配置位一一对应 | `test_rule_document_slots_match_code_bidirectionally`（机器可读槽位块 ↔ `OPPORTUNITY_RULE_KEYS`/`VALUE_KINDS` 双向相等＋库行全 unset）＋ `test_rule_slots_are_unset_by_default` |
| 规则数值不定数、无硬编码默认值 | 五配置位迁移播种 unset＋`test_actions_gated_by_unconfigured_rules`（续期/客户选择/争议/改派 409 `rule_not_configured`）；变异 M3 转红 |
| 规则配置须书面依据 | `test_rule_configuration_requires_evidence`（缺 URI/指纹 400；配置后动作放行见 `test_actions_enabled_after_rules_configured`） |
| 客户自主选择不改归属 | `test_actions_enabled_after_rules_configured`（选择生效且归属人不变；另证续期计数＋改派显式留痕） |
| 撮合不张冠李戴／结算引用既有分账 | `test_match_requires_same_enterprise_package`（409 `package_enterprise_mismatch`）＋ `test_settlement_requires_project_share_entry`（409 `ledger_subject_mismatch`） |
| 争议期间链路冻结 | `test_dispute_freezes_downstream_steps`（409 `opportunity_disputed`）；变异 M4 转红 |
| 归属人工确认、不得静默改写 | `test_attribution_cannot_be_silently_overwritten`（409 `attribution_already_confirmed`）；变异 M5 转红 |
| 报备＝R2；治理写双闸；事件无密码 | `test_report_requires_r2_role`＋`test_admin_actions_require_admin_and_password`＋`test_attribution_event_recorded_without_password` |
| 读面权限 | `test_read_scope_and_permissions`（本人／admin 全量／他人 403／未认证 401）＋ `test_withdraw_only_by_reporter` |
| 治理面不进 api_catalog | `test_governance_face_not_in_api_catalog`＋路由审计 CSV（ENTRIES 94 不变） |
| 新增服务端逻辑有测试 | NEW `test_commercial_opportunity_attribution.py` **23 例**＋变异五连全红→还原→绿 |

### 遗留问题

1. 五个规则位**数值仍待业务拍板**（任务书 §17 数值类）：保护期长度／续期条件／客户自主选择权／争议处理机制／归属判定——配置结构＋成文规则文件已就位，附书面依据配置即生效，无需改结构。
2. 商机保护期封堵提示文案与派单池内判定的先后语序，随数值拍板一并复核。
3. GAP-15（AI 草稿采纳率埋点）仍开放；ADR-004 §1.4 多子公司集团归并仍待法务。

### 部署活体验证（合并后）

- 三镜像 rebuild 自本工作树干净树＋`docker compose up -d --force-recreate`；容器内 `alembic upgrade head` 实跑 `c4f7a2d9e1b6 -> e7b2c4d9f1a3`，`alembic current` ＝ **`e7b2c4d9f1a3 (head)`**。
- **活体断言三项全绿**：①容器内 `create_app` url_map **428** 条（commercial **43**／admin commercial **27**／opportunity 14＋12，蓝图 **49**）与本轮口径一致；②容器 `alembic current` ＝ 本轮 head `e7b2c4d9f1a3`；③api/worker/scheduler 三容器镜像 ID ＝ 本工作树构建产物（`c7fba822aef1…`／`649da2c7ab3b…`／`113dbf0c0e4a…`，container==image）。
- 活库断言：G4 两表结构正确（opportunities 34 列/6 CHECK；rules 11 列/5 CHECK），五规则槽全 **unset**，`commercial_opportunities` **0 行**，`delivery_settlements` 仍 20 列（零既有表改列）；`/api/v1/health/ready` 200 ＋ `/live` 200，四容器 healthy。

### 是否允许进入下一阶段

**允许进入 G5（区域合作商能力建设 T-12a，**不含 T-12b**，任务书 §9）**——前置已全部满足：PR #241 四绿（run 42581664828）＋合并态 main run 四绿（run 42583246694）＋部署活体绿（见上节）。
T-12b（对外收费签约）本期不做：售卖能力默认关闭、开关绑定合规条件清单（《商业特许经营管理条例》七/八/十二/二十一条＋披露办法第四条四项）；「两直营店经营满 1 年」为客观时间门槛不可提前。

---

## G3：订阅、培训与科目结算（T-10 / T-11 / T-13）— 已完成

- 分支：`feat/commercial-g3-revenue-ledger`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `e06ae8d`（开工时）；合并前融合上游 #231／#232／AI 原生化差距评估 v1.1（冲突仅 AGENTS.md 与 CHANGELOG.md，两边全留；融合后结构口径逐位不变）
- 状态：**completed**（PR #234 squash 合并 `f65f874`；PR run 42543224303 四绿 + **main run 42544563159 四绿**；**部署活体绿**——三镜像 rebuild 自本工作树 + `alembic upgrade head` `b3e7c9d1a5f2`→`d5f9a3c7e1b4`）

### 目标

任务书 §7：把席位、培训、认证、陪跑与收入科目分离落库。

### 设计决策及理由（含 ADR 编号）

- **ADR-008**（`decisions/ADR-008-revenue-ledger-and-seat-billing.md`，G3 成文）：收入科目层独立新建（不向 `delivery_settlements` 加列）；三类科目分别记账可分别核对；六名目只定义归属；分成比例只落结构不落数；席位份额复用 `seat_shares_for`；首单扣费闸落**服务层**（验收前不触发／未书面选定不得扣费）；扣费方式＝当事人自证（他人/admin 不得代选定）；认证挂模拟考核且通过线未设即不判定通过；陪跑期限结构先落数值待定；缺省不可用（认证费未配即不可收款）。
- 承接 **ADR-003** §2.1–§2.5（科目层独立、份额复用、比例不落数、六名目只定义归属、科目层写路径属高风险写）与 **ADR-007**（admin 门＋密码确认双闸、自我动作例外、治理面不进 api_catalog）。

### 修改文件

```text
新增：
  docs/commercialization/decisions/ADR-008-revenue-ledger-and-seat-billing.md
  server/src/fde_api/commercial/ledger_service.py        （NEW：科目层＋费用配置位＋分成结构）
  server/src/fde_api/commercial/billing_service.py        （NEW：首单扣费闸＋扣费选定＋认证挂考核）
  server/migrations/versions/d5f9a3c7e1b4_commercial_g3_revenue_ledger.py
  server/tests/test_commercial_revenue_ledger.py         （NEW：26 例）
修改：
  server/src/fde_api/commercial/models.py                （+5 表 + 闭集常量）
  server/src/fde_api/commercial/routes.py                （+7 读/自证路由）
  server/src/fde_api/commercial/admin_routes.py          （+7 治理写路由）
  server/src/fde_api/commercial/service.py               （陪跑期限挂钩 G3 配置位）
  server/tests/conftest.py                               （清理序：G3 五表先于派单簇与 users）
  server/tests/test_migrations.py                        （HEAD_REVISION + 全集断言 52→53）
  docs/audit/v3-{route,database}-inventory.csv + v3-workbench-inventory.json（重生成）
  docs/architecture/archify-diagrams/architecture/*      （口径数字同步 + preview 重出）
  AGENTS.md / CHANGELOG.md（本节）
```

### 数据库迁移

迁移 `d5f9a3c7e1b4`（52→53 rev，additive 五表）：`commercial_split_rules`（分成比例结构：角色 R1–R4 × 项目类型 → `ratio_bp`，**本期零行**）、`commercial_fee_configs`（认证费金额／陪跑期限／认证通过线三个配置位，**迁移播种为 unset**）、`commercial_deduction_elections`（扣费方式书面选定；部分唯一索引＝一人一条 elected）、`commercial_certification_records`（认证挂模拟考核）、`commercial_revenue_ledger`（**收入科目层**）。单链单头，无双头。

### API / 权限 / API Catalog

- 读面（7）：`GET /api/v1/commercial/packages`、`GET /api/v1/commercial/revenue-ledger`、`GET /api/v1/commercial/revenue-ledger/reconciliation`、`GET /api/v1/commercial/revenue-ledger/<entry_id>`、`GET /api/v1/commercial/deduction-election`、`GET /api/v1/commercial/certification-records/<user_id>`。
- 自证面（1）：`POST /api/v1/commercial/deduction-election`（**只认 actor 本人**，payload 里的 `user_id` 无效——杜绝代选定）。
- 治理写面（7，admin＋密码确认双闸）：`POST /api/v1/admin/commercial/revenue-ledger`、`POST /api/v1/admin/commercial/first-order-fee`、`POST /api/v1/admin/commercial/fee-configs/<key>`、`GET /api/v1/admin/commercial/fee-configs`、`GET /api/v1/admin/commercial/split-rules`、`POST /api/v1/admin/commercial/split-rules`、`POST /api/v1/admin/commercial/certification-records`。
- **全部不进 api_catalog**（商业治理面，AI 不可调用）——`api_catalog` ENTRIES **94** 不变。

### 前端变化

无（纯服务端轮，桌面便携版不重打包；商业化桌面呈现面挂后续轮）。

### 测试命令与结果

- `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_commercial_revenue_ledger.py -q` → **26 passed**。
- 全量 `pytest -q -n 4 --dist loadfile`（**CI 同命令**）→ **2454 收集 = 2448 passed + 6 skipped，0 failed**（EXIT=0，8m16s；G2 轮基线 2402 收集 + 本轮 +26 + 融合上游 #231 的 26 ＝ 2454）。
- **PR #234 CI run 42543224303 server-tests 实测 2448 passed + 6 skipped**（569.95s）——与本地同值。
- **合并态 main run 42544563159 四绿**（合并态权威）：server-tests 实测 **2448 passed + 6 skipped**（359.40s）／desktop 2m10s／secrets-scan 12s／pseudonymization 53s。
- `python scripts/check-python-types.py` → **OK：baseline 279 occurrences / 104 distinct，current 279**（无新增）。
- `ruff check`（改动文件）→ All checks passed。
- **变异十连全转红→还原→绿**（任务书 §12.10）：M1 不重复收判定整体失效／M2 未选定方案仍扣费／M3 验收前仍扣费／M4 项目分成按比例重算（不引用分账）／M5 名目归属校验失效／M6 关联对象必填失效／M7 通过线未设也判通过／M8 书面证据指纹闸失效／M9 认证费缺省可收款／M10 陪跑期限未配置也落默认天数。

### 安全检查

- 高风险写（记账／首单扣费／配置位／分成登记／认证判定）＝admin 门＋`confirm_password` 双闸；逐动作 `operation_events` 留痕（带 request_id，**密码不落事件**）。
- 书面证据只存 `source_uri` 指针 + `content_hash` sha256 指纹；证据原件不进仓、不进库。
- 扣费方式选定＝当事人自证（ADR-007 §2.4），**admin 不得代选定**；证据缺指针或指纹非 sha256 一律 400。
- 未读取无关密钥；`server/.env` 未入库；客户资料零触碰；本轮零生产变更。

### 数据兼容与回滚

- additive 五表，**零既有表改列**（`delivery_settlements` 列集合逐位比对，结构钉）。
- 回滚＝`alembic downgrade b3e7c9d1a5f2`（子表先行：ledger → certification_records → deduction_elections → fee_configs → split_rules）+ 回滚镜像。
- 科目层与既有收款台账不双写：金额来源为配置位／关联收款实收额／线下约定金额三者之一。

### 验收证据（任务书 §7 逐条）

| 验收项 | 证据 |
|---|---|
| 「套餐含席位不重复收」反例用例（含 L2／L3／L0 三种组合） | `test_package_included_seat_is_not_charged_again[bootcamp_practical/bootcamp_mentorship]`（409 `seat_fee_already_included` ＋ **席位费科目行恒 1 行**）＋ `test_first_order_fee_applies_for_candidate_without_package`（无含席位套餐者扣 3980 且席位激活） |
| 首单扣费在验收前不触发 | `test_first_order_fee_blocked_before_acceptance`（409 `acceptance_not_passed`，零行）；变异 M3 转红 |
| 未选定方案时不得扣费 | `test_first_order_fee_blocked_without_election`（409 `deduction_method_not_selected`，零行）；变异 M2 转红 |
| 三类科目分别可查、可对账 | `test_three_subject_types_separately_queryable_and_reconcilable`（按 `subject_type` 各查各的＋对账分桶金额逐位吻合） |
| 新增服务端逻辑有测试 | NEW `test_commercial_revenue_ledger.py` 26 例；变异十连全转红→还原转绿 |
| 新增路由有权限测试 | `test_ledger_read_scope_and_permissions`（本人／admin／他人 403／未认证 401）＋ `test_governance_writes_require_admin_and_password`（非 admin 403／缺密码 400／错密码 403） |
| 席位份额复用 `seat_shares_for` | `test_project_share_references_settlement_without_recompute`（快照 ≡ `seat_shares_for`；金额 ≡ 分账 `delivery_amount`；不一致金额 409）；变异 M4 转红 |
| 不在 `delivery_settlements` 加列 | `test_delivery_settlements_keeps_its_original_columns`（列集合逐位比对） |
| 认证费金额本期不设→缺省不可收款 | `test_certification_fee_cannot_be_charged_before_configured`（409 `fee_not_configured`）；变异 M9 转红 |
| 认证挂模拟考核、通过线本期不设 | `test_certification_without_threshold_stays_pending`（`pending_threshold`、认证状态不变）＋ `test_certification_after_threshold_configured`；变异 M7 转红 |
| 陪跑期限结构先落、数值待定 | `test_mentoring_period_structure_is_pending_by_default`；变异 M10 转红 |

### 遗留问题

1. 认证费金额、陪跑周期、认证通过线、分成比例**仍待业务拍板**（任务书 §17 数值类）——配置位与结构已就位，填实数即可，无需改结构。
2. 方案 B（年度分期）的周期与算式未实现（fail-closed 拒绝），随数值拍板一并落地。
3. 商机归属与渠道保护本体 → 归 G4。
4. GAP-15（AI 草稿采纳率埋点）仍开放——ADR-007 §2.5 的复审触发器依赖它。

### 部署活体验证（合并后）

- 三镜像（api/worker/scheduler）自本工作树 `D:/test/fde-wt-g1` 重建；构建树与 `fork/main` `f65f874` **逐位一致**（`git diff fork/main <branch>` 为空）⇒ 部署的就是合并态代码。
- `docker compose -p fde-workbench up -d` 后三容器 **healthy**（api/worker/scheduler）。
- `alembic upgrade head`：`b3e7c9d1a5f2` → **`d5f9a3c7e1b4` (head)**；`alembic current` ＝ `d5f9a3c7e1b4 (head)`。
- 活体断言：`url_map` **412** 条（审计口径 411，+1 恒定差）；**commercial 27 条**（G1 七 ＋ G2 六 ＋ G3 十四，含 G3 新增的 `packages`／`revenue-ledger`×3／`deduction-election`×2／`certification-records`×2／`fee-configs`×2／`split-rules`×2／`first-order-fee`）。
- G3 五表齐备：`commercial_revenue_ledger` 28 列／`commercial_split_rules` 11 列／`commercial_fee_configs` 12 列／`commercial_deduction_elections` 10 列／`commercial_certification_records` 13 列；**CHECK 全在**（科目层 9 条、配置位 5 条、分成结构 4 条、选定 2 条、认证记录 2 条）。
- **五表零行**（`commercial_fee_configs` 3 行为迁移播种的 **unset** 配置位；其余四表 0 行——无客户数据）；`commercial_split_rules` **零行**（本期比例不定数）。
- **结构钉活体复核**：`delivery_settlements` 列集合仍为原 **20 列**（`acceptance_passed_at`／`base_amount`／`city_amount`／`created_at`／`delivery_amount`／`id`／`package_id`／`paid_at`／`paid_proof_source_uri`／`platform_amount`／`region_amount`／`seat_*`×4／`settlement_key`／`snapshot_hash`／`status`／`updated_at`／`withholding_tax`）——**零加列**。
- `/api/v1/health/ready` 与 `/api/v1/health/live` 均 **200**。
- **并发覆盖复验（跨会话共享部署）**：部署后约 30 分钟，另一条线的会话从自己的 worktree 重建并 `up -d`，把 api 容器换成了**旧代码**（活体 `url_map` 掉回 398、commercial 掉回 13 条、容器内 `alembic current` 报 「Can't locate revision」、`/app/migrations` 挂载指向别人的 worktree）。**处置**：从本工作树重建三镜像 （api 镜像 ID `84193bb29335`）＋ `up -d --force-recreate` 三容器 → **复验全绿**（`url_map` 412／commercial 27／`alembic current` ＝ `d5f9a3c7e1b4 (head)`／容器 working_dir 与 migrations 挂载均回本工作树／三容器 healthy／ready+live 200）。**教训**：镜像 tag 与 migrations 挂载源是跨会话共享资源，部署后必须复验「活体路由数 ＋ 容器内 alembic current ＋ 容器镜像 ID」三项（已写入 AGENTS「工作流与陷阱」节）。

### 是否允许进入下一阶段

**允许进入 G4（商机归属与渠道保护，T-09，任务书 §8）**——前置已全部满足：PR 四绿 ＋ 合并态 main run 四绿 ＋ 部署活体绿。
ADR-005（区域商业化闸）仍归 G5，不预支；GAP-15（AI 草稿采纳率埋点）仍开放——ADR-007 §2.5 的复审触发器依赖它。

---

## G2：免费额度与三个体验入口（T-07）— 已完成

- 分支：`feat/commercial-g2-free-quota`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `7c32736`（开工时）→ 合并后 fork/main `b0fd5fc`
- 状态：**completed**（PR #228 squash 合并 `b0fd5fc`；PR run 42505691928 四绿 + **main run 42506701371 四绿**；**部署活体绿**——三镜像 rebuild 自本工作树 + `alembic upgrade head` `e9c4a1f7b3d2`→`b3e7c9d1a5f2`）

### 目标

任务书 §6：免费只到一次完整业务诊断，且额度按企业主体计。

### 设计决策及理由（含 ADR 编号）

- **ADR-004**（`decisions/ADR-004-free-quota-subject-identity.md`）：主体认定键＝统一社会信用代码规范化（mod-31 校验位）；一次一主体、长期有效不重置；换账号不重置；多子公司保守默认＝不分别（法务待确认）；完成判据＝六项齐备＋企业确认；免费边界七项；三档纯描述；两档体验上限；三入口隔离注册表＋域闸。
- **ADR-007**（`decisions/ADR-007-human-confirmation-default.md`）：关键流转默认人工确认——admin 门＋密码确认双闸；AI 无直写入口（治理面不进 api_catalog）；人工接管沿 `handoff_run` 既有模式；自我动作例外（企业自证）；实测后复审触发器。

### 修改文件

```text
新增：
  docs/commercialization/decisions/ADR-004-free-quota-subject-identity.md
  docs/commercialization/decisions/ADR-007-human-confirmation-default.md
  server/src/fde_api/commercial/quota_service.py        （NEW：额度服务层）
  server/migrations/versions/b3e7c9d1a5f2_commercial_g2_free_quota.py
  server/tests/test_commercial_enterprise_quota.py       （NEW：13 例）
修改：
  server/src/fde_api/commercial/models.py                （+两表+常量）
  server/src/fde_api/commercial/routes.py                （+4 读/当事人路由）
  server/src/fde_api/commercial/admin_routes.py          （+2 治理写路由）
  server/tests/conftest.py                               （清理序）
  server/tests/test_migrations.py                        （HEAD+全集断言）
  server/tests/test_commercial_entitlements.py           （downgrade 改显式父版本）
  docs/audit/v3-{route,database}-inventory.csv + v3-workbench-inventory.json（重生成）
  AGENTS.md / CHANGELOG.md（本节）
```

### 数据库迁移

迁移 `b3e7c9d1a5f2`（51→52 rev，additive 两表）：`enterprise_quota_subjects`（PK=subject_key 18 位）＋ `enterprise_free_quota`（PK=subject_key 一主体一份，四条 CHECK 联锁）。单链单头，无双头。

### API / 权限 / API Catalog

- 读面：`GET /api/v1/commercial/enterprise-quota/<subject_key>`（本人/admin，他人 403，未知 404）、`POST .../start`、`POST .../confirm`、`GET /api/v1/commercial/free-diagnosis-profile`。
- 治理写面（admin＋密码确认双闸）：`POST /api/v1/admin/commercial/enterprise-quota/grant`、`POST /api/v1/admin/commercial/enterprise-quota/<subject_key>/complete`。
- **全部不进 api_catalog**（商业治理面，AI 不可调用）——`api_catalog` ENTRIES **94** 不变。

### 前端变化

无（纯服务端轮，桌面便携版不重打包；商业化桌面呈现面挂后续轮）。

### 测试命令与结果

- `PYTHONPATH=src ./.venv/Scripts/python.exe -m pytest tests/test_commercial_enterprise_quota.py -q` → **14 passed**。
- 全量 `pytest -q -n 4 --dist loadfile` → **2402 收集 = 2396 passed + 6 skipped，0 failed**（EXIT=0，12m52s）；**PR #228 CI run 42503516295 server-tests 实测 2396 passed + 6 skipped（409.81s）——与本地同值**（架构评估十项实施轮基线 2388 收集 + 本轮 +14）。
- `python scripts/check-python-types.py` → **OK：baseline 279 occurrences / 104 distinct，current 279**（无新增）。
- `ruff check`（改动文件）→ All checks passed。
- **变异六连全转红→还原→绿**（任务书 §6「至少 1 条变异用例证明『额度按账号计』的实现会转红」）：M1 换账号可重绑／M2 授予幂等键含账号／M3 放宽完成判据／M4 触限判定放宽／M5 三入口隔离失效／M6 写路径不取行锁重读（并发额度可被重发）。

### 安全检查

- 高风险写＝admin 门＋`confirm_password` 双闸；逐动作 `operation_events` 留痕（带 request_id，**密码不落事件**）。
- 企业确认只认绑定账号本人，admin 不得代确认。
- 主体键校验位本地可验证；不存客户真实业务内容（只存判据账与主体代号键）。
- 未读取无关密钥；`server/.env` 未入库；客户资料零触碰。

### 数据兼容与回滚

- additive 两表，零既有表改列；`downgrade` 子表先行（free_quota → subjects）可逆。
- 回滚＝`alembic downgrade e9c4a1f7b3d2` + 回滚镜像；既有商业化数据不与既有域混写，无双写风险。

### 验收证据（任务书 §6 逐条）

| 验收项 | 证据 |
|---|---|
| 换账号不重置额度（同一主体再注册不得获得第二次） | `test_start_binds_account_blocks_other_accounts_and_restart`（换账号 409 `quota_bound_to_other_account`）＋`test_grant_idempotent_per_subject_never_second_row`（行数恒 1）＋`test_start_race_serializes_on_row_lock`（并发启动被行锁串行化）；变异 M1/M2/M6 转红 |
| 六项交付物未齐备不算完成 | `test_completion_requires_exactly_six_true`（五键 409 点名／一 False 409／多余键 400）；变异 M3 转红 |
| 六项不免费内容不进入免费流程 | `FREE_EXCLUSIONS` 七项常量＋闭集拒绝（多余键 400）；`test_free_diagnosis_profile_meta` |
| 创业者不能取到企业真实商机 | `test_three_trial_entries_isolated`（非企业入口取 real_business 403）；变异 M5 转红（商机归属本体归 G4） |
| 交付者触及上限即受限 | `test_experience_limit_exceeded_at_cap`（used≥cap 409）；变异 M4 转红 |
| 至少 1 条变异用例证明「额度按账号计」会转红 | M1／M2 双条，均转红→还原转绿 |

### 部署活体验证（合并后）

- 三镜像（api/worker/scheduler）自本工作树 `D:/test/fde-wt-g1` 重建；`docker compose -p fde-workbench up -d` 后三容器 healthy。
- `alembic upgrade head`：`e9c4a1f7b3d2` → **`b3e7c9d1a5f2`**（G2 additive 两表）。
- 活体断言：`alembic current` = `b3e7c9d1a5f2`；`url_map` **398** 条（审计口径 397，+1 恒定差）；**commercial 13 条**（G1 七条 + G2 六条）；`enterprise_quota_subjects` 6 列 / `enterprise_free_quota` 12 列；四条 CHECK 齐备（`state`／`bound_shape`／`completed_shape`／`confirm_requires_completed`）；两表**零行**（无客户数据）。
- `/api/v1/health/ready` 与 `/api/v1/health/live` 均 **200**。

### 遗留问题

1. 主体认定口径待法务最终确认（ADR-004 状态行已注）。
2. 体验上限消费接线、三档分流人工判定留痕、注册面收 USCC → 归 G6。
3. 商机归属与渠道保护本体 → 归 G4。
4. GAP-15（AI 草稿采纳率埋点）仍开放——ADR-007 §2.5 的复审触发器依赖它。

### 是否允许进入下一阶段

**允许进入 G3（订阅、培训与科目结算，T-10/T-11/T-13）**——前置已全部满足：PR 四绿 ＋ 合并态 main run 四绿 ＋ 部署活体绿。
ADR-005（区域商业化闸）仍归 G5，不预支；GAP-15（采纳率埋点）仍开放。

---

## G1：权益四分与角色分层（T-04、T-05）— 已完成

- 分支：`feat/commercial-g1-entitlements`；合并：**fork/main `f186342`**（PR #217）
- 目标：任务书 §5。四权益独立建模；角色分层 R1–R4；对外 L 编号唯一换算入口；席位激活与 `fde_profiles.status` 的单向同步。
- 裁决落地：**ADR-001**（角色分层 vs 交付能力等级正交、`fde_profiles.level` 零改动保护清单）、**ADR-002**（四权益独立、不覆盖 `fde_profiles.status`、高风险写双闸）、**ADR-006**（R1–R4 命名与六套 level 同名家族区分）。
- 改动：`commercial_entitlements`＋`training_entitlements` 两表；迁移 `e9c4a1f7b3d2`（50→51 rev）；+7 路由（384→391）、+2 蓝图（47→49）——全不进 api_catalog（ENTRIES 94 不变）。
- 测试：NEW `test_commercial_entitlements.py` 15 例；变异双验证红→还原→绿。
- 口径：CI 实测 **pytest 2360 = 2345 + 15 + 6 skipped**；mypy 279；路由 391／蓝图 49／表 130／51 rev 单头 `e9c4a1f7b3d2`。
- 部署：合并后 rebuild 三镜像＋`alembic upgrade head`（`e9c4a1f7b3d2`），`/health/ready` 与 `/live` 200，三容器 healthy。

---

## G0：基线审计 + 四个歧义 ADR — 已完成

- 分支：`feat/commercial-g0-audit`；合并：**fork/main `28f55fd`**（PR #216）
- 基线 SHA：`eee317c`（fork/main，PR #214 合并态；任务书自述基线 `858e090` 已被其后 8 个合并超越，本轮以现测为准）
- 开始/完成时间：2026-11-08 16:35 开工 / 2026-11-08 同日收口（以 PR 合并时间为准）

### 本阶段目标

按任务书 §14 总提示词第 3 条：「第一个 Goal 只做 G0 基线审计 + 四个歧义 ADR，不改业务代码。」覆盖任务书 §2 G0 必做项 1–8。

### 真实代码定位

见 `00-baseline-audit.md` §B–§F（逐行锚点实测）。要点：任务书 §2 表格全部属实；权益四字段全库零命中；派单/席位/结算/降级链结构完备但活库零使用。

### 设计决策及理由（含 ADR 编号）

- **ADR-001**（`decisions/ADR-001-role-vs-delivery-level.md`）：角色分层与交付能力等级正交；`fde_profiles.level` 零改动保护；R1–R4 不落 L 编号；含 level 依赖全集与测试影响面。
- **ADR-002**（`decisions/ADR-002-entitlement-model.md`）：四权益独立建模方向；不覆盖 `fde_profiles.status`；`certification_status` 与 `fde_level_evidence` 并存。
- **ADR-003**（`decisions/ADR-003-revenue-ledger-vs-dispatch-settlement.md`）：收入科目层独立于 `delivery_settlements`；份额算法复用 `seat_shares_for`；比例不落数。
- **ADR-006**（`decisions/ADR-006-naming-convention-r1r4.md`）：R1–R4 命名规范；六套「level 同名家族」区分；凡引用 L 编号必须写三要素。
- ADR-004 / ADR-005 / ADR-007 分别归 G2 / G5 / G1 设计轮成文（**ADR-004/007 已于 G2 成文**；ADR-005 仍归 G5）。

### 修改文件

全部为新增文档（零业务代码、零迁移、零路由）：

```text
docs/commercialization/
  00-baseline-audit.md      （基线审计：§B 逐项核验、口径七项现测、活库智能化实测）
  00-gap-register.md        （15 条缺口登记 + Goal 矩阵）
  phase-status.md           （本文件）
  decisions/
    ADR-001-role-vs-delivery-level.md
    ADR-002-entitlement-model.md
    ADR-003-revenue-ledger-vs-dispatch-settlement.md
    ADR-006-naming-convention-r1r4.md
```

### 数据库迁移

零迁移（基线维持 49 rev，head `d5a8c2f4b7e1`）。

### API / 权限 / API Catalog

零改动（路由 384、api_catalog ENTRIES 94 不变）。

### 前端变化

无（桌面便携版重打包挂账不适用于本轮）。

### 测试命令与结果

- 本轮纯文档，未跑新测试；基线口径引用 CI main run **42461768715**（#214，2026-11-08）job log 实测：
  - server-tests：**2333 passed + 6 skipped**（11m28s，job 128672384334）
  - desktop：**951 passed / 81 文件**（vitest，job 128672384201）
  - secrets-scan / pseudonymization 均绿。
- mypy 基线 279 行未动（`wc -l server/mypy-baseline.txt` 现测）。

### 安全检查

- 活库查询全部只读 SELECT（经 api 容器应用自身配置连接），零写入、零生产变更。
- 未读取无关密钥；`server/.env` 未打开；客户资料零触碰。
- 遵守红线：本审计不含任何客户真实姓名/扫描件/凭证。

### 数据兼容与回滚

- 无 schema/数据变更，无需回滚方案；文档可随时 revert。

### 验收证据

- 任务书 §2 G0 必做项 1–8 对照：1=§A、2=§B、3=§C/§D、4=§E.1、5=§E.3、6=§G、7=§H、8=两份 00- 文档已产出。
- 智能化评级判定：实测样本=0 ⇒ 维持书面口径 **L2+（交付智能化等级：平台，越大越自动化）**，不因口述升格（§0.5 硬约束）；G1–G6 关键流转按「默认人工确认」实现。
- 四个歧义裁决全部落盘且与任务书 §0 的裁决要求逐条对照（见各 ADR 尾节）。

### 遗留问题

1. ADR-005 待 G5 成文。
2. GAP-15（AI 草稿采纳率埋点）待落地（**仍开放**——ADR-007 §2.5 的复审触发器依赖它）。
3. 任务书 §17 外部输入 8 项维持待外部状态（法务意见、数值类、v4.0 原件核验等）。
4. 任务书基线 SHA（858e090）与当前权威基线（eee317c）的漂移已在本文档头部说明，后续 Goal 以「开工前现测」纪律处置。

### 是否允许进入下一阶段

**G0 已允许 G1 开工**（G1 已完成，见上）。

---

## §16 最终验收清单核对（收尾核查轮）— 已完成

- 分支：`feat/commercial-s16-final-audit`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `9e0cd64`（G6 收口态，全阶段闭环后）
- 状态：**completed**（收尾核查轮＝纯文档零代码零迁移零路由零桌面；18/18 条款勾稽全过）
- 勾稽方法：逐条款对照 G0–G6 已交付证据（本文件各阶段「验收证据」节＋ADR-001~010＋CI 实测轮次）；**关键项当场现测**——①`fde_profiles.level`／`agent_runs.fallback_level` 两保护字段按九个商业化 squash 提交逐一 `git diff <sha>^ <sha>` 核验并对命中逐条归因；②商业域 L 字面量扫描；③`COMMERCIAL_ROLES`／`REGISTRATION_ENTRIES`／`FREE_EXCLUSIONS`／`EXPERIENCE_LIMITS` 常量现读；④G0 实测报告现读。口径数字引用前现测，不承袭。

| # | 验收条款（§16 原文） | 结论 | 证据锚点 |
|---|---|---|---|
| 1 | 四个歧义 ADR 已出，且 `fde_profiles.level`（交付能力等级）与 `agent_runs.fallback_level`（降级链状态）既有测试零改动通过 | ✅ | G0 出具 ADR-001/002/003/006（`decisions/` 十 ADR 在位；ADR-004/007 随 G2、ADR-005 随 G5、ADR-008/009/010 随 G3/G4/G6 成文）。两保护字段九提交逐核：仅 G1（f186342）命中 14 行且**全为新增 docstring 文档性引用**（ADR-001 三要素纪律落新文件），零列定义/语义/既有测试改动；其余区间命中归因上游 #195/#247/goal-d4（非商业化提交）；全量套件三轮 CI 实测通过（终值 2618 passed + 6 skipped） |
| 2 | 角色字段值域为 R1–R4，代码与迁移不出现以 L 开头的角色枚举值；对外 L 编号仅经映射表转换 | ✅ | `COMMERCIAL_ROLES = ("R1","R2","R3","R4")`（models.py:51，机器闸钉 G1/G6）；商业域 L 字面量唯一落点＝`commercial/ladder.py:38 EXTERNAL_LADDER_CODES`（G1 交付的**对外换算映射表**——正是条款允许的唯一入口，`git log --diff-filter=A` 归属 f186342）；六个商业化迁移零 L 字面量 |
| 3 | 四类权益字段/表齐备且互不覆盖；无单一「会员等级」字段代表全部权益 | ✅ | ADR-002 四权益独立建模＋ADR-001 正交裁决；G1 两表＋G2 主体/额度两表＋G3 五表＋G4 两表＋G5 四表＋G6 两表＝**145 表**（57 rev 单头 `e8b3f7c2d9a5`）；G1 15 例互不覆盖钉 |
| 4 | 四类注册入口齐备；企业客户与企业自助用户为同一主体两种状态 | ✅ | `REGISTRATION_ENTRIES`（models.py:1216）键集↔`COMMERCIAL_ROLES`↔G2 体验入口三方机器闸 `test_registration_entries_cover_all_four_identities`；`engagement_state` **派生不落列**（ADR-010 §1-1/§1-4） |
| 5 | 企业免费额度按主体计，换账号不重置；诊断完成判据＝六项交付物产出并经企业确认 | ✅ | `enterprise_quota_subjects`（PK=subject_key）＋`enterprise_free_quota`（一主体一份，四 CHECK 联锁）；`test_start_binds_account_blocks_other_accounts_and_restart`＋`test_grant_idempotent_per_subject_never_second_row`＋行锁串行钉（G2 M1/M2/M6 红）＋G6 穿透自助路径两钉（M5 红）；`test_completion_requires_exactly_six_true`（M3 红）＋confirm 只认绑定账号本人 |
| 6 | 六项不免费内容不在免费流程内；模拟体验算力与人工指导上限按两档生效 | ✅（附注记） | `FREE_EXCLUSIONS` 七项闭集（models.py:179——任务书六项＋驻场＝超集）＋闭集拒绝多余键；`EXPERIENCE_LIMITS` 两档×两资源分别计数＋触限 409 反例用例（G2 M4 红）＋`EXPERIENCE_LIMITS_PLACEHOLDER=True` 数值待定诚实标注（models.py:211）。**注记**：V3.2 simulation 域消费接线按 ADR-004 §1-8／ADR-010 §3-2 显式挂账（任务书 §3 并行线边界内，判定原语已在位） |
| 7 | 实战营／陪跑营均含首年席位；席位不重复收有反例用例 | ✅ | `covers_first_year_fee`（models.py:362）＋实战营/陪跑营含首年席位常量（models.py:55-56）＋billing_service 双路径判定；`test_package_included_seat_is_not_charged_again`（409 `seat_fee_already_included`＋科目行恒 1 行；G3 M1 红） |
| 8 | 首单扣费在交付完成并验收后触发，且须事先书面选定；无单不欠费 | ✅ | `test_first_order_fee_blocked_before_acceptance`（409 `acceptance_not_passed` 零行；M3 红）＋`test_first_order_fee_blocked_without_election`（409 `deduction_method_not_selected` 零行；M2 红）＋扣费选定＝当事人自证（admin 不得代选）——双闸结构性保证「无单不欠费」 |
| 9 | 认证独立设项、认证挂模拟考核、陪跑期限与培训周期挂钩（数值待定） | ✅ | `commercial_certification_records` 独立设项＋`commercial_fee_configs` 三配置位迁移播种 unset；`test_certification_without_threshold_stays_pending`（M7 红）＋`test_mentoring_period_structure_is_pending_by_default`（M10 红）＋`test_certification_fee_cannot_be_charged_before_configured`（M9 红）；G3 service 陪跑期限挂钩配置位 |
| 10 | 培训费／席位费／项目分成分别记账；六项计费名目已定义归属 | ✅ | ADR-003/008 科目层独立（`delivery_settlements` 列集合逐位钉**零加列**）＋`test_three_subject_types_separately_queryable_and_reconcilable`（分桶对账逐位吻合）＋六名目只定义归属（ADR-008）＋`commercial_split_rules` 零行（比例不落数） |
| 11 | 商机七步链路完整；已确认归属不因企业自行注册而转移；规则数值可配置且未预写默认值 | ✅ | G4 `test_seven_step_chain_completes`＋跳步 409；`test_attribution_not_transferred_when_enterprise_registers_directly`（M1/M2 红）＋企业侧立项无商机行写路径（结构性保证）；五配置位播种 unset＋fail-closed 409 `rule_not_configured`（M3 红）＋转移唯一路径被 `attribution_criteria` 闸（本期无转移路径） |
| 12 | 区域四阶段可区分；城市服务伙伴按项目结算；「区域代理」标注暂不启用；前两阶段无独家权 | ✅ | G5 四阶段闭集＋注记读面派生（agent.enabled=false＋note）；`test_city_service_per_project_settlement`（一单一结＋重复 409）＋`test_regional_agent_is_not_enterable`（409 无写路径）＋`test_exclusive_territory_rejected_for_first_two_stages`＋DB CHECK（M3/M4/M5 红） |
| 13 | 区域售卖能力默认关闭，开关条件绑定合规条件清单已签署；本期无任何对外收费签约路径 | ✅ | `regional_sale_gate` 单行播种 closed＋CHECK 结构性排除缺件开门＋`require_sale_gate_open` 唯一闸门（闸关 409）＋**源码扫描钉**（formal_partner 写点唯一且在过闸函数内）＋合规四项「登记≠开启」；T-12b 本期不做（独立轮次） |
| 14 | 企业空间复用既有权限模型；三档分流人工判定并留痕，无量化阈值硬编码 | ✅ | G6 既有 `add_project_member`/`project_access` **零平行权限表**（元数据机器闸：G6 仅两表且无 permission/acl 命名）；`enterprise_triage_decisions`（tier 闭集复用 G2 权威＋rationale 必填＋**零阈值常量零评分代码**＋载荷无数字哨兵）＋空间读面回看用例（M2 红＝前置闸真实拦截） |
| 15 | 三档自助分级与「不承诺完全自助」一致 | ✅ | ADR-010 §1-8①：自助面（注册/分流/选择）自助，诊断内容生产维持 L3 形态（AI 草稿→admin 登记六项→企业确认）；任务书 §10「完全自助是长期目标，不第一天承诺」逐字承接 |
| 16 | 关键流转默认需人工确认且可人工接管（L3 形态）；接管路径留审计事件；G0 已出具 AI 草稿采纳率与接管频次实测 | ✅（附注记） | ADR-007（G2 成文）：admin 门＋密码确认双闸＋自我动作例外＋AI 无直写入口（治理面六轮不进 api_catalog，ENTRIES 94 不变）；人工接管沿 `handoff_run` 既有模式；**G0 实测已出具**（00-baseline-audit.md §H）：人工接管频次 **0 行**/`agent_run_handoff` 0 条、AI 草稿采纳率 **insufficient_data**（无承载事件）——诚实无样本结论＋GAP-15 埋点缺口登记 gap-register（§17 外部输入）；G1–G6 关键流转逐动作 operation_events 留痕（密码不落事件） |
| 17 | 全部写操作留审计事件；未新增未解释的 skip；全量测试与 lint／typecheck／mypy 通过 | ✅ | 逐动作 operation_events（G1–G6 各轮安全检查节）；skipped 恒 6（G0 基线 2333+6 → G6 2618+6，零新增零未解释）；main run 42663433357 四 job 全绿（desktop/server-tests/secrets-scan/pseudonymization）；mypy 279 基线六轮不变；ruff All checks passed；desktop typecheck/vitest CI 绿 |
| 18 | 桌面端改动已挂账（便携版重打包 + asar 字节验证），本期不交付 | ✅ | G0–G6 六阶段「前端变化：无」（纯服务端/纯文档）；商业化桌面呈现面挂后续轮（ADR-010 §3-4），无需重打包 |

- 总结论：**18/18 全过**（其中 #6/#16 附诚实注记——挂账项均为任务书 §17 预期内的外部输入或显式架构边界〔V3.2 simulation 接线、GAP-15 埋点〕，非验收缺口）。
- 收尾核查轮零代码零迁移零路由零桌面：无需 rebuild/alembic/重打包；部署活体维持 G6 收口态（url_map 442／容器内 alembic `e8b3f7c2d9a5` head／三镜像 ID 一致／`/health/ready` 200）。
- **商业化 G1–G6 Goal 循环至此全部收口**（G0 基线审计与四个歧义 ADR → G1–G6 六个实施阶段 → §16 收尾核查轮）；开放挂账汇总见各阶段「遗留问题」节与 ADR-010 §3。

---

## 挂账清偿轮 1：GAP-15 AI 草稿采纳率埋点 — 已完成

- 分支：`feat/commercial-gap15-adoption`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `edac1b7`（§16 收口后上游四笔 #266/#267/#269/#270 之上；G6 遗留清单与 ADR-007 §2.5 复审触发器的第一顺位开放项）
- 状态：**completed**（实现＋文档同 PR **#275**，合并 SHA **`2363f77`**＝fork/main 顶；分支 push run **`42746750980`** 4/4 success、PR run **`42746759083`** 4/4 success、合并后 main run **`42748188994`** 4/4 success〔四个 job 逐条读结论（secrets-scan／server-tests／desktop／pseudonymization），非 `gh pr checks` 单点结论〕；本节测试数为本地 CI 同命令 `-n 4 --dist loadfile` 实测，PR CI 复核）
- 落点（零新表零迁移零新路由零桌面；`api_catalog` ENTRIES 94 不变）：
  1. **方案确认流（系统派生，GAP-15 处置方向①）**：`solutions/service.py` NEW `_ai_draft_provenance` 派生助手——`solution_signoff_resolved`（人工拍板 approved/rejected）与 `project_solution_archived`（弃用＝拒绝/放弃信号）事件在 `generated_by='agent'` 方案上携带 `ai_draft` 块（generated_by/agent_run_id/modified_after_generation）；`update_solution` 对 agent 方案**首改即落** `source_json.ai_draft_modified` 戳（幂等不翻回，首改时间戳/操作人定格）；人工方案零触碰——事件不带 ai_draft 键（既有形状零漂移，用例钉住）。
  2. **诊断确认流（人工申报，GAP-15 处置方向②）**：`complete_diagnosis` 新增可选 `ai_draft_adoption` ∈ `AI_DRAFT_ADOPTION_OUTCOMES`（accepted/modified/rejected 闭集，models.py 新常量）——交付咨询环节申报「AI 草稿→人工登记六项」的采纳形态，随 `commercial_quota_completed` 事件留痕；缺省不落键（向后兼容）；非法值 400 闭集拒绝零副作用。
- 测试：NEW `server/tests/test_solution_ai_draft_adoption.py` **8 例**（首改落戳幂等/人工零戳/signoff 块三形态〔approved 未修改＝接受原稿、approved+修改戳＝修改后接受、rejected〕/人工方案两处 omit 钉/archive 块）＋ `test_commercial_enterprise_quota.py` **+3 例**（申报两值落事件/非法 400+零副作用/省略不落键）；**变异三连全红→还原→绿**（摘派生块→4 红；摘首改戳→3 红；摘申报校验与落键→2 红）；全量套件本地 `-n 4 --dist loadfile` EXIT=0（**2638 收集 = 2632 passed + 6 skipped**＝G6 后基线 2627 收集＋本轮 +11；第八度上游插队 rebase 融合 #271/#272/#273/#274 四笔〔pytest 增量 #274 评测集 +12〕⇒ 融合树 **2650 收集 = 2644 passed + 6 skipped** 实测）；ruff 触碰文件全过；mypy 279 基线零新增。
- 语义注记：采纳率口径＝事件序可查（approved+未修改／approved+已修改／rejected／弃用），不建第二套事件体系、零聚合表——聚合在复审轮按 BP §1.3a 证据口径现算（「口径引用前现测」）。
- 部署活体复验（合并后，本工作树 `D:\test\fde-wt-g1` @ `2363f77`）：重建三镜像（api `ad0c5cf…`／worker `2e3fa11…`／scheduler `102e2e4…`）＋`up -d` 重建容器＋`alembic upgrade head`（**零迁移幂等 no-op**，无 Running upgrade 行）；活体三项逐条复验——①`url_map` 规则 **442**（非 static **441** ≡ 源侧审计脚本 `route_count` 441／蓝图 49／表 145／rev 57／heads `e8b3f7c2d9a5`）②容器内 `alembic current` = **`e8b3f7c2d9a5 (head)`** ③三容器 `.Image` ＝ 本轮构建产物镜像 ID 逐位一致；另抽样核 GAP-15 代码实体在位（容器内 `solutions/service.py` 命中 `ai_draft` 13 处、`quota_service.py` 含 `ai_draft_adoption`、`models.py` 含 `AI_DRAFT_ADOPTION_OUTCOMES`）；`/health/ready` 200。
- 遗留：数据仍待首批真实 run（复审触发器另一半「agent_runs 非零」不变）；gap-register GAP-15 条目已附处置结果（登记维持，待首批数据后复审销号）。
---

## 挂账清偿轮 2：注册面节流（公开注册入口防滥用闸）— 已完成

- 分支：`feat/commercial-registration-throttle`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `ac83a81`（挂账清偿轮 1 合并＋合并证据回填之后；**第九度上游插队**：合并前上游推进两笔——#277〔纯文档，pytest 零增量〕／#278〔AI 输出格式归一，评测集 +4〕，rebase 融合后基线 **2654 收集**）
- 状态：**completed**（实现＋文档同 PR **#279**，合并 SHA **`3b67c1e`**＝fork/main 顶；分支 force-push run **`42762538756`** 4/4 success〔CI 实测 **2658 passed + 7 skipped**＝2665 收集，与本地 2659+6 收集数逐位吻合；passed/skipped 差 1 系环境相关 skip，教训 48：只认 CI 实测〕、合并后 main run **`42765507267`** 4/4 success〔CI 2658+7，四个 job 逐条读结论，非 `gh pr checks` 单点〕）
- 落点（零新表零迁移零新路由零桌面；`api_catalog` ENTRIES 94 不变）：
  1. **限流层**：`commercial/routes.py` NEW `REGISTRATION_RATE_MAX_ATTEMPTS=10`／`REGISTRATION_RATE_WINDOW_SECONDS=3600` ＋ `_registration_rate_key`／`_registration_throttle`——复用 #250 登录限流模式（Redis INCR+TTL、fail-open 缺省可切 fail-closed、429 结构化错误 `registration_rate_limited`、ProxyFix 后取真实客户端 IP）。
  2. **接线面**：`POST /api/v1/commercial/enterprise-registrations` 在**载荷解析与 argon2 计算之前**计入一次尝试——被限的请求零成本拒绝。
  3. **配置面**：NEW `Settings.registration_rate_fail_closed`（缺省 false＝fail-open）＋ `server/.env.example` 登记 `FDE_REGISTRATION_RATE_FAIL_CLOSED`（对外暴露部署从严切 fail-closed）。
- 语义三条（与登录限流的刻意差异）：①键＝**来源 IP 单键**（注册时没有既有用户名可入键，攻击者可随意换名）；②**成功不清零**（注册成功同样创建账号，成功清零会让「注册→清零→再注册」绕过配额——这是容量上限不是失败锁定）；③阈值为**技术防滥用闸**（公开入口洪泛／批量建号），非任务书 §17 商业数值红线（保护期长度／续期条件／归属判定／分成比例／认证费金额／试运营升级指标与首期金额一概不落数）。
- **测试隔离件（关键，非装饰）**：限流键含来源 IP、计数落在**共享 Redis**（测试库 DB 2）上——若所有用例共用 127.0.0.1，前一个用例留下的计数会把后一个用例挡在 429 上。`server/tests/conftest.py` NEW `PerTestIPClient`（按 app 实例＝用例分配独立来源 IP，第三段按 xdist worker 编号分段避免并行撞键）＋ `app` 夹具挂 `app.test_client_class`——**生产语义不变**（限流键始终是来源 IP）。实测证据：摘掉隔离件 ⇒ `test_commercial_enterprise_space.py` **14 failed / 13 passed**（429），还原 ⇒ 27 passed。
- 测试：NEW `server/tests/test_commercial_registration_throttle.py` **11 例**（阈值 429／换 IP 不牵连／计数在载荷解析之前／被限零副作用〔账号·主体·事件三查〕／成功不清零／窗口 TTL／Redis 挂 fail-open＋WARNING／fail-closed＋WARNING／XFF 真实 IP／无 XFF 回落／隔离件钉）；**变异五连全红→还原→绿**（M1 摘节流接线→10 红；M2 阈值差一→5 红；M3 注册成功后清零→1 红；M4 忽略 fail-closed 配置→1 红；M0 摘测试隔离件→邻域 14 红）；全量套件本地 `-n 4 --dist loadfile` EXIT=0（**2665 收集 = 2659 passed + 6 skipped**＝融合树基线 2654 收集〔2650＋上游 #278 评测集 +4〕＋本轮 +11；第九度上游插队（#277 纯文档／#278 评测集 +4）rebase 融合后本地实测）；ruff 触碰文件全过；mypy 279 基线零新增。
- 遗留（显式维持挂账，不假装完成）：①**企业空间桌面呈现面**（自助注册页／空间视图）仍挂后续桌面轮（ADR-010 §3-4）；②ADR-004 §1.8 体验上限消费接线（真实消费方在 V3.2 simulation 域）；③ADR-004 §1.4 多子公司集团归并（法务）；④任务书 §17 商业数值拍板（保护期长度／续期条件／归属判定／分成比例／认证费金额／试运营升级指标与首期金额）——本轮不落数。
- **部署复验（合并后从 `3b67c1e` 干净树重建）**：三镜像 rebuild（compose `-p fde-workbench`）——api **`054da5f5d643`**／worker **`02a5e0844708`**／scheduler **`69679697a1f3`**，`up -d` 后三容器 `.Image` 与构建产物逐位一致且 running；`alembic upgrade head` 幂等 no-op（本轮零迁移）、容器内 `alembic current`＝**`e8b3f7c2d9a5 (head)`**；活体 `url_map` **442 total / 441 non-static** ≡ 本轮口径（零新路由）；容器内 `grep -c registration_rate /app/src/fde_api/commercial/routes.py`＝**5**（节流代码在镜像内）；`/api/v1/health/ready` **200**。
---

## 挂账清偿轮 3：商业域权益行并发安全 ＋ 桌面焦点竞态修复 — 已完成

- 分支：`feat/commercial-entitlement-concurrency`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main `6ad6640`（挂账清偿轮 2 回填之后；**第十度上游插队**：#280 获客诊断 T-10a〔新迁移 `f3a9c7e1d5b2`／新蓝图／pytest +26〕与 #282 回填已并入，rebase 融合后基线 2691 收集〔CI 实测 2684+7〕）
- 状态：**completed**（实现＋测试＋文档同 PR；PR/main run ID 与合并 SHA 以合并记录为准）
- **起因与核实**：外部评审（另一智能体评估）列出五项改进空间，逐项核实后——①「商业化桌面呈现面为零」**表述不准**（项目侧 G1–G4 面已有 `CommercialBoard.tsx` 931 行；真正为零的是**企业自助注册页／企业空间视图**，即 ADR-010 §3-4，见后续轮）；②「未配置槽位管理员可见面」**确无汇总面**（API 有分散读面、桌面对 26 条 commercial admin 路由零消费）；③「法务审查状态可见」**确无可见面**；④「GAP-15 埋点无数据」**本轮不可实施**（需真实 run，触发器已登记）；⑤「并发覆盖偏薄」**确真且已落成真实缺陷**；⑥「users.test.tsx 焦点断言 flaky」**确真**（实测 12 轮红 1 轮）。
- **缺陷事实（⑤）**：`commercial_entitlements`（一人一份，PK=user_id）的席位激活与首单扣费此前是**无行锁读-改-写**（`ensure_entitlement` 只做 `session.get`，identity map 命中即返回旧实例）——并发窗口里两个请求可都读到旧值并各自写入：席位双激活（激活事件落两条、席位来源被后写者静默覆盖）；更严重的是**账本侧无唯一约束兜底**（`commercial_revenue_ledger` 不对 `(subject_type, subject_user_id)` 建唯一键）⇒ 同一交付者可能被记两笔 3980 席位费（实测 M2 变异下并发请求确实写出了第 2 行）。
- **修法**：NEW `commercial/service.py::lock_entitlement`——房内范式（`quota_service._lock_quota` 同款）**行锁＋刷新**：`SELECT ... FOR UPDATE` ＋ `execution_options(populate_existing=True)`（缺刷新＝只锁住行却不刷新内存视图＝等于没锁，CR-021 同款教训）；「行尚不存在」＝并发插入窗口，用 savepoint 兜住唯一约束冲突（IntegrityError）后按已提交行加锁，首次并发不 500 化。接线＝权益**写**路径六处一律走行锁原语（`set_commercial_role`／`activate_seat`／`set_certification`／`set_delivery_eligibility`／`charge_first_order_seat_fee`／`record_certification_evaluation`），**读**面 `get_entitlement_for_view` 保持无锁（读面加锁＝把并发读变成串行写）。
- **测试**：NEW `server/tests/test_commercial_concurrency.py` **8 例**——并发激活串行化／真并发（对方持行锁**未提交**时本请求必须等待并在其提交后读真值，区分「行锁」与「只刷新」）／并发扣费零记账／席位费科目行恒 1 行／并发建行不 500／写路径行锁与读面无锁双静态钉／被拒激活不留事件。**断言纪律**：关键断言置于 `rollback()` **之前**——rollback 会把未提交的写入冲掉，把证据一起抹了＝假绿（本次已实测踩中并修正）。
- **变异四连全红→还原→绿**：M1 席位激活退无锁→2 红／M2 首单扣费退无锁→2 红／M3 摘 `populate_existing`→3 红／M4 摘 `with_for_update`→2 红。
- **桌面焦点竞态修复（⑥，纯桌面零服务端）**：焦点管理挂在 **passive effect** 时，焦点生效落在 commit 之后的宏任务，而断言/读屏侧常由 DOM 变更的 MutationObserver（微任务）唤醒，两条链先后不定 ⇒「提交失败后焦点回到输入框」偶发断言红（实测 12 轮红 1 轮 ≈8%）。修法＝焦点管理改挂 **useLayoutEffect**（焦点属布局关注点，commit 内同步生效，早于任何观察者回调）：`users/UsersPage.tsx`（复位对话框两处）＋`common/DangerConfirmDialog.tsx`（危险确认两处）；**不靠放宽断言蒙过去**。验证＝users 连跑 30 轮零红、danger-confirm 连跑 20 轮零红、桌面全量 84 文件/985 例全绿。
- 口径：pytest **2699 收集 = 2693 passed + 6 skipped**（融合树本地 CI 同命令 `-n 4 --dist loadfile` EXIT=0 实测，PR CI 复核）；vitest **985**（84 文件）不变；mypy 279 基线零新增；ruff 全过；零迁移零新路由零新表。
- 遗留（显式维持挂账，不假装完成）：①**企业空间桌面呈现面**（自助注册页／空间视图，ADR-010 §3-4）——下一轮 G7 专项；②**商业化运维可见面**（配置缺口汇总槽位＋售卖闸状态＋法务审查未完成提示；服务端 admin 26 条路由桌面零消费）——下一轮；③ADR-004 §1.8 体验上限消费接线（消费方在 V3.2 simulation 域）；④ADR-004 §1.4 多子公司集团归并（法务）；⑤任务书 §17 商业数值拍板（保护期长度／续期条件／归属判定／分成比例／认证费金额／试运营升级指标与首期金额）——本轮不落数；⑥GAP-15 首批真实 run 复审（触发器已登记，样本=0 不可实施）。
---

## 挂账清偿轮 4：商业化运维就绪度可见面 — 已完成

- 分支：`feat/commercial-ops-readiness`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main 含挂账清偿轮 3（PR #283）
- 状态：**completed**（实现＋测试＋文档同 PR）
- **起因与核实**：外部评审列出五项改进空间，逐项核实——②「未配置槽位无管理员可见面」**确无**（服务端有分散配置位读面但无汇总面；桌面对 26 条 commercial admin 路由零消费）；③「法务审查未完成只活在文档里」**确无可见面**；④「GAP-15 埋点无数据」**本轮不可实施**（需真实 run）；①与⑤⑥已在挂账清偿轮 3 落地。本轮清偿②③。
- **落点**：
  1. **服务端汇总面**：NEW `commercial/readiness_service.py` ＋ `GET /api/v1/admin/commercial/readiness`（admin 只读；治理面不进 api_catalog；零迁移零新表）。
  2. **枚举纪律**：槽位按**权威键集**枚举（`FEE_CONFIG_KEYS`／`OPPORTUNITY_RULE_KEYS`），行只提供状态——槽位永不缺项（缺行即少报＝「缺什么」漏报，变异 M3 钉）。
  3. **数值纪律**：只报状态（`unset`/`configured`、`registered`/`unregistered`），**绝不补默认值**——fail-closed 方向不变；用例钉死「响应里不得出现金额形态数字」。
  4. **等待来源**：每个未就绪项带「等谁拍板」指针（§17 商业数值／分成比例／法务合规输入），话术单一权威在服务端，桌面端只渲染。
  5. **桌面面板**：NEW `commercial/CommercialOpsPage.tsx` ＋ 路由 `#commercial-ops`（admin 专属）＋ 侧栏「商业化运维」入口——未就绪横幅 ＋ 槽位状态表 ＋ 售卖闸逐项登记态。
- **测试**：NEW `server/tests/test_commercial_readiness.py` **7 例** ＋ NEW `desktop/tests/renderer/commercial-ops.test.tsx` **5 例**；**变异三连全红→还原→绿**（M1 摘 admin 闸→1 红／M2 摘闸条件呈现→1 红／M3 槽位改按行枚举→1 红）。
- 口径：pytest **2706 收集 = 2700 passed + 6 skipped**（本地 CI 同命令 `-n 4 --dist loadfile` EXIT=0 实测，PR CI 复核）；vitest **990**（85 文件，+5）；mypy 279 基线零新增；ruff 全过；路由 **447 → 448**（审计清单已重生成，CSV 恰 +1 行）；迁移头仍 `f3a9c7e1d5b2`。
- 遗留（显式维持挂账，不假装完成）：①**企业空间桌面呈现面**（自助注册页／空间视图，ADR-010 §3-4）——下一轮 G7 专项；②ADR-004 §1.8 体验上限消费接线（消费方在 V3.2 simulation 域）；③ADR-004 §1.4 多子公司集团归并（法务）；④任务书 §17 商业数值拍板（本轮只**呈现缺口**，不落数）；⑤GAP-15 首批真实 run 复审（触发器已登记，样本=0 不可实施）。
---

## 挂账清偿轮 5：G7 企业空间桌面呈现面 — 已完成

- 分支：`feat/commercial-enterprise-space`（工作树 `D:\test\fde-wt-g1`）
- 基线 SHA：fork/main 含挂账清偿轮 4（PR #286 squash → `8c0b113`）
- 状态：**completed**（实现＋测试＋文档同 PR；ADR-010 §3-4 桌面呈现挂账销号）
- **起因与核实**：外部评审①「商业化桌面呈现面为零」核实为**部分失实**——项目侧 `CommercialBoard.tsx`（931 行）已消费 G1–G4；真实零面＝G6 企业注册/企业空间的桌面消费（本轮清偿）。
- **落点**：
  1. **企业自助注册公开页**（NEW `commercial/EnterpriseRegisterPage.tsx`）：未登录可达且顶替登录页；`window.fde.api.request` 直连＋`accessToken: ""`（api client 无会话即拒，公开入口本就免鉴权）；只提交代号与必要登记信息（客户资料红线桌面侧承接）。
  2. **企业空间视图**（NEW `commercial/EnterpriseSpacePage.tsx`）：主体登记／免费额度状态／交付状态／付费选项与现行选择／交付项目五板块；选择付费选项＝POST 后先复读刷新再落提示（顺带修真缺陷：原顺序提示被复读清空）；主体代码 localStorage 记忆预填；**零数值呈现**（服务端单一权威下发原样呈现，不推导金额）。
  3. **接线**：`#enterprise-register`／`#enterprise-space` 路由（authorizedRoute 不加闸——企业账号即 viewer 档，服务端最终防线）；侧栏「交付与商业」组「企业空间」入口。
- **测试**：NEW `enterprise-register.test.tsx` **4 例** ＋ NEW `enterprise-space.test.tsx` **5 例**；**变异三连全红→还原→绿**（M1 注册载荷丢 subject_key→1 红／M2 提示先落被吞→1 红／M3 预填短路→1 红）；typecheck 绿。
- 口径：vitest **999**（87 文件，+9；本地全量 EXIT=0 实测，PR CI 复核）；pytest 2706 不变（纯桌面零服务端）；零迁移零路由；迁移头仍 `f3a9c7e1d5b2`。
- 遗留（显式维持挂账，不假装完成）：①ADR-004 §1.8 体验上限消费接线（消费方在 V3.2 simulation 域）；②ADR-004 §1.4 多子公司集团归并（法务）；③任务书 §17 商业数值拍板（轮 4 运维面板已呈现缺口，数值仍不落）；④GAP-15 首批真实 run 复审（触发器已登记，样本=0 不可实施）；⑤便携版重打包（桌面变更挂账，随下次桌面交付轮）。
---

## 收口轮：部署活体复验 ＋ 便携版 r31 交付 — 已完成

- 分支：`chore/round5-closeout-docs`（工作树 `D:\test\fde-wt-g1`，基线 fork/main `b39ca9b`）
- 状态：**completed**（纯文档零代码零迁移零路由零桌面）
- **部署**：确定版 rebuild 从合并态 `8c0b113` 干净 server 树——三镜像 api `f863fe65…`／worker `a0d9fe40…`／scheduler `749c618a…`（容器 `.Image` ≡ 构建产物且 healthy）；alembic 幂等 no-op（`f3a9c7e1d5b2 (head)`）；活体 url_map non-static **448** ≡ 口径；ready **200**。部署即覆盖轮 3（权益行锁）＋轮 4（就绪度汇总面）全部 server 变更；轮 5 纯桌面不需重建。main run 轮 4 `42797107137`／轮 5 `42800276475` 双四绿收口。
- **便携版 r31**：从合并态 `b39ca9b` 打包；asar sha256 `113289d4…24cb`；中文 marker ×3 全命中（商业化运维／读取企业空间／企业自助）；交付目录 `release/蔡工FDE-0.3.0-便携版-r31`（旧目录零覆盖）。**轮 3/4/5 累计便携版重打包挂账就此清偿**。
- 剩余开放挂账（全部带外部闸，非本轮可实施）：①GAP-15 首批真实 run 复审（触发器已登记，样本=0）；②ADR-004 §1.8 体验上限消费接线（消费方在 V3.2 simulation 域）；③ADR-004 §1.4 多子公司集团归并（法务）；④任务书 §17 商业数值拍板（数值位 unset 为有意 fail-closed，运维面板已呈现缺口）。
---

## 挂账清偿轮 6：GAP-15 数据化复审中间态 — 已完成（纯文档零代码零迁移零路由零桌面）

- 分支：`docs/commercial-parked-triage`（工作树 `D:\test\fde-wt-g1`，基线 fork/main `a0b9ec3`）
- 状态：**completed**（现测＋登记；剩余外部闸维持挂账，未假装完成）
- **起因**：用户要求「用交互式问题选择方式解决遗留挂账」——四项挂账逐项核实可实施性后，**唯一真正可推进**的是 GAP-15 复审（`agent_runs` 已非零）；§1.8 体验上限消费接线归 V3.2 simulation 域 Goal 线（跨域不越线）；§1.4 集团归并（法务）＋§17 数值拍板（业务）为外部闸无代码落点（运维面板已呈现缺口，催办靠外部）。
- **GAP-15 触发器现测（活库 @ 部署镜像 `f863fe65…`，`fork/main` `a0b9ec3`）**：
  1. 前半 `agent_runs 非零` ✅＝实 run **12**（`idempotency_key not like 'rehearsal:%'`；completed 6／failed 3／timeout 2／succeeded_but_receipt_invalid 1；`fallback_level` L2×3、None×9；落库 2026-11-09）。
  2. 后半 `采纳率埋点有数` ❌＝0（`solution_signoff_resolved` 带 `ai_draft` 派生块 0／`commercial_quota_completed` 带 `ai_draft_adoption` 0／`guidance.draft_*` ∅）——12 条实 run 无一在方案确认流上产生采纳留痕，缺**首条采纳样本**而非样本量。
  3. 判定＝触发器**半激活**，ADR-007「默认人工确认」不放松（§0.5 红线）；对照信号＝人工拍板 `gates` passed 6／failed 1／pending 11、`automation_approvals` approved 2。
  4. **销号条件**：任一真实采纳/否决样本落 `operation_events` 即具备完整复审证据，按 BP §1.3a 复核智能化评级与确认点密度；数据到位即销号，无需再开轮。
- 00-gap-register GAP-15 条目追加「复审中间态」条（现测数字＋判定＋销号条件）。
- 口径：纯文档，pytest/vitest/mypy 全不变（2706 收集/999/279）；零代码 ⇒ 无需 rebuild/alembic/重打包。
- 剩余开放挂账（本轮裁决，全部带外部闸）：①**§1.8 体验上限消费接线**＝消费方在 V3.2 simulation 域，归 V3.2 线开工同线实施（跨域不越线）；②**§1.4 集团归并**＝法务口径（`normalize_subject_key` 单点待法务确认后改）；③**§17 数值拍板**＝业务红线，数值位 unset 为有意 fail-closed（运维面板已呈现缺口与等待来源）；④**GAP-15**＝半激活待首条采纳样本（销号条件已登记）。
---

## 外部闸消解轮：§1.4 法务裁定问题单 ＋ §1.8／§17 裁决落账 — 已完成（纯文档零代码）

- 分支：`docs/legal-14-question-sheet`（工作树 `D:\test\fde-wt-g1`，基线 fork/main `0f2005b`）
- 状态：**completed**（交互选择三项裁决＋问题单落盘）
- **起因**：用户要求以交互式问题选择解决剩余外部闸——逐项核实后：§1.4 **可问清**（问题写清即解锁销号路径）；§1.8／§17 为**裁决性**（归域／落数），选择即落定。
- **落点**：
  1. **NEW `ADR-004-集团归并-法务裁定问题单-v1.md`（Q1–Q5）**：额度法人/集团计（A 不分别＝现状保守默认＋人工闸／B 归并→`normalize_subject_key` 单点）／母公司 USCC 字段三态／无 USCC 主体（只境内零改动 vs 放宽另立 ADR）／去重规则终态（§17-3 销号条件）／归并证据要求（门禁证据红线：指针＋sha256）；每项带代码锚、等待方、到位后动作；**裁定前维持现状，不预置工程**。
  2. **§1.8 裁决＝归 V3.2 simulation 域**：消费方属独立 V3.2 Goal 线（`fde-wt-v32`），跨域不越线，V3.2 线开工同线实施。
  3. **§17 裁决＝维持 unset（fail-closed）**：数值一律不落数（缺省即不可收款），运维 readiness 面已呈现缺口与等待来源；待试点数据＋业务方书面输入再落（D-12 同向）。
- 口径：纯文档零代码；pytest/vitest/mypy 全不变；零迁移零路由 ⇒ 无需 rebuild/alembic/重打包。
- 剩余外部闸（本轮后终态）：**§1.4＝问题单已备、等法务回应**（Q1–Q5 逐一应答即销号，回应前维持保守默认＋人工闸）；§1.8（V3.2 域）与 §17（业务拍板）为**裁决性维持**，非外部闸卡点。
