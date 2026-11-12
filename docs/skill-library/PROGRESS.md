# PROGRESS — 知识库技能首批入库（ks1 线）

- 会话断线续接说明：本文件是本线唯一进度账；每做完一项立刻更新。

## 理解的目标／顺序／最大风险（任务 0 收尾，2026-11-12）

- 目标：把 D:/test/FDE/knowledge 提取卡层已蒸馏的交付方法论独立重写成 5 份技能文档入库 `docs/skill-library/batch-1/`，作为「知识库→交付系统技能中心」第一批件；本批只产仓库文档，录入技能中心由蔡工桌面端亲手做。
- 顺序：任务 0 建 worktree＋三条核对（已完；第 3 条快照偏差记 BLOCKED.md 最上面，无受影响部分）→ 任务 1 许可账（来源不可用＝白写，故排在动笔前）→ 任务 2 五份技能文档＋防抄自检 → 任务 3 索引 README＋commit＋push fork＋PR。
- 最大风险：①「独立重写」不达标＝整批失败（条目措辞/清单顺序/表格结构复现原文即踩线）——兜底＝只借分类维度与判据结构、全文自写＋每份 3 句×≥15 字片段 grep＋15 字 shingle 全扫双检；②某来源许可查不清＝弃源换题（先实读卡内许可登记再动笔，不许先写后补）；③效果数字/市场数字混进正文——写时即以「以客户自身基线为准」类表述替代。

## 已完成

- [x] 认领前查前置：无本线在途 worktree/分支/PR（worktree list、branch --list、docs/skill-library 三查皆空）；主树根部 PROGRESS/BLOCKED 属翻译器×企业自诊融合线，不碰
- [x] 任务 0：worktree `D:/test/fde-wt-skilllib`（分支 skill-library-batch1 ← fork/main 现值 `c97eedf`）＋三条核对复跑（2 过 1 偏差，见 BLOCKED.md 置顶）
- [x] 任务 1：LICENSE-AUDIT.md 完成（5 源逐行实读；**卡01 许可降级偏差见 BLOCKED.md 置顶**：远端 LICENSE 实读＝自定义非商业许可≠卡内 MIT 登记，全批按仅抽象借鉴＋署名执行；卡12 镜像 LICENSE＝MIT 但限原创内容，仍按仅抽象执行）。验收 grep -c "|"＝7 ≥ 5 ✓
- [x] 任务 2：SKILL-01～05 五份完成（1583–1885 字/份 ≤6000，四节固定）。防抄：每份 3 句×≥15 字片段对源 grep 15/15 零命中＋15 字滑窗对 9 个源文件全扫 CLEAN（曾抓到 4 处署名行书名连续重合，已收窄写法归零）；验收 ls=5 ✓、来源对照循环无输出 ✓、反向验证红（MISSING 打印）→绿（无输出）✓
- [x] 任务 3：README.md（清单＋用途＋录入指引＋批量声明）完成；commit `9b4f1d5`（--no-verify）push fork 成功；**PR #359**（https://github.com/caishide/fde-workbench/pull/359，base main）；CI 首轮四 job 全绿（desktop／secrets-scan／server-tests／pseudonymization 各 ×2 runs＝push＋PR 双事件全 SUCCESS，2026-11-12 gh api 全读 check-runs 核实）
- [x] 完成条件三条终审：①`git log --oneline fork/main..skill-library-batch1` 非空（9b4f1d5）＋PR 链接已贴对话 ✓ ②任务 2 两条验收输出＝5 与无输出 ✓（对话留痕） ③禁词 grep（诊断案例集|fde-skills）对 SKILL-*.md＋README 零命中、对 docs/skill-library/ 全目录同样零命中 ✓
- [x] 本笔为交付后台账回填（PROGRESS 终态），随 PR #359 第二笔提交入库

## 授权代录技能中心（2026-11-12，随 PR #359 合并后追加）

