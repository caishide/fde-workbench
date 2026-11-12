// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  confirm: vi.fn(),
  user: { id: "actor-1", role: "admin" as string },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))
vi.mock("../../src/renderer/src/common/ConfirmProvider", () => ({
  useConfirm: () => mocks.confirm,
}))

import { ApiClientError } from "../../src/renderer/src/api/client"
import {
  isChannelLinkRow,
  ChannelLinksPanel,
  type ChannelLinkRow,
} from "../../src/renderer/src/leads/ChannelLinksPanel"
import { LeadPoolPage } from "../../src/renderer/src/leads/LeadPoolPage"

const LINKS_PREFIX = "/api/v1/diagnostics/leads/channel-links"

function linkRow(overrides: Record<string, unknown> = {}): ChannelLinkRow {
  return {
    id: "link-1",
    region_name: "浙江省",
    note: "r4-zj-001",
    is_active: true,
    deactivated_at: null,
    created_by_user_id: "actor-9",
    created_at: "2026-11-12T00:00:00+00:00",
    lead_count: 3,
    ...overrides,
  } as ChannelLinkRow
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.confirm.mockReset()
  mocks.confirm.mockResolvedValue(true)
  mocks.user = { id: "actor-9", role: "admin" }
})

afterEach(() => {
  cleanup()
})

it("isChannelLinkRow：形状守卫放行/拒绝", () => {
  expect(isChannelLinkRow(linkRow())).toBe(true)
  expect(isChannelLinkRow({ id: "x" })).toBe(false)
  expect(isChannelLinkRow(null)).toBe(false)
})

it("清单渲染：区域/备注/归因线索数/在用徽标", async () => {
  mocks.apiRequest.mockImplementation((path: string) => {
    if (path === LINKS_PREFIX) return Promise.resolve([linkRow()])
    throw new Error(`unexpected GET ${path}`)
  })
  render(<ChannelLinksPanel />)

  expect(await screen.findByText("浙江省")).toBeVisible()
  expect(screen.getByText("r4-zj-001")).toBeVisible()
  expect(screen.getByText("归因线索 3 条")).toBeVisible()
  expect(screen.getByRole("status")).toHaveTextContent("在用")
  expect(screen.getByRole("button", { name: "停用" })).toBeVisible()
})

it("空清单与加载失败就地呈现", async () => {
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === LINKS_PREFIX && options?.method === "GET") return Promise.resolve([])
    throw new Error(`unexpected ${path}`)
  })
  const { unmount } = render(<ChannelLinksPanel />)
  expect(await screen.findByText("还没有渠道链接。")).toBeVisible()
  unmount()

  mocks.apiRequest.mockImplementation(() =>
    Promise.reject(new ApiClientError({ code: "server_error", message: "boom" }, 500)),
  )
  render(<ChannelLinksPanel />)
  expect(await screen.findByText("boom")).toBeVisible()
})

it("诊断面未启用（404 闸）⇒ 引导文案，不报错", async () => {
  mocks.apiRequest.mockImplementation(() =>
    Promise.reject(new ApiClientError({ code: "not_found", message: "资源不存在。" }, 404)),
  )
  render(<ChannelLinksPanel />)
  expect(await screen.findByText(/诊断面未启用（部署闸默认关闭）/)).toBeVisible()
})

it("创建链接：POST 区域/备注，token 就地呈现（明文只此一次），关闭后消失并刷新清单", async () => {
  const user = userEvent.setup()
  const created: ChannelLinkRow & { token: string } = {
    ...linkRow({ id: "link-2", region_name: "广东省", note: null, lead_count: 0 }),
    token: "tok-secret-once",
  }
  const gets: string[] = []
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
    if (path === LINKS_PREFIX && options?.method === "POST") {
      expect(options.body).toEqual({ region_name: "广东省" })
      return Promise.resolve(created)
    }
    if (path === LINKS_PREFIX) {
      gets.push(path)
      return Promise.resolve([linkRow()])
    }
    throw new Error(`unexpected ${path}`)
  })
  render(<ChannelLinksPanel />)
  await screen.findByText("浙江省")

  await user.type(screen.getByLabelText("区域（可选）"), "广东省")
  await user.click(screen.getByRole("button", { name: "生成专属链接" }))

  expect(
    await screen.findByText(/链接标识已生成（明文只此一次，关闭后不再可见）/),
  ).toBeVisible()
  expect(screen.getByText(/channel_ref=tok-secret-once/)).toBeVisible()
  // 创建后清单重拉（归因线索数对账可见）
  await waitFor(() => expect(gets.length).toBeGreaterThanOrEqual(2))

  await user.click(screen.getByRole("button", { name: "我已保存，关闭" }))
  expect(screen.queryByText(/链接标识已生成/)).toBeNull()
})

