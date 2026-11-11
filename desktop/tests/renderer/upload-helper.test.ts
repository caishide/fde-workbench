/**
 * CR-056（夜审 r6 设计稿 A′）：直连分片上传共享 helper `uploadMultipartParts` 行为钉。
 *
 * 钉三面：
 * - 分片 PUT 逐片取签＋回 etag（complete 端点消费的形状）＋onProgress 单调到 1；
 * - 取签失败（非 http(s) 签名 URL）⇒ 抛 `invalid signed part`（4 站旧语义保留）；
 * - 取消语义：`isCancelled(label)` 为真时提前返回（已传分片保留、未传不传）。
 *
 * 在途写计数面（notifyUploadBegin/End）经 `window.fde.app` 桥 best-effort：
 * 单测环境无该全局时静默（safeNotify try/catch），本测试钉「上传行为不依赖桥面
 * 在场」＝web 形态/桥缺位的零回归承诺；桥面接线由 close-guard.test.ts 静态钉守。
 */
import { describe, expect, it, vi } from "vitest"

import { uploadMultipartParts, type RendererApiRequest } from "../../src/renderer/src/files/upload-helper"
import type { UploadSessionDto } from "../../src/renderer/src/files/types"

function makeSession(partSize: number): UploadSessionDto {
  return {
    id: "sess-1",
    project_id: "p-1",
    name: "a.bin",
    category: "attachment",
    business_category: null,
    size_bytes: partSize * 2 + 5,
    mime_type: "application/octet-stream",
    part_size: partSize,
    upload_id: "up-1",
    expires_at: "2026-11-11T00:00:00Z",
    idempotency_key: "ik-1",
  }
}

function makeFile(size: number): File {
  return new File([new Uint8Array(size)], "a.bin", { type: "application/octet-stream" })
}

/** 逐片返回签名 URL 的 apiRequest（parts 端点：`.../parts` POST part_number）。 */
function signedApiRequest(base: string): RendererApiRequest {
  return (async (path: string) => {
    const partNumber = Number(path.split("/").pop())
    return { url: `https://oss.example.com/${base}/${partNumber}` }
  }) as unknown as RendererApiRequest
}

/** PUT 成功回 etag 的 fetch 替身（headers.get("etag") 形状与浏览器一致）。 */
function okFetchSpy(etag: string) {
  const spy = vi.fn(async (_url: string, init?: { body?: Blob }) => ({ ok: true, headers: new Map([["etag", `"${etag}"`]]) }))
  vi.stubGlobal("fetch", spy)
  return spy
}

describe("CR-056 uploadMultipartParts 行为面", () => {
  it("逐片取签并回 etag，onProgress 单调到 1（3 片）", async () => {
    const session = makeSession(10)
    const file = makeFile(25) // 10/10/5 → 3 片
    const putSpy = okFetchSpy("etag-x")
    const progress: number[] = []
    try {
      const parts = await uploadMultipartParts(
        signedApiRequest("parts"),
        `/api/v1/projects/p-1/files`,
        session,
        file,
        { label: "unit", onProgress: (fraction) => progress.push(fraction) },
      )
      expect(parts.map((p) => p.part_number)).toEqual([1, 2, 3])
      expect(parts.map((p) => p.etag)).toEqual(["etag-x", "etag-x", "etag-x"])
      expect(putSpy).toHaveBeenCalledTimes(3)
      // PUT body 分片边界：[0,10) [10,20) [20,25)
      const bodies = putSpy.mock.calls.map((call) => call[1]?.body?.size ?? 0)
      expect(bodies).toEqual([10, 10, 5])
      expect(progress).toEqual([0.4, 0.8, 1])
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("取签失败（非 http(s) 签名 URL）⇒ 抛 invalid signed part", async () => {
    const session = makeSession(10)
    const badApi = (async () => ({ url: "not-a-url" })) as unknown as RendererApiRequest
    vi.stubGlobal("fetch", vi.fn())
    try {
      await expect(
        uploadMultipartParts(badApi, "/api/v1/projects/p-1/files", session, makeFile(10), { label: "unit" }),
      ).rejects.toThrow("invalid signed part")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("PUT 非 ok ⇒ 抛 storage_upload_failed:<status>（旧站同款错误码）", async () => {
    const session = makeSession(10)
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 403, headers: new Map() })))
    try {
      await expect(
        uploadMultipartParts(signedApiRequest("parts"), "/api/v1/projects/p-1/files", session, makeFile(10), { label: "unit" }),
      ).rejects.toThrow("storage_upload_failed:403")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("isCancelled(label) 为真时零分片直接返回", async () => {
    const session = makeSession(10)
    const putSpy = okFetchSpy("etag-x")
    try {
      const parts = await uploadMultipartParts(
        signedApiRequest("parts"),
        "/api/v1/projects/p-1/files",
        session,
        makeFile(30),
        { label: "unit", isCancelled: () => true },
      )
      expect(parts).toEqual([])
      expect(putSpy).not.toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
