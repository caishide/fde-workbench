// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { App } from "../../src/renderer/src/App"
import { parseHashRoute } from "../../src/renderer/src/routing/useHashRoute"
import type { UserDto } from "../../src/shared/contracts"
import {
  adminUser,
  authResult,
  bridge,
  installBridge,
  ok,
  renderApp,
} from "./test-utils"

afterEach(() => {
  cleanup()
  location.hash = ""
})

function userFor(role: UserDto["role"]): UserDto {
  return {
    ...adminUser,
    id: `${role}-id`,
    username: `${role}.user`,
    displayName: `${role} 用户`,
    role,
  }
}

function renderAuthenticatedApp(role: UserDto["role"]): void {
  installBridge(
    bridge({
      refresh: vi.fn().mockResolvedValue(ok(authResult(userFor(role)))),
    }),
  )
  renderApp(<App />)
}

function waitForHistoryHash(hash: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanupListeners()
      reject(new Error(`History did not navigate to ${hash}.`))
    }, 1_000)
    const check = () => {
      if (location.hash !== hash) return
      cleanupListeners()
      resolve()
    }
    const cleanupListeners = () => {
      window.clearTimeout(timeout)
      window.removeEventListener("popstate", check)
      window.removeEventListener("hashchange", check)
    }
    window.addEventListener("popstate", check)
    window.addEventListener("hashchange", check)
  })
}

