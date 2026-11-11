import type { IpcMain, IpcMainInvokeEvent } from "electron"

import {
  IPC_CHANNELS,
  type ApiErrorDto,
  type ApiMethod,
  type ApiResponse,
  type BridgeResult,
} from "../shared/contracts"
// CR-071（夜审 r8 设计稿推荐 A）：校验族提升 shared/api-safety.ts 纯函数单点，
// 桌面 IPC 与 web 桥双消费同一原语；等价性静态钉防再漂移。
import {
  isAllowedMethod,
  isAuthExcludedPath,
  isBodySerializable,
  isSafeApiPath,
  serializeBodyString,
  validateMultipartFileShape,
} from "../shared/api-safety"

interface ApiRequestHandlerOptions {
  apiBaseUrl: string
  fetch: typeof fetch
  timeoutMs: number
}

interface ValidatedApiRequest {
  url: string
  method: ApiMethod
  accessToken: string
  body?: unknown
}

interface MultipartFileBody {
  kind: "multipart_file"
  fields: Record<string, string>
  file: {
    field_name: string
    name: string
    type: string
    bytes: Uint8Array
  }
}

export type ApiRequestHandler = (
  input: unknown,
) => Promise<ApiResponse<unknown>>

interface RegisterApiIpcOptions {
  ipcMain: Pick<IpcMain, "handle">
  request: ApiRequestHandler
  isTrustedSender(event: IpcMainInvokeEvent): boolean
}

const ALLOWED_KEYS = new Set(["path", "method", "accessToken", "body"])
const REDACTED = "[REDACTED]"

export class ApiIpcError extends Error implements ApiErrorDto {
  readonly code: string
  readonly details?: unknown

  constructor(code: string, message: string, details?: unknown) {
    super(message)
    this.name = "ApiIpcError"
    this.code = code
    this.details = details
  }
}

export function createApiRequestHandler(
  options: ApiRequestHandlerOptions,
): ApiRequestHandler {
  return async (input: unknown): Promise<ApiResponse<unknown>> => {
    const request = validateRequest(input, options.apiBaseUrl)
    const controller = new AbortController()
    const pluginDecision = request.method === "POST"
      && /^\/api\/v1\/extensions\/plugin-requests\/[^/]+\/decision$/.test(new URL(request.url).pathname)
    const timeout = setTimeout(() => controller.abort(), pluginDecision ? Math.max(options.timeoutMs, 330_000) : options.timeoutMs)
    const secrets = [request.accessToken, ...collectSensitiveValues(request.body)]
    try {
      const multipartBody = isMultipartFileBody(request.body) ? buildMultipartBody(request.body) : undefined
      const serializedBody = request.body === undefined || multipartBody
        ? undefined
        : serializeBody(request.body)
      const response = await options.fetch(request.url, {
        method: request.method,
        headers: {
          accept: "application/json",
          authorization: `Bearer ${request.accessToken}`,
          ...(serializedBody === undefined || multipartBody
            ? {}
            : { "content-type": "application/json" }),
        },
        ...(multipartBody ? { body: multipartBody } : serializedBody === undefined ? {} : { body: serializedBody }),
        signal: controller.signal,
        redirect: "error",
        cache: "no-store",
        credentials: "omit",
        referrerPolicy: "no-referrer",
      })
      return parseApiResponse(response, secrets)
    } catch (error) {
      if (error instanceof ApiIpcError) {
        throw error
      }
      if (controller.signal.aborted || isAbortError(error)) {
        throw new ApiIpcError("request_timeout", "AI 或服务端响应超时，请稍后重试。")
      }
      throw new ApiIpcError("network_error", "无法连接本地服务，请确认服务已启动。")
    } finally {
      clearTimeout(timeout)
    }
  }
}

export function registerApiIpc(options: RegisterApiIpcOptions): void {
  options.ipcMain.handle(IPC_CHANNELS.apiRequest, (event, input: unknown) =>
    toBridgeResult(async () => {
      if (!options.isTrustedSender(event)) {
        throw new ApiIpcError(
          "unauthorized_ipc",
          "The IPC sender is not authorized.",
        )
      }
      return options.request(input)
    }),
  )
}

function validateRequest(
  value: unknown,
  apiBaseUrl: string,
): ValidatedApiRequest {
  if (
    !isRecord(value) ||
    Object.keys(value).some((key) => !ALLOWED_KEYS.has(key)) ||
    typeof value.path !== "string" ||
    typeof value.method !== "string" ||
    !isAllowedMethod(value.method) ||
    typeof value.accessToken !== "string" ||
    value.accessToken.length === 0 ||
    value.accessToken.length > 16_384
  ) {
    throw invalidRequest()
  }
  const path = value.path
  let apiOrigin: string
  try {
    apiOrigin = new URL(apiBaseUrl).origin
  } catch {
    throw invalidRequest()
  }
  // 校验项 2+3+4+5（路径遍历/编码结构逃逸/控制字符，raw+decoded 双查）
  // ＋校验项 8（origin 匹配）由 shared 原语 isSafeApiPath 一次判定，
  // 与 web 桥 fde-web-bridge.ts 消费同一实现（等价性静态钉防漂移）。
  if (!isSafeApiPath(path, apiOrigin)) {
    throw invalidRequest()
  }
  // 校验项 2：auth 路径排除（verify-password 唯一例外）
  if (isAuthExcludedPath(path, value.method)) {
    throw invalidRequest()
  }
  if (value.method === "GET" && value.body !== undefined) {
    throw invalidRequest()
  }
  if (value.body !== undefined) {
    // 校验项 6＋7（shared 原语）：声称 multipart_file 的 body 必须过严格 schema
    // （旧内联 validateMultipartFileBody 语义逐位保留——非法形状即拒，绝不落
    // JSON 回环分支被当普通 body 放行）；其余 body 走可序列化回环。
    if (isRecord(value.body) && value.body.kind === "multipart_file") {
      if (validateMultipartFileShape(value.body) !== null) throw invalidRequest()
    } else if (!isBodySerializable(value.body)) {
      throw invalidRequest()
    }
  }
  let finalUrl: URL
  try {
    finalUrl = new URL(path, `${apiBaseUrl}/`)
  } catch {
    throw invalidRequest()
  }
  // url 保留绝对形态（远程 apiBaseUrl 部署必需），isSafeApiPath 已断言
  // finalUrl.origin === apiOrigin，此处归一结果逐位等价旧行为。
  return {
    url: finalUrl.toString(),
    method: value.method as ApiMethod,
    accessToken: value.accessToken,
    ...(value.body === undefined ? {} : { body: value.body }),
  }
}

