# BLOCKED — skill-library-batch1（知识库技能首批入库 ks1 线）

## 任务 1 许可实读发现：卡01 登记的「MIT」与远端 LICENSE 实读不符（2026-11-12，证据置顶）

- 任务书「已知」栏：卡01 许良＝MIT ⇒ 可改编。本次按「实读其 LICENSE 或卡内登记」纪律双查，**两者矛盾**：
  - 卡内登记（`cards/01-xuliang-handbook.md` 元数据节，实读）：「开源仓 github.com/RichardXu001/the-fde-handbook（77 stars / MIT）」；
  - 远端 LICENSE 原文实读（gh api contents/LICENSE，2026-11-12）：**自定义非商业许可**——© 2026 许良；允许阅读/学习/非商业转述/引用/分享；**商业用途须书面许可**；任何使用须署名；**未授予修改/演绎权**；GitHub API license 字段＝NOASSERTION/Other；repo pushed_at 2026-09-10（早于卡快照 2026-10-19，即卡登记时点该自定义许可大概率已在场，卡登记疑似据仓库侧栏旧信息或登记笔误）。
- 处置（按让步顺序「许可合规 > 独立重写」）：**卡01 可用层从「可改编」降为「仅抽象借鉴＋署名」**——本批对卡01 只借思想/方法/判据结构、全文独立重写，并在引用该源的技能文档来源对照表内署名（满足其许可的署名义务），不复制不引用任何原文。**五份技能文档主题不变**：独立重写纪律本就对全部来源生效，降级不改变任何一份的写法与交付形态，故无需弃源换题。
- 待裁决：无阻塞项。若领导日后想对卡01 做超出抽象借鉴的使用（如翻译/改编/商用汇编），须先取得著作权人书面许可（LICENSE 尾注联系方式 xuliang001@hotmail.com）；本批不涉及。
- 附带发现（正向）：卡12 本地镜像根 LICENSE 实读＝MIT（Copyright (c) 2026 FDE Knowledge Base Contributors），但随附注记限定「仅覆盖本仓原创正文/模板/清单，第三方摘编除外」——本批对卡12 同样按仅抽象执行，不依赖该 MIT 授权。已如实记入 LICENSE-AUDIT.md。

## 任务 0 核对偏差（2026-11-12 现测）

### 偏差：第 3 条核对「本地 main=fork/main 零差异；fork/main 顶=`e05f1d6`」对不上

- 本次现测（`git -C D:/test/fde-workbench fetch fork` 后）：
  - fork/main 顶＝`c97eedf`「feat(multi-tenant): M5-1 成员邀请面＋M5-2 三档分流入口与六项判据聚合（GAP-05/GAP-14） (#349)」，≠任务书快照值 `e05f1d6`；
  - `git rev-list --count main..fork/main`＝**1**、`git rev-list --count fork/main..main`＝**0** ⇒ 本地 main 落后 fork/main 恰 1 个提交（＝任务书快照 2026-11-11 之后新合并的 PR #349）。
- 定性：任务书快照陈旧（快照后上游推进一笔已合并提交），非仓库分叉/损坏。
- 影响面评估：①源材料两条核对全过——卡数 `ls cards | wc -l`＝24、许良抽取件在场（`FDE-企业AI落地实战手册-许良_extracted.txt`），原料与任务书完全一致；②任务书给定的 worktree 命令本就从 fork/main 现值建分支（实测建出 `c97eedf`）；③交付物纯文档，全部验收命令为相对口径（`git log fork/main..skill-library-batch1`、grep/ls 循环），不依赖具体基线哈希。⇒ **无受影响部分，按「只做不受影响的部分」继续全量施工**。
- 附注：任务书明令「不许动 main」，且主工作树被另一条线占用（现检出 `docs/case-learning-ledger-backfill`）——main 的 ff 归属方，不在本线职责内。
- 待裁决：无（快照陈旧类偏差，按现测值走；若领导认为必须以 `e05f1d6` 为基线，将本分支 rebase 过去即可，交付物为全新目录零冲突）。

## 正式 BLOCKED 项

- 无（截至本文件随交付提交时点）。
