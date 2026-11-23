// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiClientError } from "../../src/renderer/src/api/client"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  user: { id: "admin-1", role: "admin" },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))

import { OpsBriefPanel } from "../../src/renderer/src/system/OpsBriefPanel"

const briefPayload = {
  brief_markdown: "# 运营简报 2026-11-24\n\n## 一、运营待办（共 2 项，已到期 1 项）\n\n- automation_approval：1 项\n\n| 域 | 事项 |\n|---|---|\n| 审批 | 导出 SOW |",
  brief_sha256: "a".repeat(64),
  todo_total: 2,
  due_total: 1,
  funnel: { delivery_packages: { offered: 1 } },
  generated_at: "2026-11-24T09:00:00+00:00",
}

const todoItems = [
  { domain: "automation_approval", object_id: "ap-1", title: "solutions.export_sow",
    deadline_at: "2026-11-24T10:00:00+00:00", state: "pending", queue: "production_data_writes" },
  { domain: "meeting_todo", object_id: "min-1:0", title: "补齐验收材料",
    deadline_at: null, state: "open", queue: null },
]

beforeEach(() => {
  mocks.apiRequest.mockReset()
})

afterEach(() => {
  cleanup()
})

describe("运营待办与简报面板", () => {
  it("拉取并呈现待办清单（含域过滤与无期限标注）", async () => {
    mocks.apiRequest.mockResolvedValue({ items: todoItems, total: 2 })
    render(<OpsBriefPanel />)

    expect(await screen.findByRole("region", { name: "运营待办" })).toBeInTheDocument()
    expect(mocks.apiRequest).toHaveBeenCalledWith("/api/v1/ops/todos?limit=100", { method: "GET" })
    expect(screen.getByText("solutions.export_sow")).toBeInTheDocument()
    expect(screen.getByText("补齐验收材料")).toBeInTheDocument()
    expect(screen.getByText("无期限")).toBeInTheDocument()
    expect(screen.getByText("production_data_writes")).toBeInTheDocument()
    // queue 为 null 的域呈现运营协调归类
    expect(screen.getByText("运营协调")).toBeInTheDocument()

    // 本地域过滤：切到纪要待办只剩一条
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText("按域过滤"), "meeting_todo")
    expect(screen.queryByText("solutions.export_sow")).not.toBeInTheDocument()
    expect(screen.getByText("补齐验收材料")).toBeInTheDocument()
  })

  it("待办读取失败呈现告警不炸面板", async () => {
    mocks.apiRequest.mockRejectedValue(
      new ApiClientError({ code: "forbidden", message: "运营待办聚合视图仅平台管理员可读。" }, 403))
    render(<OpsBriefPanel />)
    expect(await screen.findByRole("alert")).toHaveTextContent("运营待办聚合视图仅平台管理员可读。")
    // 简报区仍可用
    expect(screen.getByRole("button", { name: "生成运营简报" })).toBeEnabled()
  })

  it("生成简报呈现正文指纹并提供下载", async () => {
    const user = userEvent.setup()
    mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string; body?: unknown }) => {
      if (path.startsWith("/api/v1/ops/todos")) return { items: todoItems, total: 2 }
      if (path === "/api/v1/ops/briefs/generate" && options?.method === "POST") {
        expect(options.body).toEqual({})
        return briefPayload
      }
      throw new Error(`unexpected call: ${path}`)
    })
    render(<OpsBriefPanel />)

    await user.click(await screen.findByRole("button", { name: "生成运营简报" }))
    expect(await screen.findByRole("status")).toHaveTextContent("已到期 1 项")
    expect(screen.getByRole("heading", { name: "运营简报 2026-11-24" })).toBeInTheDocument()
    expect(screen.getByText(briefPayload.brief_sha256)).toBeInTheDocument()
    expect(mocks.apiRequest).toHaveBeenCalledWith(
      "/api/v1/ops/briefs/generate", { method: "POST", body: {} })

    // 下载：blob anchor 注入后点击（jsdom 无真实下载，仅断言锚点形状）
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
    await user.click(screen.getByRole("button", { name: "下载 Markdown" }))
    expect(clickSpy).toHaveBeenCalledTimes(1)
    clickSpy.mockRestore()
  })

  it("简报生成失败呈现告警且按钮恢复可用", async () => {
    const user = userEvent.setup()
    mocks.apiRequest.mockImplementation(async (path: string) => {
      if (path.startsWith("/api/v1/ops/todos")) return { items: [], total: 0 }
      throw new ApiClientError({ code: "forbidden", message: "运营简报仅平台管理员可生成。" }, 403)
    })
    render(<OpsBriefPanel />)
    await screen.findByRole("region", { name: "运营待办" })

    await user.click(screen.getByRole("button", { name: "生成运营简报" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("运营简报仅平台管理员可生成。")
    expect(screen.getByRole("button", { name: "生成运营简报" })).toBeEnabled()
    expect(screen.getByText("尚未生成简报。")).toBeInTheDocument()
  })

  it("空待办呈现空态文案", async () => {
    mocks.apiRequest.mockResolvedValue({ items: [], total: 0 })
    render(<OpsBriefPanel />)
    expect(await screen.findByText("没有符合条件的待办。")).toBeInTheDocument()
    // 「共 N 项」被 <strong> 拆开，按 region 文本断言
    expect(screen.getByRole("region", { name: "运营待办" })).toHaveTextContent("共 0 项")
  })
})
