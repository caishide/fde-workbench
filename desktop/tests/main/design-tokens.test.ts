import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

/**
 * 设计令牌静态守卫（B / S0）
 *
 * 与 brand-hardcode.test.ts 同属「静态文本闸」：不启动 Electron、不渲染 React、
 * 不改写任何既有用例。docs/tokens.json 是配色与视觉变量的唯一规范真源，
 * 运行时 :root 是它的镜像；本文件负责让两者不再各自漂移。
 *
 * 对应方案：docs/UI-UX美化方案-v2.md §3.0 B0 / §3.5 F7 / §6 验收。
 */

const REPO_ROOT = fileURLToPath(new URL("../../..", import.meta.url))
const read = (relative: string): string =>
  readFileSync(join(REPO_ROOT, relative), "utf8")

const styles = read("desktop/src/renderer/src/styles.css")
const site = read("site/index.html")
const tokens = JSON.parse(read("docs/tokens.json")) as {
  color: {
    brand: {
      primary: { value: string }
      accent: { value: string }
      interactive: { value: string }
      interactiveDeep: { value: string }
    }
    background: { page: { value: string }; surface: { value: string } }
    text: { primary: { value: string }; secondary: { value: string } }
    border: { default: { value: string }; buttonPrimary: { value: string } }
    status: {
      success: { base: string }
      warning: { base: string }
      danger: { base: string }
      info: { base: string; border: string }
    }
    button: { primary: { text: { value: string }; background: { value: string } } }
  }
}

/** 抽出某个选择器的声明块（CSS 内无嵌套花括号，够用且不会误吞相邻规则）。 */
function block(source: string, selector: string): string {
  const start = source.indexOf(selector)
  if (start < 0) return ""
  const open = source.indexOf("{", start)
  const close = source.indexOf("}", open)
  if (open < 0 || close < 0) return ""
  return source.slice(open + 1, close)
}

/** 静态文本检测前剥离 CSS 注释，避免「说明文字里写了某个变量名」被当成真实引用。 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "")
}

/** 抽出 :root 中的自定义属性声明。 */
function rootDeclarations(): Map<string, string> {
  const rootBlock = stripComments(block(styles, ":root {"))
  const declarations = new Map<string, string>()
  for (const match of rootBlock.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    declarations.set(match[1].trim(), match[2].trim())
  }
  return declarations
}

function collectTsx(dir: string): string[] {
  const files: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      files.push(...collectTsx(full))
    } else if (entry.endsWith(".tsx")) {
      files.push(full)
    }
  }
  return files
}

const root = rootDeclarations()

describe("设计令牌 · 单一真源与 :root 一致性", () => {
  it("docs/tokens.json 可解析且核心色值与运行时 :root 逐项一致", () => {
    const expected: Array<[string, string]> = [
      ["--brand-ink", tokens.color.brand.primary.value],
      ["--brand-gold", tokens.color.brand.accent.value],
      ["--brand-blue", tokens.color.brand.interactive.value],
      ["--gold-5", tokens.color.brand.interactiveDeep.value],
      ["--bg", tokens.color.background.page.value],
      ["--surface", tokens.color.background.surface.value],
      ["--text", tokens.color.text.primary.value],
      ["--muted", tokens.color.text.secondary.value],
      ["--line", tokens.color.border.default.value],
      ["--success", tokens.color.status.success.base],
      ["--warning", tokens.color.status.warning.base],
      ["--danger", tokens.color.status.danger.base],
      ["--info", tokens.color.status.info.base],
      ["--info-border", tokens.color.status.info.border],
    ]
    for (const [name, value] of expected) {
      expect(root.get(name)?.toUpperCase(), `${name} 应与 tokens.json 一致`).toBe(
        value.toUpperCase(),
      )
    }
  })

  it("不存在对未定义变量的引用，重复令牌已别名化", () => {
    expect(stripComments(styles)).not.toMatch(/var\(--primary\)/)
    expect(root.get("--blue-pale-border")).toBe("var(--info-border)")
    expect(root.get("--radius-lg")).toBe("var(--radius)")
  })

  it("深底文字令牌与语义色小字加深令牌已建立", () => {
    for (const name of [
      "--on-dark-primary",
      "--on-dark-secondary",
      "--on-dark-muted",
      "--on-dark-disabled",
      "--success-ink",
      "--warning-ink",
      "--danger-ink",
      "--info-ink",
      "--opacity-disabled",
    ]) {
      expect(root.has(name), `${name} 应已在 :root 定义`).toBe(true)
    }
    expect(block(styles, ".sidebar-account .app-version {")).not.toMatch(/11px/)
  })
})

