import { Buffer } from "node:buffer"
import { join } from "node:path"

import { describe, expect, it, vi } from "vitest"

import {
  createAuthStore,
  type AuthStoreFileSystem,
  type SafeStorageAdapter,
} from "../../src/main/auth-store"

// 期望路径一律用 join 计算：path.join 在 win32 产反斜杠，
// 写死正斜杠的断言在 Windows 上永远失败（这些用例上游从未在 Windows 跑过）。
const USER_DATA = "/private/user-data"
const TMP_NAME = "session.bin.tmp-test"
const FINAL_PATH = join(USER_DATA, "session.bin")
const TMP_PATH = join(USER_DATA, TMP_NAME)
const ENC_PREFIX = "fde-session-enc-v1:"

function createHarness(options: { encryptionAvailable?: boolean } = {}) {
  const files: AuthStoreFileSystem = {
    mkdir: vi.fn().mockResolvedValue(undefined),
    writeFile: vi.fn().mockResolvedValue(undefined),
    rename: vi.fn().mockResolvedValue(undefined),
    readFile: vi.fn(),
    unlink: vi.fn().mockResolvedValue(undefined),
  }
  const safeStorage: SafeStorageAdapter = {
    isEncryptionAvailable: vi
      .fn()
      .mockReturnValue(options.encryptionAvailable ?? true),
    encryptString: vi
      .fn()
      .mockImplementation((value: string) => Buffer.from(`encrypted:${value.length}`)),
    decryptString: vi.fn().mockReturnValue("decrypted-refresh-token"),
  }

  return {
    files,
    safeStorage,
    store: createAuthStore({
      files,
      safeStorage,
      userDataPath: USER_DATA,
      temporaryName: () => TMP_NAME,
    }),
  }
}

describe("auth store", () => {
  it("persists refresh tokens encrypted when OS-backed storage is available", async () => {
    const { files, store } = createHarness()

    await store.save("raw-refresh-token")

    const written = vi.mocked(files.writeFile).mock.calls[0]?.[1] as Buffer
    expect(
      written.subarray(0, Buffer.byteLength(ENC_PREFIX)).toString("utf8"),
    ).toBe(ENC_PREFIX)
    expect(written.toString("utf8")).not.toContain("raw-refresh-token")
  })

  it("falls back to plaintext only when OS-backed storage is unavailable", async () => {
    const { files, store } = createHarness({ encryptionAvailable: false })

    await store.save("raw-refresh-token")

    expect(files.writeFile).toHaveBeenCalledWith(
      TMP_PATH,
      Buffer.from("raw-refresh-token"),
      { flag: "wx", mode: 0o600 },
    )
  })

  it("round-trips an encrypted session", async () => {
    const { files, safeStorage, store } = createHarness()
    vi.mocked(files.readFile).mockResolvedValue(
      Buffer.concat([Buffer.from(ENC_PREFIX, "utf8"), Buffer.from("ciphertext")]),
    )

    await expect(store.load()).resolves.toBe("decrypted-refresh-token")
    expect(safeStorage.decryptString).toHaveBeenCalledWith(Buffer.from("ciphertext"))
  })

  it("atomically promotes the protected session file", async () => {
    const { files, store } = createHarness()

    await store.save("raw-refresh-token")

    expect(files.mkdir).toHaveBeenCalledWith(USER_DATA, {
      recursive: true,
      mode: 0o700,
    })
    expect(files.rename).toHaveBeenCalledWith(TMP_PATH, FINAL_PATH)
    expect(vi.mocked(files.writeFile).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(files.rename).mock.invocationCallOrder[0]!,
    )
  })

  it("loads the legacy plaintext session (pre-encryption upgrade path)", async () => {
    const { files, store } = createHarness({ encryptionAvailable: false })
    vi.mocked(files.readFile).mockResolvedValue(Buffer.from("raw-refresh-token"))

    await expect(store.load()).resolves.toBe("raw-refresh-token")
  })

  it("returns null when there is no persisted session", async () => {
    const { files, store } = createHarness()
    vi.mocked(files.readFile).mockRejectedValue(
      Object.assign(new Error("not found"), { code: "ENOENT" }),
    )

    await expect(store.load()).resolves.toBeNull()
  })

  it("clears both the final and interrupted temporary session files", async () => {
    const { files, store } = createHarness()

    await store.clear()

    expect(files.unlink).toHaveBeenCalledWith(FINAL_PATH)
    expect(files.unlink).toHaveBeenCalledWith(TMP_PATH)
  })
})