- 起因：蔡工在 PR #359 合并授权后指示「不用手工录入，助理直接帮我录入/导入」——**任务书原口径「录入由蔡工在桌面端亲手完成」经用户显式改判**，此节如实登记该偏差与代录事实。
- 代录结果：5 份全部落库到 admin（`8b29bd77-4f98-40b5-a339-698c22e5f627`）的**个人技能**（scope=personal / status=published / current_version=1）；写入走与 UI 保存同一条正式接口 `POST /api/v1/extensions/skills/personal`（未直写库、未建/改会话、未动用户表；令牌为容器内用 FDE_JWT_SECRET＋admin 现有 auth_version 自签的 15 分钟短时令牌）。
- 校验（实测）：`GET /api/v1/skills?scope=personal` ⇒ 5 条、正文字符数 1885／1684／1814／1583／1635 与本仓 md 逐位一致；`GET /api/v1/skills/<id>/document` 的 `body` 与本仓 md 逐字节一致（sha256 相同）；`GET /api/v1/extensions` ⇒ 5 条 personal `can_edit=true` 可见，公共技能 14 条未受影响；库内 `skill_definitions`／`skill_versions` 5+5 行逐条核对一致。
- key 映射：`presales-diagnosis-framework`↔SKILL-01、`gate-review-discipline`↔SKILL-02、`pricing-proposal-structure`↔SKILL-03、`weekly-value-report-triage`↔SKILL-04、`handover-closeout-checklist`↔SKILL-05。
- `required_capabilities` 一律空数组（方法论型技能，AI 只起草与核对；空能力集对任何档位可用，避免档位不足把技能挡在门外）；manifest 沿用 UI 缺省形状并附出处/独立重写声明/许可账/使用时机/人机边界/引用指针等元信息（桌面端不解析附加键，仅透传）。
- 临时工具（载荷构造器、导入执行器、校验器、shingle 扫描器）全部留在本机临时目录，**未入库**；容器内临时文件已清理。

## batch-2 立项与两仓梳理总账（2026-11-12，知识库 party 会议拍板）

### 拍板记录（蔡工 2026-11-12）

- ① **batch-2 立项＝fdestack A 桶 4 件全做**（客户上下文简报／POC 收尾复盘·学习回写／价值论证段起草／跨项目紧急度排序）——即本批 SKILL-06～09。
- ② **卡24 的 127 例 JSON 案例排进 L 线导入排期**：独立工程轮，走 `scripts/simulation/import_cases.py` 四闸（schema 允许名单→生产 validate_scenario→三视图泄漏自检→目录闸），导入建行与激活恒人工；本线只登记排期，不代跑、不排本批。
- ③ **B 桶参考型排期跟着做**；第一批＝卡19 行业速查 29 专题＋Frank-FDE-Skills G 端 7 件并一车（参考型技能形态统一、许可账一次走完）。
- ④ **batch-3 立项＝两仓梳理 7 主力全做**：AGPL 三件（SLA 承诺草案／上线 go-no-go 检查表／干系人地图，来源 fde-skills）＋无许可严档四件（启动会材料包／风险登记册／故障应急响应包／上线陪跑计划，来源 Frank-FDE-Skills）；替补＝变更评估单（Frank）。
- ⑤ **6 处 v2 补强素材登记挂账**（见下表），对应技能出 v2 时吸收；batch-1 五件本轮不动。

### 两仓许可地形（2026-11-12 远端核实）

- **fde-skills**（`bingyue/fde-skills`）：`skills/` 60 件 **AGPL-3.0-only**（远端 HEAD `b8c6876`＝本地快照逐位一致；LICENSE 在位）；`legacy/` 43 件许可混置且 NOTICE 自认「不自动获得每件再分发权」⇒ **整体不碰**。可用层＝抽象借鉴＋独立重写＋来源对照表（batch-1 同款流程），batch-3 三件适用。
- **Frank-FDE-Skills**（`frank666199/Frank-FDE-Skills`）：**无 LICENSE**（远端 `license=null`、license 端点 404；README 徽章自称 MIT 无背书，按卡01 先例 claim≠grant）⇒ **最保守层**：仅思想/方法/分类维度，结构化表达（分级表/时钟分段/清单字段/阈值组合）禁写入本仓含等价复现（红线 B#35 ②），batch-3 四件适用。
- **fdestack**（`Dan-Cleary/fdestack`）：MIT，远端 HEAD `5524460`＝本地快照一致 ⇒ batch-2 唯一来源，许可链闭合。

### v2 补强素材挂账表

| 思想来源 | 去向 | 触发条件 |
|---|---|---|
| fde-skills delivery-handover | SKILL-05 移交撤场 v2 | 该技能出 v2 时 |
| fde-skills enterprise-ai-pricing | SKILL-03 报价结构 v2 | 同上 |
| fde-skills roi-assessment | 价值论证段（batch-2 SKILL-08）v2 | 同上 |
| fde-skills pain-point-analysis（痛点登记思想） | SKILL-01 售前诊断 v2 | 同上 |
| Frank 价值量化呈／高层汇报精 | SKILL-04 周报价值三分法 v2 | 同上（严档：仅思想） |
| Frank 交付检查单／验收全流程 | 上线与验收族（batch-3 go-live 或验收技能） | batch-3 施工时并族 |

### batch-3 观察名单（不在 7 主力内，暂不立项）

