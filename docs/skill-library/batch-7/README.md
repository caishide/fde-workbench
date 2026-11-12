# 知识库技能第七批（batch-7）——A 桶观察名单转正批（交付收口三件）

> 批量声明：本批 3 份全部为**独立重写**——只借鉴来源的思想、分类维度与判据结构，条目措辞、清单顺序、表格结构与数值参数均为本批原创，未复现任何来源的原文表达（每份已过 15 字滑窗全文扫描、英文长片段抽查、可执行型附加扫描与禁词零命中，口径见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)）；效果数字与时限参数不入正文，承诺类时限一律交由合同或实测数据。来源一档：AGPL-3.0-only 仓库（A，借鉴判据结构＋独立重写，**主动选择更严的独立重写**）；逐源登记与当日远端复核记录见 LICENSE-AUDIT.md，真实仓名仅在台账登记（见 [../PROGRESS.md](../PROGRESS.md)），不入本批交付面。

## 与前六批的关系

- 形态：batch-1 方法论型／batch-2 可执行型／batch-3 可执行型七件／batch-4 参考型两件／batch-5 参考型三件／batch-6 参考型两件（收尾车）。本批回到**可执行型四固定节**（适用场景／怎么做／人机边界／来源对照表），正文指示 AI 用平台现有工具面动作并逐条写明人机边界——承 batch-2／batch-3 的可执行形态，与 batch-4 至 batch-6 的参考形态不同族。
- 立项由来：第三批观察名单（不在七主力内、暂不立项）里挂着三件交付收口方向的候选面——**企业验收／项目复盘／POC 转生产**。挂起原因是「权威归属或与既有面的划界先行」；batch-2 至 batch-6 全部交付后，划界前提具备，本批**转正**为三份可执行型卡。
- 本批内部互链成一条交付收尾主线：客户验收判定（24）→ 项目复盘（25）→ POC 转生产（26）——同一段交付的三种收口视角：对外签收判定、事后归因沉淀、验证转正式环境的推进。
- 单一权威划界：验收签收＝SKILL-24（上线放行决策、撤场交接、SLA 承诺条款各归既有面）；项目级复盘＝SKILL-25（POC 段收尾回写、故障应急处置各归既有面；**复盘产出不回灌案例库**，案例语料走训练场案例导入通道）；验证转生产＝SKILL-26（验证进场前的环境与验证口径、部署形态选型、上线后护航各归既有面）。

## 本批清单

| 文件 | key | 主题 | 一句用途 | 来源（仓·文件） |
|---|---|---|---|---|
| `SKILL-24-customer-acceptance-review.md` | `customer-acceptance-review` | 客户验收判定 | 口径先定、逐条对账、物／用／值三层各判、遗留项三要素、签收口径与结论三选一 | A·delivery/enterprise-acceptance |
| `SKILL-25-delivery-retrospective-review.md` | `delivery-retrospective-review` | 交付复盘 | 一次一问、事实与回忆分开写、归因三类落位、三类分流、改进项三要素、只走既有通道回灌 | A·delivery/project-retrospective |
| `SKILL-26-poc-production-transition.md` | `poc-production-transition` | POC 转生产 | 转段前提三问、差异清单六覆盖、临时物一律重来、分批放开的进入／观察／退出、双负责人值守、销账判定 | A·deployment/poc-to-production |

观察名单其余四项（业务流程映射族／成本评估／源件清单族／需求转验证实验族）维持暂不立项，理由与去处在 LICENSE-AUDIT §四。

## 立项依据（2026-11-12 授权继续）

- 用户指令：继续（承第六批往下推进；按「按推荐执行＋留痕可推翻」先例解释为推进 A 桶观察名单转正批）。
- 选题依据：第六批为 B 桶参考型收尾车，两仓已点名的候选面全部归位；下一批须回到 A 桶未立项面。第三批观察名单挂起的原因是「权威归属或与既有面的划界先行」，该前提在 batch-2 至 batch-6 交付完成后已具备。
- 与既有面的划界逐行写在各卡「不适用」行与来源对照表（见上节单一权威划界），真实来源件名只在台账与许可账登记。

## 录入

- 录入通道：`POST /api/v1/extensions/skills/personal`（服务端个人技能写面契约，6 键：key／name／description／instructions／manifest／required_capabilities）。
- 一技能一版本；`required_capabilities` 传空数组（可执行型卡不声明工具能力，正文用平台既有工具面动作）。
- manifest 形状：`entrypoint`／`format`／`source`／`batch`＝"batch-7"／`rewrite`／`license_ledger`（指向本目录 LICENSE-AUDIT.md）／`use_boundaries`（when_to_use＋human_boundary）／`references`（required_reading＋authoritative_sources）／`form`／`knowledge_discipline`。
- 正文直接粘贴本批对应 md 全文，key 用上表的 key。

## 已入库状态（2026-11-12 实测）

- PR：[#391](https://github.com/caishide/fde-workbench/pull/391) 已 squash 合并（`6733124`），CI 8 check-runs 全绿（API check-runs 终审）。
- 代录：已授权代录通道（2026-11-12 蔡工口径延续）3 条全部 `POST /api/v1/extensions/skills/personal` 成功（HTTP 201，一技能一版本 v1）：
  - `customer-acceptance-review` → id `049be454-034f-4c20-916a-bb19b4b630b3`
  - `delivery-retrospective-review` → id `57f46376-e452-4a61-a97a-20d13289b2bf`
  - `poc-production-transition` → id `fe919d7c-8c1f-4e5b-a015-e3465f84f341`
- 双校验 **ALL MATCH**：①服务端结构化指纹 `content_sha256`（规范化 JSON 的 sha256）与本地载荷重算逐位一致；②`GET /skills/<id>/document` 回读正文与本批 md 文件逐字节一致（3859／3826／4124 B，body sha256 逐位一致）。
- 库内核验：`skill_definitions` scope=personal 23→**26** 行（三条均 published v1），`scope=public` **14** 行未变。
- 容器清场：`/tmp/ks7*` 已清零，`/api/v1/health/ready` 复探 200。
- 台账回填随本节同批入库（PROGRESS.md batch-7 节已入库 bullet）。
