#!/usr/bin/env node
/**
 * bridge-poll.mjs —— P2 集成桥·宿主侧采集器（设计 §4，v0.3.4 架构修订）
 *
 * 为什么在宿主侧：openfde CLI 是 Windows Node 工具（pnpm + tsx，better-sqlite3
 * 按 Win 编译），Linux 容器 subprocess 不到；A3 的 PATH 注入（D:\software\nodejs）
 * 只在宿主有意义。采集 → 白名单快照 → POST 服务端（校验/投影/orphan 都在服务端）。
 *
 * 只读纪律：本脚本只调 openfde 只读命令（engagement list / status）+ 读文件，
 * 绝不写真相层；写命令（remember/ingest/log/debrief）不在采集器白名单内。
 *
 * 用法：node scripts/bridge-poll.mjs [--check]
 *   常规：采集 + 推送，退出码 0/1
 *   --check：同上，但快照里有 orphan 项目指针时退出码 2（缺一指位=孤儿，§1 铁律 3）
 * 计划任务：FDE-Bridge-Poll（15 min），见 scripts/install-bridge-poll-task.ps1
 */

import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));

// ---- 配置（环境变量可覆盖；默认值即本机真身路径，R9：真身在 D 盘，不走 C 盘指针）----
const OPENFDE_REPO = process.env.BRIDGE_OPENFDE_REPO || "D:\\test\\FDE\\openfde";
const OPENFDE_HOME = process.env.BRIDGE_OPENFDE_HOME || "D:\\test\\FDE\\engagements\\openfde";
const FDEOPS_ROOT = process.env.BRIDGE_FDEOPS_ROOT || "D:\\test\\FDE\\engagements\\fdeops";
const API_BASE = process.env.BRIDGE_API_BASE || "http://127.0.0.1:8010";
// A3/R6：显式 PATH 注入，不信会话环境（Node 24 在 D:\software\nodejs）
const NODE_DIRS = ["D:\\software\\nodejs", "D:\\software\\nodejs\\node_global"];

const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,79}$/;
const CLI_TIMEOUT_MS = 90_000;

function log(message) {
  const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  console.log(`[${now}] ${message}`);
}

function fail(message, code = 1) {
  log(`FAIL ${message}`);
  process.exit(code);
}

function readBridgeToken() {
  const envPath = join(SCRIPT_DIR, "..", "server", ".env");
  if (!existsSync(envPath)) fail(`缺少 ${envPath}（FDE_BRIDGE_TOKEN 所在）`);
  const match = readFileSync(envPath, "utf8").match(/^FDE_BRIDGE_TOKEN=(.+)$/m);
  if (!match) fail("server/.env 里没有 FDE_BRIDGE_TOKEN");
  return match[1].trim();
}

function cliEnv() {
  return {
    ...process.env,
    PATH: `${NODE_DIRS.join(";")};${process.env.PATH || ""}`,
    // 设计 §4.2：环境变量每次注入，不信会话
    OPENFDE_HOME,
  };
}

/** 跑 openfde 只读命令，取输出里的 JSON（pnpm banner 行混在 stdout，逐行从尾解析）*/
function runOpenfdeJson(args) {
  const command = `pnpm openfde ${args.join(" ")}`;
  const result = spawnSync(command, {
    cwd: OPENFDE_REPO,
    env: cliEnv(),
    shell: true,
    windowsHide: true,
    encoding: "utf8",
    timeout: CLI_TIMEOUT_MS,
    maxBuffer: 8 * 1024 * 1024,
  });
  if (result.status !== 0) {
    const tail = String(result.stderr || result.stdout || "").trim().split("\n").slice(-3).join(" | ");
    throw new Error(`exit ${result.status}: ${tail.slice(0, 400)}`);
  }
  const lines = String(result.stdout || "").split(/\r?\n/);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i].trim();
    if (line.startsWith("{") || line.startsWith("[")) {
      try {
        return JSON.parse(line);
      } catch {
        /* 继续往上找 */
      }
    }
  }
  throw new Error("stdout 里找不到 JSON 行");
}