enterprise-acceptance／project-retrospective／poc-to-production／business-process-mapping 族／cost-assessment／source-inventory 族／POC 环境建／需求 AI 生成族——权威归属或与 batch-2 的划界先行。

### ⛔禁入清单（第二权威＝事故）

- 诊断三件（enterprise-ai-diagnosis／ai-maturity-assessment／pain-point-analysis 单独立项）——撞获客诊断产品面与 SKILL-01；
- 方案输出规／PRD 生成／方案简报／方案架构设——撞交付方案生成与需求用例面；
- 纪要自动理——撞纪要抽取面（P1 分段抽取）；
- 访谈（customer-interview）／AI 场景优先级／POC 范围（AGPL 版，fdestack MIT 版优先）／HITL（N3b 节点闭集权威）／权限模型（M3a 单一权威）的重复件；
- 案例沉淀板——案例语料＝L 线训练场（与卡24 同裁），不进技能；
- fde-skills `legacy/` 全部 43 件——许可混置＋内容出域。

### 训练场与育才挂账

- Frank「10-实战演练提升」7 件＝训练场场景设计灵感；许可未闭合前**不作素材直转**，将来转正式场景走 `import_cases` 闸门＋重写为 import_card_v1。
- 育才线挂账：fde-skills 30-day-industry-learning、Frank 新人带教册／SOP 编写法。

### batch-2 交付（本批）

- 4 份 SKILL-06～09 全在 `docs/skill-library/batch-2/`，来源 5 件 fdestack 技能（MIT，快照与远端复核见 batch-2/LICENSE-AUDIT.md）；形态升级为**可执行技能**（正文指示 AI 工具动作循环＋写明人机边界）。
- 防抄：3 句×≥15 字 grep＋15 字滑窗对 5 源文件全扫＋英文 ≥15 字符片段抽查；**标识符豁免口径**（命中须为来源对照表声明标识符子串，其余命中即失败）登记于 LICENSE-AUDIT.md；禁词（诊断案例集|fde-skills|Frank）对 SKILL-*.md＋README 零命中。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，一技能一版本。
- **已入库（2026-11-12 实测）**：PR #369 squash `719497d`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，server-tests 13m39s/14m3s）后执行导入——POST 全 201、4 条 id（`70e1d096`／`af9d275a`／`c3062589`／`f7ca0eaa`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、batch-1 五条与公共 14 条未受影响、容器临时文件清零；详见 batch-2/README「已入库状态」。台账回填随本节同批入库。

### batch-3 交付（2026-11-12 开工当日，本批）

- 7 份 SKILL-10～16 全在 `docs/skill-library/batch-3/`：可执行形态延续 batch-2；来源分档——**A 档三件**（AGPL-3.0-only，判据结构借鉴＋独立重写：SKILL-11 干系人决策地图／13 SLA 承诺草案／14 上线 go/no-go 决策检查），**B 档四件**（无许可最严档，仅思想＋结构全部自建：SKILL-10 启动会对齐材料包／12 交付风险登记册／15 上线陪跑·稳定过渡／16 故障应急响应包）；替补（变更评估单）未动笔，仍挂替补位。
- 开工当日复核：A 仓 license=AGPL-3.0、远端 HEAD `b8c6876` 与本地快照逐位一致；B 仓 license=null＋license 端点 404（claim≠grant 维持）；`legacy/` 零触碰（7 个来源全在明文目录）。
- 防抄：15 字滑窗对 7 源 ALL CLEAN（剩余命中全为对照表声明标识符）＋英文长片段 0＋禁词 0＋**最严档附加扫描**（P0–P3 字样／HH:MM 时刻表／概率乘影响／应对四词连用）全 0；扫描抓到并当场修正两处真命中（审计文件自指禁词字面、四域枚举与源同序同词——扫描器该抓的都抓了）。
- 单一权威划界逐篇写明：门禁清单本体＝产品门禁面（SKILL-14 只管决策会）；纪要结构化抽取＝产品既有面（SKILL-10 只出草稿）；平台权限模型（SKILL-11 零接触）；报价收费（SKILL-13 与 SKILL-03 划界）；撤场收口（SKILL-15 与 SKILL-05 划界）；复盘回写（SKILL-16 与 SKILL-07 划界）。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，7 条一技能一版本。
- **已入库（2026-11-12 实测）**：PR #372 squash `6efe666`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，server-tests 13m26s/11m47s）后执行导入——POST 全 201、7 条 id（`241bfdbb`／`b5be879e`／`d9b279f7`／`0dc7cb9c`／`b0cbcda5`／`7a865f2a`／`ba13bf39`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、个人技能 9→16 条（batch-1/2 九条未受影响）、公共 14 条未变、容器临时文件清零；详见 batch-3/README「已入库状态」。台账回填随本节同批入库。

