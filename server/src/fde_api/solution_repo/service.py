"""solution_repo 服务面（AF3-WP1）：仓库绑定＋读面＋状态面＋分支面。

纪律：
- **租户绑定服务端强制**（任务书 §15；沿 AE1 ``submit_action`` 口径）：一律以
  ``actor.org_id`` 过滤，不盲信请求体 org_id；跨租户 404 不泄露；
- **不进他人 dirty tree**（04 §3.3）：绑定时刻 porcelain 非空即 409；
- **四拒 fail-closed**（04 §3.3 A1）：读面前先 ``check_path``（形状）再
  ``check_path_fs``（symlink 实探）；
- **撤权即时生效**（AF1② 同构）：``revoked`` 后一切操作面 403 permission_revoked；
- **停点纪律**（AF2① 携带）：branch 缺失/allow_roots 空＝422，禁臆造参数继续；
- session 纪律沿 AE1 ``_ae_session``（``db.session()`` 全新 Session 用完即还，
  同一 session 变量贯穿查询与赋值）。

审计口径（WP1 范围声明）：bind/revoke 落 ``audit_json`` 事件；read/status/
branch_create 计数累加。结构化审计台账归 WP5 证据绑定面（20 号 §3 WP5）。
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from fde_api.extensions import db
from fde_api.solution_repo.errors import SolutionRepoError
from fde_api.solution_repo.git_ops import GitFailed, GitRunner
from fde_api.solution_repo.models import RepoBinding
from fde_api.solution_repo.path_guard import Verdict, check_path, check_path_fs
from fde_api.solution_repo.snapshot import load_whitelist

_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

# verdict.code → 域错误码（errors.py 闭集映射；403 面＝保护路径，422 面＝形状/越界）
_VERDICT_ERRORS: dict[str, str] = {
    "protected_path": "protected_path_rejected",
    "path_escape": "path_escape_rejected",
    "outside_allow_roots": "outside_allow_roots",
    "symlink_escape": "symlink_escape_rejected",
    "oversize_patch": "oversize_patch",
}

_VERDICT_MESSAGES: dict[str, str] = {
    "protected_path_rejected": "保护路径拒绝（.git/**、hooks、.github/workflows/**）。",
    "path_escape_rejected": "路径穿越形态拒绝（..、绝对路径、盘符、反斜杠）。",
    "outside_allow_roots": "越界路径（不在绑定 allow_roots 内）。",
    "symlink_escape_rejected": "符号链接逃逸拒绝。",
    "oversize_patch": "Patch 超出上限（bytes/files/lines）。",
}


def _verdict_error(verdict: Verdict, path: str) -> SolutionRepoError:
    code = _VERDICT_ERRORS[verdict.code]
    return SolutionRepoError(
        code,
        _VERDICT_MESSAGES[code],
        details={"path": path, "reason": verdict.reason},
    )


@contextmanager
def _sr_session() -> Iterator[Any]:
    """``db.session()`` 用后即还连接（沿 AE1 ``_ae_session`` WP5-B 登记口径）。"""
    session = db.session()
    try:
        yield session
    finally:
        session.close()


def _validate_branch_name(name: Any) -> str:
    if not isinstance(name, str) or not name or len(name) > 128:
        raise SolutionRepoError("validation_failed", "branch 名须为 1..128 字符字符串。")
    if not _BRANCH_RE.match(name):
        raise SolutionRepoError("validation_failed", "branch 名含非法字符或以非法字符开头。")
    if ".." in name or "//" in name or name.endswith("/") or name.endswith(".lock"):
        raise SolutionRepoError("validation_failed", "branch 名含非法序列（..、空段、.lock 结尾）。")
    return name


def _validate_allow_roots(allow_roots: Any) -> list[str]:
    if not isinstance(allow_roots, list) or not allow_roots:
        # 停点纪律：allow_roots 空＝禁臆造（不默认放全仓）。
        raise SolutionRepoError("validation_failed", "allow_roots 须为非空数组（禁臆造参数）。")
    whitelist = load_whitelist()
    deny_semantics = whitelist["path_rules"]
    roots: list[str] = []
    for root in allow_roots:
        if not isinstance(root, str) or not root.endswith("/") or "/" in root.rstrip("/"):
            raise SolutionRepoError(
                "validation_failed",
                "allow_roots 条目须为形如 'dir/' 的单层目录前缀。",
                details={"root": root},
            )
        # 白名单自身不得引入四拒路径：对 '<root>/probe' 走形状面判定。
        probe = check_path(root + "probe", allow_roots=(root,))
        if not probe.ok:
            raise SolutionRepoError(
                "validation_failed",
                f"allow_roots 条目含保护路径部件：{root}",
                details={"root": root, "reason": probe.reason},
            )
        roots.append(root)
    del deny_semantics
    return roots


def _load_binding(session: Any, actor_org: str, binding_id: str, *, allow_revoked: bool = False) -> RepoBinding:
    """按租户加载绑定行；跨租户/不存在 404 不泄露；revoked 默认 403（撤权即时生效）。"""
    row = session.get(RepoBinding, binding_id)
    if row is None or row.org_id != actor_org:
        raise SolutionRepoError("not_found", "绑定不存在。")
    if row.status == "revoked" and not allow_revoked:
        raise SolutionRepoError("permission_revoked", "绑定已撤销，操作面已停。")
    return row


def _touch_audit(session: Any, row: RepoBinding, event: str, details: dict[str, Any] | None = None) -> None:
    """审计计数＋事件累加（bind/revoke 落事件；读面计数）。"""
    audit = dict(row.audit_json or {})
    ops = dict(audit.get("ops") or {})
    ops[event] = int(ops.get(event) or 0) + 1
    audit["ops"] = ops
    if event in ("bind", "revoke"):
        events = list(audit.get("events") or [])
        events.append({"event": event, "details": details or {}})
        audit["events"] = events[-20:]
    row.audit_json = audit


def bind_repo(actor: Any, payload: Any) -> dict[str, Any]:
    """绑定受控示例仓：git 仓校验→dirty tree 校验→分支创建→白名单快照落行。"""
    if not isinstance(payload, dict):
        raise SolutionRepoError("validation_failed", "请求体须为 JSON 对象。")
    repo_root = payload.get("repo_root")
    workspace_root = payload.get("workspace_root") or repo_root
    branch = _validate_branch_name(payload.get("branch"))
    allow_roots = _validate_allow_roots(payload.get("allow_roots"))
    if not isinstance(repo_root, str) or not repo_root:
        raise SolutionRepoError("validation_failed", "repo_root 须为非空字符串。")

    repo_path = Path(repo_root)
    ws_path = Path(workspace_root) if isinstance(workspace_root, str) and workspace_root else repo_path
    if not repo_path.is_dir():
        raise SolutionRepoError("validation_failed", f"repo_root 不存在：{repo_root}")
    try:
        repo_resolved = repo_path.resolve()
        ws_resolved = ws_path.resolve()
        if not ws_resolved.is_relative_to(repo_resolved):
            raise SolutionRepoError("validation_failed", "workspace_root 须位于 repo_root 内。")
    except OSError as exc:
        raise SolutionRepoError("validation_failed", f"路径解析失败：{exc}") from None

    runner = GitRunner(repo_resolved)
    try:
        inside = runner.run_ok("rev-parse", "--is-inside-work-tree")
        if inside != "true":
            # 探测失败（退码非零）＝非 git 仓：请求形状级问题 → 422，不是执行层 500。
            raise SolutionRepoError("validation_failed", "repo_root 不是 git 工作树。")
        porcelain = runner.run("status", "--porcelain")
        if porcelain:
            # S-AF3-08：不进他人 dirty tree。
            raise SolutionRepoError(
                "dirty_tree_conflict",
                "目标工作树存在未提交变更（不进他人 dirty tree）。",
                details={"porcelain_rows": porcelain.splitlines()[:20]},
            )
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None

    # 重复绑定裁决先行：同 (org, repo_root, branch) 已有绑定行 → 409
    # binding_exists（分支是此前绑定自建的——让重复绑定伪装成 422「分支已
    # 存在」会把幂等冲突错报成请求形状问题；UNIQUE 约束的业务前置检查，
    # IntegrityError 兜底仍在落库路径）。
    with _sr_session() as dup_session:
        existing = (
            dup_session.query(RepoBinding)
            .filter(
                RepoBinding.org_id == actor.org_id,
                RepoBinding.repo_root == str(repo_resolved),
                RepoBinding.branch == branch,
            )
            .first()
        )
    if existing is not None:
        raise SolutionRepoError(
            "binding_exists", "同 org+repo+branch 绑定已存在。", details={"branch": branch}
        )

    try:
        if runner.run_ok("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", "--") is not None:
            raise SolutionRepoError(
                "validation_failed", f"分支已存在：{branch}", details={"branch": branch}
            )
        base_commit = runner.run("rev-parse", "HEAD")
        runner.run("branch", branch)
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None

    binding_id = str(uuid4())
    with _sr_session() as session:
        row = RepoBinding(
            id=binding_id,
            org_id=actor.org_id,
            requester_id=actor.id,
            repo_root=str(repo_resolved),
            workspace_root=str(ws_resolved),
            allow_roots_json=allow_roots,
            base_commit=base_commit,
            branch=branch,
            status="active",
            audit_json={"ops": {}, "events": [{"event": "bind", "details": {"branch": branch}}]},
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise SolutionRepoError(
                "binding_exists", "同 org+repo+branch 绑定已存在。", details={"branch": branch}
            ) from None
        return row.snapshot()


def get_binding(actor: Any, binding_id: str) -> dict[str, Any]:
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id, allow_revoked=True)
        return row.snapshot()


def list_bindings(actor: Any) -> dict[str, Any]:
    with _sr_session() as session:
        rows = (
            session.query(RepoBinding)
            .filter(RepoBinding.org_id == actor.org_id)
            .order_by(RepoBinding.created_at.desc())
            .limit(100)
            .all()
        )
        return {"items": [row.snapshot() for row in rows], "count": len(rows)}


def revoke_binding(actor: Any, binding_id: str) -> dict[str, Any]:
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        row.status = "revoked"
        _touch_audit(session, row, "revoke")
        session.commit()
        return row.snapshot()


def read_file(actor: Any, binding_id: str, rel_path: str) -> dict[str, Any]:
    """读文件面：形状面→symlink 实探→大小上限→文本返回（四拒在读取面同样生效）。"""
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "read_file")
        session.commit()

    allow_roots = tuple(row.allow_roots_json or [])
    shape = check_path(rel_path, allow_roots=allow_roots)
    if not shape.ok:
        raise _verdict_error(shape, rel_path)
    fs_verdict = check_path_fs(
        rel_path, workspace_root=Path(row.workspace_root), allow_roots=allow_roots
    )
    if not fs_verdict.ok:
        raise _verdict_error(fs_verdict, rel_path)

    target = Path(row.workspace_root) / rel_path
    if not target.is_file():
        raise SolutionRepoError("not_found", "文件不存在。", details={"path": rel_path})
    whitelist = load_whitelist()
    max_bytes = int(whitelist["path_rules"]["max_file_read_bytes"])
    size = target.stat().st_size
    if size > max_bytes:
        raise SolutionRepoError(
            "validation_failed",
            f"文件超出读取上限（{size} > {max_bytes} 字节）。",
            details={"path": rel_path, "size": size, "max_bytes": max_bytes},
        )
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": rel_path, "size": size, "content": content}


def get_status(actor: Any, binding_id: str) -> dict[str, Any]:
    """状态面：porcelain 如实回报（脏树不阻断读取面——读无害；写面 WP2 另钉）。"""
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "status")
        session.commit()

    runner = GitRunner(Path(row.repo_root))
    try:
        porcelain = runner.run("status", "--porcelain")
        branch = runner.run("rev-parse", "--abbrev-ref", "HEAD")
        head = runner.run("rev-parse", "HEAD")
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None
    rows = porcelain.splitlines() if porcelain else []
    return {
        "binding_id": row.id,
        "branch": branch,
        "head": head,
        "base_commit": row.base_commit,
        "dirty": bool(rows),
        "porcelain": rows[:50],
    }


def create_branch(actor: Any, binding_id: str, name: Any) -> dict[str, Any]:
    """分支面（agent_allowed branch_create）：名校验→已存在拒→受控创建。"""
    branch = _validate_branch_name(name)
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "branch_create")
        session.commit()

    runner = GitRunner(Path(row.repo_root))
    try:
        if runner.run_ok("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", "--") is not None:
            raise SolutionRepoError(
                "validation_failed", f"分支已存在：{branch}", details={"branch": branch}
            )
        head = runner.run("rev-parse", "HEAD")
        runner.run("branch", branch)
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None
    return {"binding_id": row.id, "branch": branch, "base_commit": head}
