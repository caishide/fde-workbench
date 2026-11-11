import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { defineConfig } from "electron-vite"

import { buildCspConnectSrc } from "./src/main/build-csp"

/**
 * CR-057（夜审 r6 设计稿 A＋D）：打包态 CSP connect-src 构建注入。
 *
 * `desktop/src/renderer/index.html` 的 meta CSP 原先写死
 * `connect-src http://127.0.0.1:8010`——远程 https API（README 文档化一等路径：
 * 打包前改 `build.extraMetadata.fdeApiUrl`）或 `storage_backend=oss`（config.py 一等
 * 配置）下，renderer 直连 signed URL 的文件二进制面被 CSP 静默阻断（API 面走 IPC
 * 桥不受 CSP 管）⇒ 半坏隐蔽态。
 *
 * 本插件在 **build 时**（不碰 dev）读 package.json `build.extraMetadata` 的
 * `fdeApiUrl`＋可选 `fdeOssHost`，用 `buildCspConnectSrc` 纯函数派生 connect-src
 * 并注入 index.html 的 meta CSP。单点来源＝extraMetadata（与 fdeApiUrl 同点，
 * 不造第二配置面）。本地形态（未设 fdeOssHost、fdeApiUrl 缺省/回环）派生结果
 * 恒等于旧写死值 ⇒ 默认打包物零行为变化。
 */
interface FdeExtraMetadata {
  fdeApiUrl?: string
  fdeOssHost?: string
}

function readExtraMetadata(): FdeExtraMetadata {
  try {
    const raw = readFileSync(resolve(__dirname, "package.json"), "utf8")
    const parsed = JSON.parse(raw) as { build?: { extraMetadata?: FdeExtraMetadata } }
    return parsed?.build?.extraMetadata ?? {}
  } catch {
    // 读不到 extraMetadata ⇒ 本地形态缺省（回环），不静默失败。
    return {}
  }
}

function cspInjectionPlugin() {
  const { fdeApiUrl, fdeOssHost } = readExtraMetadata()
  const connectSrc = buildCspConnectSrc(fdeApiUrl, fdeOssHost)
  return {
    name: "fde-csp-connect-src-inject",
    apply: "build" as const,
    transformIndexHtml(html: string) {
      // index.html 写死值恒为本地回环缺省；远程/OSS 形态才替换。
      // 本地形态（派生值==旧写死值）原样返回——默认打包物零行为变化。
      const marker = "connect-src http://127.0.0.1:8010"
      if (connectSrc === "http://127.0.0.1:8010") return html
      return html.replace(marker, `connect-src ${connectSrc}`)
    },
  }
}

export default defineConfig({
  main: {
    build: {
      rollupOptions: {
        input: resolve(__dirname, "src/main/index.ts"),
      },
    },
  },
  preload: {
    build: {
      rollupOptions: {
        input: resolve(__dirname, "src/preload/index.ts"),
      },
    },
  },
  renderer: {
    root: resolve(__dirname, "src/renderer"),
    plugins: [cspInjectionPlugin()],
    build: {
      rollupOptions: {
        input: resolve(__dirname, "src/renderer/index.html"),
      },
    },
  },
})
