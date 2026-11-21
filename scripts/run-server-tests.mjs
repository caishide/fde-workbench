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

// pre-commit 在 `git commit` 场景向钩子进程注入 GIT_DIR / GIT_INDEX_FILE 等
// git 上下文变量；经本脚本原样透传进 pytest 后，凡自行启动 git 子进程的
// 测试（AF3 solution_repo 的 git runner 等）会命中错误的仓库/index——实测
// 钩子下 111 errors（AF3 域 fixture 级）＋提交方 index 被污染（1957 文件
// staged deletions）。测试套件一律按 cwd 定位仓库，这里显式剥离。
const {
  GIT_DIR,
  GIT_INDEX_FILE,
  GIT_WORK_TREE,
  GIT_OBJECT_DIRECTORY,
  GIT_ALTERNATE_OBJECT_DIRECTORIES,
  GIT_COMMON_DIR,
  ...inheritedEnv
} = process.env

const child = spawn(python, ["-m", "pytest", ...extraArgs], {
  cwd: serverRoot,
  stdio: "inherit",
  env: { ...inheritedEnv, PYTHONPATH: "src" },
})
child.on("exit", (code) => process.exit(code ?? 1))