function sha256(text) {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

function captureOpenfde() {
  const listing = runOpenfdeJson(["engagement", "list", "--json"]);
  const slugs = Array.isArray(listing.engagements) ? listing.engagements : [];
  const entries = [];
  for (const slug of slugs) {
    if (typeof slug !== "string" || !SLUG_RE.test(slug)) {
      log(`  跳过非法 slug: ${JSON.stringify(slug)}`);
      continue;
    }
    try {
      const raw = runOpenfdeJson(["status", "-e", slug, "--json"]);
      const stdout = JSON.stringify(raw);
      entries.push({
        slug,
        ok: true,
        status: raw,
        stdout_sha256: sha256(stdout),
        source_uri: `cli://openfde/status?engagement=${slug}`,
      });
      log(`  openfde ${slug}: ${raw.episodes ?? "?"} episodes / ${raw.entities ?? "?"} entities`);
    } catch (error) {
      entries.push({ slug, ok: false, error: String(error.message || error).slice(0, 500) });
      log(`  openfde ${slug}: 采集失败（保留旧投影）— ${entries.at(-1).error.slice(0, 120)}`);
    }
  }
  return {
    current: typeof listing.current === "string" ? listing.current : null,
    engagements: entries,
    source_uri: "cli://openfde/engagement/list",
  };
}

/** fdeops 轨：CLI 未装机，走文件探针（.registry + engagement 目录 + 绑定工作区 .fde）*/
function captureFdeops() {
  const registryPath = join(FDEOPS_ROOT, ".registry");
  const bindings = [];
  let registrySha = null;
  if (existsSync(registryPath)) {
    const text = readFileSync(registryPath, "utf8");
    registrySha = sha256(text);
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const splitAt = trimmed.lastIndexOf(" "); // 路径含空格：最后一个空格后是 slug
      if (splitAt <= 0) continue;
      const path = trimmed.slice(0, splitAt);
      const slug = trimmed.slice(splitAt + 1);
      if (SLUG_RE.test(slug)) bindings.push({ slug, path });
    }
  }
  const bindingBySlug = new Map(bindings.map((b) => [b.slug, b.path]));

  const dirs = [];
  if (existsSync(FDEOPS_ROOT)) {
    for (const entry of readdirSync(FDEOPS_ROOT, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
      const slug = entry.name;
      if (!SLUG_RE.test(slug)) continue;
      const boundPath = bindingBySlug.get(slug) || null;
      // 单个目录读取失败（Windows 上 EBUSY/EPERM 常见）不许中断整轮——
      // 降级为空清单继续，其余 slug 照常采集推送。
      let files = [];
      try {
        files = readdirSync(join(FDEOPS_ROOT, slug))
          .filter((name) => !name.startsWith("."))
          .slice(0, 50);
      } catch (error) {
        log(`  fdeops ${slug}: 目录读取失败，降级为空清单（${error?.code || error?.message}）`);
      }
      // .fde 流程轨在绑定的工作区里（.registry: <工作区路径> <slug>）；目录本体也可能有
      const fdeInitialized =
        (boundPath && existsSync(join(boundPath, ".fde"))) ||
        existsSync(join(FDEOPS_ROOT, slug, ".fde"));
      dirs.push({ slug, exists: true, fde_initialized: fdeInitialized, bound_path: boundPath, files });
      log(`  fdeops ${slug}: 目录在，绑定 ${boundPath || "无"}，.fde ${fdeInitialized ? "已初始化" : "未初始化"}`);
    }
  } else {
    log(`  fdeops 根目录不存在：${FDEOPS_ROOT}`);
  }
  return {
    registry_sha256: registrySha,
    source_uri: `file:///${FDEOPS_ROOT.replace(/\\/g, "/")}/.registry`,
    bindings,
    dirs,
  };
}

async function main() {
  const checkMode = process.argv.includes("--check");
  log("P2 集成桥采集开始（openfde 只读白名单 + fdeops 文件探针）");
  if (!existsSync(OPENFDE_REPO)) fail(`openfde 仓库不存在：${OPENFDE_REPO}`);

  let openfde;
  try {
    openfde = captureOpenfde();
  } catch (error) {
    fail(`openfde engagement list 失败：${String(error.message || error)}`);
  }
  const fdeops = captureFdeops();

  const bundle = {
    captured_at: new Date().toISOString(),
    openfde,
    fdeops,
  };

  const token = readBridgeToken();
  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/bridge/snapshots`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(bundle),
    });
  } catch (error) {
    fail(`推送失败（服务端不可达？${API_BASE}）— ${String(error.cause?.code || error.message || error)}`);
  }
  const bodyText = await response.text();
  if (!response.ok) {
    fail(`服务端拒绝（HTTP ${response.status}）：${bodyText.slice(0, 300)}`);
  }
  const data = JSON.parse(bodyText).data || {};
  const summary = data.summary || {};
  log(
    `推送成功：run ${String(data.run_id).slice(0, 8)}，engagement ${data.engagements_seen} 个` +
      `，unlinked ${summary.unlinked ?? "?"}，orphan 项目 ${summary.orphan_projects ?? "?"}，vanished ${summary.vanished ?? "?"}`
  );

  if (checkMode && (summary.orphan_projects ?? 0) > 0) {
    log("--check：存在缺指位/orphan 项目指针（§1 铁律 3），退出码 2");
    process.exit(2);
  }
}

main().catch((error) => fail(String(error.stack || error)));
