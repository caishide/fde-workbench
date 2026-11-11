# BLOCKED — 待裁决清单（随交付提交）

## 任务 0 现状核对偏差（2026-11-12 现测，证据在最上面）

### 偏差 ①：diagnostics 文件数「11」对不上

- 任务书口径：`server/src/fde_api/diagnostics/`＝11 文件。
- 本次现测：**10 个 .py 文件（含 `__init__.py`）／9 个（除 init 计）**，无子目录、无隐藏文件：
  `__init__.py / assessment.py / jobs.py / models.py / policy_data.py / prompts.py / questionnaire.py / report_contract.py / routes.py / service.py`（`find server/src/fde_api/diagnostics -type f -name "*.py"` 实测输出）。
- 处置：疑为任务书把 `__pycache__` 或计数口径差计为 11。**结构性结论（9 路由／部署闸／R-1~R-7 契约／judge 方法论）全部核对吻合，不受影响，继续施工**；设计稿 §1 一律采用本次现测值。待裁决：无需（计数口径差，按现测值走）。

### 偏差 ②：「AI 单一入口纪律」作为两模块**已共享面**按字面不成立

- 现测：**diagnostics** 经 `execute_ai_prompt` 单一入口（`server/src/fde_api/control/ai_server_client.py:317` 定义；`server/src/fde_api/diagnostics/jobs.py:38` import、`:165` 调用——预算闸与 N2 归因都在此入口内）。
  **translator** 不走该入口——经 `DeepSeekClient` 直连文本 JSON 栈（`server/src/fde_api/translator/jobs.py:20` import、`:252-261` `_client` 构造；模块 docstring `:14-16` 载明 goal-d14 拍板「与 AI 聊天同源解析模型」），仅复用该模块的 `ai_actor_id` 上下文（`translator/jobs.py:66`）。
- 影响面：设计稿 §4（评分移植）必须显式回答「评分/评测跑在哪条通道」——本设计稿按「评测与 judge 只在评测脚本侧运行、生成器各走各的既有生产通道」设计，不动两模块既有通道；是否在后续轮统一 AI 入口属独立裁决，**不在本设计稿默认范围**。
- 处置：设计稿如实记录双通道现状；待裁决项＝「后续是否统一两模块 AI 调用入口（如 translator 迁往 execute_ai_prompt）」——建议挂领导拍板设计稿时一并裁定，本包不预设结论。

## 待裁决（正式 BLOCKED 项）

- 无其余待裁决项。顺手活（修 bug/重构/改配置/装依赖）未遇到，零登记。
- 设计稿红线扫描（客户真实资料／诊断答案材料／第三方结构化表达复制）：写作时逐节自检，未撞上；若评审发现撞面，按规矩登记本文件不写入。