describe("role-aware project workbench navigation", () => {
  it.each([
    ["#projects", { kind: "projects" }],
    ["#projects/new", { kind: "new-project" }],
    ["#projects/73c3f6ee-08a6-41e9-985b-39df01777b67", { kind: "project", projectId: "73c3f6ee-08a6-41e9-985b-39df01777b67" }],
    ["#templates", { kind: "templates" }],
    ["#modules", { kind: "modules" }],
    ["#users", { kind: "users" }],
    ["#system-configuration", { kind: "system-configuration" }],
    ["#task-center", { kind: "task-center" }],
    ["#help", { kind: "help" }],
    ["#extensions", { kind: "extensions" }],
    ["#account", { kind: "account" }],
    ["#diagnostics", { kind: "public-diagnostics" }],
    ["#diagnostics/share/AbC_123-x", { kind: "public-diagnostics-share", shareToken: "AbC_123-x" }],
  ])("parses the supported route %s", (hash, route) => {
    expect(parseHashRoute(hash)).toEqual(route)
  })

  it("normalizes legacy project tabs and rejects ambiguous tab queries", () => {
    expect(parseHashRoute("#projects/alpha?tab=gantt")).toEqual({ kind: "project", projectId: "alpha", tab: "overview" })
    expect(parseHashRoute("#projects/alpha?tab=files")).toEqual({ kind: "project", projectId: "alpha", tab: "library" })
    expect(parseHashRoute("#projects/alpha?tab=documents")).toEqual({ kind: "project", projectId: "alpha", tab: "library" })
    expect(parseHashRoute("#projects/alpha?tab=members")).toEqual({ kind: "project", projectId: "alpha", tab: "management" })
    expect(parseHashRoute("#projects/alpha?tab=modules")).toEqual({ kind: "project", projectId: "alpha", tab: "management" })
    expect(parseHashRoute("#projects/alpha?tab=tasks&tab=gantt")).toEqual({ kind: "projects" })
    expect(parseHashRoute("#projects/alpha?tab=unknown")).toEqual({ kind: "projects" })
  })

  it.each([
    "",
    "#",
    "#projects/",
    "#projects/new/extra",
    "#projects/alpha/beta",
    "#projects/%2F",
    "#projects/%252F",
    "#projects/a%252Fb",
    "#projects/%3F",
    "#projects/%23",
    "#projects/%5C",
    "#projects/%25",
    "#projects/a%253Fb",
    "#projects/a%2523b",
    "#projects/a%255Cb",
    "#projects/a%2525b",
    "#projects/%E0%A4%A",
    "#projects/%2D",
    "#projects/.",
    "#unknown",
    // 获客诊断 T-14a：分享令牌非法形态不确认路由存在（回落 projects）
    "#diagnostics/share/",
    "#diagnostics/share/..",
    "#diagnostics/share/bad token",
    "#diagnostics/share/a%20b",
    "#diagnostics/share/%E0%A4%A",
  ])("rejects an ambiguous or malformed route %s", (hash) => {
    expect(parseHashRoute(hash)).toEqual({ kind: "projects" })
  })

  it("renders the public diagnostic flow for unauthenticated visitors (T-14a)", async () => {
    location.hash = "#diagnostics"
    installBridge(
      bridge({
        refresh: vi.fn().mockResolvedValue(ok(null)),
        apiRequest: vi.fn().mockResolvedValue(
          ok({ status: 404, data: null, error: { code: "not_found", message: "" } }),
        ),
      }),
    )
    renderApp(<App />)
    // 未登录直达 #diagnostics 渲染访客引导页（而非登录页）；部署闸默认关在
    // 点击「开始测算」后才以「暂未开放」呈现（404 不确认面存在）。
    expect(await screen.findByRole("heading", { name: "政策补贴测算" })).toBeVisible()
    expect(screen.getByRole("button", { name: "开始测算" })).toBeVisible()
    expect(screen.queryByRole("heading", { name: /登录/ })).not.toBeInTheDocument()
  })

  it("renders the public diagnostic share view for unauthenticated visitors (T-14a)", async () => {
    location.hash = "#diagnostics/share/tokABC_1"
    installBridge(
      bridge({
        refresh: vi.fn().mockResolvedValue(ok(null)),
        apiRequest: vi.fn().mockResolvedValue(
          ok({
            status: 200,
            data: {
              version: "diag-report-v2",
              generated_at: "2026-11-12T10:00:00+00:00",
              headline: "现状一句话：报价靠老师傅",
              findings: [],
              first_step: null,
              policy_opportunities: [],
              loop_completed: { identified: false, located: false, handled: false, written_back: false },
              notice: "这是诊断摘要。",
            },
            error: null,
          }),
        ),
      }),
    )
    renderApp(<App />)
    expect(await screen.findByRole("heading", { name: "现状一句话：报价靠老师傅" })).toBeVisible()
  })

  it.each([
    ["admin", ["项目工作台", "任务中心", "使用帮助", "行业模板", "模块管理", "用户管理", "系统配置"]],
    ["project_lead", ["项目工作台", "任务中心", "使用帮助"]],
    ["fde_engineer", ["项目工作台", "任务中心", "使用帮助"]],
    ["viewer", ["项目工作台", "任务中心", "使用帮助"]],
  ] as const)("shows permitted navigation for %s", async (role, labels) => {
    location.hash = "#projects"
    renderAuthenticatedApp(role)

    for (const label of labels) {
      expect(await screen.findByRole("link", { name: label })).toBeVisible()
    }
  })

  it("redirects non-admin template route to projects", async () => {
    location.hash = "#templates"
    renderAuthenticatedApp("project_lead")

    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()
    await waitFor(() => expect(location.hash).toBe("#projects"))
  })

  it("redirects non-admin away from the extensions center (J6)", async () => {
    // J6：扩展中心（LCSC 工具页 / 插件审批）属管理口径——此前任何已登录用户
    // 都能打开 #extensions（执行仍被服务端拦，但属于 UI 暴露面）。
    location.hash = "#extensions"
    renderAuthenticatedApp("project_lead")

    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()
    await waitFor(() => expect(location.hash).toBe("#projects"))
  })

  it("redirects non-admin away from the pilot report (goal-d12, d11 挂账④)", async () => {
    // UM-1 试点报告 admin 专属：d11 落地时 authorizedRoute 漏了 #/pilot 归一化，
    // project_lead 直输 #/pilot 会渲染页面并吃到服务端 403（pilot_report_forbidden）。
    location.hash = "#pilot"
    renderAuthenticatedApp("project_lead")

    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()
    await waitFor(() => expect(location.hash).toBe("#projects"))
  })

  it("keeps the pilot report for admin", async () => {
    location.hash = "#pilot"
    renderAuthenticatedApp("admin")

    expect(await screen.findByRole("heading", { name: "UM-1 试点观测（30 天 / 20 run）" })).toBeVisible()
    expect(location.hash).toBe("#pilot")
  })

  it.each(["fde_engineer", "viewer"] as const)("redirects %s away from project creation", async (role) => {
    location.hash = "#projects/new"
    renderAuthenticatedApp(role)

    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()
    await waitFor(() => expect(location.hash).toBe("#projects"))
  })

  it("normalizes a blank history entry and follows later hashchange navigation", async () => {
    location.hash = ""
    renderAuthenticatedApp("admin")

    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()
    await waitFor(() => expect(location.hash).toBe("#projects"))

    location.hash = "#templates"
    window.dispatchEvent(new HashChangeEvent("hashchange"))
    expect(await screen.findByRole("heading", { name: "行业模板" })).toBeVisible()

    location.hash = "#modules"
    window.dispatchEvent(new HashChangeEvent("hashchange"))
    expect(await screen.findByRole("heading", { name: "模块管理" })).toBeVisible()
  })

  it("uses browser history to return to projects and then forward to project detail", async () => {
    location.hash = "#projects"
    renderAuthenticatedApp("admin")
    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()

    location.hash = "#projects/73c3f6ee-08a6-41e9-985b-39df01777b67"
    expect(await screen.findByRole("heading", { name: "项目详情" })).toBeVisible()

    const back = waitForHistoryHash("#projects")
    window.history.back()
    await back
    expect(await screen.findByRole("heading", { name: "项目工作台" })).toBeVisible()

    const forward = waitForHistoryHash("#projects/73c3f6ee-08a6-41e9-985b-39df01777b67")
    window.history.forward()
    await forward
    expect(await screen.findByRole("heading", { name: "项目详情" })).toBeVisible()
  })
})
