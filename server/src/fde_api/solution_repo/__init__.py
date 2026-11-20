"""solution_repo 域（AF3 解决方案仓工程闭环，20 号 §3 WP1 起）。

仓库绑定与白名单四拒（WP1）／类型化 Patch 与测试 Diff adapter（WP2）／
固定受信任 CI（WP3）／修复闭环（WP4）／证据绑定与保护路径负向（WP5）。

安全范式沿 AE1 ``action_execution`` 同域先例：FROZEN 快照只读加载
（缺失/损坏 fail-closed）＋闭集精确匹配＋路径白名单四拒（04 §3.3 A1）
＋边界规则机器可检（D2 已批）。
"""
