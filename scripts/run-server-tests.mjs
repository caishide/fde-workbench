// C13：跨平台运行 server pytest——Windows 用 .venv/Scripts/python.exe，
// Unix 用 .venv/bin/python；PYTHONPATH=src 与本地/CI 命令一致。
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
const child = spawn(python, ["-m", "pytest", ...extraArgs], {
  cwd: serverRoot,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: "src" },
})
child.on("exit", (code) => process.exit(code ?? 1))