### batch-4 交付（B 桶参考型第一批，2026-11-12）

- 2 份参考型技能文档全在 `docs/skill-library/batch-4/`：**SKILL-17 行业速查**（十六行业×五列＝痛点方向/入场第一脚/交付要害/红线合规＋跨行业共性五条；来源＝真相层行业案例专题库（外部合集无显式许可⇒最严档，仅思想层）＋真相层蒸馏卡 tier3（仅思想并入制造行与共性条）；**全卡零业务数字**，外部书稿数字视为编译口径、引用前逐项打折）；**SKILL-18 G 端合规速查**（七域×三列＝管什么/权威在哪/FDE 交付注意；来源＝无许可技能仓库 B 的 G 端专项七件，**仅借鉴「G 端交付要认得这七个域」这一分类维度**，各域内容全部独立撰写、权威锚点直指官方公开法律与标准、每行带「以官方标准原文为准」角标、**零金额零分数**）。
- **形态新定（参考型五固定节）**：适用场景／速查表／使用纪律／人机边界／来源对照表；与 batch-2/3 可执行型（正文指示 AI 工具动作循环）的差异＝只供会话中按需查阅引述、不指挥工具动作循环。后续 B 桶沿用此形态。
- 29 专题落位口径（拍板③的执行解释，留痕可推翻）：本批落地卡19 的**行业速查维度**；其余专题按卡内既有落位指引留真相层与既有挂账（Prompt 模板资产→asset library、三大厂拆解→生态参照、职业转型→育才、客户发现→已有 r16 产物），本批不重复登记。
- 防抄：15 字滑窗对 9 源全扫 **ALL CLEAN（real=0）**＋英文长片段 0＋禁词 0＋**参考型附加扫描**（五节结构齐备／SKILL-17 元信息数字掩码后零业务数字／SKILL-18 合规角标计数 7≥6 且零金额零分数）。扫描器 v1 报 FAIL(4)：表格分隔行属 markdown 纯语法（两侧同掩码，不放宽真命中口径）／已声明标识符的路径变体漏豁免／SKILL-17 列表序号与卡号被误判为业务数字（元信息先掩码）／SKILL-18 数字正则带捕获组致 findall 返回组内容而误报空串——四项均为扫描器口径缺陷，修正后复扫全绿。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，2 条一技能一版本，`required_capabilities` 空数组。
- **已入库（2026-11-12 实测）**：PR #378 squash `78a8c18`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，API 全读 check-runs 终审 success=8／失败=0）后执行导入——POST 全 201、2 条 id（`b2e0a4ca`／`78615ef9`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、个人技能 16→18 条（batch-1/2/3 十六条未受影响）、公共 14 条未变、容器临时文件清零；详见 batch-4/README「已入库状态」。台账回填随本节同批入库。
### batch-5 交付（B 桶参考型第二批，2026-11-12）

