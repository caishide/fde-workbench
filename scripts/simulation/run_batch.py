# -*- coding: utf-8 -*-
"""训练场批跑器（L 线 L2 轮，2026-11-12）。

走生产 HTTP 面（``POST /simulation/runs`` → ``execute`` → ``evaluate`` →
``GET /runs/<id>/evaluation``）真机批跑指定场景 N 次，逐 run 落一行 JSONL
到**真相层** ``--out-dir``（拒绝仓内输出）；分数与轴值入行，场景正文与判卷
基准零落盘（仓库侧只存汇总＋指针＋sha256，沿 E-2 先例）。

锚点模式（``--anchor``）：指名场景按「固定输入＋固定 agent 配置」跑——**只建
一个 run**（固定 seed、固定产物），随后对**同一个 run 反复 evaluate N 轮**，
每轮取一次评估报告＝一个评估侧噪声样本。服务端同 (run, 层, 评估器, 规则
版本) 重评是**更新该行**而非追加，故 N 轮覆盖同一行、读数逐轮独立。

（为何不用 ``retry``：服务端 ``retry_run`` 只允许 failed/timeout/cancelled 的
run 重试，completed 的 run 一律 409「只有失败/超时/取消的运行可重试」——锚点
取样改走「同一 fixed run 反复评估」。）

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

# 训练场 run 终态词表（server/src/fde_api/simulation/models.py::RUN_STATUSES）——
# 成功终态是 ``completed``（**没有** ``succeeded``）。写错词表 ⇒ 成功 run 当失败、
# 评估永不触发（本轮真机批跑撞出来的缺陷，已按服务端词表校正）。
RUN_STATUS_SUCCESS = "completed"

# 评估层 → 评估器 id（服务端 evaluator.py）：规则层 ``rules``，模型层 ``model:<mode>``。
DETERMINISTIC_EVALUATOR = "rules"
MODEL_EVALUATOR_PREFIX = "model:"


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
    """解析某业务键的**当前有效** active 场景（默认 normal 分支优先）。

    走默认有效版本投影（include_history=false + q={scenario_key}），不走
    include_history=true——否则历史版本链里残留的旧 active 行会被升序遍历先捞到，
    绕过当前有效版本的真实状态与内容快照。
    """
    from urllib.parse import quote

    status, resp = _http(
        "GET",
        f"{base}/simulation/scenarios?q={quote(scenario_key, safe='')}&limit=200",
        token=token,
    )
    if status != 200:
        raise SystemExit(f"场景列表失败 http={status}")
    rows = (resp.get("data") or {}).get("items") or []
    matched = [
        row
        for row in rows
        if row.get("scenario_key") == scenario_key and row.get("status") == "active"
    ]
    if not matched:
        raise SystemExit(f"场景无 active 有效版本：{scenario_key}")
    for row in matched:
        if row.get("variant") == "normal":
            return row
    return matched[0]


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


def _normalize_report(report: dict, model_mode: str = "stub", layer: str = "model") -> dict:
    """把评估报告规约成记录行形状。

    **按 evaluator_id 索引层行**（不是层名）——同一 run 上模型层可同时存在
    ``model:stub`` 与 ``model:server`` 两行（服务端按评估器分行落库），按层名
    索引会让后写的覆盖先写的 ⇒ 两种评估器的分数互相污染。

    ``layer_evaluator_id`` 记下**所测层**对应的评估器 id，供分布库做层感知
    轴取值（锚点组轴＝rubric_version × 评估器版本）。
    """
    layers_out: dict[str, dict] = {}
    by_layer: dict[str, list[dict]] = {}
    raw_layers = report.get("layers")
    if isinstance(raw_layers, list):
        for row in raw_layers:
            if not isinstance(row, dict):
                continue
            evaluator_id = str(row.get("evaluator_id") or "")
            layer_name = str(row.get("layer") or "")
            layers_out[evaluator_id or layer_name] = {
                "layer": layer_name,
                "total_score": row.get("total_score"),
                "verdict": row.get("verdict"),
                "evaluator_id": evaluator_id,
                "rubric_version": row.get("rubric_version"),
            }
            by_layer.setdefault(layer_name, []).append(layers_out[evaluator_id or layer_name])

    picked = None
    if layer == "model":
        # 模型层：优先取与请求模式对应的评估器（model:server / model:stub）。
        for row in by_layer.get("model", []):
            if str(row.get("evaluator_id") or "") == f"{MODEL_EVALUATOR_PREFIX}{model_mode}":
                picked = row
                break
    if picked is None:
        candidates = by_layer.get(layer) or []
        picked = candidates[0] if candidates else None

    rubric_version = str((picked or {}).get("rubric_version") or "")
    evaluator_id = str((picked or {}).get("evaluator_id") or "")
    return {
        "rubric_version": rubric_version,
        "evaluator_version": f"{evaluator_id}@{rubric_version}" if evaluator_id or rubric_version else "",
        "layer_evaluator_id": evaluator_id,
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
    parser.add_argument(
        "--call-interval-seconds",
        type=float,
        default=0.2,
        help="相邻两轮评估调用之间的间隔秒数（默认 0.2；对限流敏感的 provider 建议加大）",
    )
    parser.add_argument("--out-dir", required=True, help="JSONL 输出目录（真相层，仓内即拒）")
    args = parser.parse_args()
    if args.call_interval_seconds < 0:
        raise SystemExit("--call-interval-seconds 不能为负")

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
    # 幂等键含**评估轮次**：锚点同一 run 反复评估 ⇒ (场景, run, 轮次) 才是唯一样本。
    done_keys = {
        (r.get("scenario_key"), r.get("run_id"), r.get("eval_round")) for r in records
    }

    for scenario_key in args.scenario:
        scenario = _resolve_active_scenario(base, token, scenario_key)
        is_anchor = scenario_key in anchors
        print(f"[scenario] {scenario_key} id={scenario['id']} v={scenario.get('version')} anchor={is_anchor}")
        anchor_run = None
        for i in range(args.runs_per_scenario):
            if is_anchor:
                # 锚点：只建**一个** run（输入固定＋agent 配置固定），随后对同一
                # run 反复 evaluate——每轮读数＝一个评估侧噪声样本。
                if anchor_run is None:
                    anchor_run = _run_once(
                        base, token, scenario, adapter=args.adapter, seed=args.seed
                    )
                run = anchor_run
                eval_round = i + 1
            else:
                # 逐场景：换 seed 换产物（mock 适配器按 seed 取样）⇒ 读生成侧方差。
                run = _run_once(
                    base, token, scenario, adapter=args.adapter, seed=args.seed + i
                )
                eval_round = 1
            run_id = str(run.get("id") or "")
            identity = (scenario_key, run_id, eval_round)
            if identity in done_keys:
                print(f"  [skip] 已在册 {run.get('run_key')} round={eval_round}")
                continue
            status = str(run.get("status") or "")
            if status == RUN_STATUS_SUCCESS:
                _evaluate(base, token, run_id, args.model_mode)
                report = _evaluation_report(base, token, run_id)
            else:
                report = {}
            record = {
                "run_id": run_id,
                "run_key": run.get("run_key"),
                "scenario_key": scenario_key,
                "scenario_id": scenario.get("id"),
                "scenario_version": scenario.get("version"),
                "variant": run.get("run_key", "").split(":")[1] if ":" in str(run.get("run_key", "")) else None,
                "split": run.get("split") or scenario.get("split"),
                "adapter_mode": run.get("adapter_mode") or args.adapter,
                "seed": run.get("seed"),
                "attempt": run.get("attempt"),
                "eval_round": eval_round,
                "status": status,
                "error": run.get("error"),
                "degraded": False,
                "evaluation": _normalize_report(report, args.model_mode),
            }
            records.append(record)
            done_keys.add(identity)
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            score = (
                record["evaluation"].get("layers") or {}
            ).get(record["evaluation"].get("layer_evaluator_id") or "") or {}
            print(
                f"  [run] {run.get('run_key')} round={eval_round} status={status} "
                f"model_total={score.get('total_score')} verdict={score.get('verdict')}"
            )
            time.sleep(args.call_interval_seconds)

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
