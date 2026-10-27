import { describe, expect, it, vi } from "vitest"
import type { IpcMain, IpcMainInvokeEvent } from "electron"

import { IPC_CHANNELS } from "../../src/shared/contracts"
import {
  createBridgeCaptureHandler,
  registerBridgeIpc,
} from "../../src/main/bridge-capture"

function fakeIpcMain(): {
  handlers: Map<string, (event: IpcMainInvokeEvent) => unknown>
} & Pick<IpcMain, "handle"> {
  const handlers = new Map<string, (event: IpcMainInvokeEvent) => unknown>()
  return {
    handlers,
    handle(channel, listener) {
      handlers.set(channel, listener)
    },
  }
}

describe("bridge capture handler", () => {
  it("runs the host scheduled task via schtasks and reports success", async () => {
    const execFile = vi.fn().mockResolvedValue({ stdout: "SUCCESS: 尝试运行", stderr: "" })
    const capture = createBridgeCaptureHandler({
      execFile,
      taskName: "FDE-Bridge-Poll",
      timeoutMs: 15_000,
      platform: "win32",
    })

    await expect(capture()).resolves.toEqual({ triggered: true, task: "FDE-Bridge-Poll" })
    expect(execFile).toHaveBeenCalledWith(
      "schtasks",
      ["/Run", "/TN", "FDE-Bridge-Poll"],
      { timeout: 15_000, encoding: "utf8" },
    )
  })

  it("maps a missing scheduled task to task_missing with the install hint", async () => {
    const failure = Object.assign(new Error("schtasks exited 1"), {
      stdout: "",
      stderr: 'ERROR: The scheduled task "FDE-Bridge-Poll" does not exist.',
    })
    const execFile = vi.fn().mockRejectedValue(failure)
    const capture = createBridgeCaptureHandler({
      execFile,
      taskName: "FDE-Bridge-Poll",
      timeoutMs: 15_000,
      platform: "win32",
    })

    await expect(capture()).rejects.toMatchObject({ code: "task_missing" })
  })

  it("maps other schtasks failures to capture_failed", async () => {
    const execFile = vi.fn().mockRejectedValue(Object.assign(new Error("access denied"), { stdout: "", stderr: "" }))
    const capture = createBridgeCaptureHandler({ execFile, taskName: "T", timeoutMs: 1_000, platform: "win32" })

    await expect(capture()).rejects.toMatchObject({ code: "capture_failed" })
  })

  it("rejects on non-Windows platforms without spawning anything", async () => {
    const execFile = vi.fn()
    const capture = createBridgeCaptureHandler({ execFile, taskName: "T", timeoutMs: 1_000, platform: "linux" })

    await expect(capture()).rejects.toMatchObject({ code: "bridge_platform" })
    expect(execFile).not.toHaveBeenCalled()
  })

  it("refuses untrusted IPC senders before touching schtasks", async () => {
    const ipcMain = fakeIpcMain()
    const execFile = vi.fn()
    registerBridgeIpc({
      ipcMain,
      capture: createBridgeCaptureHandler({ execFile, taskName: "T", timeoutMs: 1_000 }),
      isTrustedSender: () => false,
    })
    const handler = ipcMain.handlers.get(IPC_CHANNELS.bridgeCapture)

    await expect(handler?.({} as IpcMainInvokeEvent)).resolves.toEqual({
      ok: false,
      error: { code: "unauthorized_ipc", message: "The IPC sender is not authorized." },
    })
    expect(execFile).not.toHaveBeenCalled()
  })
})
