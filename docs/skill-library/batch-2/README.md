# 知识库技能第二批（batch-2）：4 份可执行技能文档（来源 fdestack · MIT）

> 批量声明：本批 4 份全部为**独立重写**——只借鉴来源的思想、分类维度与判据结构，条目措辞、清单顺序、表格结构、数值参数均为本批原创，未复现任何来源的原文表达（每份已过 3 句×≥15 字片段抽查、15 字滑窗全文扫描与英文长片段零拷贝抽查；命中仅限来源对照表声明的技术标识符，口径见 LICENSE-AUDIT.md）；效果数字与市场数字不入正文。来源许可 MIT（2026-11-12 远端复核），逐源登记见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)。

## 与 batch-1 的形态差异

batch-1 五件是**方法论型**技能（AI 只起草与核对）；本批四件是**可执行技能**——正文指示 AI 用平台现有工具面（项目查询／备忘写入／文档生成）执行动作循环，并全部写明「AI 起草、写入逐次经蔡工确认、排序只读」的人机边界。

## 本批清单

| 文件 | key | 主题 | 一句用途 | 来源技能 |
|---|---|---|---|---|
| `SKILL-06-customer-context-brief.md` | `customer-context-brief` | 客户上下文简报 | 会话开场装载项目背景：简报五块＋增量分流＋确认后落笔 | /customer-context |
| `SKILL-07-poc-retro-learnings.md` | `poc-retro-learnings` | POC 收尾复盘·学习回写 | POC 必回写：三路回写＋零收获追问一次＋复现升级 | /poc＋/engagement-retro |
| `SKILL-08-value-narrative-draft.md` | `value-narrative-draft` | 价值论证段起草 | 单杠杆＋假设三态＋三口径＋防御预演；与 SKILL-03 报价分工不混数 | /value-frame |
| `SKILL-09-cross-project-triage.md` | `cross-project-triage` | 跨项目紧急度排序（只读） | 期限压倒堆积＋未决封顶；可见性过滤是硬边界 | /triage |

## 立项依据（2026-11-12 蔡工拍板）

知识库 party 会议评估 fdestack 八技能后选定的 A 桶四件全做：客户上下文简报＋POC 收尾复盘·学习回写（首选）、价值论证段起草（次选，须与 SKILL-03 划界）、跨项目紧急度排序（须写明可见性边界）。另两座技能仓库的梳理终账、batch-3 立项与禁入清单见 [../PROGRESS.md](../PROGRESS.md)（仓名仅在台账登记，不入本批交付面）。

## 录入

合并后由助理按已授权代录通道（2026-11-12 蔡工口径延续）导入 admin 个人技能；一技能一版本；`required_capabilities` 空数组；manifest 沿 batch-1 形状（`source`=batch-2／独立重写声明／许可账／使用时机／人机边界／引用指针）。

## 已入库状态（2026-11-12，经授权代录）

- 落点：桌面端 **扩展页 → 个人技能**，owner＝admin（`8b29bd77-4f98-40b5-a339-698c22e5f627`），scope=personal，status=published，current_version=1；写入走与 UI 保存同一条正式接口 `POST /api/v1/extensions/skills/personal`，未直写库、未建/改会话；
- 4 条 id：`customer-context-brief`＝`70e1d096…`、`poc-retro-learnings`＝`af9d275a…`、`value-narrative-draft`＝`c3062589…`、`cross-project-triage`＝`f7ca0eaa…`；
- 校验（实测）：`POST` 全 201；`GET /api/v1/skills?scope=personal` 列表 9 条（batch-1 五条未受影响），本批 4 条正文字符数 1267／1296／1108／990 与本仓 md 逐位一致；`GET /api/v1/skills/<id>/document` 的 `body` 与本仓 md 逐字节一致（sha256 相同）且服务端 `content_sha256`（结构化指纹）与本地按服务端算法复算值逐位一致，`ALL MATCH: True`；库内 `skill_definitions`／`skill_versions` 行 9+9 一致，公共技能 14 条未变；
- 容器内临时文件（载荷/执行器/报告）已 `docker exec -u root rm -f` 清零；临时脚本留本机临时目录未入库；
- 后续新版本由蔡工在桌面端亲手录（一人一版本）。