function isMultipartFileBody(value: unknown): value is MultipartFileBody {
  if (!isRecord(value) || value.kind !== "multipart_file") return false
  return validateMultipartFileShape(value) === null
}

function buildMultipartBody(value: MultipartFileBody): FormData {
  const body = new FormData()
  for (const [key, item] of Object.entries(value.fields)) body.append(key, item)
  const bytes = value.file.bytes.slice()
  body.append(value.file.field_name, new Blob([bytes], { type: value.file.type }), value.file.name)
  return body
}

// 传输层序列化（handler 内）：shared 原语产出字符串，此处翻译为
// invalid_request（与旧内联版逐位等价；校验面已由 validateRequest 先行通过）。
function serializeBody(body: unknown): string {
  try {
    return serializeBodyString(body)
  } catch {
    throw invalidRequest()
  }
}

async function parseApiResponse(
  response: Response,
  secrets: string[],
): Promise<ApiResponse<unknown>> {
  if (response.ok && response.status === 204) {
    return { status: response.status, data: null, error: null }
  }
  let value: unknown
  try {
    value = JSON.parse(await response.text())
  } catch {
    throw new ApiIpcError(
      "invalid_api_response",
      "The API service returned an invalid response.",
    )
  }
  if (!isRecord(value) || !("data" in value) || !("error" in value)) {
    throw new ApiIpcError(
      "invalid_api_response",
      "The API service returned an invalid response.",
    )
  }
  let error: ApiErrorDto | null = null
  if (value.error !== null) {
    if (
      !isRecord(value.error) ||
      typeof value.error.code !== "string" ||
      typeof value.error.message !== "string"
    ) {
      throw new ApiIpcError(
        "invalid_api_response",
        "The API service returned an invalid response.",
      )
    }
    error = {
      code: redactString(value.error.code, secrets),
      message: redactString(value.error.message, secrets),
      ...(value.error.details === undefined
        ? {}
        : { details: sanitizeDetails(value.error.details, secrets) }),
    }
  }
  if (response.ok && error !== null) {
    throw new ApiIpcError(
      "invalid_api_response",
      "The API service returned an invalid response.",
    )
  }
  if (!response.ok && error === null) {
    throw new ApiIpcError(
      "invalid_api_response",
      "The API service returned an invalid response.",
    )
  }
  return {
    status: response.status,
    data: response.ok ? value.data : null,
    error,
  }
}

async function toBridgeResult<T>(
  operation: () => Promise<T>,
): Promise<BridgeResult<T>> {
  try {
    return { ok: true, data: await operation() }
  } catch (error) {
    if (error instanceof ApiIpcError) {
      return {
        ok: false,
        error: {
          code: error.code,
          message: error.message,
          ...(error.details === undefined ? {} : { details: error.details }),
        },
      }
    }
    return {
      ok: false,
      error: { code: "internal_error", message: "请求处理失败，请稍后重试。" },
    }
  }
}

function invalidRequest(): ApiIpcError {
  return new ApiIpcError("invalid_request", "请求内容不符合要求。")
}

function collectSensitiveValues(value: unknown, depth = 0): string[] {
  if (depth > 5 || ArrayBuffer.isView(value) || !isRecord(value)) {
    return []
  }
  return Object.entries(value).flatMap(([key, item]) => {
    if (isSensitiveKey(key) && typeof item === "string" && item) {
      return [item]
    }
    if (Array.isArray(item)) {
      return item.flatMap((entry) => collectSensitiveValues(entry, depth + 1))
    }
    return collectSensitiveValues(item, depth + 1)
  })
}

function sanitizeDetails(value: unknown, secrets: string[], depth = 0): unknown {
  if (depth > 5) return "[TRUNCATED]"
  if (typeof value === "string") return redactString(value, secrets)
  if (Array.isArray(value)) {
    return value.slice(0, 50).map((item) => sanitizeDetails(item, secrets, depth + 1))
  }
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .slice(0, 50)
        .map(([key, item]) => [
          key,
          isSensitiveKey(key)
            ? REDACTED
            : sanitizeDetails(item, secrets, depth + 1),
        ]),
    )
  }
  if (value === null || typeof value === "number" || typeof value === "boolean") {
    return value
  }
  return undefined
}

function redactString(value: string, secrets: string[]): string {
  return secrets.reduce(
    (result, secret) => (secret ? result.split(secret).join(REDACTED) : result),
    value,
  )
}

function isSensitiveKey(key: string): boolean {
  return /password|token|secret|authorization|credential/i.test(key)
}

function isAbortError(error: unknown): boolean {
  return isRecord(error) && error.name === "AbortError"
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
