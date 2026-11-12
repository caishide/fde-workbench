# -*- coding: utf-8 -*-
"""训练场批跑器（L 线 L2 轮，2026-11-12）。

走生产 HTTP 面（``POST /simulation/runs`` → ``execute`` → ``evaluate`` →
``GET /runs/<id>/evaluation``）真机批跑指定场景 N 次，逐 run 落一行 JSONL
到**真相层** ``--out-dir``（拒绝仓内输出）；分数与轴值入行，场景正文与判卷
基准零落盘（仓库侧只存汇总＋指针＋sha256，沿 E-2 先例）。

锚点模式（``--anchor``）：指名场景按「固定输入＋固定 agent 配置」跑——首个
run 正常创建执行，后续 run 走 ``retry``（attempt+1、seed 不变 ⇒ 输入逐字节
同源），得分差异＝纯评估侧噪声。

鉴权：``--token-file`` 读容器内签发的 JWT（15 分钟有效期；签发配方见
V3.1 试点操作配方——create_app(Settings()) app context 内
``issue_access_token``）。AI 不代发起真实 zcode 沙箱 run（``--adapter real``
须人工在授权 run 内执行本脚本；mock 批跑无此约束）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/simulation/ → 本仓根


def _refuse_inside_repo(out_dir: Path) -> None:
    # 对比本仓根路径（L1 转换器同款守卫）——不能按「祖先链有 .git」判，
    # 真相层自带 .git（知识库自身是仓）会误伤。
    repo = _REPO_ROOT.resolve()
    root = out_dir.resolve()
    if root == repo or repo in root.parents:
        raise SystemExit(f"输出目录落在本仓内，拒绝（真相层专用）：{root}")


API_PREFIX = "/api/v1"


def _api_base(raw: str) -> str:
    """把主机根归一成 API 根（带 ``/api/v1`` 前缀）。

    蓝图前缀写在 ``simulation_blueprint = Blueprint(..., url_prefix="/api/v1/simulation")``
    ——只写 ``{base}/simulation/...`` 会 404（前缀整段缺失）。此处统一补齐，
    已带前缀者原样保留（幂等）。
    """
    base = raw.rstrip("/")
    if base.endswith(API_PREFIX):
        return base
    return base + API_PREFIX


def _http(method: str, url: str, *, token: str, body: dict | None = None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=900) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def _resolve_active_scenario(base: str, token: str, scenario_key: str) -> dict:
    status, resp = _http(
        "GET", f"{base}/simulation/scenarios?include_history=true&limit=200", token=token
    )
    if status != 200:
        raise SystemExit(f"场景列表失败 http={status}")
    rows = (resp.get("data") or {}).get("items") or []
    for row in rows:
        if row.get("scenario_key") == scenario_key and row.get("status") == "active":
            return row
    raise SystemExit(f"场景无 active 版本：{scenario_key}")


def _run_once(base: str, token: str, scenario: dict, *, adapter: str, seed: int) -> dict:
    status, resp = _http(
        "POST",
        f"{base}/simulation/runs",
        token=token,
        body={
            "scenario_id": scenario["id"],
            "adapter_mode": adapter,
            "seed": seed,
            "execute": True,
        },
    )
    if status != 201:
        raise SystemExit(
            f"run 创建/执行失败 {scenario.get('scenario_key')} http={status} "
            f"{json.dumps(resp.get('error') or resp, ensure_ascii=False)[:300]}"
        )
    return resp.get("data") or {}


def _retry_once(base: str, token: str, run_id: str) -> dict:
    status, resp = _http("POST", f"{base}/simulation/runs/{run_id}/retry", token=token)
    if status != 201:
        raise SystemExit(
            f"retry 失败 http={status} {json.dumps(resp.get('error') or resp, ensure_ascii=False)[:300]}"
        )
    return resp.get("data") or {}


def _evaluate(base: str, token: str, run_id: str, model_mode: str) -> None:
    status, resp = _http(
        "POST",
        f"{base}/simulation/runs/{run_id}/evaluate?include_model=true&model_mode={model_mode}",
        token=token,
    )
    if status not in (200, 201):
        raise SystemExit(
            f"evaluate 失败 run={run_id} http={status} "
            f"{json.dumps(resp.get('error') or resp, ensure_ascii=False)[:300]}"
        )


def _evaluation_report(base: str, token: str, run_id: str) -> dict:
    status, resp = _http(
        "GET", f"{base}/simulation/runs/{run_id}/evaluation", token=token
    )
    if status != 200:
        return {}
    return resp.get("data") or {}


def _normalize_report(report: dict) -> dict:
    """把评估报告规约成记录行形状：{rubric_version, evaluator_version, layers:{}}。"""
    layers_out: dict[str, dict] = {}
    rubric_version = ""
    evaluator_version = ""
    raw_layers = report.get("layers")
    if isinstance(raw_layers, list):
        for row in raw_layers:
            if not isinstance(row, dict):
                continue
            name = str(row.get("layer") or "")
            layers_out[name] = {
                "total_score": row.get("total_score"),
                "verdict": row.get("verdict"),
                "evaluator_id": row.get("evaluator_id"),
                "rubric_version": row.get("rubric_version"),
            }
            if name == "deterministic":
                rubric_version = str(row.get("rubric_version") or "")
                evaluator_version = (
                    f"{row.get('evaluator_id')}@{row.get('rubric_version')}"
                )
    return {
        "rubric_version": rubric_version,
        "evaluator_version": evaluator_version,
        "layers": layers_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="训练场批跑器（L2 分布读数用）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--token-file", required=True, help="JWT 文件（容器内签发）")
    parser.add_argument("--scenario", action="append", required=True, help="场景业务键（可重复）")
    parser.add_argument(
        "--anchor", action="append", default=[], help="锚点场景业务键（固定输入+固定配置，retry 取样）"
    )
    parser.add_argument("--runs-per-scenario", type=int, default=3)
    parser.add_argument("--adapter", choices=("mock", "real"), default="mock")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-mode", choices=("stub", "server"), default="stub")
    parser.add_argument("--out-dir", required=True, help="JSONL 输出目录（真相层，仓内即拒）")
    args = parser.parse_args()

    base = _api_base(args.base_url)
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    out_dir = Path(args.out_dir)
    _refuse_inside_repo(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "runs.jsonl"
    manifest_path = out_dir / "manifest.json"

    anchors = {key for key in args.anchor}
    unknown = anchors - set(args.scenario)
    if unknown:
        raise SystemExit(f"--anchor 必须是 --scenario 的子集：{sorted(unknown)}")

    existing_lines = jsonl_path.read_text(encoding="utf-8").splitlines() if jsonl_path.exists() else []
    records = [json.loads(line) for line in existing_lines if line.strip()]
    done_keys = {(r.get("scenario_key"), r.get("seed"), r.get("attempt")) for r in records}

    for scenario_key in args.scenario:
        scenario = _resolve_active_scenario(base, token, scenario_key)
        is_anchor = scenario_key in anchors
        print(f"[scenario] {scenario_key} id={scenario['id']} v={scenario.get('version')} anchor={is_anchor}")
        anchor_run_id = None
        for i in range(args.runs_per_scenario):
            if is_anchor:
                # 锚点：首个 run 建+执行；后续走 retry（attempt+1，seed 不变）。
                if anchor_run_id is None:
                    run = _run_once(base, token, scenario, adapter=args.adapter, seed=args.seed)
                    anchor_run_id = run.get("id")
                else:
                    run = _retry_once(base, token, anchor_run_id)
            else:
                run = _run_once(base, token, scenario, adapter=args.adapter, seed=args.seed + i)
            identity = (scenario_key, run.get("seed"), run.get("attempt"))
            if identity in done_keys:
                print(f"  [skip] run 已在册 {run.get('run_key')}")
                continue
            status = str(run.get("status") or "")
            if status == "succeeded":
                _evaluate(base, token, str(run["id"]), args.model_mode)
                report = _evaluation_report(base, token, str(run["id"]))
            else:
                report = {}
            record = {
                "run_id": run.get("id"),
                "run_key": run.get("run_key"),
                "scenario_key": scenario_key,
                "scenario_id": scenario.get("id"),
                "scenario_version": scenario.get("version"),
                "variant": run.get("run_key", "").split(":")[1] if ":" in str(run.get("run_key", "")) else None,
                "split": run.get("split") or scenario.get("split"),
                "adapter_mode": run.get("adapter_mode") or args.adapter,
                "seed": run.get("seed"),
                "attempt": run.get("attempt"),
                "status": status,
                "error": run.get("error"),
                "degraded": False,
                "evaluation": _normalize_report(report),
            }
            records.append(record)
            done_keys.add(identity)
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            score = (record["evaluation"].get("layers") or {}).get(args.model_mode if args.model_mode == "server" else "model") or {}
            print(
                f"  [run] {run.get('run_key')} status={status} "
                f"model_total={score.get('total_score')} verdict={score.get('verdict')}"
            )
            time.sleep(0.2)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runs_file": jsonl_path.name,
        "runs_sha256": hashlib.sha256(jsonl_path.read_bytes()).hexdigest() if jsonl_path.exists() else None,
        "record_count": len(records),
        "scenarios": list(args.scenario),
        "anchors": sorted(anchors),
        "adapter": args.adapter,
        "model_mode": args.model_mode,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {len(records)} 行 -> {jsonl_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
