// CR-071（夜审 r8 设计稿推荐 A，2026-11-11）：桌面 IPC 桥（main/api-ipc.ts）与
// web 桥（renderer/fde-web-bridge.ts）共用的 API 请求校验原语单点。
//
// 两桥此前校验面不等价——桌面 validateRequest 八项校验全在位，web 桥 apiRequest
// 只有路径白名单粗查＋origin 断言，缺 method 白名单／auth 路径排除／编码结构
// 逃逸（%25 双重编码）／multipart 严格 schema（非法形状静默降级为无 body 裸发）
// 等六项。本模块把八项校验提升为纯函数，两桥消费同一实现；等价性静态钉
// （tests 样本集断言两桥判定恒同）防未来任一侧单独加校验项导致漂移。
//
// 纯函数纪律：零 electron 导入、零 DOM 依赖（origin 以参数注入），tsconfig.node
// 与 renderer 双侧可编译可测。

import type { ApiMethod } from "./contracts"

/** 八项校验的 method 白名单（与桌面 ALLOWED_METHODS 同一集合语义）。 */
export const ALLOWED_API_METHODS: ReadonlySet<string> = new Set<ApiMethod>([
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
])

const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/
const PATH_TRAVERSAL = /(^|\/)\.{1,2}(\/|$)/
const ENCODED_STRUCTURAL_ESCAPE = /%(?:25|2f|3f|23|5c)/i
const ENCODED_DOT = /%2e/i
const AUTH_PATH = /^\/api\/v1\/auth(?:\/|$)/i
const FIELD_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/

export interface MultipartFileBodyShape {
  kind: "multipart_file"
  fields: Record<string, string>
  file: {
    field_name: string
    name: string
    type: string
    bytes: Uint8Array
  }
}

const MAX_MULTIPART_FILE_BYTES = 100 * 1024 * 1024
const MAX_MULTIPART_FIELDS = 20
const MAX_FIELD_VALUE_BYTES = 10_000

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const allowed = new Set(keys)
  return keys.every((key) => Object.hasOwn(value, key)) &&
    Object.keys(value).every((key) => allowed.has(key))
}

/**
 * 校验项 1：method 白名单。返回 true＝放行；false＝拒绝。
 */
export function isAllowedMethod(method: string): boolean {
  return ALLOWED_API_METHODS.has(method)
}

/**
 * 编码结构逃逸判定（桌面既有语义原样提升，供 isSafeApiPath 内部与
 * 诊断面复用）：raw 形态的 %25 双重编码（%2f/%3f/%23/%5c）与可选的 %2e。
 * 必须在 **decode 之前**对 raw 串调用——decode 后 %2e 已变 ".." 而原样丢失
 * 「这是编码逃逸」的证据（旧桌面 validateRequest 对 rawQuery 的
 * hasEncodedStructuralEscape(rawQuery, false) 即此语义）。
 */
export function hasEncodedStructuralEscape(value: string, rejectEncodedDots: boolean): boolean {
  if (ENCODED_STRUCTURAL_ESCAPE.test(value)) return true
  return rejectEncodedDots && ENCODED_DOT.test(value)
}

/**
 * 校验项 2＋3＋4＋5 合成：路径安全判定（raw＋decoded 双查）。
 *
 * @param path    请求路径（含可选查询串，raw 形态）
 * @param origin  允许的目标 origin（桌面＝apiBaseUrl origin；web＝location origin）
 * @returns true＝路径安全可放行；false＝拒绝（遍历/编码逃逸/控制字符/越 origin）。
 */
export function isSafeApiPath(path: string, origin: string): boolean {
  if (typeof path !== "string" || !path.startsWith("/api/v1/")) return false
  const queryIndex = path.indexOf("?")
  const rawPathname = queryIndex === -1 ? path : path.slice(0, queryIndex)
  const rawQuery = queryIndex === -1 ? "" : path.slice(queryIndex + 1)
  let decodedPathname: string
  let decodedQuery: string
  try {
    decodedPathname = decodeURIComponent(rawPathname)
    decodedQuery = decodeURIComponent(rawQuery)
  } catch {
    // 未闭合的百分号编码本身即非法（桌面语义：decode 失败即拒）
    return false
  }
  if (
    !decodedPathname.startsWith("/api/v1/") ||
    decodedPathname.includes("//") ||
    path.includes("#") ||
    path.includes("\\") ||
    decodedPathname.includes("\\") ||
    decodedQuery.includes("\\") ||
    CONTROL_CHARACTERS.test(path) ||
    CONTROL_CHARACTERS.test(decodedPathname) ||
    CONTROL_CHARACTERS.test(decodedQuery) ||
    PATH_TRAVERSAL.test(rawPathname) ||
    PATH_TRAVERSAL.test(decodedPathname) ||
    hasEncodedStructuralEscape(rawPathname, true) ||
    hasEncodedStructuralEscape(rawQuery, false)
  ) {
    return false
  }
  let finalUrl: URL
  let targetOrigin: string
  try {
    finalUrl = new URL(path, `${origin}/`)
    targetOrigin = new URL(origin).origin
  } catch {
    return false
  }
  // origin 归一：参数可能是带路径的 apiBaseUrl，也可能是纯 origin（web 形态）
  if (finalUrl.origin !== targetOrigin || !finalUrl.pathname.startsWith("/api/v1/") ||
      PATH_TRAVERSAL.test(finalUrl.pathname)) {
    return false
  }
  return true
}

