"""诊断评测批跑 CLI（获客诊断工具任务书 T-07 生成 + T-08 评分 + T-09 曲线）。

跑法（宿主 Windows，server venv；**在主树 server/ 目录跑**——Settings 读 cwd
的 .env，代码走本仓 worktree 的 src）：

```bash
cd <repo>/server
PYTHONPATH=<worktree>/server/src python <worktree>/scripts/diagnostic_eval/run_eval.py bootstrap
PYTHONPATH=... run_eval.py generate --run 2026-11-11
PYTHONPATH=... run_eval.py judge   --run 2026-11-11
PYTHONPATH=... run_eval.py curve   --doc-number 1 --out ../docs/audit/诊断评测-评分曲线-1.md
```

**评测的是生产路径**：generate 走与线上完全相同的受理链（create_session →
首屏测算 → 续填 → 留资 → request_report 受理）与完全相同的生成函数
（``jobs.handle_diagnostic_report``——与 worker 同一代码路径，含 R-1~R-7 契约
闸与输出端兜底脱敏），只是把异步排队换成同步直调。唯一例外：本进程内把
``enqueue_outbox`` 置为 no-op——防止把作业投给**另一个进程里在跑的 worker**
（共享部署栈）造成同卡双跑双计费；受理逻辑本身（配额/留资闸/幂等）不绕。

**纪律**：报告原件只落真相层（E-2）；judge 元验证先行，元验证不过 ⇒ 评分
档案带 ``usable_as_evolution_evidence=false``（分数留档但不得作进化判定输入）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SERVER_SRC = Path(__file__).resolve().parents[2] / "server" / "src"
sys.path.insert(0, str(SERVER_SRC))

import eval_lib  # noqa: E402  (scripts 同目录直import)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_ACTOR_USERNAME = "diag-ai-service"


def _actor_username() -> str:
    import os

    return (
        os.environ.get("FDE_DIAGNOSTICS_AI_ACTOR_USERNAME") or ""
    ).strip() or DEFAULT_ACTOR_USERNAME


def _make_app(extra: dict[str, Any] | None = None):
    from fde_api.app import create_app
    from fde_api.config import Settings

    app = create_app(Settings())
    update: dict[str, Any] = {"diagnostics_enabled": True}
    if extra:
        update.update(extra)
    app.config["SETTINGS"] = app.config["SETTINGS"].model_copy(update=update)
    return app


def _require_generation_ready(app) -> None:
    settings = app.config["SETTINGS"]
    if not getattr(settings, "deepseek_api_key", None) or not getattr(
        settings.deepseek_api_key, "get_secret_value", lambda: ""
    )():
        raise SystemExit("无 DeepSeek API Key——生成面不可用（fail-closed，不产空档案）。")


# ── bootstrap ────────────────────────────────────────────────────────


def cmd_bootstrap(_args: argparse.Namespace) -> int:
    root = eval_lib.truth_root()
    from sqlalchemy import select

    from fde_api.auth.models import User
    from fde_api.auth.passwords import hash_password
    from fde_api.extensions import db

    username = _actor_username()
    with _make_app(extra={"diagnostics_ai_actor_username": username}).app_context():
        with db.session() as session:
            user = session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    username=username,
                    display_name="诊断报告生成·平台服务账号",
                    role="fde_engineer",
                    password_hash=hash_password(uuid.uuid4().hex),
                    must_change_password=False,
                    is_active=True,
                )
                session.add(user)
                session.commit()
                print(f"service_account_created={username}")
            elif not user.is_active:
                raise SystemExit(f"服务账号 {username} 存在但已停用——请先在管理面恢复。")
            else:
                print(f"service_account_ok={username}")
    fixtures = eval_lib.load_fixtures(SERVER_SRC.parents[1])
    print(f"fixtures={len(fixtures)}: {', '.join(sorted(fixtures))}")
    for card_id in sorted(fixtures):
        eval_lib.load_card(root, card_id)  # 缺卡即 fail-closed
    meta_path = root / "meta" / META_FIXTURE_FILENAME
    if not meta_path.is_file():
        raise SystemExit(f"元验证夹具缺失：{meta_path}")
    print(f"truth_root={root}")
    print("BOOTSTRAP_OK")
    return 0


# ── generate（T-07：生产路径批跑） ───────────────────────────────────


def cmd_generate(args: argparse.Namespace) -> int:
    root = eval_lib.truth_root()
    repo_root = SERVER_SRC.parents[1]
    fixtures = eval_lib.load_fixtures(repo_root)
    wanted = sorted(fixtures) if not args.cases else [c.strip() for c in args.cases.split(",")]
    unknown = [case for case in wanted if case not in fixtures]
    if unknown:
        raise SystemExit(f"未知 case_id：{unknown}")

    from fde_api.diagnostics import jobs as diag_jobs
    from fde_api.diagnostics import service
    from fde_api.diagnostics.jobs import handle_diagnostic_report
    from fde_api.diagnostics.report_contract import NUMBER_GATE_VERSION
    from fde_api.diagnostics.questionnaire import DIAGNOSTIC_SLOTS, FIRST_SCREEN_SLOTS

    slot_keys = {
        "first_screen": {slot.key for slot in FIRST_SCREEN_SLOTS},
        "diagnostic": {slot.key for slot in DIAGNOSTIC_SLOTS},
    }
    # 考卷口语原话值 → 生产问卷闭集适配（fail-closed；指纹进 run.json 留痕）
    answer_mapping = eval_lib.load_answer_mapping(repo_root)
    mapping_path = eval_lib.fixtures_dir(repo_root) / eval_lib.ANSWER_MAPPING_FILENAME
    mapping_sha = eval_lib.file_sha256(mapping_path)
    # ★共享部署栈防双跑：本进程内 outbox 打点置空（受理逻辑不绕，作业不外投）。
    import fde_api.jobs.outbox as outbox_mod

    outbox_mod.enqueue_outbox = lambda *a, **k: None  # type: ignore[assignment]

    app = _make_app(extra={"diagnostics_ai_actor_username": _actor_username()})
    _require_generation_ready(app)
    settings = app.config["SETTINGS"]
    prompt_version = diag_jobs.REPORT_PROMPT_VERSION
    report_version = None

    run_out = eval_lib.run_dir(root, args.run)
    reports_dir = run_out / "reports"
    cases: dict[str, Any] = {}
    failures: list[str] = []

    with app.app_context():
        for index, case_id in enumerate(wanted):
            fixture = fixtures[case_id]
            first, diag = eval_lib.split_fixture_answers(fixture, slot_keys=slot_keys)
            overrides = (answer_mapping.get("_case_overrides") or {}).get(case_id) or {}
            first = eval_lib.apply_answer_mapping(
                case_id, first, answer_mapping, overrides=overrides
            )
            diag = eval_lib.apply_answer_mapping(case_id, diag, answer_mapping)
            ip = f"203.0.113.{(index % 200) + 10}"  # 每卡独立合成 IP（同款测试隔离法）
            contact = f"eval-{case_id}@example.invalid"
            row, token = service.create_session(ip_address=ip, source_type="direct")
            service.submit_first_screen(token, first)
            service.submit_answers(token, diag)
            service.capture_lead(token, {"contact": contact, "name": "评测样例", "consent": True})
            service.request_report(token)
            handle_diagnostic_report(SimpleNamespace(target_id=row.id))
            fresh = service.get_session(token)
            report_version = (fresh.report or {}).get("version") or report_version
            if not fresh.report:
                failures.append(f"{case_id}: {fresh.failure_code or 'report_missing'}")
                cases[case_id] = {
                    "session_id": row.id,
                    "report_state": service.report_state(fresh),
                    "failure_code": fresh.failure_code,
                }
                print(f"[{case_id}] FAILED: {fresh.failure_code}", flush=True)
                continue
            report_path = reports_dir / f"{case_id}.json"
            eval_lib.write_json(
                report_path,
                {
                    "case_id": case_id,
                    "session_id": row.id,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "model": (fresh.report or {}).get("model") or {},
                    "report": fresh.report,
                },
            )
            cases[case_id] = {
                "session_id": row.id,
                "report_state": "ready",
                "report_file": f"reports/{case_id}.json",
                "report_sha256": eval_lib.file_sha256(report_path),
            }
            print(f"[{case_id}] ready ({report_path})", flush=True)

    run_json = {
        "run_id": args.run,
        "eval_set_version": args.eval_set_version or args.run,
        "created_at": datetime.now(UTC).isoformat(),
        "prompt_version": prompt_version,
        # 数字闸版本随 run 落档（curve 3 断点）：口径变 ⇒ 生成结果可比性变，
        # 必须与 prompt_version 同列可追（曲线文档按此标注版本断点）。
        "number_gate_version": NUMBER_GATE_VERSION,
        "report_version": report_version or "",
        "generator": {"mode": "production_path_sync", "actor": _actor_username()},
        "fixtures_version": sorted(
            {str(f.get("fixture_version") or "") for f in (fixtures[c] for c in wanted)}
        ),
        "answer_mapping_sha256": mapping_sha,
        "cases": cases,
    }
    eval_lib.write_json(run_out / "run.json", run_json)
    if failures:
        print(f"GENERATE_PARTIAL: {failures}")
        return 1
    print(f"GENERATE_OK run={args.run} cases={len(cases)}")
    return 0


# ── judge（T-08：元验证先行 + 逐卡评分） ─────────────────────────────

# 元验证夹具文件名（真相层 meta/ 目录）。v0.2＝curve 1 元验证 fail 的版本
# 断点修订（A1 期望带 78–100 ＋ rubric-v0.2 同源豁免）；v0.1 原件留存不覆写。
META_FIXTURE_FILENAME = "元验证夹具-v0.2.json"


def _build_anchors(root: Path) -> list[dict[str, Any]]:
    meta = eval_lib.load_json(root / "meta" / META_FIXTURE_FILENAME)
    anchors: list[dict[str, Any]] = []
    missing: list[str] = []
    for anchor in meta.get("anchors") or []:
        anchor_id = str(anchor.get("anchor_id") or "")
        card_id = eval_lib.ANCHOR_CARD_BY_ID.get(anchor_id)
        if not card_id:
            raise SystemExit(f"锚点 {anchor_id} 无案例卡映射（脚本侧知识缺失）")
        card = eval_lib.load_card(root, card_id)
        kind = str(anchor.get("kind") or "")
        doc_type = eval_lib.ANCHOR_DOC_TYPE_BY_KIND.get(kind)
        if not doc_type:
            raise SystemExit(f"锚点 {anchor_id} kind={kind!r} 无评分对象类型映射")
        report_text = ""
        pointer = str(anchor.get("path_pointer") or "").strip()
        path = Path(str(anchor.get("path") or ""))
        if path.suffix.lower() == ".json" and path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            field_name = pointer.rsplit(".", 1)[-1] if pointer else "report_demo"
            report_text = str((payload.get("display") or {}).get(field_name) or "")
        elif path.is_file():
            report_text = path.read_text(encoding="utf-8", errors="replace")
        if not report_text.strip():
            missing.append(f"{anchor_id}: {path}")
            continue
        band_low, band_high = eval_lib.parse_band(str(anchor.get("expected_judge_band") or ""))
        anchors.append(
            {
                "anchor_id": anchor_id,
                "label": str(anchor.get("label") or ""),
                "report_text": report_text,
                "reference_material": eval_lib.build_reference_material(card),
                "band_low": band_low,
                "band_high": band_high,
                "doc_type": doc_type,
            }
        )
    if missing:
        raise SystemExit(
            "锚点原件缺失/不可读 ⇒ insufficient_data（不默认通过、不用部分锚点评分）："
            + "; ".join(missing)
        )
    return anchors


def cmd_judge(args: argparse.Namespace) -> int:
    root = eval_lib.truth_root()
    repo_root = SERVER_SRC.parents[1]
    from flask import current_app

    from fde_api.simulation.diagnostic_judge import (
        DIAGNOSTIC_JUDGE_PURPOSE,
        DIAGNOSTIC_JUDGE_RUBRIC_VERSION,
        evaluate_diagnostic_report,
        judge_client,
        render_report_text,
        run_meta_validation,
    )

    app = _make_app()
    with app.app_context():
        client = judge_client()
        if client is None:
            raise SystemExit("评分面无 provider（缺 API Key）——fail-closed，不产空评分档案。")
        settings = current_app.config["SETTINGS"]
        override = str(getattr(settings, "diagnostic_judge_model", "") or "").strip()
        judge_model = override or settings.deepseek_simulation_evaluation_model

        run_out = eval_lib.run_dir(root, args.run)
        run_json_path = run_out / "run.json"
        if not run_json_path.is_file():
            raise SystemExit(f"run 不存在：{run_out}（先跑 generate）")
        run_json = eval_lib.load_json(run_json_path)
        cases_meta = run_json.get("cases") or {}
        wanted = (
            [c.strip() for c in args.cases.split(",")]
            if args.cases
            else sorted(k for k, v in cases_meta.items() if v.get("report_state") == "ready")
        )

        anchors = _build_anchors(root)
        meta_fixture = eval_lib.load_json(root / "meta" / META_FIXTURE_FILENAME)
        counterexamples = [
            {
                "case_id": str(item.get("case_id") or ""),
                "label": str(item.get("label") or ""),
                "input_text": str(item.get("input") or ""),
            }
            for item in (meta_fixture.get("counterexamples") or [])
        ]
        print(f"meta_validation: anchors={len(anchors)} counterexamples={len(counterexamples)}", flush=True)
        meta_gate = run_meta_validation(client, anchors=anchors, counterexamples=counterexamples)
        meta_gate["meta_fixture_version"] = str(meta_fixture.get("fixture_version") or "")
        print(f"meta_gate={meta_gate['verdict']}", flush=True)

        scored: dict[str, Any] = {}
        for index, case_id in enumerate(wanted):
            if args.card_delay_seconds and index:
                time.sleep(args.card_delay_seconds)  # 共享配额环境节流：评分卡间隔
            report_path = run_out / str(cases_meta[case_id].get("report_file") or "")
            report = (eval_lib.load_json(report_path) or {}).get("report") or {}
            card = eval_lib.load_card(root, case_id)
            judgment = evaluate_diagnostic_report(
                client,
                report_text=render_report_text(report),
                reference_material=eval_lib.build_reference_material(card),
                case_id=case_id,
                doc_type="diagnosis_advice",
            )
            scored[case_id] = judgment.to_json()
            scored[case_id]["report_sha256"] = cases_meta[case_id].get("report_sha256")
            print(
                f"[{case_id}] {judgment.status} total={judgment.total} "
                f"verdict={judgment.verdict} parroting={judgment.parroting_suspected}",
                flush=True,
            )

        usable = meta_gate.get("verdict") == "pass"
        scores = {
            "run_id": args.run,
            "judged_at": datetime.now(UTC).isoformat(),
            "judge_version": DIAGNOSTIC_JUDGE_RUBRIC_VERSION,
            "judge_model": judge_model,
            "judge_purpose": DIAGNOSTIC_JUDGE_PURPOSE,
            "rubric_version": DIAGNOSTIC_JUDGE_RUBRIC_VERSION,
            "meta_gate": meta_gate,
            "usable_as_evolution_evidence": usable,
            "cases": scored,
        }
        eval_lib.write_json(run_out / "scores.json", scores)
        run_json["judge_version"] = DIAGNOSTIC_JUDGE_RUBRIC_VERSION
        eval_lib.write_json(run_json_path, run_json)
        print(f"SCORES_OK run={args.run} usable_as_evolution_evidence={usable}")
        return 0 if usable else 3


# ── curve（T-09：版本化曲线文档） ────────────────────────────────────


def cmd_curve(args: argparse.Namespace) -> int:
    root = eval_lib.truth_root()
    runs = eval_lib.aggregate_runs(root)
    markdown = eval_lib.render_curve_md(
        runs, doc_number=args.doc_number, breakpoints=args.breakpoint or None
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(f"CURVE_OK {out} runs={len(runs)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断评测批跑（T-07/T-08/T-09）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("bootstrap", help="服务账号 + 真相层/fixtures 在场核验（幂等）")

    gen = sub.add_parser("generate", help="生产路径批跑生成报告（原件落真相层）")
    gen.add_argument("--run", required=True, help="评测集版本号，如 2026-11-11")
    gen.add_argument("--cases", default="", help="逗号分隔子集（缺省=全量）")
    gen.add_argument(
        "--eval-set-version",
        default="",
        help=(
            "考卷版本标签（缺省＝run id）。**同一考卷的多轮重跑必须显式传同一个值**——"
            "曲线按「考卷版本 + 生成器版本」两轴呈现，只改生成器不许改考卷版本号"
            "（改了就是 C 类改考题，须打版本断点）。"
        ),
    )

    jud = sub.add_parser("judge", help="元验证闸 + 逐卡评分（评分档案落真相层）")
    jud.add_argument("--run", required=True)
    jud.add_argument("--cases", default="", help="逗号分隔子集（缺省=已就绪全量）")
    jud.add_argument(
        "--card-delay-seconds",
        type=float,
        default=0.0,
        help=(
            "评分卡之间的间隔秒数（共享 AI 配额环境的节流；缺省 0＝无间隔原行为）。"
            "评分调用比生成调用快得多，无间隔连发易触发 provider 限流（2026-11-11 实录）。"
        ),
    )

    cur = sub.add_parser("curve", help="聚合全部 run 渲染版本化曲线文档")
    cur.add_argument("--doc-number", type=int, required=True)
    cur.add_argument("--out", required=True, help="仓库侧输出路径（汇总+指针，零正文）")
    cur.add_argument(
        "--breakpoint",
        action="append",
        help="版本断点行（C 类修复处，可多次）",
    )

    args = parser.parse_args()
    return {
        "bootstrap": cmd_bootstrap,
        "generate": cmd_generate,
        "judge": cmd_judge,
        "curve": cmd_curve,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
