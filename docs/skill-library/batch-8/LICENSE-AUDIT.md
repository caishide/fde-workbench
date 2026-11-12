# batch-8 许可与来源账（挂账消解批：v2 补强 6 处＋育才两条）

> 本批为**既有卡的 v2 升级（6 份）＋育才新卡（2 份）**。全部为独立重写（v2 部分只借思想与判据结构；文集 B 系来源为无许可仓库，按最严档仅思想执行）。逐源登记与 2026-11-12 当日远端复核记录如下。

## §1 来源逐件登记

| 来源 | 许可（实读依据） | 快照/复核 | 用于 | 可用层 |
|---|---|---|---|---|
| 仓库 A `skills/diagnosis/pain-point-analysis/`（含 SKILL.md＋assets＋examples 共 3 件） | AGPL-3.0-only（远端 LICENSE 在位） | HEAD `b8c6876`，2026-11-12 `git ls-remote` 与本地快照逐位一致 | SKILL-01 v2 | 抽象借鉴＋独立重写＋对照表 |
| 仓库 A `skills/business/enterprise-ai-pricing/`（3 件） | 同上 | 同上 | SKILL-03 v2 | 同上 |
| 仓库 A `skills/business/roi-assessment/`（3 件） | 同上 | 同上 | SKILL-08 v2 | 同上 |
| 仓库 A `skills/delivery/delivery-handover/`（3 件） | 同上 | 同上 | SKILL-05 v2 | 同上 |
| 仓库 A `skills/discovery/30-day-industry-learning/`（3 件） | 同上 | 同上 | SKILL-27 新卡 | 同上 |
| 文集 B `04-B端企业专项/价值量化呈.md`、`07-客户界面沟通/高层汇报精.md` | **无 LICENSE**（GitHub license API 复核 404，2026-11-12；README 徽章自称 MIT 无背书，沿卡01「claim≠grant」先例） | 2026-11-12 当日复核 | SKILL-04 v2 | **严档仅思想**：清单/分级表/时钟分段/阈值组合禁写入含等价复现 |
| 文集 B `01-全流程SOP/交付检查单.md`、`01-全流程SOP/验收全流程.md` | 同上 | 同上 | SKILL-14 v2 | 同上 |
| 文集 B `08-交付沉淀知识/新人带教册.md`、`08-交付沉淀知识/SOP编写法.md` | 同上 | 同上 | SKILL-28 新卡 | 同上 |
| fdestack `/value-frame`（SKILL-08 v1 既有来源，本批未新增接触） | MIT（Dan-Cleary/fdestack） | 快照 `5524460`（2026-05-19），batch-2 登记沿用 | SKILL-08 v2（承 v1） | 可改编（本卡按独立重写执行） |
| 卡01／卡08／卡11／卡12（batch-1 既有来源，本批未新增接触） | 见 batch-1/LICENSE-AUDIT.md | 沿袭 | SKILL-01/03/04/05 v2 正文主体 | 沿袭各卡 v1 口径 |

仓库 A／文集 B 真实仓名的台账登记见 [../PROGRESS.md](../PROGRESS.md)（两仓梳理总账节），不入本批交付面。

## §2 时效复核（红线第 8 条④）

- 仓库 A 末次提交 2026-10-07，距本批复核日 36 天 > 30 天 ⇒ 本地快照**停更失效重核**：`git ls-remote` 实测远端 HEAD `b8c687616c0880ed7f3603440aa936ba4d1487ab` 与本地快照逐位一致，LICENSE 无变化（AGPL-3.0-only）⇒ 重核通过（与 batch-7 同日同源，本批独立复跑）。
- 文集 B：license API 实测 404（无 LICENSE 文件）⇒ 严档维持。
- fdestack：本批零新增接触，v1 快照沿用。

## §3 独立重写声明与防抄口径

1. v2 六份＝v1 正文主体保留＋补强节注入；补强文字全部独立重写，逐卡在来源对照表新增「v2 补强」行登记借用的判据思想与**未复现清单**（源字段集、小节定序、状态词表、乘式字面、域内条目、分钟级模板、档位判据等）；
2. 育才两份为全新独立重写，来源对照表登记借用维度与未复现项；
3. 防抄：15 字滑窗全文扫描＋英文 ≥15 字符片段抽查＋strict 措辞钉；语料沿用 v4 的 268 文件口径（本批新读源件全部已在其内——仓库 A `skills/` 全树与文集 B 全树），扫描对象换为本批 10 件交付面；命中即改写，禁词表（评测答案目录名与两仓实名，同 batch-2..7 扫描器口径，此处不列举）对交付面零命中；**标识符豁免口径**＝来源对照表声明的标识符子串（源件路径/件名/key/许可串），其余命中即失败；数字纪律沿 batch-7：掩掉编号/日期/哈希后零残留 ASCII 数字，SKILL-27 的自有流程时限（第 N 周／30 天）按 batch-1「流程性参数自定不受限」口径豁免；
4. 评审否决等价复现：凡与本批源件在清单结构、表格编排、阈值组合上等价的段落，按红线第 8 条②否决。

## §4 落位与挂账销号

- **挂账表六行全部销号**：delivery-handover→SKILL-05 v2；enterprise-ai-pricing→SKILL-03 v2；roi-assessment→SKILL-08 v2；pain-point-analysis（痛点登记思想）→SKILL-01 v2；价值量化呈／高层汇报精→SKILL-04 v2；交付检查单／验收全流程→SKILL-14 v2。
- **育才两条挂账销号**：30-day-industry-learning→SKILL-27 新卡；新人带教册／SOP编写法→SKILL-28 新卡。
- **训练场挂账移交**：文集 B「10-实战演练提升」7 件按原口径转 L 线导入轮执行（思想重写为 import_card_v1 场景卡，走 `import_cases` 四闸），不进技能库——见 import-round-1 登记。
- **观察名单**：其余四项（业务流程映射族／成本评估／源件清单族／需求转验证实验族）维持暂不立项——蔡工 2026-11-12 授权口径确认「维持暂不立项（理由在 batch-7 LICENSE-AUDIT §四）」，本批零触碰。
- **⛔禁入清单**：零触碰（pain-point-analysis 仅以「痛点登记思想」并入 SKILL-01，未单独立项，与挂账表原口径一致）。
