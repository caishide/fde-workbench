// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import { cleanup, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({ apiRequest: vi.fn(), user: { role: "admin" } }))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))

import { ApiClientError } from "../../src/renderer/src/api/client"
import { CapabilityProfilesPage } from "../../src/renderer/src/dispatch/CapabilityProfilesPage"

const profile = {
  user_id: "supply-a",
  username: "supply-a",
  display_name: "交付方 A",
  level: "L2",
  status: "active",
  is_active: false,
  can_enable: true,
  scores: { biz_cognition: 2, scenario_eng: 3, ai_tech: 2, delivery_assure: 2 },
  industry_tags: [],
  in_hand: 0,
  capacity_cap: 5,
}
const listUrl = "/api/v1/dispatch/profiles"
const registerUrl = "/api/v1/admin/dispatch/profiles"
const enableUrl = `${registerUrl}/${profile.user_id}/enable`

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.user = { role: "admin" }
})
afterEach(cleanup)

it("管理员核对档案并输入密码后才提交启用", async () => {
  mocks.apiRequest.mockResolvedValueOnce([profile]).mockResolvedValueOnce({
    user_id: profile.user_id,
    is_active: true,
    changed: true,
  })
  render(<CapabilityProfilesPage />)
  const enable = await screen.findByRole("button", { name: "启用派单档案：交付方 A" })
  expect(screen.getByText("未启用")).toBeInTheDocument()
  await userEvent.click(enable)
  let dialog = within(screen.getByRole("dialog", { name: "启用派单档案" }))
  expect(dialog.getByText(/交付方 A（supply-a）/)).toBeInTheDocument()
  expect(dialog.getByRole("button", { name: "确认启用" })).toBeDisabled()
  await userEvent.type(dialog.getByLabelText("当前账号密码"), "discard-me")
  await userEvent.click(dialog.getByRole("button", { name: "取消" }))
  expect(mocks.apiRequest.mock.calls).toEqual([[listUrl, { method: "GET" }]])

  await userEvent.click(enable)
  dialog = within(screen.getByRole("dialog", { name: "启用派单档案" }))
  expect(dialog.getByLabelText("当前账号密码")).toHaveValue("")
  await userEvent.type(dialog.getByLabelText("当前账号密码"), "test-current-password")
  await userEvent.click(dialog.getByRole("button", { name: "确认启用" }))
  expect(mocks.apiRequest).toHaveBeenLastCalledWith(enableUrl, {
    method: "POST",
    body: { confirm_password: "test-current-password" },
  })
  expect(await screen.findByRole("status")).toHaveTextContent("已启用派单档案。")
  expect(screen.getByText("已启用")).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: /启用派单档案/ })).not.toBeInTheDocument()
})

it("密码确认失败会清除密码并保持档案未启用", async () => {
  mocks.apiRequest.mockResolvedValueOnce([profile]).mockRejectedValueOnce(
    new ApiClientError({ code: "invalid_password", message: "当前账号密码不正确。" }),
  )
  render(<CapabilityProfilesPage />)
  await userEvent.click(await screen.findByRole("button", { name: /启用派单档案/ }))
  const dialog = within(screen.getByRole("dialog", { name: "启用派单档案" }))
  await userEvent.type(dialog.getByLabelText("当前账号密码"), "wrong-password")
  await userEvent.click(dialog.getByRole("button", { name: "确认启用" }))
  expect(await dialog.findByRole("alert")).toHaveTextContent("当前账号密码不正确。")
  expect(dialog.getByLabelText("当前账号密码")).toHaveValue("")
  expect(screen.getByText("未启用")).toBeInTheDocument()
})

it.each([
  ["project_lead", profile, "未启用"],
  ["admin", { ...profile, can_enable: false }, "未启用"],
  ["admin", { ...profile, is_active: undefined, can_enable: undefined }, "未知"],
])("%s 未获得启用能力时仅显示档案状态", async (role, row, label) => {
  mocks.user = { role }
  mocks.apiRequest.mockResolvedValueOnce([row])
  render(<CapabilityProfilesPage />)
  expect(await screen.findByText(label)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: /启用派单档案/ })).not.toBeInTheDocument()
  if (role === "project_lead") {
    expect(screen.queryByRole("button", { name: "登记派单档案" })).not.toBeInTheDocument()
  }
})

it("管理员登记档案后刷新列表并显示仍未启用", async () => {
  mocks.apiRequest
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce({ user_id: profile.user_id, is_active: false, changed: true })
    .mockResolvedValueOnce([{ ...profile, status: "pending", can_enable: false }])
  render(<CapabilityProfilesPage />)
  await userEvent.click(screen.getByRole("button", { name: "登记派单档案" }))
  const dialog = within(screen.getByRole("dialog", { name: "登记派单档案" }))
  const submit = dialog.getByRole("button", { name: "确认登记" })
  await userEvent.type(dialog.getByLabelText("交付者账号 ID"), profile.user_id)
  await userEvent.type(dialog.getByLabelText("常驻城市（选填）"), "苏州")
  expect(submit).toBeDisabled()
  await userEvent.type(dialog.getByLabelText("当前账号密码"), "test-current-password")
  await userEvent.click(submit)
  expect(mocks.apiRequest.mock.calls).toEqual([
    [listUrl, { method: "GET" }],
    [registerUrl, {
      method: "POST",
      body: { user_id: profile.user_id, home_city: "苏州", confirm_password: "test-current-password" },
    }],
    [listUrl, { method: "GET" }],
  ])
  expect(await screen.findByRole("status")).toHaveTextContent("已登记派单档案。")
  expect(await screen.findByText("pending")).toBeInTheDocument()
  expect(screen.getByText("未启用")).toBeInTheDocument()
})
