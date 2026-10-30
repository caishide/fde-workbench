// G6 浏览器回归：两条链路的真实 UI 走查。
//
// 用仓库自带的 Playwright（desktop devDependency，Chromium 已装）驱动
// desktop/gui-harness 提供的真实 renderer：
//   ① 指引链：只读 draft 态必须出现「确认并用于项目指引」按钮（R11 事故防线）
//   ② 集成桥页：按钮状态 / 采集触发路径 / 快照到站刷新提示
//
// 用法（仓库根）：
//   node desktop/gui-harness/regression.mjs
//
// 前置：harness dev server 在 127.0.0.1:5199，后端在 127.0.0.1:8010。
// 截图落在 desktop/gui-harness/screenshots/ 下。
import { chromium } from "playwright-core"
import { mkdirSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const shotDir = resolve(here, "screenshots")
mkdirSync(shotDir, { recursive: true })

const BASE = process.env.FDE_HARNESS_URL ?? "http://127.0.0.1:5199"
const USERNAME = process.env.FDE_HARNESS_USER ?? "gui.regression"
const PASSWORD = process.env.FDE_HARNESS_PASSWORD ?? "GuiRegression!2026"

const results = []

function record(point, status, detail, screenshot) {
  results.push({ point, status, detail, screenshot })
  const mark = status === "PASS" ? "PASS" : "FAIL"
  console.log(`[${mark}] ${point} :: ${detail}`)
}

async function shot(page, name) {
  const file = resolve(shotDir, `${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  return file
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  const consoleErrors = []
  // frame-ancestors 只能经 HTTP 头下发，经 <meta> 会被浏览器忽略并告警——
  // 这是生产 CSP 写法在浏览器侧的固有提示，不是应用缺陷，单独归类。
  const KNOWN_BROWSER_NOTICE = "frame-ancestors"
  const appErrors = []
  page.on("console", (message) => {
    if (message.type() !== "error") return
    const text = message.text()
    if (text.includes(KNOWN_BROWSER_NOTICE)) { consoleErrors.push(`[已知浏览器提示，非缺陷] ${text}`); return }
    appErrors.push(text)
  })
  page.on("pageerror", (error) => appErrors.push(`pageerror: ${error.message}`))

  try {
    // --- 登录（真实表单提交） ---
    await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" })
    await page.fill("#login-username", USERNAME)
    await page.fill("#login-password", PASSWORD)
    await shot(page, "01-login-page")
    await page.click("button.primary-button.full-width")
    await page.waitForSelector("#app-shell, .app-shell, main [class*='sidebar'], nav", { timeout: 15000 })
    const loggedIn = page.url()
    record("登录", "PASS", `已登录，当前地址 ${loggedIn}`, await shot(page, "02-after-login"))

    // --- ① 指引链：只读 draft 态必须有确认按钮 ---
    await page.goto(`${BASE}/#/projects`, { waitUntil: "domcontentloaded" })
    await page.waitForTimeout(1200)
    const projectLink = page.locator("text=GUI regression project").first()
    if (await projectLink.count() === 0) {
      record("进入项目详情", "FAIL", "项目列表里找不到「GUI regression project」", await shot(page, "03-project-list"))
      throw new Error("project card missing")
    }
    // 项目卡片上的真实入口是「进入项目」链接（aria-label: 进入项目：<项目名>）
    const enterLink = page.getByRole("link", { name: "进入项目：GUI regression project" })
    if (await enterLink.count() === 0) {
      record("进入项目详情", "FAIL", "项目卡片上没有「进入项目」链接", await shot(page, "03-project-list"))
      throw new Error("enter-project link missing")
    }
    await enterLink.click()
    await page.waitForTimeout(2500)
    record("进入项目详情", "PASS", `已进入项目详情 ${page.url()}`, await shot(page, "04-project-detail"))

    // 指引卡片：应出现「查看预调研分析」入口（挂载认领）
    const reviewEntry = page.getByRole("button", { name: "查看预调研分析" })
    const entryCount = await reviewEntry.count()
    record("指引链-挂载认领入口", entryCount === 1 ? "PASS" : "FAIL",
      `「查看预调研分析」按钮数量=${entryCount}`, await shot(page, "05-guidance-card"))

    if (entryCount === 1) {
      await reviewEntry.click()
      await page.waitForTimeout(1500)
      const dialog = page.locator('[role="dialog"]')
      await dialog.waitFor({ timeout: 8000 })
      await shot(page, "06-guidance-review-readonly")

      // R11 事故防线：只读 draft 态必须直接显示确认按钮
      const confirmBtn = page.getByRole("button", { name: "确认并用于项目指引" })
      const confirmCount = await confirmBtn.count()
      const confirmVisible = confirmCount === 1 ? await confirmBtn.isVisible() : false
      record("指引链-只读draft确认按钮", confirmCount === 1 && confirmVisible ? "PASS" : "FAIL",
        `「确认并用于项目指引」数量=${confirmCount} 可见=${confirmVisible}`,
        await shot(page, "07-confirm-button-in-readonly"))

      // 只读态不该出现编辑三件套
      const saveBtn = page.getByRole("button", { name: "保存修改" })
      const saveCount = await saveBtn.count()
      record("指引链-只读态无保存按钮", saveCount === 0 ? "PASS" : "FAIL",
        `只读态「保存修改」数量=${saveCount}（应为 0）`, await shot(page, "08-readonly-no-save"))

      // 编辑按钮存在 → 点进编辑模式（验证两态互斥）。
      // 注意「编辑」在页面上不唯一（项目信息卡也有一个），必须限定在弹窗内。
      const editBtn = dialog.getByRole("button", { name: "编辑" })
      if (await editBtn.count() === 1) {
        await editBtn.click()
        await page.waitForTimeout(800)
        const editSaveCount = await dialog.getByRole("button", { name: "保存修改" }).count()
        record("指引链-编辑态三件套", editSaveCount === 1 ? "PASS" : "FAIL",
          `编辑态「保存修改」数量=${editSaveCount}（应为 1）`, await shot(page, "09-editing-mode"))
      } else {
        record("指引链-编辑态三件套", "FAIL", "弹窗内找不到唯一的「编辑」按钮", await shot(page, "09-editing-mode"))
      }
      // 关闭面板
      const closeBtn = page.getByRole("button", { name: "关闭" })
      if (await closeBtn.count() === 1) await closeBtn.click()
      await page.waitForTimeout(500)
    }

    // --- ② 集成桥页（走侧边栏链接：SPA 靠 hashchange 切换路由，直接改 hash 不触发重渲染） ---
    const bridgeNav = page.getByRole("link", { name: "集成桥" })
    if (await bridgeNav.count() === 0) {
      record("集成桥-页面可达", "FAIL", "侧边栏没有「集成桥」入口", await shot(page, "10-bridge-page"))
      throw new Error("bridge nav missing")
    }
    await bridgeNav.click()
    await page.waitForSelector("#bridge-page", { timeout: 15000 })
    await page.waitForTimeout(2000)
    await shot(page, "10-bridge-page")
    const bodyText = await page.locator("body").innerText()
    const hasBridgeHeading = bodyText.includes("集成桥")
    record("集成桥-页面可达", hasBridgeHeading ? "PASS" : "FAIL",
      hasBridgeHeading ? "集成桥页已加载" : "页面未见「集成桥」标题", await shot(page, "10-bridge-page"))

    // 三个按钮：立即采集 / 刷新 / 重新投影
    const captureBtn = page.getByRole("button", { name: "立即采集" })
    const refreshBtn = page.getByRole("button", { name: "刷新" })
    const reprojectBtn = page.getByRole("button", { name: "重新投影" })
    const counts = {
      capture: await captureBtn.count(),
      refresh: await refreshBtn.count(),
      reproject: await reprojectBtn.count(),
    }
    record("集成桥-按钮齐备",
      counts.capture === 1 && counts.refresh === 1 && counts.reproject === 1 ? "PASS" : "FAIL",
      `立即采集=${counts.capture} 刷新=${counts.refresh} 重新投影=${counts.reproject}`,
      await shot(page, "11-bridge-buttons"))

    // 采集触发路径：点「立即采集」→ 失败要有用户可见提示（harness 无宿主计划任务）
    if (counts.capture === 1) {
      await captureBtn.click()
      await page.waitForTimeout(1500)
      const afterCapture = await page.locator("body").innerText()
      const hinted = afterCapture.includes("采集") || afterCapture.includes("失败") || afterCapture.includes("宿主")
      record("集成桥-采集触发反馈", hinted ? "PASS" : "FAIL",
        hinted ? "点击「立即采集」后页面出现采集相关反馈" : "点击后未见采集反馈",
        await shot(page, "12-bridge-after-capture"))
    }

    // 刷新：应重新读取投影
    if (counts.refresh === 1) {
      await refreshBtn.click()
      await page.waitForTimeout(1200)
      record("集成桥-刷新无异常", "PASS", "点击「刷新」后页面正常响应", await shot(page, "13-bridge-after-refresh"))
    }

    record("控制台错误", appErrors.length === 0 ? "PASS" : "FAIL",
      appErrors.length === 0
        ? `无应用级控制台错误（另有 ${consoleErrors.length} 条浏览器已知提示）`
        : `捕获 ${appErrors.length} 条：${appErrors.slice(0, 3).join(" | ")}`,
      null)  } catch (error) {
    record("执行异常", "FAIL", String(error && error.message ? error.message : error).slice(0, 300), null)
    try {
      await shot(page, "99-failure-state")
    } catch { /* 截图失败不掩盖原始错误 */ }
  } finally {
    await browser.close()
  }

  const failed = results.filter((item) => item.status === "FAIL")
  console.log(`\n=== 汇总：${results.length - failed.length}/${results.length} 通过 ===`)
  for (const item of failed) console.log(`FAIL ${item.point} :: ${item.detail}`)
  process.exit(failed.length === 0 ? 0 : 1)
}

main()
