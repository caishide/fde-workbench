// CR-057（夜审 r6 设计稿推荐 A＋D：构建注入＋形态矩阵成文）：
// 打包态 renderer index.html 的 CSP connect-src 由「打包配置」单点派生，
// 不再写死 `http://127.0.0.1:8010`。
//
// 背景：`desktop/src/renderer/index.html:7` 的 meta CSP connect-src 硬编码回环主机；
// 远程 https API（README 文档化一等路径：打包前改 `build.extraMetadata.fdeApiUrl`）或
// `storage_backend=oss`（config.py 一等配置，signed URL 直连 OSS 域）下，文件二进制面
// （renderer 直连 signed URL 的 PUT/GET）被 CSP 静默阻断，而 API 面走 IPC 桥不受 CSP
// 管 ⇒ 「半坏隐蔽态」。
//
// 本模块是**纯函数**（零 electron 导入，tsconfig.node 类型检查＋可单测）：
//   - 把 connect-src 主机集合的「派生逻辑」抽成可测纯面（设计稿 §三方案 A 的落点）；
//   - electron.vite.config.ts 的构建插件在 build 时读 package.json `build.extraMetadata`
//     （`fdeApiUrl`＋可选 `fdeOssHost`），用本纯函数算出 connect-src 并注入 index.html。
// 缺省（本地形态）时派生结果＝旧写死值 `http://127.0.0.1:8010`，行为零变化（方案 D 的
// 「本地默认零回归」承诺）；远程/OSS 形态才扩展 connect-src。
//
// 设计稿 §三裁定的「B 运行时下发」被剔除（meta∧header CSP 取交集语义），故这里只做
// 构建期注入——单一来源＝package.json `build.extraMetadata`，与 fdeApiUrl 同点，不造第二配置面。

/** 本地形态缺省 connect-src（＝旧 index.html 写死值，保证缺省行为零变化）。 */
export const DEFAULT_LOCAL_CONNECT_SRC = "http://127.0.0.1:8010"

/**
 * 由 `new URL(apiUrl).origin` 取 origin（scheme://host[:port]）。
 * 取 origin 而非整串 URL：CSP connect-src 需要 scheme+host（+port），不含 path。
 * 无法解析/非 http(s) 时回落到本地回环缺省（构建期不静默失败，且更严格更安全）。
 */
function originOf(apiUrl: string): string {
  try {
    const url = new URL(apiUrl)
    if (url.protocol !== "http:" && url.protocol !== "https:") return DEFAULT_LOCAL_CONNECT_SRC
    return url.origin
  } catch {
    return DEFAULT_LOCAL_CONNECT_SRC
  }
}

/** 可选 OSS 主机（形如 `oss-cn-hangzhou.example.com` 或带 scheme）→ origin。 */
function originOfOss(ossHost: string): string | null {
  const withScheme = /^https?:\/\//.test(ossHost) ? ossHost : `https://${ossHost}`
  try {
    const url = new URL(withScheme)
    if (url.protocol !== "http:" && url.protocol !== "https:") return null
    return url.origin
  } catch {
    return null
  }
}

/**
 * 派生打包态 index.html 的 CSP `connect-src` 值（设计稿 §三方案 A）。
 *
 * - `apiUrl` 缺省（本地形态）⇒ 恒等于本地回环缺省（**零回归承诺**：默认打包物与旧写死值一致）。
 * - `apiUrl` 设值（远程 https API 一等路径）⇒ connect-src＝该 origin。
 * - `ossHost` 设值（OSS 一等配置）⇒ **恒追加**该 origin（去重保序）；与 apiUrl 独立——
 *   本地 API＋OSS 存储、远程 API＋OSS 存储 都成立。
 *
 * @param apiUrl   打包配置的 API origin（`build.extraMetadata.fdeApiUrl`）。缺省/空＝本地形态。
 * @param ossHost  可选 OSS 主机（`build.extraMetadata.fdeOssHost`）；缺省/解析失败＝不追加。
 * @returns connect-src 指令值（多个 origin 空格分隔；本地缺省＝`http://127.0.0.1:8010`）。
 */
export function buildCspConnectSrc(apiUrl?: string, ossHost?: string): string {
  const hosts: string[] = []
  // 本地形态（apiUrl 未设）恒锚定回环缺省，不猜；远程形态取 apiUrl 的 origin。
  hosts.push(apiUrl ? originOf(apiUrl) : DEFAULT_LOCAL_CONNECT_SRC)
  // OSS 主机与 API 面独立，设值即追加（只加部署者显式配的主机，绝不 https: 通配——
  // 设计稿 §三 方案 C 否决留痕）。
  const oss = ossHost ? originOfOss(ossHost) : null
  if (oss && !hosts.includes(oss)) hosts.push(oss)
  return hosts.join(" ")
}