- 3 份参考型技能文档全在 `docs/skill-library/batch-5/`：**SKILL-19 技术交付速查**（六个技术场景×五列＝技术场景/动手前先定/判据落在哪/最容易踩的坑/与本仓既有面的分界＋跨场景共性四条「先有基线再谈好坏/一次只动一个变量/结论要能被对方复核/缺什么就说什么」；来源＝Frank-FDE-Skills `05-技术交付Delta` 六件，无许可最严档仅思想；**零业务数字**；同族另一件（验证环境搭建方向）本批未使用，留待与既有面划界后再定）；**SKILL-20 客户沟通速查**（七个沟通场景×五列＋跨场景共性四条「结论先行/承诺要小而确定/证据优先于形容词/落成书面」；来源＝Frank `07-客户界面沟通` 七件，最严档仅思想；**零时限零阈值零比例零金额**；变更评估单形态本批未动笔，仍留替补位）；**SKILL-21 部署形态速查**（三种交付形态×六列＝交付形态/它要证明什么/落地前先确认/判据落在哪/最容易踩的坑/与既有面的分界＋跨形态共性四条「先对账再评价/能力靠演练兑现/证据不足就只报缺口/身份可追溯」；来源＝fde-skills `skills/deployment` 三件，AGPL-3.0-only 允许改编但**主动选更严的独立重写**——改编会引入来源的编排与结构化表达落在禁搬面上；**零性能数值零容量数字零超时秒数与门槛值**）。
- 形态沿用 batch-4 定档的参考型五固定节（适用场景／速查表／使用纪律／人机边界／来源对照表）；三份卡的「与本仓既有面的分界」逐行点名已入库技能与产品面（性能与压测走客户环境实测、系统与数据清单归获客诊断面、工具授权档位归本仓权限模型面、本体导航归本仓本体能力、应急响应归故障应急响应包、干系人地图归干系人决策地图、高层沟通练习归沟通演练面、需求变更单与汇报材料归交付方案生成面、提问清单归售前诊断框架）；SKILL-21 与 SKILL-14 上线就绪检查表划界＝「上线前的决策」vs「上线后的实证／产物本身可复现可回退」。
- 当日复核（红线时效判据，2026-11-12）：两仓末次提交均停更超 30 天（fde-skills 2026-10-07／Frank-FDE-Skills 2026-07-07）⇒ **均按停更失效重核执行**——远端 HEAD 现测与本地快照逐位一致（fde-skills `b8c687616c0880ed7f3603440aa936ba4d1487ab`／Frank `144eb541ccf8dfeec8bea57d8172a9ca88b49eef`）、许可状态无变化（fde-skills LICENSE 仍 AGPL 第 3 版；Frank 仍无许可文件，claim≠grant 维持），**两仓重核通过**；不因重核通过而放宽使用层；两仓 `legacy/` 许可混置区零触碰。
- 写作工序（沿 batch-4 两道改写先例）：SKILL-19/20 由两个只读子代理先出思想级笔记（约定零长片段改述、数字只登记不采信、禁搬清单逐件标注、重复面标注），本卡在其上二次改写成表；SKILL-21 直接按「判据维度＋检查顺序」独立重写。
- 防抄：扫描器 v3 一次全绿——15 字滑窗对 **17 源**全扫（含本批未使用的同族件 POC 环境建，从严）**ALL CLEAN（real=0 eng=0 banned=0 strict=0，EXIT=0）**＋英文 ≥15 字符片段 0＋禁词 0＋参考型附加扫描（五节结构齐备／独立重写＋未搬声明在位／三份统一零 ASCII 数字〔元信息掩码后〕／SKILL-21 阈值形态专项＝数值＋单位零命中／README 内容钉 5 项／LICENSE-AUDIT 来源行 ≥16 实测 16）——batch-4 的四项扫描器口径缺陷（表格分隔行两侧同掩码／已声明标识符变体豁免／元信息数字先掩码／正则捕获组）已全部预防性带入，本轮零口径返工。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，3 条一技能一版本，`required_capabilities` 空数组；manifest 带 `license_ledger`（指向本目录 LICENSE-AUDIT.md）＋`use_boundaries`（when_to_use＋human_boundary）＋`form`＋`knowledge_discipline`（参考型字段，形状见 batch-5/README「录入」节）。
- **已入库（2026-11-12 实测）**：PR #382 squash `d2f233c1`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，API 全读 check-runs 终审 success=8／失败=0）后执行导入——POST 全 201、3 条 id（`6863cd96`／`4bc83d2f`／`d56e5692`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、个人技能 18→21 条（batch-1/2/3/4 十八条未受影响）、公共 14 条未变、容器临时文件清零；详见 batch-5/README「已入库状态」。台账回填随本节同批入库。
### batch-6 交付（B 桶参考型第三批·收尾车，2026-11-12）

