# 知识库技能第五批（batch-5）——参考型第二批

本批 3 份技能文档全部为**独立重写**：只借鉴来源的思想与判据维度，正文文字、表格结构与每格内容均为本仓原创；来源的结构化表达（条目级清单、分级表、步骤序列、参数表、阈值组合、模板资产与示例数据文件）一律未搬，含改数字、换措辞、重排的等价复现。逐源许可判定见 [LICENSE-AUDIT.md](LICENSE-AUDIT.md)。

来源分两档：**仓库 A**（许可 AGPL-3.0-only，允许改编，本批主动选择更严的独立重写）与**无许可技能仓库 B**（许可字段为空且许可端点取不到内容，声明不等于授权 ⇒ 最严档，只取思想层）。两份参考卡（SKILL-19／SKILL-20）来自仓库 B，技术交付族另有一件（验证环境搭建方向）本批未使用；原定的变更评估单形态本批未动笔，仍留替补位。

## 参考型技能形态（本批沿用，后续 B 桶同形态）

固定五节：**适用场景／速查表／使用纪律／人机边界／来源对照表**。与 batch-2／batch-3 的可执行型差异：正文**不指挥工具动作循环**，不写命令、参数、模板与产物格式，只给方向与判据，供会话中按需查阅引述。

三份卡的数字纪律各不相同：SKILL-19 零业务数字、SKILL-20 零时限零阈值零比例零金额、SKILL-21 零性能数值零容量数字零超时秒数与门槛值。

## 本批清单

| 文件 | key | 主题 | 一句用途 | 来源 |
|---|---|---|---|---|
| `SKILL-19-technical-delivery-reference.md` | `technical-delivery-reference` | 技术交付速查（六个技术场景的方向判据） | 进入客户现场做技术交付前，先对齐该定哪个口径、判据落在哪 | 仓库 B 技术交付族六件（性能调优技／接口联调册／数据接入册／智能体配置／本体建模法／环境排障指） |
| `SKILL-20-client-communication-reference.md` | `client-communication-reference` | 客户沟通速查（七个沟通场景的方向判据） | 与客户、同事、上级谈事情前，先判断该接哪一头 | 仓库 B 客户界面沟通族七件（变更应对策／异议应答框／情绪安抚法／现场汇报技／跨方协同话／预期管理法／高层汇报精） |
| `SKILL-21-deployment-form-reference.md` | `deployment-form-reference` | 部署形态速查（三种交付形态的证据判据） | 客户项目要落成长跑的东西时，先确认形态与证据链够不够 | 仓库 A 部署族三件（容器化交付／受限网络私有化交付／生产验收） |

## 立项依据（2026-11-12 授权继续）

- 用户指令：授权继续（承 batch-4 的 B 桶参考批 1 往下推进）。
- 本批＝B 桶参考批 2：沿用 batch-4 定档的参考型形态，把两仓里「只借思想不搬结构」的剩余面做成第二车参考卡，许可账一次走完。
- 与既有交付面的划界逐行写在各卡的「与本仓既有面的分界」列：性能与压测走客户环境实测、系统与数据清单归获客诊断面、工具授权档位归本仓权限模型面、本体导航归本仓本体能力、应急响应归本仓故障应急响应包、干系人地图归干系人决策地图、高层沟通练习归本仓沟通演练面、需求变更单与汇报材料归交付方案生成面、提问清单归售前诊断框架。
- 与既有批次的分工：SKILL-21 管「产物本身可复现、可回退」与「上线后的实证」，上线就绪检查表管「能不能做上线决定」，两者不重叠。

## 录入

- 录入通道：`POST /api/v1/extensions/skills/personal`（服务端个人技能写面契约，6 键：key／name／description／instructions／manifest／required_capabilities）。
- 一技能一版本；`required_capabilities` 传空数组（参考型不声明工具能力）。
- manifest 形状：`entrypoint`／`format`／`source`／`batch`／`rewrite`／`license_ledger`／`use_boundaries`（when_to_use＋human_boundary）／`references`（required_reading＋authoritative_sources）／`form`／`knowledge_discipline`；`license_ledger` 指向本目录的 LICENSE-AUDIT.md。
- 正文直接粘贴本批对应 md 全文，key 用上表的 key。

## 已入库状态（2026-11-12 实测）

PR #382 squash `d2f233c1`＝fork/main 顶（CI 4 job × 双事件 8 runs 全绿，API 全读 check-runs 终审 success=8／失败=0）后执行导入——POST 全 201、3 条 id（`6863cd96`／`4bc83d2f`／`d56e5692`）、正文逐字节一致＋服务端结构化指纹逐位一致（ALL MATCH: True）、个人技能 18→21 条（batch-1/2/3/4 十八条未受影响）、公共 14 条未变、容器临时文件清零。台账回填随本节同批入库。
