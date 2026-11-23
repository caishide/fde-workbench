// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const auth = vi.hoisted(() => ({ apiRequest: vi.fn(), user: { id: "actor", role: "admin" } }))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => auth }))

import { ApiClientError } from "../../src/renderer/src/api/client"
import { CommercialBoard } from "../../src/renderer/src/projects/CommercialBoard"

const PROJECT = "project-id"
const ADMIN_PATH = `/api/v1/admin/dispatch/projects/${PROJECT}/settlements`
const RECEIPT_PATH = `/api/v1/projects/${PROJECT}/payments/G8`
const ROW = {
  id: "settlement-1", package_code: "PKG-CODE", settlement_key: "G4", status: "draft",
  base_amount: "10000.00", allocation_snapshot: "a".repeat(64) as string | null,
  version_no: null as number | null, requires_versioned_allocation: true,
  delivery_user_id: "delivery-id", paid_at: null as string | null, allocations: [],
  input_invoice_required: false, input_invoice_recorded: false,
}

let settlement: typeof ROW | null
let received: number | null
let receiptFailure: boolean
let allocationConflict: boolean

beforeEach(() => {
  auth.user.role = "admin"
  settlement = null
  received = null
  receiptFailure = false
  allocationConflict = false
  auth.apiRequest.mockReset()
  auth.apiRequest.mockImplementation(async (path: string, options: { method: string }) => {
    if (path.endsWith("/quotes")) return { quotes: [] }
    if (path.endsWith("/contracts")) return { contracts: [] }
    if (path.endsWith("/payments")) return {
      summary: { received: 0, receivable: 10000, outstanding: 10000, overdue: 0, dunning_counts: {} },
      payments: [{ id: "G8-payment", milestone_key: "G8", amount: 10000, received_amount: received,
        received_at: received === null ? null : "2026-11-23", invoice_no: null, ratio: null }],
    }
    if (path === RECEIPT_PATH && options.method === "POST") {
      if (receiptFailure) throw new Error("空缺继承须校验当前账号密码。")
      received = 10000
      return {}
    }
    if (path === `${ADMIN_PATH}/${ROW.id}/input-invoice` && settlement) {
      settlement = { ...settlement, input_invoice_recorded: true }
      return { changed: true }
    }
    if (path === ADMIN_PATH) return { settlements: settlement ? [settlement] : [] }
    if (path === `${ADMIN_PATH}/${ROW.id}/allocate`) {
      if (allocationConflict) throw new ApiClientError({ code: "allocation_snapshot_conflict", message: "结算已变更。" }, 409)
      settlement = { ...(settlement ?? ROW), version_no: 100 }
      return { status: "draft" }
    }
    if (path === `${ADMIN_PATH}/${ROW.id}/payable`) {
      settlement = { ...ROW, version_no: 100, status: "payable" }
      return { status: "payable" }
    }
    if (path === `${ADMIN_PATH}/${ROW.id}/paid`) {
      settlement = { ...ROW, version_no: 100, status: "paid", paid_at: "2026-11-23T09:00:00Z" }
      return { status: "paid" }
    }
    return {}
  })
})

afterEach(cleanup)

it("keeps the settlement surface and inheritance password hidden from a project lead", async () => {
  auth.user.role = "project_lead"
  render(<CommercialBoard projectId={PROJECT} canManage />)
  expect(await screen.findByRole("button", { name: "回填" })).toBeVisible()
  expect(screen.queryByRole("region", { name: "管理员结算记账" })).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/继承五席空缺时的当前密码/)).not.toBeInTheDocument()
  expect(auth.apiRequest.mock.calls.some(([path]) => path === ADMIN_PATH)).toBe(false)
})

