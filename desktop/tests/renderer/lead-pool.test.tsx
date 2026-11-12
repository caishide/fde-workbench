// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  confirm: vi.fn(),
  user: { id: "actor-1", role: "fde_engineer" as string },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))
vi.mock("../../src/renderer/src/common/ConfirmProvider", () => ({
  useConfirm: () => mocks.confirm,
}))

import { ApiClientError } from "../../src/renderer/src/api/client"
import {
  describeSelfClaimSignals,
  formatClaimWindow,
  isLeadClaimView,
  isLeadPoolEntry,
  LeadPoolPage,
} from "../../src/renderer/src/leads/LeadPoolPage"

function leadRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "lead-1",
    status: "report_ready",
    source_type: "direct",
    channel_ref: null,
    region_name: "浙江省",
    industry: "制造与工业",
    scale: "100–499人",
    pain_summary: "报价要问老工程师，一单两三天",
    report_ready: true,
    created_at: "2026-11-11T00:00:00+00:00",
    claim_window_expires_at: "2027-02-09T00:00:00+00:00",
    attribution_tier: null,
    ...overrides,
  }
}

function claimRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "claim-1",
    session_id: "lead-1",
    claimant_username: "diag.fde_engineer.ab12",
    claimant_kind: "r4_partner",
    region_name: "浙江省",
    status: "pending",
    attribution_tier: null,
    fee_basis: null,
    self_claim: false,
    self_claim_signals: [],
    ledger_line_no: null,
    ledger_written_at: null,
    decided_at: null,
    decision_note: null,
    note: "想跟这个单子",
    created_at: "2026-11-12T00:00:00+00:00",
    lead: leadRow(),
    ...overrides,
  }
}

function poolResponse(rows: unknown[]) {
  return (path: string) => {
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve(rows)
    if (path.startsWith("/api/v1/diagnostics/leads/claims?")) return Promise.resolve([])
    throw new Error(`unexpected GET ${path}`)
  }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.confirm.mockReset()
  mocks.confirm.mockResolvedValue(true)
  mocks.user = { id: "actor-1", role: "fde_engineer" }
})

afterEach(() => {
  cleanup()
})

it("isLeadPoolEntry：形状守卫放行/拒绝", () => {
  expect(isLeadPoolEntry(leadRow())).toBe(true)
  expect(isLeadPoolEntry({ id: 42 })).toBe(false)
  expect(isLeadPoolEntry(null)).toBe(false)
})

it("isLeadClaimView：形状守卫放行/拒绝", () => {
  expect(isLeadClaimView(claimRow())).toBe(true)
  expect(isLeadClaimView({ id: "x" })).toBe(false)
})

it("formatClaimWindow：过期/剩余天数/未知三态", () => {
  const now = new Date("2026-11-12T00:00:00Z")
  expect(formatClaimWindow("2026-11-10T00:00:00Z", now)).toBe("窗口已过期")
  expect(formatClaimWindow("2026-11-20T00:00:00Z", now)).toBe("剩 8 天")
  expect(formatClaimWindow("2026-11-12T06:00:00Z", now)).toBe("不足 1 天")
  expect(formatClaimWindow(null, now)).toBe("窗口未知")
})

it("describeSelfClaimSignals：三信号中文描述，空集为空串", () => {
  expect(describeSelfClaimSignals(["ip", "contact"])).toBe("同一 IP／同一联系方式")
  expect(describeSelfClaimSignals([])).toBe("")
})

it("渲染线索池卡片：代号化字段与认领窗口倒计时", async () => {
  mocks.apiRequest.mockImplementation(poolResponse([leadRow()]))
  render(<LeadPoolPage />)

  expect(await screen.findByText("制造与工业")).toBeVisible()
  expect(screen.getByText("浙江省")).toBeVisible()
  expect(screen.getByText(/剩 \d+ 天/)).toBeVisible()
  // 池子不暴露联系方式字段
  expect(document.body.textContent).not.toContain("13800000042")
})

it("R4 未填区域时提交认领被客户端拦下（不打服务端）", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation(poolResponse([leadRow()]))
  render(<LeadPoolPage />)

  await screen.findByText("制造与工业")
  await user.selectOptions(screen.getByLabelText("认领身份"), "r4_partner")
  await user.click(screen.getByRole("button", { name: "认领" }))
  await user.click(screen.getByRole("button", { name: "提交认领申请" }))

  expect(await screen.findByText("区域合作商认领必须填写所在区域。")).toBeVisible()
  const postCalls = mocks.apiRequest.mock.calls.filter(([path]) =>
    String(path).includes("/claims") && !String(path).startsWith("/api/v1/diagnostics/leads/claims?"),
  )
  expect(postCalls).toHaveLength(0)
})