/**
 * 校验项 2：auth 路径排除。桌面既有语义原样提升：
 * /api/v1/auth/* 一律不走通用桥（令牌面自持 auth-ipc/web 桥 postAuth 专属通道），
 * 唯一例外 POST /api/v1/auth/verify-password。
 *
 * @returns true＝该（path, method）组合被 auth 排除（通用桥应拒）。
 */
export function isAuthExcludedPath(path: string, method: string): boolean {
  const queryIndex = path.indexOf("?")
  const rawPathname = queryIndex === -1 ? path : path.slice(0, queryIndex)
  let decodedPathname: string
  try {
    decodedPathname = decodeURIComponent(rawPathname)
  } catch {
    // isSafeApiPath 已先行拒绝 decode 失败路径；此处兜底保守拒
    return true
  }
  const isPasswordVerification =
    decodedPathname === "/api/v1/auth/verify-password" && method === "POST"
  return AUTH_PATH.test(decodedPathname) && !isPasswordVerification
}

/**
 * 校验项 6：multipart 严格 schema。非法形状返回 error（桌面侧翻译为
 * invalid_request，web 侧翻译为 fail({code:"invalid_request"})），
 * **绝不返回 null 降级**（web 桥旧行为 buildMultipartBody→null⇒无 body 裸发，
 * 本轮封堵为显式失败）。
 *
 * @returns error 文案（拒因）；null＝形状合法可放行。
 */
export function validateMultipartFileShape(body: unknown): string | null {
  if (!isRecord(body)) return "multipart body 形状非法"
  if (!hasExactKeys(body, ["kind", "fields", "file"]) || body.kind !== "multipart_file" ||
      !isRecord(body.fields) || !isRecord(body.file)) {
    return "multipart body 形状非法"
  }
  if (Object.keys(body.fields).length > MAX_MULTIPART_FIELDS) {
    return "multipart 字段数超限"
  }
  for (const [key, item] of Object.entries(body.fields)) {
    if (!FIELD_NAME_PATTERN.test(key) || typeof item !== "string" ||
        item.length > MAX_FIELD_VALUE_BYTES || CONTROL_CHARACTERS.test(item)) {
      return "multipart 字段名/值非法"
    }
  }
  if (!hasExactKeys(body.file, ["field_name", "name", "type", "bytes"])) {
    return "multipart file 形状非法"
  }
  const { field_name: fieldName, name, type, bytes } = body.file
  if (
    typeof fieldName !== "string" || !FIELD_NAME_PATTERN.test(fieldName) ||
    typeof name !== "string" || name.length < 1 || name.length > 255 ||
    name === "." || name === ".." || /[/\\]/.test(name) || CONTROL_CHARACTERS.test(name) ||
    typeof type !== "string" || type.length > 255 || CONTROL_CHARACTERS.test(type) ||
    !(bytes instanceof Uint8Array) || bytes.byteLength > MAX_MULTIPART_FILE_BYTES
  ) {
    return "multipart file 字段非法"
  }
  return null
}

export function isMultipartFileShape(body: unknown): body is MultipartFileBodyShape {
  if (!isRecord(body) || body.kind !== "multipart_file") return false
  return validateMultipartFileShape(body) === null
}

/**
 * 校验项 7：body 可序列化。与桌面 serializeBody 的 JSON.parse(JSON.stringify)
 * 回环同一语义；纯判定函数（不产出字符串），失败返回 false 由调用方翻译。
 *
 * 注意：JSON.stringify 对 undefined/函数/Symbol 产出 undefined；对 BigInt 抛错；
 * 回环 parse 兜住其余不可序列化形态——与桌面行为逐位等价。
 */
export function isBodySerializable(body: unknown): boolean {
  try {
    const serialized = JSON.stringify(body)
    if (serialized === undefined) return false
    JSON.parse(serialized)
    return true
  } catch {
    return false
  }
}

/**
 * 校验项 7 的桌面侧等价：返回序列化字符串；不可序列化时抛 TypeError
 * （桌面侧 catch 后翻译为 invalid_request，保持既有 throw 语义）。
 */
export function serializeBodyString(body: unknown): string {
  const serialized = JSON.stringify(body)
  if (serialized === undefined) {
    throw new TypeError("body 不可序列化")
  }
  JSON.parse(serialized)
  return serialized
}
