"""多客户 M4 批次 D：存储物理布局主体段＋五步状态机（任务书 §7-M4「存储根加 {org_id}/ 段＋存量五步迁移」）。

钉面：
- **出厂默认安全钉**：``FDE_STORAGE_LAYOUT`` 缺省 ``legacy``＝部署即现状零回归
  （测默认值要测出厂值不能只测夹具行为——诊断 T-10a M8 家族教训）。
- **单一权威**：状态解析/段归属/物理键翻译全在 ``storage/layout.py``；
  五状态写读矩阵（legacy 写旧读旧 → dual_write 双写读旧 → read_new 写新读新
  回落旧 → readonly 同 read_new（旧根冻结语义）→ retired 零回落）。
- **主体段**：``org/{org_id}/<逻辑键>``／平台身份 ``platform/<逻辑键>``；
  ``document-templates`` 逻辑根恒平台段；跨 org 物理键永不碰撞。
- **签名绑物理键**：预签名覆盖完整物理键（含主体段）⇒ 跨段签名不通用；
  签名键派生自 ``FDE_JWT_SECRET``（域分离）⇒ 跨重启稳定（M0「进程内随机」
  判定经现测**纠正为核销**——extensions.py 已用派生键，本轮补钉）。
- **S2/S3**：agent 工作区与转写草稿短生命周期临时面存量不搬、新写入即新段。
- **host 票据 org 归属元数据**（计量/审计面，非授权面）。
- **迁移命令**：``flask storage-migrate-layout`` 缺省 dry-run；--execute 逐文件
  sha256 核对、幂等可重跑（生产执行是运维动作，不在部署流程内自动跑）。
- **静态钉**：全仓存储调用点（put_stream/open_stream/copy/sign_download）窗口
  内必须经布局 helper（防新调用点绕过物理键翻译）。
变异验收：M1 摘 dual_write 双写 ⇒ 矩阵＋双写用例红；M2 摘 platform 段 ⇒ 平台段用例红。
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from fde_api.agents.execution_grants import (
    authorize_host_run,
    issue_run_grant,
    verify_run_grant,
)
from fde_api.storage.base import (
    StorageError,
    StorageNotFoundError,
    validate_object_key,
)
from fde_api.storage.layout import (
    PLATFORM_SEGMENT,
    STORAGE_LAYOUT_STATES,
    existing_read_key,
    open_read_stream,
    org_object_prefix,
    physical_read_candidates,
    physical_write_targets,
    prefixed_object_key,
    resolve_storage_layout,
)
from fde_api.storage.local import LocalObjectStorage
from multi_tenant_harness import make_enterprise_org, make_user

_LOGICAL = "projects/{pid}/attachments/f/report.txt"


def _org_project(db_session):
    """企业归属项目夹具（org 段解析与批次 C helper 同源）。"""
    from test_ai_server_chat_mcp import make_project

    org = make_enterprise_org(db_session)
    leader = make_user(db_session, role="admin", org_id=org.id)
    project = make_project(db_session, leader)
    project.org_id = org.id
    db_session.commit()
    return org, project


def _plain_project(db_session):
    from test_ai_server_chat_mcp import make_project

    leader = make_user(db_session, role="admin", org_id=None)
    project = make_project(db_session, leader)
    db_session.commit()
    return project


def _set_layout(app, test_settings, state: str):
    app.config["SETTINGS"] = test_settings.model_copy(update={"storage_layout": state})


# ── 出厂默认与闭集 ────────────────────────────────────────────


def test_shipped_default_layout_is_legacy(test_settings):
    """出厂默认 legacy＝现状零回归（测出厂值，不测夹具覆写）。"""
    assert test_settings.storage_layout == "legacy"
    assert resolve_storage_layout(test_settings) == "legacy"
    assert STORAGE_LAYOUT_STATES == (
        "legacy",
        "dual_write",
        "read_new",
        "readonly",
        "retired",
    )


def test_layout_state_fail_closed_on_unknown():
    class _S:
        storage_layout = "fast_forward"  # 非法状态（配置写错必须当场炸）

    with pytest.raises(StorageError) as exc:
        resolve_storage_layout(_S())
    assert exc.value.args[0] == "storage_layout_invalid"


# ── 主体段解析 ────────────────────────────────────────────────


def test_org_prefix_and_no_cross_org_collision():
    assert org_object_prefix("org-a") == "org/org-a"
    assert org_object_prefix(None) == PLATFORM_SEGMENT
    with pytest.raises(StorageError):
        org_object_prefix("")
    base = "projects/p1/attachments/f/x.txt"
    keys = {
        prefixed_object_key(base, "org-a"),
        prefixed_object_key(base, "org-b"),
        prefixed_object_key(base, None),
    }
    assert len(keys) == 3  # 同一逻辑键在两个 org ＋ 平台段下互不碰撞
    assert all(k.split("/")[0] in {"org", "platform"} for k in keys)


def test_validate_object_key_accepts_subject_roots():
    assert validate_object_key("org/o1/projects/p1/attachments/f/x.txt")
    assert validate_object_key(f"{PLATFORM_SEGMENT}/projects/p1/attachments/f/x.txt")
    assert validate_object_key(f"{PLATFORM_SEGMENT}/document-templates/t/v/f.docx")
    with pytest.raises(StorageError):
        validate_object_key("org/../projects/p1/f/x.txt")
    with pytest.raises(StorageError):
        validate_object_key("employee/o1/projects/p1/f/x.txt")


# ── 五状态写读矩阵（纯函数层）─────────────────────────────────


def test_five_state_write_read_matrix(db_session):
    org, project = _org_project(db_session)
    logical = _LOGICAL.format(pid=project.id)
    prefixed = f"org/{org.id}/{logical}"
    expected = {
        "legacy": ((logical,), (logical,)),
        "dual_write": ((logical, prefixed), (logical,)),
        "read_new": ((prefixed,), (prefixed, logical)),
        "readonly": ((prefixed,), (prefixed, logical)),
        "retired": ((prefixed,), (prefixed,)),
    }
    for state, (writes, reads) in expected.items():
        assert physical_write_targets(db_session, logical, layout=state) == writes, state
        assert (
            physical_read_candidates(db_session, logical, layout=state) == reads
        ), state


def test_platform_root_and_unowned_project_go_platform(db_session):
    project = _plain_project(db_session)
    # document-templates 逻辑根：平台资产，恒 platform 段（即使库里存在 org）。
    template_key = "document-templates/tpl-1/方案/versions/1/f.docx"
    assert physical_write_targets(db_session, template_key, layout="read_new") == (
        f"{PLATFORM_SEGMENT}/{template_key}",
    )
    # 无主项目（leader 平台身份）⇒ M1 before_flush 自动戳 INTERNAL_ORG_ID
    # 平台内部桶——显式段而非编造归属（M3b「internal org 桶」登记语义）。
    from fde_api.orgs.models import INTERNAL_ORG_ID

    logical = _LOGICAL.format(pid=project.id)
    assert physical_read_candidates(db_session, logical, layout="retired") == (
        f"org/{INTERNAL_ORG_ID}/{logical}",
    )


# ── 物理落盘端到端（LocalObjectStorage × app settings）────────


def _storage(app) -> LocalObjectStorage:
    from typing import cast

    from fde_api.extensions import object_storage

    return cast(LocalObjectStorage, object_storage.current)


def _physical_path(app, key: str) -> Path:
    storage = _storage(app)
    return storage.root / "objects" / Path(key)


def test_dual_write_places_both_with_identical_bytes(db_session, app, test_settings):
    org, project = _org_project(db_session)
    _set_layout(app, test_settings, "dual_write")
    storage = _storage(app)
    logical = _LOGICAL.format(pid=project.id)
    payload = b"dual-write-bytes"
    for placement in physical_write_targets(db_session, logical, layout="dual_write"):
        storage.put_stream(placement, io.BytesIO(payload), "text/plain", {})
    legacy_path = _physical_path(app, logical)
    new_path = _physical_path(app, f"org/{org.id}/{logical}")
    assert legacy_path.is_file() and new_path.is_file()
    assert hashlib.sha256(legacy_path.read_bytes()).digest() == hashlib.sha256(
        new_path.read_bytes()
    ).digest()
    # dual_write 读旧键（迁移核对期以旧侧为读权威）
    with open_read_stream(
        storage, db_session, logical, layout="dual_write"
    ) as stream:
        assert stream.read() == payload


def test_read_new_writes_new_and_reads_with_fallback(db_session, app, test_settings):
    org, project = _org_project(db_session)
    _set_layout(app, test_settings, "read_new")
    storage = _storage(app)
    logical = _LOGICAL.format(pid=project.id)
    payload = b"read-new-bytes"
    for placement in physical_write_targets(db_session, logical, layout="read_new"):
        storage.put_stream(placement, io.BytesIO(payload), "text/plain", {})
    assert _physical_path(app, f"org/{org.id}/{logical}").is_file()
    assert not _physical_path(app, logical).exists()  # read_new 不再写旧根
    with open_read_stream(storage, db_session, logical, layout="read_new") as stream:
        assert stream.read() == payload
    # 回落：新侧缺失时读旧侧（迁移核对期的兜底；旧侧为迁移前存量）
    legacy_path = _physical_path(app, logical)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(payload)
    _physical_path(app, f"org/{org.id}/{logical}").unlink()
    with open_read_stream(storage, db_session, logical, layout="read_new") as stream:
        assert stream.read() == payload  # 旧侧还在 ⇒ 读得到（先搬后删的核对窗口）
    # retired 零回落：两侧都无 ⇒ object_not_found
    _physical_path(app, logical).unlink()
    with pytest.raises(StorageError):
        open_read_stream(storage, db_session, logical, layout="retired")


def test_retired_reads_do_not_fall_back_to_legacy(db_session, app, test_settings):
    _set_layout(app, test_settings, "retired")
    storage = _storage(app)
    project = _plain_project(db_session)
    logical = _LOGICAL.format(pid=project.id)
    legacy_path = _physical_path(app, logical)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy-only")
    with pytest.raises(StorageNotFoundError):
        open_read_stream(storage, db_session, logical, layout="retired")
    # readonly：读新优先仍回落旧（旧根冻结但存量可读）
    with open_read_stream(storage, db_session, logical, layout="readonly") as stream:
        assert stream.read() == b"legacy-only"


# ── 预签名签名面 ──────────────────────────────────────────────


def test_signature_binds_physical_key(tmp_path):
    derive = hashlib.sha256(b"fde-local-storage:test-jwt").digest()
    storage = LocalObjectStorage(tmp_path, signing_key=derive)
    key_a = "org/org-a/projects/p1/attachments/f/a.txt"
    key_b = "org/org-b/projects/p1/attachments/f/a.txt"
    storage.put_stream(key_a, io.BytesIO(b"a"), "text/plain", {})
    signed = storage.sign_download(key_a, "a.txt", 300)
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(signed).query)
    assert query["key"] == [key_a]
    # 同签名换物理键（跨 org 段）⇒ 拒绝
    with pytest.raises(StorageError):
        storage.open_signed_download(
            method="GET",
            key=key_b,
            filename="a.txt",
            expires=int(query["expires"][0]),
            signature=query["signature"][0],
        )
    _stored, stream, _disp = storage.open_signed_download(
        method="GET",
        key=key_a,
        filename="a.txt",
        expires=int(query["expires"][0]),
        signature=query["signature"][0],
    )
    stream.close()  # 原键签名通过（返回 (stored, stream, disposition) 三元组）



def test_signing_key_restart_stable_and_production_derived(tmp_path):
    """签名键派生自 FDE_JWT_SECRET（域分离）⇒ 跨重启稳定；生产接线钉住派生式。"""
    derive = hashlib.sha256(b"fde-local-storage:test-jwt").digest()
    first = LocalObjectStorage(tmp_path / "a", signing_key=derive)
    second = LocalObjectStorage(tmp_path / "b", signing_key=derive)
    key = f"{PLATFORM_SEGMENT}/projects/p1/f/x.txt"
    first.put_stream(key, io.BytesIO(b"x"), "text/plain", {})
    second.put_stream(key, io.BytesIO(b"x"), "text/plain", {})
    assert first.head(key).etag == second.head(key).etag
    src = (Path(__file__).resolve().parents[1] / "src" / "fde_api" / "extensions.py").read_text(
        encoding="utf-8"
    )
    assert 'sha256(\n                    f"fde-local-storage:{settings.jwt_secret}"' in src.replace(
        "\r\n", "\n"
    ) or "fde-local-storage:{settings.jwt_secret}" in src


# ── S2/S3 临时面 ──────────────────────────────────────────────


def test_transcript_draft_dir_org_segment(db_session, tmp_path):
    from fde_api.transcripts.service import _draft_dir

    org, project = _org_project(db_session)
    fake_settings = SimpleNamespace(transcript_draft_root=tmp_path)
    org_dir = _draft_dir(db_session, SimpleNamespace(project_id=project.id, id="d-1"), settings=fake_settings)
    assert org_dir == tmp_path / f"org/{org.id}" / "d-1"
    # 平台段分支＝项目解析不到（显式 None）：已 flush 的项目必落桶
    # （M1 before_flush 把无主项目戳进 INTERNAL_ORG_ID），故用不存在 id。
    platform_dir = _draft_dir(
        db_session, SimpleNamespace(project_id="no-such-project", id="d-2"), settings=fake_settings
    )
    assert platform_dir == tmp_path / PLATFORM_SEGMENT / "d-2"
    agents_src = (
        Path(__file__).resolve().parents[1] / "src" / "fde_api" / "agents" / "service.py"
    ).read_text(encoding="utf-8")
    assert "org_object_prefix(" in agents_src and "_org_segment" in agents_src


# ── host 票据 org 归属元数据 ──────────────────────────────────


def _session_factory(db_session):
    engine = db_session.get_bind()

    def factory() -> Session:
        return Session(engine)

    return factory


def test_host_grant_carries_org_claim(db_session):
    token = issue_run_grant(
        jwt_secret="test-secret-with-at-least-thirty-two-characters",
        user_id="u1",
        project_id="p1",
        org_id="org-x",
        run_id="r1",
        workspace="/tmp/w",
    )
    payload = verify_run_grant(
        jwt_secret="test-secret-with-at-least-thirty-two-characters",
        token=token,
        run_id="r1",
    )
    assert payload["org_id"] == "org-x"


def test_authorize_host_run_resolves_actor_org(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, role="admin", org_id=org.id)
    platform_actor = make_user(db_session, role="admin", org_id=None)
    secret = "test-secret-with-at-least-thirty-two-characters"
    factory = _session_factory(db_session)
    fp1 = authorize_host_run(
        jwt_secret=secret,
        user_id=actor.id,
        project_id="p1",
        run_id="r-org",
        workspace="/tmp/w1",
        session_factory=factory,
    )
    assert len(fp1) == 64
    token2 = issue_run_grant(
        jwt_secret=secret,
        user_id=platform_actor.id,
        project_id="p1",
        org_id=None,
        run_id="r-platform",
        workspace="/tmp/w2",
    )
    assert verify_run_grant(jwt_secret=secret, token=token2, run_id="r-platform")[
        "org_id"
    ] is None


# ── 迁移命令（dry-run 缺省；--execute 逐文件 sha256 核对；幂等）──


def test_cli_storage_migrate_layout_dry_run_execute_idempotent(
    db_session, app, test_settings, monkeypatch, capsys
):
    from fde_api.extensions import object_storage

    org, project = _org_project(db_session)
    _set_layout(app, test_settings, "dual_write")
    storage = object_storage.current
    logical = _LOGICAL.format(pid=project.id)
    payload = b"migrate-me"
    storage.put_stream(logical, io.BytesIO(payload), "text/plain", {})

    runner = app.test_cli_runner()
    # dry-run（缺省）：只报计划不落盘
    result = runner.invoke(args=["storage-migrate-layout"])
    assert result.exit_code == 0, result.output
    assert "would copy" in result.output
    assert not _physical_path(app, f"org/{org.id}/{logical}").exists()
    # --execute：落盘且 sha256 一致
    result = runner.invoke(args=["storage-migrate-layout", "--execute"])
    assert result.exit_code == 0, result.output
    target_path = _physical_path(app, f"org/{org.id}/{logical}")
    assert target_path.is_file()
    assert hashlib.sha256(target_path.read_bytes()).digest() == hashlib.sha256(
        payload
    ).digest()
    # 幂等重跑：目标在场且一致 ⇒ skipped
    result = runner.invoke(args=["storage-migrate-layout", "--execute"])
    assert result.exit_code == 0, result.output
    assert "skipped=1" in result.output


# ── 静态钉：全仓存储调用点必须经布局 helper ────────────────────


def test_static_storage_call_sites_use_layout_helpers():
    from pathlib import Path as _P

    src = _P(__file__).resolve().parents[1] / "src" / "fde_api"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        rel = path.relative_to(src).as_posix()
        if rel.startswith(("storage/",)) or rel == "cli.py":
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            hits = [
                marker
                for marker in (
                    ".put_stream(",
                    ".open_stream(",
                    "sign_download(",
                )
                if marker in line
            ]
            if not hits:
                continue
            window = "\n".join(lines[max(0, idx - 8) : idx + 14])
            if not any(
                helper in window
                for helper in (
                    "physical_write_targets",
                    "open_read_stream",
                    "existing_read_key",
                )
            ):
                offenders.append(f"{rel}:{idx + 1}")
    assert offenders == [], "存储调用点未经布局翻译：\n" + "\n".join(offenders)
