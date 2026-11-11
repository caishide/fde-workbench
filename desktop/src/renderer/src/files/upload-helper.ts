// CR-056（夜审挂账设计轮 r6 推荐 A′）：renderer 直连分片 PUT 的共享上传面。
//
// 背景：桌面 4 处「取签→分片 PUT」上传站（ProjectFiles / PresurveyUploadAction /
// NewProjectPageV2 / FileVersionTimeline）各自内联同构循环，且分片 PUT 走
// `fetch(signed.url)` 直连——**不经 IPC 桥，不被 close-guard 的 activeMutations 计数**。
// 100MB 级上传中途关窗时 close-guard 视为零在途、直接放行 ⇒ 半成品 multipart 悬挂。
//
// 本 helper 做两件事（行为对 4 站零变化，纯收拢）：
// ① 把分片 PUT 循环收敛为单一 `uploadMultipartParts`（4 站不再各写一遍）；
// ② 上传前经既有 IPC 桥 `appUploadBegin/End` 事件把在途直连写计入 main 侧
//    `activeMutations`（close-guard 判据不变——语义归一到「在途写＝IPC 桥写＋直连上传写」）。
//    `try/finally` 保 begin/end 成对；异常路径也必落 end（不泄漏计数）。
//
// 直连面识别（台账触发条件「直连分片上传真实场景」的机械守护）：全仓 renderer
// 侧只许本文件出现裸 `fetch(...url, { method: "PUT" })` 分片直连——静态钉
// 守「第 5 处上传面出现即红」。

import type { RendererApiRequestOptions } from "../api/client"
import type { UploadSessionDto } from "./types"

// 与 4 站既有 `useAuth()["apiRequest"]` 同款签名（client.ts 的渲染侧 apiRequest）。
export type RendererApiRequest = <T>(
  path: string,
  options: RendererApiRequestOptions,
) => Promise<T>

/**
 * 分片上传：对给定 multipart session 逐片取签并 PUT 到签名 URL，返回
 * `{ part_number, etag }[]`（供 complete 端点）。
 *
 * - `filesPath(projectId)` 由调用方以 `filesPath` 形参传入（各站的 filesPath
 *   构造略有差异：带不带 filterCategory，但 parts/complete 路径一致），helper
 *   只依赖「base + session.id」拼 parts URL，保持与 4 站原逻辑逐位一致。
 * - 在途写计数**由本 helper 自己保证**（不经 4 站回调——结构上杜绝「新增上传站
 *   忘接计数」）：取签前 `notifyUploadBegin(label)`，`try/finally` 兜住成功/取消/
 *   异常都落 `notifyUploadEnd(label)`。`label` 是站点标识（如 `"ProjectFiles"`），
 *   main 侧只作计数归因、不参与 close-guard 判定。
 * - 计数走既有 IPC 桥 `window.fde.app.uploadBegin/uploadEnd`；web 发行形态无 IPC
 *   桥、无 close-guard（同源反代＋无主窗拦截），`uploadBegin/uploadEnd` 在
 *   `fde-web-bridge.ts` 实现为 no-op，故 web 形态自动零行为变化。桥面不可用
 *   （renderer 重载/异常）时 notify 是 best-effort 静默——退化为旧行为（不计入），
 *   不阻断上传本身。
 * - `isCancelled(label)` 由调用方传入，保留 ProjectFiles 的取消语义；其余站传恒 False。
 * - `onProgress(fraction)` 每片完成后回调（fraction=已传字节/总字节），调用方映射
 *   进自己的进度 UI（ProjectFiles 的 patchUpload percent）；不传＝不报进度，行为同旧站。
 */
export async function uploadMultipartParts(
  apiRequest: RendererApiRequest,
  filesPath: string,
  session: UploadSessionDto,
  file: File,
  options: {
    label: string
    isCancelled?: (id: string) => boolean
    onProgress?: (fraction: number) => void
  },
): Promise<Array<{ part_number: number; etag: string }>> {
  const partSize = session.part_size
  const total = Math.max(1, Math.ceil(file.size / partSize))
  const parts: Array<{ part_number: number; etag: string }> = []
  let uploadedBytes = 0
  notifyUploadBegin(options.label)
  try {
    for (let partNumber = 1; partNumber <= total; partNumber += 1) {
      if (options.isCancelled?.(options.label)) return parts
      const signed = await apiRequest<unknown>(
        `${filesPath}/${encodeURIComponent(session.id)}/parts`,
        { method: "POST", body: { part_number: partNumber } },
      )
      if (options.isCancelled?.(options.label)) return parts
      const part = normalizeSignedPart(signed)
      if (!part) throw new Error("invalid signed part")
      const start = (partNumber - 1) * partSize
      const end = Math.min(file.size, start + partSize)
      // 唯一直连分片 PUT 面（静态钉守护）。signed.url 是 storage（OSS/local）
      // 签名地址，不走 API 桥，故不经 close-guard 计数——由本文件的 begin/end 兜住。
      const response = await fetch(part.url, {
        method: "PUT",
        body: file.slice(start, end),
      })
      if (!response.ok) throw new Error(`storage_upload_failed:${response.status}`)
      const etag = stripQuote(response.headers.get("etag") ?? "")
      parts.push({ part_number: partNumber, etag })
      uploadedBytes += end - start
      options.onProgress?.(file.size > 0 ? uploadedBytes / file.size : 1)
    }
  } finally {
    notifyUploadEnd(options.label)
  }
  return parts
}

/** 直连分片上传在途写计数（best-effort）：经 IPC 桥 `appUploadBegin` 计入 main activeMutations。 */
export function notifyUploadBegin(label: string): void {
  safeNotify("uploadBegin", label)
}
/** 直连分片上传在途写计数收尾（best-effort，try/finally 保证必落）。 */
export function notifyUploadEnd(label: string): void {
  safeNotify("uploadEnd", label)
}

function safeNotify(which: "uploadBegin" | "uploadEnd", label: string): void {
  // window.fde.app 面不可用（web 形态无 IPC 桥、renderer 重载、单测无全局 window）
  // 时静默——计数是 close-guard 增益项不是硬闸，桥面缺位退化为旧行为不阻断上传。
  try {
    void window.fde.app[which]?.(label)
  } catch {
    /* best-effort：计数面不可达不改变上传行为 */
  }
}

/** 校验 + 归一化签名分片 DTO（4 站原各自 isUploadedPartDto + url 提取收敛于此）。 */
export function normalizeSignedPart(value: unknown): { url: string } | null {
  if (typeof value !== "object" || value === null) return null
  const url = (value as { url?: unknown }).url
  if (typeof url !== "string" || !url) return null
  // 只认 http(s) 签名 URL（OSS 直连或 local-storage 代理）；非 http 面不直连。
  if (!/^https?:\/\//.test(url)) return null
  return { url }
}

function signedUrl(part: { url: string }): string {
  return part.url
}

/** 与 4 站既有 etag 去引号逻辑逐位一致（`stripQuote` / `replace(/^"|"$/g,"")` 等价）。 */
export function stripQuote(value: string): string {
  return value.startsWith('"') && value.endsWith('"') ? value.slice(1, -1) : value
}