it("认领提交成功：POST 载荷带身份/区域，就地回执并刷新", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
    if (path === "/api/v1/diagnostics/leads/lead-1/claims" && options?.method === "POST") {
      expect(options.body).toMatchObject({
        claimant_kind: "r4_partner",
        region_name: "浙江省",
      })
      return Promise.resolve(claimRow())
    }
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve([leadRow()])
    if (path.startsWith("/api/v1/diagnostics/leads/claims?")) return Promise.resolve([])
    throw new Error(`unexpected ${path}`)
  })
  render(<LeadPoolPage />)

  await screen.findByText("制造与工业")
  await user.selectOptions(screen.getByLabelText("认领身份"), "r4_partner")
  await user.type(screen.getByLabelText(/所在区域/), "浙江省")
  await user.click(screen.getByRole("button", { name: "认领" }))
  await user.click(screen.getByRole("button", { name: "提交认领申请" }))

  expect(await screen.findByText("认领申请已提交（待平台接受后生效）。")).toBeVisible()
  expect(await screen.findByText("认领申请已提交（待平台接受）")).toBeVisible()
})

it("409 一线一线等错误在弹层内就地呈现", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/api/v1/diagnostics/leads/lead-1/claims" && options?.method === "POST") {
      return Promise.reject(
        new ApiClientError(
          { code: "claim_in_flight", message: "该线索有一条待裁定的认领申请。" },
          409,
        ),
      )
    }
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve([leadRow()])
    if (path.startsWith("/api/v1/diagnostics/leads/claims?")) return Promise.resolve([])
    throw new Error(`unexpected ${path}`)
  })
  render(<LeadPoolPage />)

  await screen.findByText("制造与工业")
  await user.click(screen.getByRole("button", { name: "认领" }))
  await user.click(screen.getByRole("button", { name: "提交认领申请" }))

  expect(await screen.findByText("该线索有一条待裁定的认领申请。")).toBeVisible()
})

it("诊断面未启用（404）⇒ 引导文案而非裸错误", async () => {
  mocks.apiRequest.mockRejectedValue(
    new ApiClientError({ code: "not_found", message: "资源不存在。" }, 404),
  )
  render(<LeadPoolPage />)

  expect(
    await screen.findByText(/诊断面未启用（部署闸默认关闭）/),
  ).toBeVisible()
})

it("admin：裁定队列展示认领人/自认领信号，接受走 POST accept", async () => {
  const user = userEvent.setup()
  mocks.user = { id: "actor-9", role: "admin" }
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
    if (
      path === "/api/v1/diagnostics/leads/claims/claim-1/accept" &&
      options?.method === "POST"
    ) {
      expect(options.body).toMatchObject({ decision_note: "区域吻合，接受" })
      return Promise.resolve(
        claimRow({ status: "accepted", attribution_tier: "B", fee_basis: "pending_pricing" }),
      )
    }
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve([])
    if (path === "/api/v1/diagnostics/leads/channel-links") return Promise.resolve([])
    if (path.includes("/claims?status=")) {
      return Promise.resolve([
        claimRow({
          self_claim: true,
          self_claim_signals: ["ip", "subject"],
        }),
      ])
    }
    throw new Error(`unexpected ${path}`)
  })
  render(<LeadPoolPage />)

  expect(await screen.findByText("认领人 diag.fde_engineer.ab12")).toBeVisible()
  expect(screen.getByText(/自认领信号：同一 IP／同一主体/)).toBeVisible()
  // 认领单状态徽标（role=status；「待平台接受」也出现在状态下拉的 option 里，
  // 所以按 role 而不是全文匹配）。
  expect(
    screen
      .getAllByRole("status")
      .some((element) => element.textContent === "待平台接受"),
  ).toBe(true)

  await user.type(screen.getByLabelText(/裁定备注/), "区域吻合，接受")
  await user.click(screen.getByRole("button", { name: "接受" }))

  await waitFor(() => {
    const acceptCalls = mocks.apiRequest.mock.calls.filter(
      ([path]) => String(path) === "/api/v1/diagnostics/leads/claims/claim-1/accept",
    )
    expect(acceptCalls).toHaveLength(1)
  })
})

it("非 admin：看不到裁定按钮，只看自己的申请列表", async () => {
  mocks.apiRequest.mockImplementation(poolResponse([]))
  render(<LeadPoolPage />)

  await waitFor(() => expect(screen.getByText("我的认领申请")).toBeVisible())
  expect(screen.queryByText("认领裁定")).toBeNull()
  expect(screen.queryByRole("button", { name: "接受" })).toBeNull()
})

it("admin 驳回走确认弹窗后 POST reject", async () => {
  const user = userEvent.setup()
  mocks.user = { id: "actor-9", role: "admin" }
  mocks.apiRequest.mockImplementation((path: string, options?: { method?: string }) => {
    if (path === "/api/v1/diagnostics/leads/claims/claim-1/reject" && options?.method === "POST") {
      return Promise.resolve(claimRow({ status: "rejected" }))
    }
    if (path.startsWith("/api/v1/diagnostics/leads?")) return Promise.resolve([])
    if (path === "/api/v1/diagnostics/leads/channel-links") return Promise.resolve([])
    if (path.includes("/claims?status=")) return Promise.resolve([claimRow()])
    throw new Error(`unexpected ${path}`)
  })
  render(<LeadPoolPage />)

  await screen.findByText("待平台接受")
  await user.click(screen.getByRole("button", { name: "驳回" }))
  await waitFor(() => expect(mocks.confirm).toHaveBeenCalled())
  expect(
    await screen.findByText("已驳回：线索释放，仍可被他人认领。"),
  ).toBeVisible()
})
