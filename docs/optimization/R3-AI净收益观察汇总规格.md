# R3-AI净收益观察汇总规格（离线工具）

日期：2026-11-21。状态：工具与口径就绪；无真实用户观察、无人工单价、无AI净收益结论。本工具只处理OWNER授权采集后、执行者在本地转成的代号化 JSON，不采集、不外发、不接生产库。

## 1. 目标与边界

- 复用 [试用观察与人工基线模板](试用观察与人工基线模板.md) 的分母纪律，把多份观察记录机械汇总为可复核读数。
- 只输出观察性聚合：完成率、独立完成率、首次验收通过率、人工投入、返工、总历时、模型费用、每份验收成果模型费用。不推断总体，不自动升档，不设未批准阈值。
- 输入只允许闭合字段；自由文本、姓名、联系方式、原始录屏、真实客户名、标准答案、密钥和单价都拒绝。`observation_id`/`cohort_id` 只允许 1–80 个 UTF-8 字符的代号。
- 人时单价与人工费用不在本工具范围；模型费用只累加观察者提供的计量单位，不折算货币。

## 2. 输入契约

每行/每项记录的字段全部必填，未知写 `null` 或对应枚举，不删除分母：

| 字段 | 闭合取值 | 口径 |
|---|---|---|
| `observation_id` | 代号 | 复核键，输出不回显 |
| `cohort_id` | 代号 | 显式同质组；只有同组人工/AI可对照 |
| `comparison_arm` | `manual` / `ai_assisted` | 对照臂 |
| `attempt_state` | `attempted` / `not_attempted` / `unknown` | 是否已尝试；unknown保留单独列 |
| `result` | `completed` / `failed` / `abandoned` / `unknown` / `not_applicable` | 任务结果 |
| `completion_mode` | `independent` / `assisted` / `not_applicable` | 仅 completed 允许前两者 |
| `first_acceptance` | `passed` / `failed` / `unknown` / `not_entered` | 首次验收；仅 completed 可进入 |
| `accepted` | boolean | 仅 `first_acceptance=passed` 可 true |
| `human_minutes` | number/null | 操作＋复核，不含返工 |
| `rework_minutes` | number/null | 返工 |
| `wall_minutes` | number/null | 开始到收口总历时 |
| `model_cost_units` | number/null | 含失败与重试；manual 必须为 null |

一致性拒绝：未尝试/尝试未知混入完成结果或非空测量；缺失字段返回具体字段名；未 completed 却给完成方式或进入验收；`accepted` 与首次验收不一致；负数、非有限数、布尔冒充数字、未知键。错误只含记录序号、字段名和固定码，不回显值。

## 3. 输出契约

`build_observation_report(records)` 返回 `schema_version=1`、`interpretation="observation_only"`、全局汇总和按 `cohort_id` 的分组汇总。CLI `python scripts/metrics/observation_rollup.py --input <json文件>` 输出同一 JSON；`--input -` 读stdin。非法输入 exit 2，成功 exit 0。

汇总规则：

- `attempted = completed + failed + abandoned + result_unknown`；`not_attempted` 与 `attempt_state_unknown` 不进已尝试分母。
- 尝试为 0 时率指标 `value=null`、`status=insufficient_data`，不报 0% 或 100%。
- `independent + assisted = completed`；失败/放弃/未知保留分母。
- 首次验收分母＝`passed + failed + unknown`；通过率＝passed/分母。
- 活跃人工投入＝`human_minutes + rework_minutes`；总历时单独输出，不用生成或系统等待替代。任一分量为 null，该记录进入对应 unknown 计数，不以零补齐。
- 中位数只基于已知读数；中位数旁保留 known/unknown 计数。
- 每份验收成果模型费用＝AI臂全部已知模型费用之和 / `accepted=true` 数；accepted 为 0 或存在未知 AI 费用时 `value=null`、状态 `insufficient_data`/`incomplete`，不给出偏小值。
- 人工/AI对照只输出同组活跃人工投入与总历时中位数差（模型费用不跨臂相减）；缺任一侧中位数则为 null。所有差异都标观察性证据，不因样本量改变表述。

## 4. 红队压测与停止条件

| 承重假设 | 失效方式 | 机械防线 |
|---|---|---|
| 同一 `cohort_id` 代表可比任务 | 观察者把不同任务塞进同组后求净节省 | 分组只由显式ID聚合；报告不输出跨组合并净节省；`cohort_id` 与任务定义在本地记录核对 |
| 时间字段语义稳定 | 复核/返工重复计时或漏记 | 闭合字段定义分离操作＋复核、返工、总历时；null保留计数，不以零补齐 |
| 模型费用可除以验收成果 | 未知失败成本造成偏小成本 | 任一AI费用未知即拒绝给出每份验收成本；accepted=0显式无数据 |
| 样本可推广到用户群 | 小样本被当成普遍结论 | 输出固定 `observation_only`；工具不设显著性阈值，不输出推广结论 |

真实观察数据、OWNER同意和人工单价仍属外部前提；本工具就绪不销项。

## 5. 验证与交付

- `python -m unittest discover -s tests/metrics -p test_*.py -v（本地合成20例）`
- CI只追加独立测试步骤，不改变既有四job判据。
- 变异检查至少两条：尝试未知进入已尝试分母、未知AI费用仍算每份验收成本，各至少一例转红；还原后复绿。
- 文档只登记口径与合成验证；不登记真实用户结果。
