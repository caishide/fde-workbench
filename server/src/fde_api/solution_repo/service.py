"""solution_repo 服务面（AF3-WP1）：仓库绑定＋读面＋状态面＋分支面。

纪律：
- **租户绑定服务端强制**（任务书 §15；沿 AE1 ``submit_action`` 口径）：一律以
  ``actor.org_id`` 过滤，不盲信请求体 org_id；跨租户 404 不泄露；
- **服务端围栏（评审 G1 决策单推荐案）**：``repo_root``/``workspace_root``
  必须位于 ``Settings.solution_repo_base`` 之下；未配置（空串）＝绑定面整体
  停用（fail-closed，任何绑定请求 422）——「指定 solution repo」的服务端
  强制语义由此承载，绑定请求只提供相对选址，不能指到宿主任意路径；
- **不进他人 dirty tree**（04 §3.3）：绑定时刻 porcelain 非空即 409；
- **四拒 fail-closed**（04 §3.3 A1）：读面前先 ``check_path``（形状）再
  ``check_path_fs``（symlink 实探）；
- **Git 操作两级闭集**（D2；评审 G4 接线）：服务面各操作入口经
  ``resolve_op`` 二道闸（第一道＝路由层只暴露 agent_allowed 端点）；
- **撤权即时生效**（AF1② 同构）：``revoked`` 后读写/状态/分支面 403
  permission_revoked（详情/列表面保持可见——撤权状态本身可查，评审 G18 口径）；
- **停点纪律**（AF2① 携带）：branch 缺失/allow_roots 空＝422，禁臆造参数继续；
- session 纪律沿 AE1 ``_ae_session``（``db.session()`` 全新 Session 用完即还，
  同一 session 变量贯穿查询与赋值）。

审计口径（WP1 范围声明）：bind/revoke 落 ``audit_json`` 事件；read/status/
branch_create 计数累加。结构化审计台账（actor/时刻/逐事件）归 WP5 证据
绑定面（评审 D2 defer 登记，20 号 §3 WP5）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import re
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from fde_api.extensions import db
from fde_api.solution_repo.errors import SolutionRepoError
from fde_api.solution_repo.git_boundary import resolve_op
from fde_api.solution_repo.git_ops import GitFailed, GitRunner
from fde_api.solution_repo.models import RepoBinding, RepoCIRun, RepoCorrection, RepoPatch
from fde_api.solution_repo.patch_plan import validate_patch_plan
from fde_api.solution_repo.path_guard import (
    Verdict,
    verdict_error,
    verify_resolved,
    check_path,
    check_path_fs,
)
from fde_api.solution_repo.snapshot import load_whitelist

_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _verdict_error(verdict: Verdict, path: str) -> SolutionRepoError:
    payload = verdict_error(verdict)
    return SolutionRepoError(
        payload.code,
        payload.message,
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


def _load_whitelist_or_fail() -> dict:
    """快照加载折算（评审 G5）：缺失/损坏/结构残缺 → 域信封 git_operation_failed，
    不让 FileNotFoundError/ValueError/KeyError 逃成裸 500。"""
    try:
        return load_whitelist()
    except SolutionRepoError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise SolutionRepoError("git_operation_failed", f"白名单快照加载失败：{exc}") from None


def _resolve_op(op: str) -> None:
    """第二道闸（评审 G4 接线）：Git 操作闭集判定，闭集外/human_only → 403。"""
    verdict = resolve_op(op, whitelist=_load_whitelist_or_fail())
    if not verdict.ok:
        raise SolutionRepoError("tool_not_allowed", verdict.reason)


def _ensure_grant(row: RepoBinding, op: str) -> None:
    """绑定级 grant 闸（评审 D3 清偿；04 §3.3 绑定五要素之「执行 grant」）：
    ``grant_json`` 为 null＝全量 agent_allowed；否则 op 必须在 ``ops`` 子集内，
    越权 → 403 tool_not_allowed（二道闸之后的第三道闸）。

    评审 M11 fail-closed：损坏形态（非 dict／缺 ops／ops 非字符串元素）一律
    403 拒绝该操作——空 dict ``{}`` 语义为「声明了 grant 但未授权任何 op」，
    **不是**全量放行（fail-open 缺口的反向封堵）。"""
    grant = row.grant_json
    if grant is None:
        return
    if not isinstance(grant, dict) or not isinstance(grant.get("ops"), list):
        raise SolutionRepoError(
            "tool_not_allowed",
            "绑定 grant_json 形态损坏（fail-closed 拒绝操作）。",
            details={"op": op},
        )
    if not all(isinstance(op_name, str) for op_name in grant["ops"]):
        raise SolutionRepoError(
            "tool_not_allowed",
            "绑定 grant_json.ops 含非字符串元素（fail-closed 拒绝操作）。",
            details={"op": op},
        )
    if op not in grant["ops"]:
        raise SolutionRepoError(
            "tool_not_allowed",
            f"绑定 grant 未授权该操作：{op}",
            details={"op": op, "granted_ops": grant["ops"]},
        )


def _validate_branch_name(name: Any) -> str:
    if not isinstance(name, str) or not name or len(name) > 128:
        raise SolutionRepoError("validation_failed", "branch 名须为 1..128 字符字符串。")
    if not _BRANCH_RE.match(name):
        raise SolutionRepoError("validation_failed", "branch 名含非法字符或以非法字符开头。")
    if ".." in name or "//" in name or name.endswith("/") or name.endswith(".lock"):
        raise SolutionRepoError("validation_failed", "branch 名含非法序列（..、空段、.lock 结尾）。")
    if name.endswith(".") or "@" in name:
        # 评审 G15：git 语义拒绝形态——组件尾点与 @/@{ 序列（refspec 语法保留字）。
        raise SolutionRepoError("validation_failed", "branch 名含 git 语义非法序列（尾点、@）。")
    if any(part.startswith(".") for part in name.split("/")):
        raise SolutionRepoError("validation_failed", "branch 名部件不得以点开头。")
    return name


def _validate_allow_roots(allow_roots: Any) -> list[str]:
    if not isinstance(allow_roots, list) or not allow_roots:
        # 停点纪律：allow_roots 空＝禁臆造（不默认放全仓）。
        raise SolutionRepoError("validation_failed", "allow_roots 须为非空数组（禁臆造参数）。")
    whitelist = _load_whitelist_or_fail()
    snapshot_roots = {r.rstrip("/") for r in whitelist["path_rules"]["allow_roots"]}
    roots: list[str] = []
    for root in allow_roots:
        if not isinstance(root, str) or not root.endswith("/") or "/" in root.rstrip("/"):
            raise SolutionRepoError(
                "validation_failed",
                "allow_roots 条目须为形如 'dir/' 的单层目录前缀。",
                details={"root": root},
            )
        key = root.rstrip("/")
        # 评审 G3：绑定声明必须是快照 allow_roots 封闭集的子集——快照是
        # FROZEN 规则集而非死数据；扩集走白名单 v2＋决策单。
        if key not in snapshot_roots:
            raise SolutionRepoError(
                "validation_failed",
                f"allow_roots 条目不在白名单封闭集内（{sorted(snapshot_roots)}）。",
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
    return roots


def _load_binding(session: Any, actor_org: str, binding_id: str, *, allow_revoked: bool = False) -> RepoBinding:
    """按租户加载绑定行；跨租户/不存在 404 不泄露；revoked 默认 403（撤权即时生效）。"""
    row = session.get(RepoBinding, binding_id)
    if row is None or row.org_id != actor_org:
        raise SolutionRepoError("not_found", "绑定不存在。")
    if row.status == "revoked" and not allow_revoked:
        raise SolutionRepoError("permission_revoked", "绑定已撤销，操作面已停。")
    return row


def _touch_audit(
    session: Any,
    row: RepoBinding,
    event: str,
    details: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    """审计计数＋事件累加（bind/revoke 落事件；读面计数）。

    评审 D2 清偿（WP4）：events 逐条携 ``actor_id`` 与 UTC ``at`` 时刻——
    WP5 结构化审计台账的取证前置落位（20 号 §3 WP5 台账面在此之上聚合）。
    """
    audit = dict(row.audit_json or {})
    ops = dict(audit.get("ops") or {})
    ops[event] = int(ops.get(event) or 0) + 1
    audit["ops"] = ops
    if event in ("bind", "revoke"):
        events = list(audit.get("events") or [])
        events.append(
            {
                "event": event,
                "actor_id": actor_id,
                "at": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            }
        )
        audit["events"] = events[-20:]
    row.audit_json = audit


def bind_repo(actor: Any, payload: Any, *, repo_base: str) -> dict[str, Any]:
    """绑定受控示例仓：围栏→git 仓校验→dirty tree 校验→分支创建→白名单快照落行。

    ``repo_base`` 由路由层取 ``Settings.solution_repo_base`` 传入（评审 G1）：
    空串＝绑定面整体停用；``repo_root``/``workspace_root`` resolve 后必须
    位于 base 之内。
    """
    if not isinstance(repo_base, str) or not repo_base.strip():
        raise SolutionRepoError(
            "validation_failed",
            "服务端未配置 solution_repo_base，绑定面停用（fail-closed）。",
        )
    _resolve_op("branch_create")  # 评审 G4：绑定含建分支动作，经二道闸
    if not isinstance(payload, dict):
        raise SolutionRepoError("validation_failed", "请求体须为 JSON 对象。")
    repo_root = payload.get("repo_root")
    workspace_root = payload.get("workspace_root")
    branch = _validate_branch_name(payload.get("branch"))
    allow_roots = _validate_allow_roots(payload.get("allow_roots"))
    if not isinstance(repo_root, str) or not repo_root:
        raise SolutionRepoError("validation_failed", "repo_root 须为非空字符串。")
    if workspace_root is not None and (not isinstance(workspace_root, str) or not workspace_root.strip()):
        # 评审 G13：空串/非字符串显式 422（停点纪律——不静默回退 repo_root）。
        raise SolutionRepoError("validation_failed", "workspace_root 须为非空字符串或省略。")
    grant_json = payload.get("grant_json")
    if grant_json is not None:
        # 评审 D3 清偿：grant 须为 {"ops": [...]} 且 ops ⊆ agent_allowed 封闭集
        # （human_only/push 永不入 grant；越集 422）；**键集精确**——未知兄弟键
        # 拒（与 PatchPlan 同款纪律，评审 M11 双标修复）；ops 元素须为字符串。
        if not isinstance(grant_json, dict) or not isinstance(grant_json.get("ops"), list):
            raise SolutionRepoError(
                "validation_failed", 'grant_json 须为 {"ops": [...]} 形态。', details={"grant_json": grant_json}
            )
        unknown_keys = sorted(set(grant_json) - {"ops"})
        if unknown_keys:
            raise SolutionRepoError(
                "validation_failed",
                f"grant_json 含未登记键（键集精确）：{unknown_keys}",
                details={"unknown_keys": unknown_keys},
            )
        if not all(isinstance(op_name, str) for op_name in grant_json["ops"]):
            raise SolutionRepoError(
                "validation_failed", "grant_json.ops 元素须为字符串。", details={"grant_json": grant_json}
            )
        agent_allowed = set(_load_whitelist_or_fail()["git_ops"]["agent_allowed"])
        outside = sorted({op for op in grant_json["ops"] if op not in agent_allowed})
        if outside:
            raise SolutionRepoError(
                "validation_failed",
                f"grant_json.ops 含 agent_allowed 闭集外操作：{outside}",
                details={"outside_ops": outside},
            )

    repo_path = Path(repo_root)
    ws_path = Path(workspace_root) if isinstance(workspace_root, str) and workspace_root else repo_path
    try:
        repo_resolved = repo_path.resolve()
        ws_resolved = ws_path.resolve()
        base_resolved = Path(repo_base).resolve()
        if not repo_resolved.is_relative_to(base_resolved):
            raise SolutionRepoError(
                "validation_failed",
                "repo_root 不在服务端受控基目录内（solution_repo_base）。",
                details={"repo_root": repo_root},
            )
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
        if runner.run_ok("rev-parse", "--verify", "--quiet", "HEAD", "--") is None:
            # 评审 G5：零提交空仓 → 422（rev-parse HEAD 退码 128 不是执行层失败）。
            raise SolutionRepoError("validation_failed", "仓库无任何提交（须先有基线提交）。")
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

    # 评审 G11：allow_roots 目录必须真实存在（设计稿 §3 明文——不存在＝422，
    # 防「绑定成功但读面全 422」的死绑定）。
    missing = [r for r in allow_roots if not (ws_resolved / r.rstrip("/")).is_dir()]
    if missing:
        raise SolutionRepoError(
            "validation_failed",
            f"allow_roots 目录不存在：{missing}",
            details={"missing_roots": missing},
        )

    try:
        if runner.run_ok("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", "--") is not None:
            raise SolutionRepoError(
                "validation_failed", f"分支已存在：{branch}", details={"branch": branch}
            )
        base_commit = runner.run("rev-parse", "HEAD")
        runner.run("branch", branch)
    except GitFailed as exc:
        if "already exists" in (exc.stderr or ""):
            # 评审 G5：并发绑定竞态（双请求同过 DB 预检）→ 409 而非 500。
            raise SolutionRepoError(
                "binding_exists", "同 org+repo+branch 绑定已存在。", details={"branch": branch}
            ) from None
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None

    binding_id = str(uuid4())
    try:
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
                grant_json=grant_json,
                status="active",
                audit_json={
                "ops": {},
                "events": [
                    {
                        "event": "bind",
                        "actor_id": actor.id,
                        "at": datetime.now(timezone.utc).isoformat(),
                        "details": {"branch": branch},
                    }
                ],
            },
            )
            session.add(row)
            session.commit()
            return row.snapshot()
    except IntegrityError:
        # 评审 G6：落库失败回滚 git 分支（不留孤儿分支阻断重试——重试走
        # 409 binding_exists 而非 422「分支已存在」，错误码语义归一）。
        runner.run_ok("branch", "-D", branch)
        raise SolutionRepoError(
            "binding_exists", "同 org+repo+branch 绑定已存在。", details={"branch": branch}
        ) from None
    except Exception:
        runner.run_ok("branch", "-D", branch)
        raise


def get_binding(actor: Any, binding_id: str) -> dict[str, Any]:
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id, allow_revoked=True)
        return row.snapshot()


def list_bindings(actor: Any) -> dict[str, Any]:
    with _sr_session() as session:
        query = session.query(RepoBinding).filter(RepoBinding.org_id == actor.org_id)
        total = query.count()
        rows = (
            query.order_by(RepoBinding.created_at.desc())
            .limit(100)
            .all()
        )
        # 评审 G8：count＝全集总数（截断时显式携带 limit，不以页大小冒充总量）。
        return {"items": [row.snapshot() for row in rows], "count": total, "limit": 100}


def revoke_binding(actor: Any, binding_id: str) -> dict[str, Any]:
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        row.status = "revoked"
        _touch_audit(session, row, "revoke", actor_id=actor.id)
        session.commit()
        return row.snapshot()


def read_file(actor: Any, binding_id: str, rel_path: str) -> dict[str, Any]:
    """读文件面：二道闸→grant→形状面→symlink 实探→打开后 realpath 复核
    （评审 D1 清偿）→大小上限→文本返回（四拒同生效）。

    D1 TOCTOU：``check_path_fs`` 实探与 ``read_text`` 之间原本存在「目标被换
    symlink」窗口（Windows 无 ``O_NOFOLLOW``）——改为 ``os.open`` 后用
    ``os.path.realpath`` 对**已打开目标**复核（解析后仍在 workspace_root 内
    才读），窗口缩到打开之后；上限由「只读 max_bytes+1 字节」承接
    （stat 与读之间被换大文件的竞态同口径封堵）。
    """
    _resolve_op("read_file")  # 评审 G4
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "read_file", actor_id=actor.id)
        session.commit()
    _ensure_grant(row, "read_file")  # 评审 D3

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
    max_bytes = int(_load_whitelist_or_fail()["path_rules"]["max_file_read_bytes"])
    root = Path(row.workspace_root).resolve()

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(target), flags)
    except FileNotFoundError:
        # 评审 L1：is_file 与 open 之间目标消失（正是本修复瞄准的竞态族）→ 404
        raise SolutionRepoError("not_found", "文件不存在。", details={"path": rel_path}) from None
    except OSError as exc:
        raise SolutionRepoError("git_operation_failed", f"文件打开失败：{exc}", details={"path": rel_path}) from None
    try:
        # 评审 D1：打开后复核（真实路径仍须在工作区内 **且** 不落入保护路径
        # ——仓内链接 ontology/x.yaml→.git/config 同拒，评审盲 H2）。
        verify = verify_resolved(os.path.realpath(str(target)), root, rel_path, allow_roots)
        if not verify.ok:
            raise _verdict_error(verify, rel_path)
        size = os.fstat(fd).st_size
        if size > max_bytes:
            raise SolutionRepoError(
                "validation_failed",
                f"文件超出读取上限（{size} > {max_bytes} 字节）。",
                details={"path": rel_path, "size": size, "max_bytes": max_bytes},
            )
        raw = os.read(fd, max_bytes + 1)  # 评审 L2：读 max+1 检测读窗口内增长
        if len(raw) > max_bytes:
            raise SolutionRepoError(
                "validation_failed",
                f"读取窗口内文件增长超限（> {max_bytes} 字节）。",
                details={"path": rel_path, "max_bytes": max_bytes},
            )
    finally:
        os.close(fd)
    content = raw.decode("utf-8", errors="replace")
    return {"path": rel_path, "size": size, "content": content}


def get_status(actor: Any, binding_id: str) -> dict[str, Any]:
    """状态面：porcelain 如实回报（脏树不阻断读取面——读无害；写面 WP2 另钉）。"""
    _resolve_op("status")  # 评审 G4
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "status", actor_id=actor.id)
        session.commit()
    _ensure_grant(row, "status")  # 评审 D3

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
    """分支面（agent_allowed branch_create）：二道闸→名校验→已存在拒→受控创建。"""
    _resolve_op("branch_create")  # 评审 G4
    branch = _validate_branch_name(name)
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "branch_create", actor_id=actor.id)
        session.commit()
    _ensure_grant(row, "branch_create")  # 评审 D3

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


# ---- AF3-WP2：类型化 Patch 应用＋diff/log 读面 ----------------------------------


def _fail_row(org_id: str, binding_id: str, plan_id: str, plan_sha: str, entry_count: int,
              base_commit: str, code: str, error_json: dict[str, Any] | None) -> None:
    """应用执行失败落 failed 行（闸前拒绝不落库——AE1 口径；执行失败留痕）。"""
    with _sr_session() as session:
        session.add(
            RepoPatch(
                org_id=org_id,
                binding_id=binding_id,
                patch_id=plan_id,
                plan_sha256=plan_sha,
                entry_count=entry_count,
                base_commit=base_commit,
                status="failed",
                error_code=code,
                error_json=error_json,
                audit_json={"ops": {}, "events": [{"event": "apply_failed", "details": {"error_code": code}}]},
            )
        )
        session.commit()


def apply_patch(actor: Any, binding_id: str, payload: Any) -> dict[str, Any]:
    """patch_apply 面（白名单 v2）：二道闸→形状面→幂等查→grant→fs 实探→
    dirty→base_commit 匹配→原子写入（写入前复核）→受控 add/commit→applied 行。

    幂等（AE1 同构）：同 (org, binding, patch_id) 重放——applied 行且
    ``plan_sha256`` 一致 → 200 replayed 复放首次结果；指纹不一致 → 409
    idempotency_mismatch（AE1 同键异体口径）；**failed 行按原失败快照复放
    （不伪 replayed）且同 patch_id 不可重试**（AE1：failed 终态行复放原失败
    响应——重试须换新 patch_id）。

    失败路径逆序回滚（新文件删、改动文件恢复原内容）＋git reset；``committed``
    标志：commit 成功后不再恢复文件（防 HEAD 已前进仍写回旧字节）；执行期
    域错误回滚后落 failed 行（审计留痕纪律）；``workspace_root == repo_root``
    为 WP2 patch 面前置（分叉工作区 add/commit pathspec 语义错位——显式 422）。
    """
    _resolve_op("patch_apply")  # 白名单 v2：agent_allowed
    if not isinstance(payload, dict):
        raise SolutionRepoError("validation_failed", "请求体须为 JSON 对象。")
    plan = validate_patch_plan(payload, allow_roots=_snapshot_roots())  # 键集/闭集/上限校验
    plan_sha = _plan_sha256(payload, plan)

    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        # 幂等查先于授权与执行（AE1 同构）：同键重放按 prior 终态分派——
        # applied＋指纹一致 → replayed；指纹不一致 → idempotency_mismatch；
        # failed → 按原失败快照复放（不伪 replayed，评审 H1）。
        prior = (
            session.query(RepoPatch)
            .filter(
                RepoPatch.org_id == actor.org_id,
                RepoPatch.binding_id == binding_id,
                RepoPatch.patch_id == plan["patch_id"],
            )
            .first()
        )
        if prior is not None:
            if prior.status == "failed":
                snap = prior.snapshot()  # 原失败快照原样复放（error_code 随行）
                return snap
            if prior.plan_sha256 != plan_sha:
                raise SolutionRepoError(
                    "idempotency_mismatch",
                    "同 patch_id 已存在但 plan 指纹不一致（AE1 同键异体口径）。",
                    details={"patch_id": plan["patch_id"]},
                )
            _ensure_grant(row, "patch_apply")  # 重放分支同样过 grant（评审 M6——复放自身结果亦须授权）
            snap = prior.snapshot()
            snap["status"] = "replayed"
            return snap
        _ensure_grant(row, "patch_apply")  # 评审 D3：授权先于审计计数（评审 M6——越权被拒不累加 ops）
        _touch_audit(session, row, "patch_apply", actor_id=actor.id)
        session.commit()
    allow_roots = tuple(row.allow_roots_json or [])
    if Path(row.workspace_root).resolve() != Path(row.repo_root).resolve():
        # 评审 M7：add/commit pathspec 相对 repo_root 解析——分叉工作区下写入/
        # 暂存语义错位；WP2 patch 面显式要求 workspace == repo_root（422）。
        raise SolutionRepoError(
            "validation_failed",
            "workspace_root 与 repo_root 分叉时 patch_apply 不受支持（WP2 前置）。",
            details={"workspace_root": row.workspace_root, "repo_root": row.repo_root},
        )

    # fs 实探（逐条目按绑定 allow_roots）
    ws_root = Path(row.workspace_root)
    for entry in plan["entries"]:
        shape = check_path(entry["path"], allow_roots=allow_roots)
        if not shape.ok:
            raise _verdict_error(shape, entry["path"])
        fs_verdict = check_path_fs(entry["path"], workspace_root=ws_root, allow_roots=allow_roots)
        if not fs_verdict.ok:
            raise _verdict_error(fs_verdict, entry["path"])

    runner = GitRunner(Path(row.repo_root))
    try:
        porcelain = runner.run("status", "--porcelain")
        if porcelain:
            raise SolutionRepoError(
                "dirty_tree_conflict",
                "工作树存在未提交变更（patch 应用前须干净）。",
                details={"porcelain_rows": porcelain.splitlines()[:20]},
            )
        head = runner.run("rev-parse", "HEAD")
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None
    if plan["base_commit"] != head:
        # 04 §3.3：修改源内容后旧批准失效——基线漂移即拒。
        raise SolutionRepoError(
            "base_mismatch",
            "plan.base_commit 与当前 HEAD 不一致（修改源内容后旧批准失效）。",
            details={"plan_base_commit": plan["base_commit"], "head": head},
        )

    # 评审 T1/T2（设计件 §3.2）：Patch 条目命中 ci_protected 名单（conftest/
    # ini/pyproject 等装饰载荷与依赖面）→ 403——bundle 执行不可达的注入面。
    protected = _load_whitelist_or_fail()["ci_bundle"].get("ci_protected") or []
    # 评审 H2（基线完整性锚）：绑定基线提交（base_commit）的 tests/ 清单为
    # **验收测试锚**——Patch 修改/删除基线测试 → 403（05 §2.1 T4「验收测试
    # 不能被 Agent 删除」；防「删验收断言＋加平凡新测试」绕对拍面）。
    baseline_tests_raw = runner.run_ok(
        "ls-tree", "-r", "--name-only", row.base_commit, "--", "tests/"
    )
    baseline_tests = set((baseline_tests_raw or "").splitlines())
    for entry in plan["entries"]:
        if _ci_protected_hit(entry["path"], protected):
            raise SolutionRepoError(
                "protected_path_rejected",
                "Patch 条目命中 ci_protected 名单（CI 装饰载荷防线）。",
                details={"path": entry["path"]},
            )
        posix_path = entry["path"].replace("\\", "/").lower()
        if posix_path.startswith("tests/"):
            # 评审 H1（D3 形态白名单，设计件 §3.5）：tests/ 下新增文件仅
            # test_*.py（test 函数体）；任意 .py（payload.py 等）经 import 链
            # 在受信任 bundle 执行——形态外一律 422。
            if entry["operation"] == "create":
                basename = posix_path.rsplit("/", 1)[-1]
                if not (basename.startswith("test_") and basename.endswith(".py")):
                    raise SolutionRepoError(
                        "validation_failed",
                        "tests/ 下新增文件须为 test_*.py 形态（D3 形态白名单，"
                        "装饰载荷/任意脚本不可达）。",
                        details={"path": entry["path"]},
                    )
            # 基线完整性：修改/删除基线验收测试 → 403（新增不受限）。
            if entry["operation"] in ("update", "delete") and entry["path"] in baseline_tests:
                raise SolutionRepoError(
                    "acceptance_tests_intact_violation",
                    "基线验收测试不可被 Patch 修改或删除（05 §2.1 T4）。",
                    details={"path": entry["path"]},
                )

    # 原子写入＋逆序回滚登记（written: [(path, kind, saved_bytes|None)]）。
    # 写入前复核（评审 H3/H4：probe→write 窗口）——已存在目标 realpath 落点
    # 判定（逃逸/保护路径/越界同拒）；create 目标已存在 → 422（M8 语义守卫）。
    written: list[tuple[str, str, bytes | None]] = []
    committed = False
    applied_commit: str | None = None
    try:
        for entry in plan["entries"]:
            target = ws_root / entry["path"]
            kind = entry["operation"]
            existed = target.exists()
            if kind == "create" and existed:
                raise SolutionRepoError(
                    "validation_failed",
                    "create 目标已存在（create 语义守卫，评审 M8）。",
                    details={"path": entry["path"]},
                )
            if kind == "delete" and not existed:
                raise SolutionRepoError(
                    "validation_failed", "delete 目标不存在。", details={"path": entry["path"]}
                )
            if existed:
                # 写入前复核（读面 D1 同构；仓内链接→.git/config 等「解析不
                # 逃逸但落保护区」形态同拒——评审盲 H2）。
                verify = verify_resolved(os.path.realpath(str(target)), ws_root.resolve(), entry["path"], allow_roots)
                if not verify.ok:
                    raise _verdict_error(verify, entry["path"])
            saved = target.read_bytes() if existed else None
            if kind == "delete":
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(entry["content"] or "", encoding="utf-8", newline="")
            written.append((entry["path"], kind, saved))
        paths = [w[0] for w in written]
        runner.run("add", "--", *paths)
        runner.run("commit", "-m", f"af3: apply {plan['patch_id']}")
        committed = True
        applied_commit = runner.run("rev-parse", "HEAD")
    except GitFailed as exc:
        if not committed:
            _rollback(written, runner, ws_root)
        err = exc.to_details()
        _fail_row(actor.org_id, binding_id, plan["patch_id"], plan_sha,
                  len(plan["entries"]), plan["base_commit"], "git_operation_failed", err)
        raise SolutionRepoError("git_operation_failed", "Patch 应用失败（已回滚零残留）。", details=err) from None
    except OSError as exc:
        if not committed:
            _rollback(written, runner, ws_root)
        err = {"stderr": str(exc)}
        _fail_row(actor.org_id, binding_id, plan["patch_id"], plan_sha,
                  len(plan["entries"]), plan["base_commit"], "git_operation_failed", err)
        raise SolutionRepoError("git_operation_failed", "Patch 应用失败（已回滚零残留）。", details=err) from None
    except SolutionRepoError as exc:
        # 评审 M4：执行期域错误回滚后同样落 failed 行（审计留痕纪律一致）。
        if not committed:
            _rollback(written, runner, ws_root)
        _fail_row(actor.org_id, binding_id, plan["patch_id"], plan_sha,
                  len(plan["entries"]), plan["base_commit"], exc.code,
                  {"message": exc.message, "details": exc.details})
        raise

    with _sr_session() as session:
        binding_row = session.get(RepoBinding, binding_id)
        if binding_row is None or binding_row.org_id != actor.org_id:
            raise SolutionRepoError("not_found", "绑定不存在。")
        if binding_row.status == "revoked":
            # 评审：绑定在执行窗口内被撤销——applied 行不落（撤权即时生效语义）
            raise SolutionRepoError("permission_revoked", "绑定已撤销，操作面已停。")
        session.add(
            RepoPatch(
                org_id=actor.org_id,
                binding_id=binding_id,
                patch_id=plan["patch_id"],
                plan_sha256=plan_sha,
                entry_count=len(plan["entries"]),
                base_commit=plan["base_commit"],
                applied_commit=applied_commit,
                status="applied",
                audit_json={
                    "ops": {"apply": 1},
                    "events": [{"event": "applied", "details": {"entries": len(plan["entries"])}}],
                },
            )
        )
        try:
            session.commit()
        except IntegrityError:
            # 评审 M3：并发同 patch_id 双 apply（都穿过预检）——败者按先到者
            # 的 applied 行复放返回（bind_repo 同款兜底形态），不裸 500。
            session.rollback()
            prior = (
                session.query(RepoPatch)
                .filter(
                    RepoPatch.org_id == actor.org_id,
                    RepoPatch.binding_id == binding_id,
                    RepoPatch.patch_id == plan["patch_id"],
                )
                .first()
            )
            if prior is not None:
                snap = prior.snapshot()
                snap["status"] = "replayed"
                return snap
            raise SolutionRepoError(
                "binding_exists", "同 patch_id 并发应用冲突。", details={"patch_id": plan["patch_id"]}
            ) from None
        _touch_audit(session, binding_row, "patch_apply", actor_id=actor.id)  # 同操作同一计数名（评审：一名一事）
        session.commit()
        return {
            "patch_id": plan["patch_id"],
            "binding_id": binding_id,
            "plan_sha256": plan_sha,
            "entries_applied": len(plan["entries"]),
            "base_commit": plan["base_commit"],
            "applied_commit": applied_commit,
            "status": "applied",
        }


def _snapshot_roots() -> tuple[str, ...]:
    return tuple(_load_whitelist_or_fail()["path_rules"]["allow_roots"])


def _plan_sha256(payload: dict[str, Any], plan: dict[str, Any]) -> str:
    """PatchPlan 指纹（零明文落库——只存 sha256；同 plan 同指纹可复验）。"""
    canon = json.dumps(
        {
            "patch_id": payload.get("patch_id"),
            "base_commit": payload.get("base_commit"),
            "entries": [
                {"path": e["path"], "operation": e["operation"], "content": e["content"]}
                for e in plan["entries"]
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _rollback(written: list[tuple[str, str, bytes | None]], runner: GitRunner, ws_root: Path) -> None:
    """逆序恢复（新文件删、改动文件恢复原字节）＋git reset（撤销 staged）。

    残余声明（评审）：零残留由测试对单一路径断言与调用方回滚纪律承载，无
    运行时 porcelain 守门——回滚自身 OSError 被吞，残留表现为下一次操作的
    dirty_tree_conflict 409（不静默污染后续成功）；运行时 porcelain 复核与
    告警归 WP4 修复闭环面（预算内失败观测正是其输入）。"""
    for path, kind, saved in reversed(written):
        target = ws_root / path
        try:
            if saved is None:
                if target.exists():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(saved)
        except OSError:
            pass  # 回滚自身失败不再抛——porcelain 断言闸会暴露任何残留
    try:
        runner.run("reset", "-q", "HEAD", "--")
    except GitFailed:
        pass


def get_changes(actor: Any, binding_id: str) -> dict[str, Any]:
    """diff 读面（agent_allowed diff）：二道闸→grant→git diff --stat＋diff 截断。"""
    _resolve_op("diff")
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "diff", actor_id=actor.id)
        session.commit()
    _ensure_grant(row, "diff")
    runner = GitRunner(Path(row.repo_root))
    try:
        porcelain = runner.run("status", "--porcelain")  # dirty 判定含 untracked（git diff 不含）
        stat = runner.run("diff", "--stat")
        diff_text = runner.run("diff")
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None
    rows = porcelain.splitlines() if porcelain else []
    return {
        "binding_id": row.id,
        "dirty": bool(rows),
        "porcelain": rows[:50],
        "stat": stat,
        "diff": diff_text[:65536],
        "diff_truncated": len(diff_text) > 65536,
    }


def get_commit_log(actor: Any, binding_id: str) -> dict[str, Any]:
    """log 读面（agent_allowed log）：二道闸→grant→git log --oneline -n 20。"""
    _resolve_op("log")
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _touch_audit(session, row, "log", actor_id=actor.id)
        session.commit()
    _ensure_grant(row, "log")
    runner = GitRunner(Path(row.repo_root))
    try:
        log_text = runner.run("log", "--oneline", "-n", "20")
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None
    return {"binding_id": row.id, "commits": log_text.splitlines()}


def get_patch(actor: Any, binding_id: str, patch_id: str) -> dict[str, Any]:
    """Patch 行详情（幂等查询/failed 留痕可见；M8 排除登记形态）。"""
    with _sr_session() as session:
        _load_binding(session, actor.org_id, binding_id, allow_revoked=True)
        patch = (
            session.query(RepoPatch)
            .filter(
                RepoPatch.org_id == actor.org_id,
                RepoPatch.binding_id == binding_id,
                RepoPatch.patch_id == patch_id,
            )
            .first()
        )
    if patch is None:
        raise SolutionRepoError("not_found", "Patch 行不存在。", details={"patch_id": patch_id})
    return patch.snapshot()


# ---- AF3-WP3：固定受信任 CI bundle（设计件 §3；P1 W-A~W-E 推荐案） ----------------


def _ci_protected_hit(path: str, patterns: list[str]) -> bool:
    """评审 H3：basename 级 fnmatch＋大小写不敏感——通配（requirements-*.txt）
    与大小写伪装（tests/CONFTEST.py）均命中；嵌套子目录经 basename 判定覆盖。"""
    from fnmatch import fnmatch

    posix = path.replace("\\", "/").lower()
    basename = posix.rsplit("/", 1)[-1]
    for pat in patterns:
        pat_l = pat.lower()
        if fnmatch(posix, pat_l) or fnmatch(posix, "*/" + pat_l) or basename == pat_l or fnmatch(basename, pat_l):
            return True
    return False


def _parse_pytest_verbose(text: str, cap: int) -> list[dict[str, str]]:
    """pytest -v 输出解析：nodeid 级执行清单（PASSED/FAILED/SKIPPED/ERROR 等
    终态词）——「CI 绿但没执行新增断言」对拍面（评审 T7）。"""
    outcomes = ("PASSED", "FAILED", "SKIPPED", "ERROR", "XFAIL", "XPASS")
    checks: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        for oc in outcomes:
            marker = f" {oc} "
            idx = line.find(marker)
            if idx == -1:
                if line.endswith(f" {oc}"):
                    idx = len(line) - len(oc) - 1
                else:
                    continue
            nodeid = line[:idx].strip()
            if nodeid:
                checks.append({"nodeid": nodeid, "outcome": oc.lower()})
            break
        if len(checks) >= cap:
            break
    return checks


def run_ci(actor: Any, binding_id: str, payload: Any) -> dict[str, Any]:
    """run_ci 面（白名单 v3 agent_allowed）：二道闸→bundle 闭集→grant→
    dirty 前置→受控子进程→结果解析→RepoCIRun 落行。

    verdict 三态诚实归因（设计件 §3.3）：green＝exit 0 且执行清单非空；
    red＝exit≠0；error＝timeout/执行层失败（error_json 归因，不冒充 red）。"""
    _resolve_op("run_ci")
    if not isinstance(payload, dict):
        raise SolutionRepoError("validation_failed", "请求体须为 JSON 对象。")
    unknown_keys = sorted(set(payload) - {"bundle_id"})
    if unknown_keys:
        # 评审 M9：键集精确纪律延及 run_ci 入口（WP2 PatchPlan 同款）。
        raise SolutionRepoError(
            "validation_failed",
            f"run_ci 请求含未登记键（键集精确）：{unknown_keys}",
            details={"unknown_keys": unknown_keys},
        )
    bundle_id = payload.get("bundle_id")
    snap = _load_whitelist_or_fail()
    ci_cfg = snap["ci_bundle"]
    bundles = ci_cfg.get("bundles") or {}
    if not isinstance(bundle_id, str) or bundle_id not in bundles:
        raise SolutionRepoError(
            "tool_not_allowed",
            f"bundle_id 不在受信任闭集内：{sorted(bundles)}",
            details={"bundle_id": bundle_id},
        )
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _ensure_grant(row, "run_ci")  # 评审 M6：授权先于审计计数（同 WP2 口径）
        _touch_audit(session, row, "run_ci", actor_id=actor.id)
        session.commit()
    if Path(row.workspace_root).resolve() != Path(row.repo_root).resolve():
        # 评审 M7（WP2 M7 同款）：CI cwd 与归因锚分叉时结果错位——显式 422。
        raise SolutionRepoError(
            "validation_failed",
            "workspace_root 与 repo_root 分叉时 run_ci 不受支持。",
            details={"workspace_root": row.workspace_root, "repo_root": row.repo_root},
        )

    runner = GitRunner(Path(row.repo_root))
    try:
        porcelain = runner.run("status", "--porcelain")
        if porcelain:
            # 结果归因前置：干净树才可把 CI 结果锚到 HEAD（与 patch 前置一致）
            raise SolutionRepoError(
                "dirty_tree_conflict",
                "工作树存在未提交变更（CI 结果须可归因到 commit）。",
                details={"porcelain_rows": porcelain.splitlines()[:20]},
            )
        head = runner.run("rev-parse", "HEAD")
    except GitFailed as exc:
        raise SolutionRepoError("git_operation_failed", "Git 执行失败。", details=exc.to_details()) from None

    ws_root = Path(row.workspace_root)
    argv = list(bundles[bundle_id]["argv"])
    if argv and argv[0] == "python":
        # 模板首项 "python"＝服务端进程解释器（sys.executable——venv 内含
        # fde_api/pytest；PATH 上的裸 python 在部署形态下不可信）
        argv = [sys.executable, *argv[1:]]
    timeout = int(ci_cfg.get("subprocess_timeout_seconds") or 300)
    cap = int(ci_cfg.get("stdout_cap_bytes") or 1048576)
    started = time.monotonic()
    verdict = "error"
    exit_code = -1
    stdout_text = ""
    stderr_text = ""
    error_json: dict[str, Any] | None = None
    try:
        ci_env = GitRunner._safe_env()
        ci_env["PYTHONDONTWRITEBYTECODE"] = "1"  # 评审 M1：防 pytest __pycache__ 污染工作树（二次 run 409）
        # 服务端受控 PYTHONPATH（fde_api 可寻址）：-I 隔离与 editable 安装冲突，
        # 改为 env 白名单内显式注入服务端 src（外部 PYTHONPATH 注入面仍被封堵——
        # 与 -I 等价受控，评审实测评测修正；设计件 §3.1 落痕同步）。
        ci_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        proc = subprocess.run(  # noqa: S603 — 服务端模板 argv，禁 shell
            list(argv),
            cwd=str(ws_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            env=ci_env,
            check=False,
        )
        exit_code = proc.returncode
        if not -2147483648 <= exit_code <= 2147483647:
            # 评审 M3b：Windows 强杀退码（0xC0000409 族）超 int32——PG INTEGER
            # 溢出把已执行的 run 行丢掉；钳制为 500（执行层失败语义）。
            exit_code = 500
        stdout_text = (proc.stdout or "")[:cap]
        stderr_text = (proc.stderr or "")[:cap]
        verdict = "red" if exit_code != 0 else "green"
    except subprocess.TimeoutExpired as exc:
        verdict = "error"
        # 评审：超时部分输出留存（诊断面——TimeoutExpired.stdout/stderr 可得）
        partial_out = exc.stdout or ""
        partial_err = exc.stderr or ""
        if isinstance(partial_out, bytes):
            partial_out = partial_out.decode("utf-8", errors="replace")
        if isinstance(partial_err, bytes):
            partial_err = partial_err.decode("utf-8", errors="replace")
        error_json = {
            "reason": f"timeout after {timeout}s",
            "args": " ".join(argv),
            "stdout_head": partial_out[-4096:],
            "stderr_head": partial_err[-4096:],
        }
    except OSError as exc:
        verdict = "error"
        error_json = {"reason": str(exc), "args": " ".join(argv)}
    duration_ms = int((time.monotonic() - started) * 1000)

    executed: list[dict[str, str]] = []
    new_tests: list[str] = []
    if bundle_id in ("unit_test", "transform_test"):
        executed = _parse_pytest_verbose(stdout_text, int(ci_cfg.get("max_executed_checks") or 1000))
        # 评审 M3a：quotePath=false（非 ASCII 测试文件名不被引号转义）；失败
        # → verdict=error 落行（基线差集失真不可接受）。
        baseline_raw = runner.run_ok(
            "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", row.base_commit, "--", "tests/"
        )
        if baseline_raw is None:
            verdict = "error"
            error_json = {"reason": "baseline ls-tree 失败（基线差集不可构造）", "base_commit": row.base_commit}
        baseline_files = set((baseline_raw or "").splitlines())
        new_tests = [
            c["nodeid"]
            for c in executed
            if c["nodeid"].split("::")[0] not in baseline_files
        ]
    else:
        # 校验器 bundle：stdout JSON 的 checked 清单 → executed（nodeid 级）
        try:
            parsed = json.loads(stdout_text) if stdout_text.strip().startswith("{") else {}
            for item in parsed.get("checked") or []:
                executed.append({"nodeid": item["nodeid"], "outcome": item["outcome"]})
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # 校验器输出异常时 executed 置空——verdict 仍按 exit_code 诚实
    if verdict == "green" and not executed:
        # 「CI 绿但没执行任何检查」＝判定层拒绝（05 §5 AF3 行防线）
        verdict = "error"
        error_json = {"reason": "green 但执行清单为空（无新增断言执行证据）", "bundle_id": bundle_id}

    run_id = str(uuid4())
    with _sr_session() as session:
        session.add(
            RepoCIRun(
                id=run_id,
                org_id=actor.org_id,
                binding_id=binding_id,
                bundle_id=bundle_id,
                head_commit=head,
                exit_code=exit_code,
                verdict=verdict,
                duration_ms=duration_ms,
                executed_json=executed,
                new_tests_json=new_tests,
                stdout_head=stdout_text[:4096],
                stderr_head=stderr_text[:4096],
                error_json=error_json,
            )
        )
        session.commit()
        return {
            "run_id": run_id,
            "bundle_id": bundle_id,
            "base_commit": row.base_commit,
            "head_commit": head,
            "exit_code": exit_code,
            "verdict": verdict,
            "duration_ms": duration_ms,
            "executed_checks": executed,
            "new_test_nodeids": new_tests,
            "stdout_head": stdout_text[:4096],
            "stderr_head": stderr_text[:4096],
            "error_json": error_json,
            "executed_truncated": len(executed) >= int(ci_cfg.get("max_executed_checks") or 1000),
        }


def get_ci_runs(actor: Any, binding_id: str) -> dict[str, Any]:
    """CI 执行行列表（近 20 条；append-only 可复跑——每 run 新行）。

    评审口径对齐：grant 闸＋revoked 拒（与 /changes /commits 同域读面一致）。"""
    with _sr_session() as session:
        _load_binding(session, actor.org_id, binding_id)
        runs = (
            session.query(RepoCIRun)
            .filter(RepoCIRun.org_id == actor.org_id, RepoCIRun.binding_id == binding_id)
            .order_by(RepoCIRun.created_at.desc())
            .limit(20)
            .all()
        )
        return {"items": [r.snapshot() for r in runs], "count": len(runs), "limit": 20}


# ---- AF3-WP4：修复闭环（correction_loop 预算内失败→修复→复测） --------------------


def get_corrections(actor: Any, binding_id: str) -> dict[str, Any]:
    """修复闭环轨迹列表（近 20 条；append-only——每轨迹新行）。

    评审 M2：grant 闸（轨迹读回＝patch_apply 域读面）＋排序 tiebreaker。"""
    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _ensure_grant(row, "patch_apply")
        rows = (
            session.query(RepoCorrection)
            .filter(RepoCorrection.org_id == actor.org_id, RepoCorrection.binding_id == binding_id)
            .order_by(RepoCorrection.created_at.desc(), RepoCorrection.id.desc())
            .limit(20)
            .all()
        )
        return {"items": [r.snapshot() for r in rows], "count": len(rows), "limit": 20}


def _canonical_plan_sha(plan_payload: dict[str, Any]) -> str:
    """PatchPlan canonical 指纹（WP2 同构算法——闭环预校验与指纹一致性）。"""
    plan = validate_patch_plan(plan_payload, allow_roots=_snapshot_roots())
    return _plan_sha256(plan_payload, plan)


def start_correction(actor: Any, binding_id: str, payload: Any) -> dict[str, Any]:
    """修复闭环（AF1① correction_loop「预算内收敛不无限重试」）：

    失败 CI run（verdict=red，**CI 结果消费锚**——AF2④：修复必须锚真实失败）
    → ≤max_rounds 轮「逐轮 PatchPlan（``patches`` 数组——评审 H1：单 patch
    重提是 replay 死预算，收敛必须逐轮新计划）apply＋同 bundle 复测」→
    corrected（某轮 green）／budget_exhausted（预算耗尽仍 red——诚实终态）/
    failed（执行期失败，错误快照随行）。

    闸前拒绝（形状/锚时效/patch_id 已用/基线守卫）一律 422/403 **不落行**；
    执行期域错误落 failed 行＋错误快照。轨迹逐轮记 ``{patch_id, status,
    run_id, verdict}``（评审 M10：中间轮 red 证据不丢）。
    """
    _resolve_op("patch_apply")
    if not isinstance(payload, dict):
        raise SolutionRepoError("validation_failed", "请求体须为 JSON 对象。")
    unknown_keys = sorted(set(payload) - {"failed_run_id", "bundle_id", "patches", "max_rounds"})
    if unknown_keys:
        raise SolutionRepoError(
            "validation_failed",
            f"correction 请求含未登记键（键集精确）：{unknown_keys}",
            details={"unknown_keys": unknown_keys},
        )
    max_rounds = payload.get("max_rounds")
    if max_rounds is None:
        max_rounds = 3
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= 5:
        # 评审 M6：bool 穿透（isinstance(True, int)）显式拒。
        raise SolutionRepoError("validation_failed", "max_rounds 须为 1..5 整数。", details={"max_rounds": max_rounds})
    bundle_id = payload.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id:
        raise SolutionRepoError("validation_failed", "bundle_id 须为非空字符串。")
    patches_raw = payload.get("patches")
    if not isinstance(patches_raw, list) or not patches_raw or len(patches_raw) > max_rounds:
        raise SolutionRepoError(
            "validation_failed",
            "patches 须为 1..max_rounds 个 PatchPlan 的数组（逐轮收敛——评审 H1）。",
            details={"len": len(patches_raw) if isinstance(patches_raw, list) else None,
                     "max_rounds": max_rounds},
        )
    failed_run_id = payload.get("failed_run_id")
    if not isinstance(failed_run_id, str) or not failed_run_id:
        raise SolutionRepoError("validation_failed", "failed_run_id 须为非空字符串（CI 结果消费锚）。")

    # 闸前预校验（全部 422/403，不落行）：逐 plan 形状＋patch_id 未用。
    plans: list[dict[str, Any]] = []
    seen_patch_ids: set[str] = set()
    for plan_payload in patches_raw:
        if not isinstance(plan_payload, dict):
            raise SolutionRepoError("validation_failed", "patches 元素须为 PatchPlan 对象。")
        plan = validate_patch_plan(plan_payload, allow_roots=_snapshot_roots())
        if plan["patch_id"] in seen_patch_ids:
            raise SolutionRepoError(
                "validation_failed",
                f"patches 内 patch_id 重复：{plan['patch_id']}",
                details={"patch_id": plan["patch_id"]},
            )
        seen_patch_ids.add(plan["patch_id"])
        plans.append(plan)

    with _sr_session() as session:
        row = _load_binding(session, actor.org_id, binding_id)
        _ensure_grant(row, "patch_apply")
        _ensure_grant(row, "run_ci")  # 闭环含复测面（评审 M2 口径）
        failed_run = (
            session.query(RepoCIRun)
            .filter(
                RepoCIRun.org_id == actor.org_id,
                RepoCIRun.binding_id == binding_id,
                RepoCIRun.id == failed_run_id,
            )
            .first()
        )
    if failed_run is None:
        raise SolutionRepoError("not_found", "失败 CI run 不存在。", details={"failed_run_id": failed_run_id})
    if failed_run.verdict != "red":
        # CI 结果消费纪律（AF2④）：不锚真实失败的修复请求拒。
        raise SolutionRepoError(
            "validation_failed",
            "correction 必须锚 verdict=red 的 CI run（消费真实失败）。",
            details={"failed_run_id": failed_run_id, "verdict": failed_run.verdict},
        )
    if failed_run.bundle_id != bundle_id:
        raise SolutionRepoError(
            "validation_failed",
            "bundle_id 与失败 run 的 bundle 不一致（复测须同 bundle 对拍）。",
            details={"failed_bundle": failed_run.bundle_id, "bundle_id": bundle_id},
        )
    if plans[0]["base_commit"] != failed_run.head_commit:
        # 评审 H5（锚时效）：修复 patch 必须基于失败 run 的 HEAD——基线漂移即拒
        # （防「他人已修好、二次计入成功」的归因错乱）。
        raise SolutionRepoError(
            "validation_failed",
            "patches[0].base_commit 与失败 run 的 head_commit 不一致（锚时效）。",
            details={"plan_base": plans[0]["base_commit"], "failed_run_head": failed_run.head_commit},
        )
    with _sr_session() as session:
        used = (
            session.query(RepoPatch)
            .filter(
                RepoPatch.org_id == actor.org_id,
                RepoPatch.binding_id == binding_id,
                RepoPatch.patch_id.in_(seen_patch_ids),
            )
            .count()
        )
    if used:
        # 评审 H4 前置：已用 patch_id（含 failed 行）重提＝无视失败重提同一方案
        # （AF2④）——预校验拒，不给「失败重放洗白」通道。
        raise SolutionRepoError(
            "validation_failed",
            "patches 含已使用过的 patch_id（AF2④：不得无视错误重提同一方案）。",
            details={"failed_run_id": failed_run_id},
        )

    _ensure_grant(row, "run_ci")  # 复测面授权（闭环含 run_ci）
    rounds = 0
    trajectory: list[dict[str, Any]] = []
    patches_applied: list[str] = []
    final_verdict = failed_run.verdict
    final_run_id = failed_run_id
    status = "budget_exhausted"
    error_json: dict[str, Any] | None = None
    try:
        while rounds < len(plans):
            plan = plans[rounds]
            plan_payload = patches_raw[rounds]
            rounds += 1
            result = apply_patch(actor, binding_id, plan_payload)
            if result.get("status") != "applied":
                # 评审 H4：replay/failed 快照不得计入轨迹（patches_applied 只收
                # 真实应用——「失败重放洗白」通道封堵）。
                raise SolutionRepoError(
                    "validation_failed",
                    "patch 未真实应用（replay/failed 快照）。",
                    details={"patch_id": result.get("patch_id"), "status": result.get("status")},
                )
            patches_applied.append(result["patch_id"])
            ci_result = run_ci(actor, binding_id, {"bundle_id": bundle_id})
            trajectory.append(
                {
                    "patch_id": result["patch_id"],
                    "status": result["status"],
                    "run_id": ci_result["run_id"],
                    "verdict": ci_result["verdict"],
                }
            )
            final_run_id = ci_result["run_id"]
            final_verdict = ci_result["verdict"]
            if final_verdict == "green":
                status = "corrected"
                break
            if final_verdict == "error":
                # 评审 M5：infra 归因诚实——error 不烧预算也不冒充 budget_exhausted。
                status = "failed"
                error_json = ci_result.get("error_json")
                break
            # 仍 red：下一轮消费 patches[rounds]（AF2④——逐轮新计划）。
        else:
            status = "budget_exhausted"
    except SolutionRepoError as exc:
        # 执行期域错误（apply/run_ci）＝闭环 failed（错误快照随行——诚实终态）。
        status = "failed"
        error_json = {"round": rounds, "error_code": exc.code, "message": exc.message, "details": exc.details}
    except Exception as exc:  # 评审：未包装异常兜底——轨迹行不丢，异常如实上抛
        status = "failed"
        error_json = {"reason": str(exc)}
        with _sr_session() as session:
            session.add(
                RepoCorrection(
                    org_id=actor.org_id,
                    binding_id=binding_id,
                    failed_run_id=failed_run_id,
                    bundle_id=bundle_id,
                    rounds_consumed=rounds,
                    patches_json=[p["patch_id"] for p in trajectory],
                    final_run_id=final_run_id,
                    final_verdict=final_verdict,
                    status=status,
                    error_json=error_json,
                )
            )
            session.commit()
        raise

    correction_id = str(uuid4())
    with _sr_session() as session:
        session.add(
            RepoCorrection(
                id=correction_id,
                org_id=actor.org_id,
                binding_id=binding_id,
                failed_run_id=failed_run_id,
                bundle_id=bundle_id,
                rounds_consumed=rounds,
                patches_json=patches_applied,
                final_run_id=final_run_id,
                final_verdict=final_verdict,
                status=status,
                error_json=error_json,
            )
        )
        session.commit()
        return {
            "correction_id": correction_id,
            "failed_run_id": failed_run_id,
            "bundle_id": bundle_id,
            "rounds_consumed": rounds,
            "patches_applied": patches_applied,
            "trajectory": trajectory,
            "final_run_id": final_run_id,
            "final_verdict": final_verdict,
            "status": status,
            "error_json": error_json,
        }
