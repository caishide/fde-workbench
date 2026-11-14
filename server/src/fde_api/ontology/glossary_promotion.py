"""M5-WP3③：Glossary 单向晋升 + ``promoted_readonly`` 只读投影（改进单 4）。

职责（工作令 §3 WP3 条 3）：把项目已确认术语晋升进模板包锚点
（``OntologyTerm.promoted_readonly``，WP2 迁移 ``b2e8d4c6a9f1`` 已落锚点列）
并**单向不可逆**——晋升后术语成为模板包只读投影，任何内容改写路径在
flush 前响亮失败。

锁的落位（D30 架构纪律：不触碰 ``ontology/service.py`` 2102 行守卫）：
术语修订唯一人工路径 = change-set ``update_term``/``merge_terms`` 动物化
（confirm 全成全败事务）——本模块在 ORM 层（``before_update`` 事件，WP2
GateEvaluationReceipt 守卫同款范式）对**已晋升行**的内容列改写抛
``RuntimeError``，service.confirm 的物化 UPDATE 同样被击穿并随事务整体回滚
（全成全败语义 ⇒ 已晋升术语在物化层天然不可变，无需 service 零侵改）。

单向性：``False→True`` 转换（晋升动作本身 + ``promoted_at`` 首写）放行；
已晋升行（库值 True）的内容列（term/definition/term_type/canonical_term_id/
status）改写一律拒绝——status 降级绕道编辑同样在锁内。项目删除走库级
CASCADE 不经 ORM 事件（WP2 回执守卫同款口径）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.ontology.models import OntologyTerm
from fde_api.workbench.models import Project

# 已晋升行的内容锁定列（term_type/canonical_term_id/status 一并入锁——
# 降级/合并绕道编辑与改写定义同罪）
_PROMOTION_LOCKED_COLUMNS = (
    "term",
    "definition",
    "term_type",
    "canonical_term_id",
    "status",
)

# 晋升只读投影清单白名单（对模板包消费方的稳定输出形状）
PROMOTED_TERM_FIELDS = (
    "term_id",
    "term",
    "term_type",
    "definition",
    "promoted_at",
)


class GlossaryPromotionError(ValueError):
    """晋升流失败（code/status 进响应体，形状同 BindingError）。"""

    def __init__(self, message: str, *, status: int = 400, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


# ---------------------------------------------------------------- ORM 晋升锁


@event.listens_for(OntologyTerm, "before_update")
def _promotion_no_content_change(
    mapper: Any, connection: Any, target: OntologyTerm
) -> None:
    """已晋升行内容列改写 → flush 前失败（单向只读投影锁，WP2 守卫同款）。

    判定以 **history.deleted 的旧库值** 为权威：
    - 旧值 False（本次即晋升转换）：放行窗口只允许 ``promoted_readonly`` /
      ``promoted_at`` 本身——内容列同批混写仍拒绝（转换不捎带改写）；
    - 旧值 True 或无变化且当前值 True（库中已晋升）：锁定列任何改写拒绝
      （含 ``promoted_readonly`` True→False 降级绕道）；
    - 未晋升行（旧值 False/None 且当前 False）：零影响，普通编辑照常。
    """
    state = sa_inspect(target)
    history = state.attrs["promoted_readonly"].history
    old_value = (history.deleted or [None])[-1]
    if old_value is False:
        # 晋升转换窗口：内容列同批混写仍禁（转换不捎带改写）
        for attr in _PROMOTION_LOCKED_COLUMNS:
            column_history = state.attrs[attr].history
            if column_history.has_changes() and column_history.deleted:
                raise RuntimeError(
                    "promotion transition must not carry content-column writes "
                    f"(M5-WP3 单向晋升；column={attr})"
                )
        return
    already_promoted = bool(old_value) or bool(target.promoted_readonly)
    if not already_promoted:
        return  # 未晋升行零影响
    for attr in ("promoted_readonly", *_PROMOTION_LOCKED_COLUMNS):
        column_history = state.attrs[attr].history
        if column_history.has_changes() and column_history.deleted:
            raise RuntimeError(
                "promoted_readonly ontology_terms is immutable after promotion "
                f"(M5-WP3 单向晋升；column={attr})"
            )


# ---------------------------------------------------------------- 晋升流


def _load_promotion_project(session: Session, actor: Any, project_id: str) -> Project:
    """S-01：项目不存在或无 manage 权 → 统一 404（不泄露存在性）。"""
    from fde_api.projects.permissions import project_access

    project = session.get(Project, project_id)
    if project is None or not project_access(actor, project).can_manage:
        raise GlossaryPromotionError("project not found", status=404, code="not_found")
    return project


def promote_glossary_terms(
    session: Session,
    *,
    actor: Any,
    project_id: str,
    term_ids: Sequence[str],
) -> dict[str, Any]:
    """批量晋升已确认术语（幂等单向）：锚点落值 + 审计留痕。

    - draft/未确认术语 → 400 ``term_not_confirmed``；
    - 不属于本项目的 term_id → 404（S-01 统一不泄露）；
    - 已晋升行跳过（``duplicated_count``，``promoted_at`` 不重置）。
    """
    from fde_api.projects.events import record_event

    if not isinstance(term_ids, (list, tuple)) or not term_ids:
        raise GlossaryPromotionError("term_ids 必须为非空数组。")
    project = _load_promotion_project(session, actor, project_id)
    rows = session.scalars(
        select(OntologyTerm).where(OntologyTerm.id.in_(list(term_ids)))
    ).all()
    by_id = {row.id: row for row in rows}
    missing = [tid for tid in term_ids if tid not in by_id or by_id[tid].project_id != project.id]
    if missing:
        raise GlossaryPromotionError(
            "术语不存在或不属于本项目。", status=404, code="not_found"
        )

    promoted: list[str] = []
    duplicated: list[str] = []
    now = datetime.now(UTC)
    for tid in term_ids:
        term = by_id[tid]
        if term.promoted_readonly:
            duplicated.append(tid)
            continue
        if term.status != "confirmed":
            raise GlossaryPromotionError(
                f"术语 {term.term!r} 未确认（status={term.status}），不可晋升。",
                code="term_not_confirmed",
            )
        term.promoted_readonly = True  # False→True 转换（锁的唯一放行窗口）
        if term.promoted_at is None:
            term.promoted_at = now
        promoted.append(tid)
    if promoted:
        record_event(
            session,
            actor,
            "glossary_terms_promoted",
            project,
            {"term_ids": promoted, "duplicated_term_ids": duplicated},
        )
    session.commit()
    return {
        "promoted_count": len(promoted),
        "promoted_term_ids": promoted,
        "duplicated_count": len(duplicated),
        "duplicated_term_ids": duplicated,
    }


def list_promoted_terms(
    session: Session, *, actor: Any, project_id: str
) -> dict[str, Any]:
    """晋升只读投影清单（can_view 只读面；稳定白名单形状）。"""
    from fde_api.projects.permissions import project_access

    project = session.get(Project, project_id)
    if project is None or not project_access(actor, project).can_view:
        raise GlossaryPromotionError("project not found", status=404, code="not_found")
    rows = session.scalars(
        select(OntologyTerm)
        .where(OntologyTerm.project_id == project.id, OntologyTerm.promoted_readonly.is_(True))
        .order_by(OntologyTerm.term)
    ).all()
    return {
        "terms": [
            {
                "term_id": row.id,
                "term": row.term,
                "term_type": row.term_type,
                "definition": row.definition,
                "promoted_readonly": True,
                "promoted_at": str(row.promoted_at) if row.promoted_at else None,
            }
            for row in rows
        ]
    }


__all__ = [
    "GlossaryPromotionError",
    "list_promoted_terms",
    "promote_glossary_terms",
]
