// I1：跨平台运行 ruff —— 复用 run-server-tests.mjs 的解释器探测逻辑
// （Windows .venv/Scripts/python.exe / Unix .venv/bin/python），不写死路径。
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { spawn } from "node:child_process"

const serverRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "server")
const candidates = [
  path.join(serverRoot, ".venv", "Scripts", "python.exe"),
  path.join(serverRoot, ".venv", "bin", "python"),
]
const python = candidates.find((p) => existsSync(p))
if (!python) {
  console.error("server/.venv 不存在：先创建虚拟环境并安装依赖（pip install -e \".[test,dev]\"）")
  process.exit(1)
}

const extraArgs = process.argv.slice(2)
const args = extraArgs.length > 0 ? extraArgs : ["check", "--select", "F401,F841", "src", "tests"]
const child = spawn(python, ["-m", "ruff", ...args], {
  cwd: serverRoot,
  stdio: "inherit",
})
child.on("exit", (code) => process.exit(code ?? 1))
