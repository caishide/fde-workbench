// I1：跨平台运行 mypy 基线检查（scripts/check-python-types.py）。
// 该脚本自己也会探测解释器（Windows .venv/Scripts/python.exe / Unix .venv/bin/python），
// 这里仍显式用 node 入口统一 pre-commit 钩子，避免钩子里写死任何平台路径。
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { spawn } from "node:child_process"

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const serverRoot = path.join(repoRoot, "server")
const candidates = [
  path.join(serverRoot, ".venv", "Scripts", "python.exe"),
  path.join(serverRoot, ".venv", "bin", "python"),
]
const python = candidates.find((p) => existsSync(p))
if (!python) {
  console.error("server/.venv 不存在：先创建虚拟环境并安装依赖（pip install -e \".[test,dev]\"）")
  process.exit(1)
}

const child = spawn(python, [path.join(repoRoot, "scripts", "check-python-types.py")], {
  cwd: repoRoot,
  stdio: "inherit",
})
child.on("exit", (code) => process.exit(code ?? 1))
