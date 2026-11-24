"""模板选择契约——从模板快照挑模块建项目时的形状校验（2026-11-25）。

**为什么需要它**：行业模板（``seed_industry_templates``）按设计**只建模块与调研表、
不建任务行**（通用模板才有完整任务图）。用这类模板建项目时，项目树建不出任务与
排程：原实现按模块归集任务时抛 ``KeyError``，被 ``create_project`` 的兜底
``except Exception`` 吞成**不可读的 503 project_creation_failed**——而
``raise ... from None`` 还会把原始 traceback 一并抹掉，调用方拿不到任何线索。

**契约**：被选模块必须带任务行，否则「模板形状不满足立项前提」当场判成 400
（``template_module_without_tasks``），与服务层既有的 ``module_not_in_template``
（400）、``missing_required_module_dependency``（400）同类——都是模板形状问题，
不是服务端故障。

**归属**：形状校验归模板域，故本模块落在 ``templates`` 包；``projects`` 侧消费
（``projects/service.py`` 的立项路径）。``templates`` 不依赖 ``projects``，
无包级导入环。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fde_api.templates.service import TemplateServiceError


def select_modules_for_project(
    snapshot: Mapping[str, Any], module_keys: Sequence[str]
) -> list[dict[str, Any]]:
    """按 ``module_keys`` 从模板快照里挑模块，并校验形状可支撑立项。

    三条校验（任一不满足即 400，且错误消息指名具体模块/任务）：

    1. ``module_not_in_template``——所选模块必须属于该模板版本；
    2. ``template_module_without_tasks``——**所选模块必须带任务行**
       （行业模板按设计无任务行，用它建项目建不出任务与排程）；
    3. ``missing_required_module_dependency``——所选模块的任务若依赖未选中的
       模块任务，必须一并选中。

    抛 ``TemplateServiceError``；``projects`` 侧立项路径把它转成同码同状态的
    ``ProjectServiceError``，对外契约不变。
    """
    modules_by_key = {module["module_key"]: module for module in snapshot["modules"]}
    missing = set(module_keys) - modules_by_key.keys()
    if missing:
        raise TemplateServiceError(
            "module_not_in_template",
            "Every selected module must belong to the template version.",
            400,
        )
    selected = sorted(
        (modules_by_key[key] for key in module_keys),
        key=lambda module: (module["sort_order"], module["id"]),
    )
    without_tasks = sorted(
        str(module["module_key"]) for module in selected if not module["tasks"]
    )
    if without_tasks:
        raise TemplateServiceError(
            "template_module_without_tasks",
            "Selected template modules must contain task definitions: "
            + ", ".join(without_tasks),
            400,
        )
    selected_task_keys = {
        task["task_key"] for module in selected for task in module["tasks"]
    }
    task_module_by_key = {
        task["task_key"]: module["module_key"]
        for module in snapshot["modules"]
        for task in module["tasks"]
    }
    missing_dependencies = sorted(
        (
            task_module_by_key[dependency_key],
            dependency_key,
            module["module_key"],
            task["task_key"],
        )
        for module in selected
        for task in module["tasks"]
        for dependency_key in task["dependency_keys"]
        if dependency_key not in selected_task_keys
    )
    if missing_dependencies:
        predecessor_module, predecessor_task, successor_module, successor_task = (
            missing_dependencies[0]
        )
        raise TemplateServiceError(
            "missing_required_module_dependency",
            f"Module '{successor_module}' task '{successor_task}' requires "
            f"module '{predecessor_module}' task '{predecessor_task}'.",
            400,
        )
    return selected
