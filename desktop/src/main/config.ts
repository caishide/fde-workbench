import { isAbsolute, relative } from "node:path"
import { fileURLToPath } from "node:url"

export const DEVELOPMENT_API_URL = "http://127.0.0.1:8010"

export interface ApiUrlEnvironment {
  isPackaged: boolean
  allowPackagedLocalApi?: boolean
}

export interface RendererUrlEnvironment {
  isPackaged: boolean
  rendererRoot: string
  developmentUrl?: string
}

export function resolveApiBaseUrl(
  configuredUrl: string | undefined,
  environment: ApiUrlEnvironment,
): string {
  const candidate = configuredUrl ?? (environment.isPackaged ? undefined : DEVELOPMENT_API_URL)
  if (!candidate) {
    throw new Error("FDE_DESKTOP_API_URL is required in production.")
  }

  let url: URL
  try {
    url = new URL(candidate)
  } catch {
    throw new Error("FDE_DESKTOP_API_URL must be a valid absolute URL.")
  }

  if (
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("FDE_DESKTOP_API_URL must contain only an origin.")
  }

  const normalized = url.origin
  if (url.protocol === "https:") {
    return normalized
  }

  if (
    (!environment.isPackaged
      && url.protocol === "http:"
      && url.hostname === "127.0.0.1"
      && url.port !== "")
    || (
      normalized === DEVELOPMENT_API_URL
      && environment.allowPackagedLocalApi === true
    )
  ) {
    return normalized
  }

  throw new Error(
    "FDE_DESKTOP_API_URL must use HTTPS (except an explicitly enabled exact local API URL).",
  )
}

export function isAllowedRendererUrl(
  candidate: string,
  environment: RendererUrlEnvironment,
): boolean {
  if (!environment.isPackaged && environment.developmentUrl) {
    try {
      const target = new URL(candidate)
      const development = new URL(environment.developmentUrl)
      return (
        (development.protocol === "http:" || development.protocol === "https:") &&
        target.origin === development.origin
      )
    } catch {
      return false
    }
  }

  try {
    const url = new URL(candidate)
    if (url.protocol !== "file:" || url.search) {
      return false
    }
    let child: string
    try {
      // 分隔符归一：win32 relative() 产反斜杠，统一成 / 再判前缀逃逸。
      child = relative(environment.rendererRoot, fileURLToPath(url)).replaceAll(
        "\\",
        "/",
      )
    } catch {
      // posix 风格 file URL（无盘符）在 win32 上 fileURLToPath 会抛
      // ERR_INVALID_FILE_URL_PATH——回退为 URL pathname 与归一化 rendererRoot
      // 的纯 posix 相对比较，包含性判定不放宽。
      const root = environment.rendererRoot.replaceAll("\\", "/")
      const target = decodeURIComponent(url.pathname).replaceAll("\\", "/")
      child = posixRelative(root, target)
    }
    return (
      child === "" || (child !== ".." && !child.startsWith("../") && !isAbsolute(child))
    )
  } catch {
    return false
  }
}

function posixRelative(from: string, to: string): string {
  const base = from.split("/").filter(Boolean)
  const target = to.split("/").filter(Boolean)
  let shared = 0
  while (shared < base.length && shared < target.length && base[shared] === target[shared]) {
    shared += 1
  }
  const ups = base.length - shared
  if (ups > 0) {
    return "../".repeat(ups) + target.slice(shared).join("/")
  }
  return target.slice(shared).join("/")
}