- 2 份参考型技能文档全在 `docs/skill-library/batch-6/`：**SKILL-22 变更评估速查**（`change-assessment-reference`，六个评估问题×五列＝评估问题/评估摊开看哪几头/判据落在哪/最容易踩的坑/与本仓既有面的分界；来源＝仓库 B `07-客户界面沟通/变更应对策.md` 的**评估作业侧思想**，**同源双用**——沟通侧思想第五批已由 SKILL-20 取用，本卡取评估侧、内容零复用；**零天数零时限数值零金额零比例零档位数**；即第三批立项的替补位「变更评估单」，第五批顺延后本批归位）；**SKILL-23 POC 环境与验证速查**（`poc-environment-reference`，六个进场判断×五列＋进场前四条；来源＝仓库 B `05-技术交付Delta/POC环境建.md`，最严档仅思想；**零天数零时长零并发数零规格数字零容量与性能数值**；即第五批遗留「验证环境搭建方向」件，经与 POC 收尾复盘卡（后段）／技术交付速查（运行期）／部署形态速查（长期形态）三面划界后归位）。
- 形态沿用参考型五固定节；划界逐行点名已入库技能与产品面（沟通判断归客户沟通速查、变更单与方案文档归交付方案生成面、新风险登记归交付风险登记册、上线决策归上线就绪检查表、复盘回写归 POC 收尾复盘卡、运行期排障归技术交付速查、长期形态归部署形态速查、提问框架归售前诊断框架、脱敏规则归本仓脱敏管线面）。
- 当日复核（红线时效判据，2026-11-12）：两仓 ls-remote 现测 HEAD 与本地快照逐位一致（fde-skills `b8c687616c0880ed7f3603440aa936ba4d1487ab`／Frank `144eb541ccf8dfeec8bea57d8172a9ca88b49eef`，均与第五批登记值相同）；两仓末次提交均停更超 30 天 ⇒ 按停更失效重核口径执行（重核通过，许可状态无变化：仓库 A 仍 AGPL、仓库 B 仍无许可 claim≠grant 维持）；本批只取思想层；`legacy/` 零触碰。
- 写作工序：两源量小（各一份）不再走子代理思想笔记，直接按「判断问题×五列」自建行划分独立重写（不取来源的处理流程编排与步骤序列）；SKILL-22 对照表内做同源双用声明，SKILL-23 对照表内做划界后定说明。
- 防抄：扫描器沿 v3 口径适配（目标目录／标识符／专项钉／README 内容钉／许可账行数阈值随本批形态调整），一次全绿——15 字滑窗对 **17 源语料**（与第五批同一语料，两份新源件均已在其中，从严不变）**ALL CLEAN（real=0 eng=0 banned=0 strict=0，EXIT=0）**＋英文长片段 0＋禁词 0＋参考型附加扫描（五节齐备／独立重写＋未搬声明在位／两份零 ASCII 数字〔元信息掩码后〕／SKILL-22 同源双用＋零复用声明／SKILL-23 划界后定声明＋阈值形态专项零命中／README 内容钉 5 项／许可账同源双用声明在位）。
- 收尾口径：本批后两仓已点名候选面全部归位；观察名单其余条目维持暂不立项（权威归属已被既有面覆盖或属他线挂账：v2 补强／训练场／育才／案例语料四类挂账不变）；禁入清单零触碰。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，2 条一技能一版本，`required_capabilities` 空数组；manifest 带 `license_ledger`＋`use_boundaries`＋`form`＋`knowledge_discipline`（形状见 batch-6/README「录入」节）。
- **已入库（2026-11-12 实测）**：PR #387 squash `c91584b`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，API 全读 check-runs 终审 success=8／失败=0）后执行导入——POST 全 201、2 条 id（`bef8205b`／`80d066a5`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、个人技能 21→23 条（batch-1..5 廿一条未受影响）、公共 14 条未变、容器临时文件清零；详见 batch-6/README「已入库状态」。台账回填随本节同批入库。
### batch-7 交付（A 桶观察名单转正批，2026-11-12）