it("创建失败：服务端错误就地呈现，不弹 token", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === LINKS_PREFIX && options?.method === "POST") {
      return Promise.reject(new ApiClientError({ code: "note_too_long", message: "备注过长。" }, 400))
    }
    if (path === LINKS_PREFIX) return Promise.resolve([])
    throw new Error(`unexpected ${path}`)
  })
  render(<ChannelLinksPanel />)
  await screen.findByText("还没有渠道链接。")

  await user.click(screen.getByRole("button", { name: "生成专属链接" }))
  expect(await screen.findByText("备注过长。")).toBeVisible()
  expect(screen.queryByText(/链接标识已生成/)).toBeNull()
})

it("停用：确认弹窗后 POST deactivate，就地回执并重载", async () => {
  const user = userEvent.setup()
  const calls: Array<[string, string | undefined]> = []
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string }) => {
    calls.push([path, options?.method])
    if (path === `${LINKS_PREFIX}/link-1/deactivate` && options?.method === "POST") {
      return Promise.resolve(linkRow({ is_active: false }))
    }
    if (path === LINKS_PREFIX) {
      // 首次：在用；停用后重拉：已停用
      return Promise.resolve(
        calls.some(([p, m]) => p === `${LINKS_PREFIX}/link-1/deactivate` && m === "POST")
          ? [linkRow({ is_active: false })]
          : [linkRow()],
      )
    }
    throw new Error(`unexpected ${path}`)
  })
  render(<ChannelLinksPanel />)
  await screen.findByText("浙江省")

  await user.click(screen.getByRole("button", { name: "停用" }))
  await waitFor(() => expect(mocks.confirm).toHaveBeenCalled())
  expect(
    await screen.findByText("已停用：新线索不再按该链接归因，历史归因保持不变。"),
  ).toBeVisible()
  await waitFor(() => {
    expect(screen.getByText("已停用")).toBeVisible()
  })
})

it("停用取消：confirm 返回 false ⇒ 不打服务端", async () => {
  const user = userEvent.setup()
  mocks.confirm.mockResolvedValue(false)
  mocks.apiRequest.mockImplementation((path: string) => {
    if (path === LINKS_PREFIX) return Promise.resolve([linkRow()])
    throw new Error(`unexpected ${path}`)
  })
  render(<ChannelLinksPanel />)
  await screen.findByText("浙江省")

  await user.click(screen.getByRole("button", { name: "停用" }))
  await waitFor(() => expect(mocks.confirm).toHaveBeenCalled())
  await waitFor(() => {
    const deactivateCalls = mocks.apiRequest.mock.calls.filter(([path]) =>
      String(path).includes("/deactivate"),
    )
    expect(deactivateCalls).toHaveLength(0)
  })
})

it("LeadPoolPage：admin 可见面板，非 admin 不可见", async () => {
  mocks.apiRequest.mockImplementation((path: string) => {
    if (path === LINKS_PREFIX) return Promise.resolve([])
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve([])
    if (path.startsWith("/api/v1/diagnostics/leads/claims?")) return Promise.resolve([])
    throw new Error(`unexpected GET ${path}`)
  })
  const admin = render(<LeadPoolPage />)
  expect(await screen.findByRole("region", { name: "渠道链接管理" })).toBeVisible()
  admin.unmount()

  mocks.user = { id: "actor-1", role: "fde_engineer" }
  render(<LeadPoolPage />)
  await screen.findByText("我的认领申请")
  expect(screen.queryByRole("region", { name: "渠道链接管理" })).toBeNull()
})
