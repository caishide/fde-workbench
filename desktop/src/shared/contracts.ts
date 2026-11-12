export const USERNAME_MAX_LENGTH = 120
export const PASSWORD_MAX_LENGTH = 1_024

export const USER_ROLES = ["admin", "project_lead", "fde_engineer", "viewer"] as const
export type UserRole = (typeof USER_ROLES)[number]

export function isUserRole(value: unknown): value is UserRole {
  return typeof value === "string" && (USER_ROLES as readonly string[]).includes(value)
}

export interface UserDto {
  id: string
  username: string
  displayName: string
  role: UserRole
  mustChangePassword: boolean
  isActive: boolean
}

export interface ApiErrorDto {
  code: string
  message: string
  details?: unknown
}

export interface AuthResult {
  accessToken: string
  accessExpiresAt: string
  refreshExpiresAt: string
  user: UserDto
}

export interface LoginInput {
  username: string
  password: string
  deviceLabel: string
}

export type ApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"

export interface ApiRequestOptions {
  method: ApiMethod
  /**
   * 工作台访问令牌。**空串＝公开面**（免注册请求）：桥据此不下发
   * ``Authorization`` 头——获客诊断 T-14a 的匿名诊断流程走的就是这条路。
   */
  accessToken: string
  body?: unknown
  /**
   * 自定义请求头（获客诊断 T-14a）。**允许名单只有一个**：
   * ``X-Diagnostic-Token``（匿名诊断会话的持有即权凭证，服务端只从请求头取，
   * 不入 URL——URL 会进访问日志）。其余头一律被 shared/api-safety.ts 拒绝
   * （authorization／cookie 等可改写身份语义的头不可由渲染层覆写）。
   */
  headers?: Record<string, string>
}

export interface ApiResponse<T> {
  status: number
  data: T | null
  error: ApiErrorDto | null
}

export type BridgeResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: ApiErrorDto }

export interface BridgeCaptureResult {
  triggered: boolean
  task: string
}

export interface FdeBridge {
  auth: {
    login(input: LoginInput): Promise<BridgeResult<AuthResult>>
    refresh(): Promise<BridgeResult<AuthResult | null>>
    changePassword(
      accessToken: string,
      currentPassword: string,
      newPassword: string,
    ): Promise<BridgeResult<AuthResult>>
    logout(): Promise<BridgeResult<null>>
  }
  api: {
    request<T>(
      path: string,
      options: ApiRequestOptions,
    ): Promise<BridgeResult<ApiResponse<T>>>
  }
  bridge: {
    capture(): Promise<BridgeResult<BridgeCaptureResult>>
  }
  app: {
    version(): Promise<string>
    setLcscEnabled?(enabled: boolean): Promise<void>
    openLcscBrowser?(url: string): Promise<void>
    showLcscDownload?(filename: string): Promise<void>
    copyLcscRunId?(id: string): Promise<void>
    /**
     * CR-056（夜审 r6 设计稿推荐 A′）：直连分片上传在途写计数面。
     * renderer 直连 signed URL 的 PUT 不经 apiRequest IPC 桥，main 的
     * activeMutations 计数器看不见——上传站经此两事件把在途直连写计入
     * close-guard 判据。web 发行形态无 close-guard（同源反代+无主窗拦截），
     * 实现为空操作 no-op（形状同桌面 Promise 面）。
     */
    uploadBegin?(label: string): Promise<void>
    uploadEnd?(label: string): Promise<void>
  }
}

export const IPC_CHANNELS = {
  authLogin: "fde:auth:login",
  authRefresh: "fde:auth:refresh",
  authChangePassword: "fde:auth:change-password",
  authLogout: "fde:auth:logout",
  apiRequest: "fde:api:request",
  bridgeCapture: "fde:bridge:capture",
  appUploadBegin: "fde:app:upload-begin",
  appUploadEnd: "fde:app:upload-end",
  appVersion: "fde:app:version",
  appSetLcscEnabled: "fde:app:set-lcsc-enabled",
  appOpenLcscBrowser: "fde:app:open-lcsc-browser",
  appShowLcscDownload: "fde:app:show-lcsc-download",
  appCopyLcscRunId: "fde:app:copy-lcsc-run-id",
} as const

declare global {
  interface Window {
    fde: FdeBridge
  }
}
