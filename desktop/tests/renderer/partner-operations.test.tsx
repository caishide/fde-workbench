// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  user: { id: "actor-1", role: "viewer" },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))

import { PartnerOperationsPage } from "../../src/renderer/src/commercial/PartnerOperationsPage"
import { MyOffersPage } from "../../src/renderer/src/dispatch/MyOffersPage"

function partnerRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "rp-1",
    partner_code: "partner-sz-a",
    region_name: "深圳市南山区",
    note: null,
    stage: "city_observer",
    stage_note: "城市观察：免费自证阶段",
    tier_code: null,
    exclusive_territory: null,
    applied_at: "2026-11-24T08:00:00+00:00",
    stage_changed_at: null,
    ...overrides,
  }
}

function packageRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "pkg-1",
    package_code: "PKG-INBOX-01",
    scope_summary: "交付物 A",
    deliverables_json: "交付物 A",
    acceptance_criteria: "口径可判",
    data_systems: "ERP",
    schedule_text: "远程",
    risks_dependencies: "无",
    business_category: "PoV验证",
    client_code: "codename-a",
    client_city: "苏州",
    onsite_required: false,
    onsite_visits: null,
    deadline: "2026-12-31",
    delivery_seat_amount: 8000,
    dispatch_status: "offered",
    dispatch_round: 1,
    dispatch_mode: "assign",
    response_window_hours: 24,
    published_at: "2026-11-24T00:00:00+00:00",
    ...overrides,
  }
}

function offerRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    offer_id: "offer-1",
    status: "offered",
    version: 1,
    dispatch_round: 1,
    mode: "assign",
    offered_at: "2026-11-24T10:00:00+00:00",
    responded_at: null,
    deadline: "2026-11-25T10:00:00+00:00",
    match_breakdown: null,
    package: packageRow(),
    ...overrides,
  }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.user = { id: "actor-1", role: "viewer" }
})

afterEach(() => {
  cleanup()
})

it("伙伴运营页：三分卡渲染＋三个端点各调一次", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path) === "/api/v1/commercial/regional-partners") return [partnerRow()]
    if (String(path) === "/api/v1/commercial/regional-partner-tiers") {
      return {
        tiers: [
          {
            tier_code: "city",
            annual_fee_amount: "0",
            included_seats: 1,
            transfer_quota_seats: 0,
            basis_reference: "BP v4.0",
          },
        ],
        sale_gate_status: "closed",
      }
    }
    if (String(path) === "/api/v1/ops/todos/mine") {
      return {
        items: [
          {
            domain: "dispatch_offer",
            object_id: "o-1",
            title: "PKG-X·R1",
            deadline_at: "2026-11-25T10:00:00+00:00",
            state: "offered",
            queue: null,
          },
        ],
        total: 1,
      }
    }
    throw new Error("unexpected path " + String(path))
  })

  render(<PartnerOperationsPage />)
  await waitFor(() => {
    expect(screen.getByText("partner-sz-a")).toBeInTheDocument()
  })
  expect(screen.getByText(/城市观察 · 申请于/)).toBeInTheDocument()
  expect(screen.getByText(/区域售卖未开放/)).toBeInTheDocument()
  expect(screen.getByText("PKG-X·R1")).toBeInTheDocument()
  const calls = mocks.apiRequest.mock.calls.map((c) => String(c[0]))
  expect(calls).toContain("/api/v1/commercial/regional-partners")
  expect(calls).toContain("/api/v1/commercial/regional-partner-tiers")
  expect(calls).toContain("/api/v1/ops/todos/mine")
})

it("伙伴运营页：申请表单提交（POST 载荷与状态复位）", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation(async (path: string, init?: { method?: string }) => {
    if (String(path) === "/api/v1/commercial/regional-partners" && init?.method === "POST") {
      return { partner: partnerRow(), changed: true }
    }
    if (String(path) === "/api/v1/commercial/regional-partners") return []
    if (String(path) === "/api/v1/commercial/regional-partner-tiers") {
      return { tiers: [], sale_gate_status: "closed" }
    }
    if (String(path) === "/api/v1/ops/todos/mine") return { items: [], total: 0 }
    throw new Error("unexpected path " + String(path))
  })

  render(<PartnerOperationsPage />)
  await waitFor(() => {
    expect(screen.getByText("暂无申请记录；提交申请后会出现在这里。")).toBeInTheDocument()
  })
  await user.click(screen.getByText("申请成为城市观察伙伴"))
  await user.type(screen.getByPlaceholderText("伙伴代号（唯一）"), "partner-sz-b")
  await user.type(screen.getByPlaceholderText("区域名称（如：深圳市南山区）"), "深圳市福田区")
  await user.click(screen.getByText("提交申请"))
  await waitFor(() => {
    const post = mocks.apiRequest.mock.calls.find(
      (c) => String(c[0]) === "/api/v1/commercial/regional-partners" && c[1]?.method === "POST"
    )
    expect(post).toBeTruthy()
    expect(post![1].body).toEqual({
      partner_code: "partner-sz-b",
      region_name: "深圳市福田区",
      note: undefined,
    })
  })
})

it("我的接单三态分流：临期/待响应/已超时/已处理四组各归其位", async () => {
  const now = Date.now()
  const iso = (ms: number) => new Date(ms).toISOString()
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path) === "/api/v1/dispatch/offers/mine") {
      return [
        offerRow({ offer_id: "o-soon", deadline: iso(now + 30 * 60_000), package: packageRow({ package_code: "PKG-SOON" }) }),
        offerRow({ offer_id: "o-normal", deadline: iso(now + 20 * 3_600_000), package: packageRow({ package_code: "PKG-NORMAL" }) }),
        offerRow({ offer_id: "o-expired", status: "expired", deadline: iso(now - 3_600_000), package: packageRow({ package_code: "PKG-EXPIRED" }) }),
        offerRow({ offer_id: "o-done", status: "declined", responded_at: iso(now - 7_200_000), package: packageRow({ package_code: "PKG-DONE-1" }) }),
        offerRow({ offer_id: "o-accepted", status: "accepted", responded_at: iso(now - 8_000_000), package: packageRow({ package_code: "PKG-DONE-2" }) }),
      ]
    }
    if (String(path) === "/api/v1/dispatch/profiles/me") return null
    throw new Error("unexpected path " + String(path))
  })

  render(<MyOffersPage />)
  await waitFor(() => {
    expect(screen.getByText("待响应 2 条 / 共 5 条")).toBeInTheDocument()
  })
  // 分组标题用字符串精确匹配（正则会与「临期待响应」子串互撞）
  expect(screen.getByText("临期待响应 1 条")).toBeInTheDocument()
  expect(screen.getByText("待响应 1 条")).toBeInTheDocument()
  expect(screen.getByText("已超时 1 条")).toBeInTheDocument()
  expect(screen.getByText("已处理 2 条")).toBeInTheDocument()
  // 归属断言：每组恰含自己的包代号
  expect(within(screen.getByLabelText("临期待响应")).getByText("PKG-SOON")).toBeInTheDocument()
  expect(within(screen.getByLabelText("待响应")).getByText("PKG-NORMAL")).toBeInTheDocument()
  expect(within(screen.getByLabelText("已超时")).getByText("PKG-EXPIRED")).toBeInTheDocument()
  expect(within(screen.getByLabelText("已处理")).getByText("PKG-DONE-1")).toBeInTheDocument()
  expect(within(screen.getByLabelText("已处理")).getByText("PKG-DONE-2")).toBeInTheDocument()
})
