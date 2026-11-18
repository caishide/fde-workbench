# goal-optimize 实际进度

日期：2026-11-18。总Goal保持active；材料、工具、本机验证、CI、合并、活体与用户验收分别记账。

## 目标／顺序／最大风险

1. 让交付稳定、用户可独立完成任务、AI净收益可测；保持技术栈。
2. R0文档→R1a候选核验→R1b部署协调→R1c固定产物/恢复，再推进R2–R5；OWNER项独立备料。
3. 共享部署覆盖与历史证据冒充现测是主要风险；本轮不部署、不改生产配置。
4. 候选通过不等于镜像、数据库或用户任务通过；真实凭据/用户/生产AI授权不从本Goal推定。

## 唯一续跑位置

- 集成树：`D:/node-tools/.codex/worktrees/3177/fde-workbench`；分支`feat/goal-optimize-delivery`；基线`e8253c55`。复制和集成编辑权限已获批，后续仍遵守沙箱。
- 主树`D:/test/fde-workbench`的同名未跟踪文件是先前工作副本，禁止用旧副本覆盖集成树。主树既有代码未由本线修改。
- 最新在途盘点：#524清理文档、#499 ontology；UX #522与仿真 #523已合并。集成前重查，避免覆盖其他线。
- 下一步：提交/push fork→PR四CI绿→合并与主树安全同步；之后细化R1b白名单、接口、反例和回退。

## 分轮状态

| 轮次 | 实现/材料 | 验证 | 交付 |
|---|---|---|---|
| R0 | 建议、leader、进度、待决、观察模板已落盘 | 文档独立审查P2已关闭；leader 2770字符/6节；本地链接核验通过 | 随R1a提交 |
| R1a | 只读CLI与43例测试；CI/README/AGENTS/CHANGELOG已接线 | WSL 43通过、零skip；独立复审阻断项全部关闭 | 未提交/未跑远端CI/未合并 |
| R1b–R1c | 路线已登记，待小规格 | 未验证竞争/恢复 | 未实施/未部署 |
| R2 | 观察模板已备，配置清单待对照源码 | 真实用户与真发信未验 | OWNER前提见BLOCKED |
| R3–R4 | 基线/容量路线已登记 | 未测量净收益与容量 | 未实施 |
| R5 | 本轮入口与进度同步 | 两份手册逐字节相同 | 随轮交付 |

## R1a验证证据

- CLI全套：WSL `python3 -m unittest discover -s tests/deploy -p "test_*.py" -v`，**43 passed / 12.144s / exit0 / 零skip**。真实临时Git仓与子进程，不mock被测核心、不触碰活体。
- 早期Windows版本38例：37通过、1因本机符号链接创建权限不足skip（173.879s）；随后WSL38例全通过（11.958s），补齐循环路径。最新代码以43例WSL结果为准，不能把早期Windows结果冒称最新全套。
- 原有文档闸：`D:/test/fde-workbench/server/.venv/Scripts/python.exe -m pytest --noconftest -p no:cacheprovider server/tests/test_ledger_sync_nail.py server/tests/test_diagnostic_eval_contamination.py -q`，**9 passed / 9.10s / exit0**。两测试是独立纯文件检查，未载入服务端conftest或连库；不替代服务端全量CI。
- 本仓兼容性：只解析89份迁移AST，静态单头`b7f2d9e4c6a8`；现有alembic.ini受支持；未导入/执行迁移，不是数据库升级证据。
- 文档：15个本地链接逐项在场；leader 2770/4000字符；双份操作手册字节一致；git diff --check通过。

## 先红后绿与审查处置

- 工具缺失先红；filter执行反例先红后修，首轮23例通过。
- 独立审查指出Git对象替换、动态元数据、迁移枚举、partial clone、配置间接读文件、3.12循环路径异常和help契约。27例中条件重赋值/AugAssign两例误放行，修复后扩为38例。
- 自审补ignored迁移反例：旧工具误报candidate_consistent；增加目录文件名对账后39例通过。只枚举额外文件名，不读取内容。
- 复审补深缩进filter/include、3.12无值布尔项与Alembic忽略文件名：真实复现filter走到status、include进入Git、AttributeError泄stderr和伪合并误放行。修复为Git配置逐行去缩进后解析、固定错误转换，以及tracked/disk共用文件名选择函数；43例全过。
- 最初上述fixture误用重复core节/两个合并节点，提前触发其他检查；纠正fixture再复现，未把错误夹具计作漏洞关闭证据。
- Git/迁移解析只支持明确声明的本地可信仓静态范围；不自称恶意代码沙箱、原子快照或活体核验。
- 独立审查者只读源码/diff，不执行被审代码；实施者跑测试。最终独立复审确认3项遗留阻断全部关闭，无新增提交阻断；工具指纹0619068761d53525…、测试613593d0df12bcb1…与43例实跑版本一致。

## 技能关卡

已应用leader、fde-delivery-flow、strategy-red-team、tdd、code-review、requesting-code-review、verification-before-completion、neat-freak；桌面/服务端业务未改，不触发打包或生产部署。本轮不得把R1a本地通过等同总Goal完成。
