# 知识库技能第四批（batch-4）：2 份参考型技能文档（B 桶参考型第一批）

> 批量声明：本批 2 份为**参考型技能**（速查表＋权威指北，非可执行循环）——SKILL-17 行业速查来自真相层行业案例专题库与蒸馏卡（外部合集无显式许可，按最严档思想层执行，**零业务数字**）；SKILL-18 G 端合规速查来自无许可仓库 B 的 G 端七件（**仅分类维度**，各域内容全部独立撰写、权威锚点直指官方公开文件，每行带「以官方标准原文为准」角标）。逐源登记、29 专题落位口径与防抄实测见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)；真实仓名仅在台账登记（见 [../PROGRESS.md](../PROGRESS.md)），不入本批交付面。

## 参考型技能形态（本批统一，后续 B 桶沿用）

五固定节：**适用场景**（何时查）／**速查表**（核心参考内容）／**使用纪律**（数字打折、权威优先、时效口径）／**人机边界**（AI 只按需引述与指路，对外先经蔡工）／**来源对照表**（独立重写声明＋借鉴层）。与可执行型（batch-2/3）的差异：正文不指挥工具动作循环，只供会话中按需查阅引述。

## 本批清单

| 文件 | key | 主题 | 一句用途 | 来源 |
|---|---|---|---|---|
| `SKILL-17-industry-quick-reference.md` | `industry-quick-reference` | 行业速查 | 十六行业×五列（痛点/入场第一脚/交付要害/红线合规）＋跨行业共性五条；零业务数字 | 真相层案例专题库＋蒸馏卡（思想层） |
| `SKILL-18-gov-compliance-reference.md` | `gov-compliance-reference` | G 端合规速查 | 七域×三列（管什么/权威在哪/交付注意）＋合规角标＋零金额零分数 | 仓库 B G 端七件（仅维度）＋官方公开文件 |

## 立项依据（2026-11-12 蔡工拍板③）

B 桶参考型排期跟着做；第一批＝卡19 行业速查＋仓库 B G 端七件并一车（参考型形态统一、许可账一次走完）。29 专题中本批落地行业速查维度，其余专题落位口径见 LICENSE-AUDIT 第二节（留痕可推翻）。

## 录入

合并后由助理按已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能；一技能一版本；`required_capabilities` 空数组；manifest 沿 batch-3 形状（`source`=batch-4／参考型声明／使用时机／人机边界／引用指针）。

## 已入库状态（2026-11-12，经授权代录通道）

- 落点：桌面端 **扩展页 → 个人技能**，owner＝admin（`8b29bd77-4f98-40b5-a339-698c22e5f627`），scope=personal，status=published，current_version=1；写入走与 UI 保存同一条正式接口 `POST /api/v1/extensions/skills/personal`，未直写库、未建/改会话；
- 2 条 id：`industry-quick-reference`＝`b2e0a4ca…`、`gov-compliance-reference`＝`78615ef9…`；
- 校验（实测）：`POST` 全 201；`GET /api/v1/skills?scope=personal` 列表 18 条（batch-1/2/3 十六条旧记录未受影响），本批 2 条正文字符数 2330／1683 与本仓 md 逐位一致；`GET /api/v1/skills/<id>/document` 的 `body` 与本仓 md 逐字节一致（sha256 相同）且服务端 `content_sha256`（结构化指纹）与本地按服务端算法复算值逐位一致，`ALL MATCH: True`；库内 `skill_definitions`／`skill_versions` 行 18+18 一致，公共技能 14 条未变；
- 容器内临时文件（载荷/执行器/报告）已 `docker exec -u root rm -f` 清零；临时脚本留本机临时目录未入库；
- 后续新版本由蔡工在桌面端亲手录（一人一版本）。
