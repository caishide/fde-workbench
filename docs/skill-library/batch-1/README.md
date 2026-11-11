# 知识库技能首批（batch-1）：5 份独立重写技能文档

> 本批把外部知识库提取卡层已蒸馏的交付方法论，独立重写成 5 份可直接录入技能中心的技能文档。**批量声明：本批 5 份文档全部为独立重写**——只借鉴来源的抽象思想、分类维度与判据结构，条目措辞、清单顺序、表格结构均为本批原创，未复现任何来源的原文表达（每份已通过 3 句×≥15 字片段抽查与 15 字滑窗全文双重扫描）；效果数字与市场数字一律不入正文，一切幅度表述以客户自身基线为准。

## 本批清单

| 文件 | 主题 | 一句用途 | 来源卡 |
|---|---|---|---|
| `SKILL-01-presales-diagnosis.md` | 售前诊断提问框架 | 把客户模糊的愿望问成一句可检验、可定价、可验收的问题陈述 | 卡01＋卡11 |
| `SKILL-02-gate-review-discipline.md` | 门禁评审怎么开 | 在阶段交界处组织凭证据说话、三态结论、记录可追溯的评审（清单本体以 `server/seeds/gates.json` 为唯一权威，本文不复述） | 卡01＋卡05 |
| `SKILL-03-pricing-proposal.md` | 报价结构与收费口径 | 报价五段骨架、科目自查、四本账分离与按结果计费的前提判据 | 卡08＋卡01 |
| `SKILL-04-weekly-value-report.md` | 客户周报价值三分法 | 每条进展先定证据状态再写内容：已坐实／在做／存疑三桶，管理层三分钟读完 | 卡12＋卡11 |
| `SKILL-05-handover-closeout.md` | 移交撤场要点 | 撤场六件事＋三条可撤场判据：离场后客户自己转得动，我方零隐性义务 | 卡01 |

许可与出处逐源登记见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)（本批先许可后动笔；其中卡01 的许可实读与卡内登记不符，已按最保守层执行并登记）。

## 录入指引（蔡工亲手录）

1. 打开桌面端 **扩展页 → 个人技能**；
2. **一技能一版本**：每份 SKILL 文档录成一个独立技能（如「售前诊断提问框架 v1」），版本号从 1 起记；
3. **正文直接粘贴**：以各文件「适用场景 → 怎么做 → 人机边界」为主体粘贴；「来源对照表」节随正文一并保留（它是许可合规的一部分，勿删）；
4. 录入动作原则上由蔡工在桌面端亲手完成——本批仓库交付本身不写数据库、不代录技能中心。**例外（2026-11-12 经蔡工授权）**：batch-1 这 5 份已由助理代录到 admin 账号的个人技能，见下节「已入库状态」。

## 已入库状态（2026-11-12，经授权代录）

- 落点：桌面端 **扩展页 → 个人技能**，owner＝`admin`（`8b29bd77-4f98-40b5-a339-698c22e5f627`），scope=personal，status=published，current_version=1；
- 写入路径：与 UI 保存同一条正式接口 `POST /api/v1/extensions/skills/personal`，未走任何后门或直写库；
- 5 条 key ↔ 文件对应：`presales-diagnosis-framework`↔SKILL-01、`gate-review-discipline`↔SKILL-02、`pricing-proposal-structure`↔SKILL-03、`weekly-value-report-triage`↔SKILL-04、`handover-closeout-checklist`↔SKILL-05；
- 校验口径：`GET /api/v1/skills?scope=personal` 列出 5 条、正文字符数 1885／1684／1814／1583／1635 与本仓 md 逐位一致；`GET /api/v1/skills/<id>/document` 的 `body` 与本仓 md 逐字节一致（sha256 相同）；`GET /api/v1/extensions` 中 5 条 personal 技能 `can_edit=true` 可见，公共技能 14 条未受影响；
- 能力声明：`required_capabilities` 一律留空数组（方法论型技能，AI 只起草与核对；空能力集对任何档位可用）；
- manifest：沿用 UI 缺省 `{entrypoint:"SKILL.md", format:"markdown"}`，另附 `source`／`batch`／`rewrite`（独立重写声明）／`license_ledger`／`use_boundaries`（使用时机＋人机边界）／`references`（必读件与权威指针）元信息；桌面端不解析附加键，仅透传；
- 后续新版本仍由蔡工在桌面端亲手录（一人一版本，版本号从 1 起记）。

## 防抄自检口径（留档）

- 每份 3 句 × ≥15 字连续片段，对其来源卡与抽取件 `grep -F` 零命中；
- 每份全文 15 字滑窗对全部 9 个源文件（5 卡＋4 抽取件）扫描零重合；
- 禁止效果数字／市场数字入正文；禁止原文短引用（含带引号的卡内引语）。
