import type { IpcMain, IpcMainInvokeEvent } from "electron"

import { IPC_CHANNELS, type BridgeCaptureResult, type BridgeResult } from "../shared/contracts"

export interface ExecFileResult {
  stdout: string
  stderr: string
}

export type ExecFileFn = (
  file: string,
  args: string[],
  options: { timeout: number; encoding: "utf8" },
) => Promise<ExecFileResult>

interface BridgeCaptureOptions {
  execFile: ExecFileFn
  taskName: string
  timeoutMs: number
  /** 测试注入用；生产默认 process.platform */
  platform?: NodeJS.Platform
}

export type BridgeCaptureHandler = () => Promise<BridgeCaptureResult>

export class BridgeCaptureError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = "BridgeCaptureError"
    this.code = code
  }
}

/**
 * P2 集成桥·手动采集：采集器（bridge-poll.mjs）只能跑在 Windows 宿主上
 * （openfde CLI 是 Win 版 Node 工具，Docker 里的后端 subprocess 不到），
 * 所以桌面端不自己采集，只触发宿主已有的计划任务——与 4 小时周期
 * 走完全相同的代码路径，不复制第二套采集逻辑。
 */
export function createBridgeCaptureHandler(
  options: BridgeCaptureOptions,
): BridgeCaptureHandler {
  return async () => {
    if ((options.platform ?? process.platform) !== "win32") {
      throw new BridgeCaptureError(
        "bridge_platform",
        "集成桥采集器仅在 Windows 宿主上运行，当前平台无法触发。",
      )
    }
    try {
      await options.execFile("schtasks", ["/Run", "/TN", options.taskName], {
        timeout: options.timeoutMs,
        encoding: "utf8",
      })
    } catch (caught) {
      const error = caught as Error & { stdout?: string; stderr?: string }
      const output = `${error.stdout ?? ""}\n${error.stderr ?? ""}`
      if (/does not exist|不存在/i.test(output)) {
        throw new BridgeCaptureError(
          "task_missing",
          `未找到计划任务 ${options.taskName}，请先在宿主运行 scripts/install-bridge-poll-task.ps1 安装采集任务。`,
        )
      }
      throw new BridgeCaptureError(
        "capture_failed",
        `触发计划任务失败：${(error.message || String(caught)).slice(0, 200)}`,
      )
    }
    return { triggered: true, task: options.taskName }
  }
}

interface RegisterBridgeIpcOptions {
  ipcMain: Pick<IpcMain, "handle">
  capture: BridgeCaptureHandler
  isTrustedSender(event: IpcMainInvokeEvent): boolean
}

export function registerBridgeIpc(options: RegisterBridgeIpcOptions): void {
  options.ipcMain.handle(
    IPC_CHANNELS.bridgeCapture,
    (event): Promise<BridgeResult<BridgeCaptureResult>> =>
      toBridgeResult(async () => {
        if (!options.isTrustedSender(event)) {
          throw new BridgeCaptureError(
            "unauthorized_ipc",
            "The IPC sender is not authorized.",
          )
        }
        return options.capture()
      }),
  )
}

async function toBridgeResult(
  operation: () => Promise<BridgeCaptureResult>,
): Promise<BridgeResult<BridgeCaptureResult>> {
  try {
    return { ok: true, data: await operation() }
  } catch (error) {
    if (error instanceof BridgeCaptureError) {
      return { ok: false, error: { code: error.code, message: error.message } }
    }
    return {
      ok: false,
      error: { code: "internal_error", message: "触发采集失败，请稍后重试。" },
    }
  }
}