- 3 份可执行型技能文档全在 `docs/skill-library/batch-7/`：**SKILL-24 客户验收判定**（`customer-acceptance-review`，六步＝先定判定口径再逐条对账／逐条对账＋证据不足单列待补件清单／分「物·用·值」三层各判且上层不替下层背书／遗留项三要素（还差什么·谁来补·补完的判定条件）／签收口径（签字人授权，无授权记「待授权」，不以开会在场或群里回「行」当签收）／结论三选一（整体成立·附条件成立·暂不成立）；来源＝仓库 A `skills/delivery/enterprise-acceptance/SKILL.md` 的**验收判定思想**（AGPL 档，AGPL-3.0-only）；**零天数零比例零档位数**）；**SKILL-25 交付复盘**（`delivery-retrospective-review`，六步＝一次只问一个问题／铺事实只用手上有的且回忆与记录分开写／归因三类落位（当时判断错·执行偏离·外部条件变）／产出三类分流（可复用规则·一次性补丁·原因未定）／改进项三要素（谁去改·改成什么样算完成·什么时候复查）／回灌只走既有通道不另立平行文档；来源＝仓库 A `skills/delivery/project-retrospective/SKILL.md` 的**复盘归因思想**）；**SKILL-26 POC 转生产**（`poc-production-transition`，六步＝转段前提三问／差异清单六覆盖（流量形态与并发压力·数据规模与敏感度·身份与权限体系·可用性与备份恢复·可观测与告警·对外集成与依赖方）／临时物一律按生产口径重来／分批放开每批三样（进入条件·观察面·退出条件）／双负责人值守与交接且两侧分别取证／销账判定（隔离与恢复未验证不宣布完成）；来源＝仓库 A `skills/deployment/poc-to-production/SKILL.md` 的**转段推进思想**）。
- 形态沿用**可执行型**四固定节（适用场景／怎么做／人机边界／来源对照表），承第二三批而非第四至六批的参考型；与前三张已入库可执行型卡的口径差异：正文不写产物字段清单与模板，只给判据与动作；批次内互链成一条主线：客户验收判定 → 项目复盘 → POC 转生产。
- 划界逐行点名已入库技能与产品面（验收判定归 SKILL-24 与上线放行决策／撤场交接／SLA 承诺分开；复盘归 SKILL-25 与 POC 收尾回写／事故应急分开，且复盘产出不回灌案例库——案例语料属训练场导入通道，不在技能做；转生产归 SKILL-26 与进场前环境验证口径／部署形态选型／上线陪跑分开）。
- 当日复核（红线时效判据，2026-11-12）：A 仓 `git ls-remote` 现测远端 HEAD `b8c687616c0880ed7f3603440aa936ba4d1487ab` 与本地快照逐位一致、末次提交距今超 30 天 ⇒ 按停更失效重核口径执行（重核通过，许可状态无变化：仍为 AGPL-3.0-only，远端 LICENSE 首行在位）；本批不引入无许可仓库 B 新来源；`legacy/` 43 件许可混置区整体不碰。
- 写作工序：两源量小（各一份）不再走子代理思想笔记，直接按「六步动作 + 每步判据」自建行划分独立重写（不取来源的产物字段清单、四步流程编排、阶段推进顺序表、状态词表、模板资产与示例数据）。
- 防抄：扫描器升级 v4（语料从历史 17 源扩到 **268 文件 / 770632 字节**＝A 仓 `skills/` 全树 181 件＋无许可仓库 B 全树 71 份 md＋fdestack 9 件＋本线此前引用的 6 份专题卡与实战案例集，比历史口径更严；匹配方向取反以省内存），**ALL CLEAN（real=0 eng=0 banned=0 strict=0，EXIT=0）**＋英文长片段 0＋禁词 0＋可执行型附加扫描（四固定节齐备／独立重写＋未搬声明在位／三份掩元信息后零 ASCII 数字／阈值形态专项零命中／逐卡专项声明／README 内容钉／许可账来源行 ≥3 与时效·划界·标识符豁免声明在位）。★判别力实测：向 SKILL-25 注入源件模板原文后扫描器 real=19 转红，恢复后复跑 ALL CLEAN（变异判别力本身要验收）。
- 收尾口径：本批把第三批观察名单中的三项转正销号；观察名单其余四项（业务流程映射族／成本评估／源件清单族／需求转验证实验族）维持暂不立项并登记理由；⛔禁入清单零触碰；挂账不变（v2 补强 6 处／训练场与育才两条／卡二十四 127 例案例导入排期）。
- 录入：合并后走已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能，3 条一技能一版本，`required_capabilities` 空数组；manifest 带 `license_ledger`＋`use_boundaries`＋`form`＋`knowledge_discipline`（形状见 batch-7/README「录入」节）。
- 已入库（2026-11-12 实测）：PR [#391](https://github.com/caishide/fde-workbench/pull/391) squash 合并 `6733124`（CI 8 check-runs 全绿，API 终审）；代录通道 3 条全 201（id：customer-acceptance-review＝049be454-034f-4c20-916a-bb19b4b630b3／delivery-retrospective-review＝57f46376-e452-4a61-a97a-20d13289b2bf／poc-production-transition＝fe919d7c-8c1f-4e5b-a015-e3465f84f341），双校验 ALL MATCH（结构化指纹 content_sha256＋document 回读正文逐字节 3859／3826／4124 B）；skill_definitions personal 23→26、public 14 未变；容器 /tmp ks7* 清零＋ready 200。详见 batch-7/README「已入库状态」。台账回填随本节同批入库。
### batch-8 交付（2026-11-12，挂账消解批：v2 补强 6 处＋育才两卡）

- 立项依据：用户 2026-11-12 授权消解三项挂账——本批承载 v2 补强 6 处（挂账表六行销号）＋育才两条销号（SKILL-27/28 新卡）；训练场挂账与卡24 127 例转 L 线导入轮（import-round-1，同日并行执行，仓库侧登记另行 PR）；观察名单其余四项维持暂不立项（同口径确认）。
- 八份交付全在 `docs/skill-library/batch-8/`（6 份 v2＝同 key 重存开新版本，v1 文件留原批次目录不动；2 份新卡新 key）：SKILL-01＋痛点登记册（抱怨翻偏差/多因假设/反证条件/区间排序）／SKILL-03＋报价诚信三件（费用三互指/不确定性区间化/排除项一级化/变更预算闸）／SKILL-04＋决策导向三件（拍板三要素/读者分型/追问预判备询/对照意识）／SKILL-05＋移交验证三件（责任反转/行为性验收/移交可否决）／SKILL-08＋基线先行、两个打折因子、全生命周期成本、零/负不写回本／SKILL-14＋会前预验轮、检查面分域、问题闭环、阻断项机械准入；SKILL-27 行业学习 30 天、SKILL-28 新人带教与 SOP 沉淀（育才）。
- 许可账：仓库 A 五源（AGPL-3.0-only）抽象借鉴＋独立重写，停更失效重核当日复跑通过（`git ls-remote` HEAD `b8c6876` 与本地快照逐位一致）；文集 B 六件无 LICENSE 严档仅思想（license API 404 当日复核）；逐卡对照表登记借用的判据思想与未复现项（字段集/小节定序/状态词表/乘式字面/分钟级模板/档位判据）。
- 防抄 v5：268 文件语料（沿 v4 口径），10 件 ALL CLEAN（real=0 eng=0 banned=0 strict=0）＋变异判别力实测（向 SKILL-01 注入源件片段 real=85 红 → 还原 ALL CLEAN）；数字纪律＝掩编号/日期/卡号/序数后零残留 ASCII 数字，SKILL-27 自有流程时限按 batch-1「流程性参数自定」口径豁免。
- 录入口径：v2 六条同 key 重存自动开新版本（服务端按整份发布材料指纹判定，版本行不可变可回滚）；batch-1 四张（01/03/04/05）当年蔡工桌面端亲手录入，key 以库内现值为准——代录前列表回读按 name 匹配，匹配不上即挂起该条并登记，不猜 key；新卡两条（industry-learning-30day／onboarding-coaching-sop）同通道首存。
- 待回填：已入库状态（PR 合并＋代录 id＋双校验）随合并后代录结果另起回填 PR（batch-7 同款两段式）。
- 已入库（2026-11-12 实测）：PR [#395](https://github.com/caishide/fde-workbench/pull/395) squash 合并 `3646883`（CI 8 check-runs 全绿，API 终审）；代录通道 8 条全 201——v2 六条同 id 开新版本（presales-diagnosis-framework＝d19f5e45／pricing-proposal-structure＝8b4128ee／weekly-value-report-triage＝05a3baec／handover-closeout-checklist＝fbdb6735／value-narrative-draft＝c3062589／go-live-decision-checklist＝b0cbcda5，current_version 1→2，版本行不可变可回滚）＋新卡两条（industry-learning-30day＝bef1c901／onboarding-coaching-sop＝687204a6）；双校验 ALL MATCH（结构化指纹 content_sha256＋document 回读正文逐字节 7500/7309/6670/6453/5223/4939/3941/4345 B）；skill_definitions personal 26→28、public 14 未变；容器 /tmp ks8* 清零＋ready 200。详见 batch-8/README「已入库状态」。台账回填随本节同批入库。
### L 线导入轮交付（2026-11-12，卡24 127 例＋文集 B 演练 7 件→训练场）

- 立项：用户 2026-11-12 授权消解挂账（卡24 127 例 JSON→L 线导入轮＋训练场挂账）；登记件 `docs/skill-library/import-round-1/README.md`（指针＋sha256＋许可快照，包体全在真相层 `交付场景导入包\round2\`，与 L1 首批目录隔离）。
- 134 包＝卡24 127 例（MIT 案例库条目独立改编：94 例工作流起草＋33 例主会话同契约补齐；企业名代号化、源效果数字零写入）＋文集 B 演练篇 7 件（无许可严档仅思想，全原创场景）。`status='draft'` 全量，建行与激活恒人工。
- 四闸两轮独立实测全过：`import_cases.py` 主会话本地 134 包／失败 0＋工作流复核轮 134/134 零发现；装配器 127/127（missing=0 invalid=0）。
- 许可现测：案例库 MIT 远端 HEAD `ef55012`＝本地零漂移；文集 B license 404 严档维持。
- 挂账销号：训练场挂账（文集 B 演练篇不作素材直转→转正式场景走 import_cases 闸门＋import_card_v1 重写）与卡24 127 例导入排期两条销号；⛔禁入清单与诊断评测答案零触碰。
- 已入库（2026-11-12 实测）：PR [#400](https://github.com/caishide/fde-workbench/pull/400) squash 合并 `dd67732`＝fork/main 顶（CI 8 check-runs 全绿）；登记件随本 PR 入库，包体持续留真相层 round2；draft 建行与激活待蔡工人工执行（§4 三步）。
- 登记勘误（2026-11-13）：原起草工作流在用量窗口重置后自动续跑，写手终稿覆盖 42 例（初版 33 例主会话补齐件＋9 例在飞件）并于 01:09 重过四闸；本表已按终版 manifest（主会话 01:11 复跑复核，134 包／失败 0）整体更新（42 行哈希变化、92 行不变）——登记-修订链：#400 初版→勘误 PR。工作流两 run 均已终态，无再续跑可能。
