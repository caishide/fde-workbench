# 知识库技能第八批（batch-8）——挂账消解批（v2 补强 6 处＋育才两条）

> 批量声明：本批 8 份全部为**独立重写**（v2 六份＝v1 正文主体保留＋补强节注入；育才两份为全新卡）——补强与新增文字只借鉴来源的思想、分类维度与判据结构，条目措辞、清单顺序、表格结构与数值参数均为原创，未复现任何来源的结构化表达（口径见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)）。来源两档：AGPL-3.0-only 仓库 A（抽象借鉴＋独立重写＋对照表）与无开源许可文集 B（**严档仅思想**，逐卡登记未复现项）。真实仓名仅在台账与许可账登记（见 [../PROGRESS.md](../PROGRESS.md)），不入本批交付面。

## 立项依据（2026-11-12 用户授权）

- 用户指令原文：授权继续完成未动部分任务——观察名单其余四项**维持暂不立项**（理由在 batch-7 LICENSE-AUDIT §四）；v2 补强 6 处、训练场/育才挂账、卡24 127 例 JSON→L 线导入轮。
- 本批承载其中两件：**v2 补强 6 处**（挂账表六行销号）与**育才挂账**（两条销号，SKILL-27/28）。**训练场挂账与卡24 127 例**走 L 线导入轮独立执行（import-round-1 登记，不进技能库），与本批同日并行。

## 与前七批的关系

- 形态：可执行型四固定节（适用场景／怎么做／人机边界／来源对照表），承 batch-2／batch-3／batch-7 的可执行形态。
- v2 机制：v2 卡与其 v1 **同 key 不同版本**——库内重存（同一 key 提交、材料变化）自动开新版本，版本行不可变、旧版可回滚；v1 文件留在原批次目录不动（历史记录），v2 文件落本批目录。育才两卡为新 key 新卡。
- 单一权威划界不变：验收签收＝SKILL-24、复盘＝SKILL-25、POC 转生产＝SKILL-26（batch-7）；本批六张 v2 不改划界，只在其域内补强。

## 本批清单

| 文件 | key（库内） | 版本 | 补强来源（匿名档） | 一句用途 |
|---|---|---|---|---|
| `SKILL-01-presales-diagnosis-v2.md` | 以库内现值为准（batch-1 蔡工亲手录入，代录时按 name 现查） | v2 | A·diagnosis/pain-point-analysis | ＋痛点登记册：抱怨翻偏差、多因假设、反证条件、区间排序 |
| `SKILL-03-pricing-proposal-v2.md` | 同上现查 | v2 | A·business/enterprise-ai-pricing | ＋报价诚信三件：费用三互指、不确定性区间化、排除项一级化 |
| `SKILL-04-weekly-value-report-v2.md` | 同上现查 | v2 | B·价值量化呈／高层汇报精（严档） | ＋决策导向三件：拍板三要素、读者分型、追问预判备询 |
| `SKILL-05-handover-closeout-v2.md` | 同上现查 | v2 | A·delivery/delivery-handover | ＋移交验证三件：责任反转、行为性验收、移交可否决 |
| `SKILL-08-value-narrative-draft.md` | `value-narrative-draft` | v2 | A·business/roi-assessment | ＋基线先行、两个打折因子、全生命周期成本、零/负不写回本 |
| `SKILL-14-go-live-decision-checklist.md` | `go-live-decision-checklist` | v2 | B·交付检查单／验收全流程（严档） | ＋会前预验轮、检查面分域、问题闭环、阻断项机械准入 |
| `SKILL-27-industry-learning-30day.md` | `industry-learning-30day` | v1（新） | A·discovery/30-day-industry-learning | 育才：周产物制＋能力证据导向的 30 天行业速攻学习法 |
| `SKILL-28-onboarding-coaching-sop.md` | `onboarding-coaching-sop` | v1（新） | B·新人带教册／SOP编写法（严档） | 育才：三段爬坡带教＋SOP 化触发判据与五面骨架 |

## 录入

- v2 六条：`POST /api/v1/extensions/skills/personal` 同 key 重存——服务端按「整份发布材料指纹」判定，材料变化自动开新版本（个人技能自愈 published），旧版本行不可变可回滚；正文粘贴本批对应 md 全文。
- 新卡两条：同通道新 key 首存（v1）。
- `required_capabilities` 传空数组（可执行型卡不声明工具能力）。
- manifest 形状沿 batch-2..7：`entrypoint`／`format`／`source`／`batch`＝"batch-8"／`rewrite`／`license_ledger`＝"docs/skill-library/batch-8/LICENSE-AUDIT.md"／`use_boundaries`（when_to_use＋human_boundary）／`references`／`form`／`knowledge_discipline`；v2 条另带 `supersedes_version`＝被升级的版本号。
- batch-1 四张（01/03/04/05）当年为蔡工桌面端亲手录入，key 以库内现值为准：代录前先列表回读按 name 匹配，匹配不上即挂起该条并登记，不猜 key。

## 验收口径（本批自检）

- 8 份 SKILL 全过防抄扫描 v5（268 文件语料；15 字滑窗＋英文片段＋禁词＋strict 措辞钉＋数字纪律）；
- LICENSE-AUDIT 逐源登记＋当日远端复核（A 仓 HEAD `b8c6876` 重核通过；B 集 license 404 严档维持）；
- 挂账表六行＋育才两条在 LICENSE-AUDIT §4 逐行销号；训练场与卡24 两件移交 L 线导入轮；
- 观察名单其余四项维持暂不立项（蔡工 2026-11-12 确认），⛔禁入清单零触碰。