describe("主按钮（B1 / D4）· 两处选择器族默认态与 hover 态", () => {
  const expectedText = tokens.color.button.primary.text.value
  const expectedBackground = tokens.color.button.primary.background.value

  it("桌面端 .primary-button 为白底 + 石墨黑文字 + 达标金描边，hover 保持白底", () => {
    const base = block(styles, ".primary-button {")
    const hover = block(styles, ".primary-button:hover:not(:disabled) {")
    expect(base).toContain("background: var(--surface)")
    expect(base).toContain("color: var(--brand-ink)")
    expect(base).toContain("border: 1px solid var(--gold-5)")
    expect(base).not.toContain("brand-gradient")
    expect(hover).toContain("background: var(--surface)")
    expect(hover).toContain("border-color: var(--gold-5)")
    expect(hover).not.toContain("brand-gradient")
    expect(hover).not.toContain("filter: brightness")
    // 描边色对白底须 ≥3:1：#C98F2B 只有 2.82:1，故使用 --gold-5（4.21:1）
    expect(root.get("--gold-5")?.toUpperCase()).toBe(
      tokens.color.border.buttonPrimary.value.toUpperCase(),
    )
    expect(expectedText).toBe("#14181C")
    expect(expectedBackground).toBe("#FFFFFF")
  })

  it("官网 .btn-gold 为白底 + 石墨黑文字，hover 不再以 --gold-deep 作背景", () => {
    const base = block(site, ".btn-gold{")
    const hover = block(site, ".btn-gold:hover{")
    expect(base).toContain("background:var(--card)")
    expect(base).toContain("color:var(--ink)")
    expect(base).toContain("border-color:var(--gold-deep)")
    expect(base).not.toContain("brand-gradient")
    expect(hover).toContain("background:var(--card)")
    expect(hover).toContain("border-color:var(--gold-deep)")
    expect(hover).not.toContain("background:var(--gold-deep)")
    expect(hover).not.toContain("background: var(--gold-deep)")
  })
})

describe("--brand-gradient 降级为非交互展示面", () => {
  it("交互控件（主按钮 / 官网 CTA / 侧栏激活态 / 两个 tab 激活态）不再铺渐变", () => {
    for (const [source, selector] of [
      [styles, ".primary-button {"] as const,
      [styles, ".primary-button:hover:not(:disabled) {"] as const,
      [styles, ".nav-item.active {"] as const,
      [styles, ".template-editor-tabs button.active {"] as const,
      [styles, ".detail-tabs a.active {"] as const,
      [site, ".btn-gold{"] as const,
      [site, ".btn-gold:hover{"] as const,
    ]) {
      expect(block(source, selector), `${selector} 应存在且不含渐变`).not.toContain(
        "brand-gradient",
      )
    }
  })

  it("展示面仍保留品牌渐变（文字渐变 / 装饰条 / 进度条 / 甘特条）", () => {
    expect(styles).toContain("progress::-webkit-progress-value { background: var(--brand-gradient)")
    expect(styles).toContain(".gantt-bar > span { position: absolute; inset: 0 auto 0 0; background: var(--brand-gradient)")
    expect(styles).toContain(".completion-value { background: var(--brand-gradient)")
    expect(styles).toContain(".project-completion { display: block; background: var(--brand-gradient)")
  })
})

describe("S0 · 焦点与可读性", () => {
  it("全局焦点环统一为 2px 实心亮金 + offset 2px，不再有 3px/4px 混用", () => {
    expect(styles).toContain("outline: 2px solid var(--brand-gold-bright)")
    expect(styles).not.toContain("outline: 3px solid var(--brand-focus)")
    expect(styles).not.toContain("outline-offset: 4px")
    expect(styles).not.toContain("outline-offset:3px")
  })

  it("语义色 12px 小字使用加深 ink 色，soft 底与边框不变", () => {
    expect(styles).toContain(".badge.success, .badge.ok { background: var(--success-soft); color: var(--success-ink); }")
    expect(styles).toContain(".notice { border: 1px solid var(--success-border); background: var(--success-soft); color: var(--success-ink); }")
    expect(styles).toContain("color: var(--danger-ink)")
    expect(styles).toContain("color: var(--warning-ink)")
    expect(styles).toContain("color: var(--info-ink)")
  })
})

describe("S0 起禁止新增原生确认旁路（裁决 4）", () => {
  // 2026-11-06 实施基线实测 16 处 window.confirm / window.alert。
  // 归一属 S2（单独排期），本守卫只锁「不得新增」，不改写既有用例。
  const BASELINE_NATIVE_CONFIRM_CALLS = 16

  it("window.confirm / window.alert 调用数不超过实施基线", () => {
    const srcDir = join(REPO_ROOT, "desktop/src/renderer/src")
    const hits = collectTsx(srcDir).reduce((total, file) => {
      const source = readFileSync(file, "utf8")
      return total + (source.match(/window\.(?:confirm|alert)/g) ?? []).length
    }, 0)
    expect(hits, "如需新增原生确认，请改走统一 Modal（见方案 F6 / 裁决 4）").toBeLessThanOrEqual(
      BASELINE_NATIVE_CONFIRM_CALLS,
    )
  })
})