it("uses the selected package and settlement, requiring fresh consent for the five-seat definition", async () => {
  settlement = { ...ROW }
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  expect(await screen.findByText(/此处操作仅更新内部账目/)).toBeVisible()
  await user.click(await screen.findByRole("button", { name: "五席分配" }))
  expect(screen.getByRole("button", { name: "确认保存五席分配" })).toBeDisabled()
  await user.type(screen.getByLabelText("市县收款人账号 ID"), "county-user")
  expect(screen.getByText(/省级席本期固定为无省级服务商/)).toBeVisible()
  await user.type(screen.getByLabelText("当前账号密码"), "first-password")
  await user.click(screen.getByRole("button", { name: "取消结算操作" }))
  expect(auth.apiRequest.mock.calls.some(([path]) => path.endsWith("/allocate"))).toBe(false)
  await user.click(screen.getByRole("button", { name: "五席分配" }))
  expect(screen.getByLabelText("当前账号密码")).toHaveValue("")
  await user.type(screen.getByLabelText("市县收款人账号 ID"), "county-user")
  expect(screen.getByText(/省级席本期固定为无省级服务商/)).toBeVisible()
  await user.type(screen.getByLabelText("当前账号密码"), "confirmed-password")
  await user.click(screen.getByRole("button", { name: "确认保存五席分配" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(`${ADMIN_PATH}/${ROW.id}/allocate`, {
    method: "POST", body: {
      confirm_password: "confirmed-password", expected_allocation_snapshot: ROW.allocation_snapshot,
      seat_payees: { county: "county-user" }, vacant_reasons: { province: "no_province_partner" },
    },
  })
  expect(await screen.findByText(/待计提 · v100/)).toBeVisible()
  expect(screen.queryByLabelText("当前账号密码")).not.toBeInTheDocument()
})

it("reloads the changed amount after a conflict and requires a new allocation confirmation", async () => {
  settlement = { ...ROW }
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  const allocatePath = `${ADMIN_PATH}/${ROW.id}/allocate`
  await user.click(await screen.findByRole("button", { name: "五席分配" }))
  expect(screen.getByText(/保存五席分配.*¥10000\.00/)).toBeVisible()
  await user.type(screen.getByLabelText("市县收款人账号 ID"), "county-user")
  await user.type(screen.getByLabelText("当前账号密码"), "original-password")
  settlement = { ...ROW, base_amount: "12000.00", allocation_snapshot: "b".repeat(64) }
  allocationConflict = true

  await user.click(screen.getByRole("button", { name: "确认保存五席分配" }))
  expect(await screen.findByText(/请核对最新实收基数后重新确认/)).toBeVisible()
  expect(await screen.findByText("¥12000.00")).toBeVisible()
  expect(screen.queryByRole("button", { name: "确认保存五席分配" })).not.toBeInTheDocument()
  expect(auth.apiRequest.mock.calls.filter(([path]) => path === allocatePath)).toEqual([
    [allocatePath, { method: "POST", body: expect.objectContaining({ expected_allocation_snapshot: ROW.allocation_snapshot }) }],
  ])

  allocationConflict = false
  await user.click(screen.getByRole("button", { name: "五席分配" }))
  expect(screen.getByText(/保存五席分配.*¥12000\.00/)).toBeVisible()
  expect(screen.getByLabelText("当前账号密码")).toHaveValue("")
  expect(screen.getByRole("button", { name: "确认保存五席分配" })).toBeDisabled()
  await user.type(screen.getByLabelText("市县收款人账号 ID"), "county-user")
  await user.type(screen.getByLabelText("当前账号密码"), "new-password")
  await user.click(screen.getByRole("button", { name: "确认保存五席分配" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(allocatePath, {
    method: "POST", body: expect.objectContaining({ expected_allocation_snapshot: "b".repeat(64) }),
  })
  expect(await screen.findByText(/待计提 · v100/)).toBeVisible()
})

it("disables allocation if the response has no confirmation snapshot", async () => {
  settlement = { ...ROW, allocation_snapshot: null }
  render(<CommercialBoard projectId={PROJECT} canManage />)
  expect(await screen.findByRole("button", { name: "五席分配" })).toBeDisabled()
})

it("transitions a versioned accrued row and books an external payout with a proof pointer", async () => {
  settlement = { ...ROW, status: "accrued", version_no: 100 }
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  await user.click(await screen.findByRole("button", { name: "转应付" }))
  await user.type(screen.getByLabelText("当前账号密码"), "payable-password")
  await user.click(screen.getByRole("button", { name: "确认转应付" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(`${ADMIN_PATH}/${ROW.id}/payable`, {
    method: "POST", body: { confirm_password: "payable-password" },
  })
  await user.click(await screen.findByRole("button", { name: "登记线下付款" }))
  expect(screen.getByLabelText("当前账号密码")).toHaveValue("")
  await user.type(screen.getByLabelText("当前账号密码"), "paid-password")
  expect(screen.getByRole("button", { name: "确认登记线下付款" })).toBeDisabled()
  await user.type(screen.getByLabelText("付款凭证指针"), "fdeops://m1-test/payout")
  await user.click(screen.getByRole("button", { name: "确认登记线下付款" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(`${ADMIN_PATH}/${ROW.id}/paid`, {
    method: "POST", body: { confirm_password: "paid-password", paid_proof_source_uri: "fdeops://m1-test/payout" },
  })
  expect(await screen.findByText(/已记账 · v100/)).toBeVisible()
})

it("disables the payable action for unversioned pilot settlements", async () => {
  settlement = { ...ROW, status: "accrued" }
  render(<CommercialBoard projectId={PROJECT} canManage />)
  expect(await screen.findByText("缺完整的版本化五席明细")).toBeVisible()
  expect(screen.queryByRole("button", { name: "转应付" })).not.toBeInTheDocument()
})

it("records a legacy province input invoice before exposing the payable action", async () => {
  settlement = { ...ROW, status: "accrued", version_no: 100, input_invoice_required: true }
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  await user.click(await screen.findByRole("button", { name: "登记省级进项票" }))
  expect(screen.queryByRole("button", { name: "转应付" })).not.toBeInTheDocument()
  await user.type(screen.getByLabelText("当前账号密码"), "current-password")
  await user.type(screen.getByLabelText("进项票凭证指针"), "fdeops://m1-test/invoice")
  expect(screen.getByRole("button", { name: "确认登记省级进项票" })).toBeDisabled()
  await user.type(screen.getByLabelText("进项票 SHA-256 指纹"), "A".repeat(64))
  await user.click(screen.getByRole("button", { name: "确认登记省级进项票" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(`${ADMIN_PATH}/${ROW.id}/input-invoice`, {
    method: "POST", body: { confirm_password: "current-password", source_uri: "fdeops://m1-test/invoice", content_hash: "a".repeat(64) },
  })
  expect(await screen.findByRole("button", { name: "转应付" })).toBeVisible()
})

it("records a missing sales invoice on an already received payment without replaying the receipt", async () => {
  received = 10000
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  await user.type(await screen.findByLabelText("销项票号"), "SYNTHETIC-OUT")
  await user.click(screen.getByRole("button", { name: "保存销项票号" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(RECEIPT_PATH, {
    method: "POST", retryAfterAuthRefresh: true, body: { invoice_no: "SYNTHETIC-OUT" },
  })
})

it("forwards the optional G8 password only on receipt and clears it on cancel, failure or success", async () => {
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT} canManage />)
  const password = await screen.findByLabelText(/继承五席空缺时的当前密码/)
  await user.type(password, "cancelled-password")
  await user.type(screen.getByPlaceholderText("实收金额"), "10000")
  await user.click(screen.getByRole("button", { name: "取消尾款回填" }))
  expect(password).toHaveValue("")
  expect(screen.getByPlaceholderText("实收金额")).toHaveValue("")
  expect(auth.apiRequest.mock.calls.some(([path]) => path === RECEIPT_PATH)).toBe(false)
  receiptFailure = true
  await user.type(screen.getByPlaceholderText("实收金额"), "10000")
  await user.click(screen.getByRole("button", { name: "回填" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(RECEIPT_PATH, { method: "POST", body: { received_amount: 10000 } })
  expect(await screen.findByText("空缺继承须校验当前账号密码。")).toBeVisible()
  receiptFailure = false
  await user.type(password, "current-password")
  await user.click(screen.getByRole("button", { name: "回填" }))
  expect(auth.apiRequest).toHaveBeenCalledWith(RECEIPT_PATH, {
    method: "POST", body: { received_amount: 10000, confirm_password: "current-password" },
  })
  await waitFor(() => expect(password).not.toBeInTheDocument())
  expect(auth.apiRequest.mock.calls.filter(([path]) => path === ADMIN_PATH).length).toBeGreaterThanOrEqual(2)
})
