// @vitest-environment jsdom
// goal-d2：售前录入卡桌面入口——读取回显、保存载荷、错误透传。
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({
  useAuth: () => ({ apiRequest: mocks.apiRequest }),
}))

import { PresurveyIntakeCard } from "../../src/renderer/src/guidance/PresurveyIntakeCard"

function intakeFixture(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    project_id: "project-1",
    industry: "零售连锁", scale: "门店 150 家", region: "华东（苏州）",
    interview_mode: "remote", interviewee_roles: ["运营负责人", "IT 负责人"],
    customer_vision: "数据驱动门店网络", phase_objective: "完成诊断", notes: "",
    updated_at: "2026-10-31T00:00:00+00:00",
    ...overrides,
  }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("打开时读取服务端录入卡并回显", async () => {
  mocks.apiRequest.mockResolvedValue(intakeFixture())
  render(<PresurveyIntakeCard projectId="project-1" onClose={() => {}} />)

  await waitFor(() => expect(screen.getByLabelText(/行业/)).toHaveValue("零售连锁"))
  expect(screen.getByLabelText(/访谈方式/)).toHaveValue("remote")
  expect(screen.getByLabelText(/访谈对象角色/)).toHaveValue("运营负责人\nIT 负责人")
})

it("保存时按契约字段 PUT，成功后显示已保存", async () => {
  mocks.apiRequest.mockImplementation(async (_path: string, options?: { method?: string }) => {
    if (options?.method === "PUT") return intakeFixture({ industry: "餐饮连锁" })
    return intakeFixture()
  })
  render(<PresurveyIntakeCard projectId="project-1" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByLabelText(/行业/)).toHaveValue("零售连锁"))

  fireEvent.change(screen.getByLabelText(/行业/), { target: { value: "餐饮连锁" } })
  fireEvent.click(screen.getByRole("button", { name: "保存录入卡" }))

  await waitFor(() => expect(screen.getByText("已保存")).toBeInTheDocument())
  const [path, call] = mocks.apiRequest.mock.calls.find(([, options]) => (options as { method?: string })?.method === "PUT")!
  expect(path).toBe("/api/v1/projects/project-1/presurvey-intake")
  const body = call.body as Record<string, unknown>
  expect(body).toMatchObject({ industry: "餐饮连锁", interview_mode: "remote", interviewee_roles: ["运营负责人", "IT 负责人"] })
  expect(Object.keys(body).sort()).toEqual(["customer_vision", "industry", "interview_mode", "interviewee_roles", "notes", "phase_objective", "region", "scale"])
})

it("服务端校验错误原样透传（如未知字段/超长）", async () => {
  mocks.apiRequest.mockImplementation(async (_path: string, options?: { method?: string }) => {
    if (options?.method === "PUT") throw new Error("industry 必须为 80 字以内的文本。")
    return intakeFixture()
  })
  render(<PresurveyIntakeCard projectId="project-1" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByLabelText(/行业/)).toHaveValue("零售连锁"))

  fireEvent.click(screen.getByRole("button", { name: "保存录入卡" }))
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("industry 必须为 80 字以内的文本。"))
})

it("本地行数超限直接报错，不发请求", async () => {
  mocks.apiRequest.mockResolvedValue(intakeFixture())
  render(<PresurveyIntakeCard projectId="project-1" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByLabelText(/访谈对象角色/)).toBeInTheDocument())

  fireEvent.change(screen.getByLabelText(/访谈对象角色/), { target: { value: Array.from({ length: 21 }, (_, index) => `角色${index}`).join("\n") } })
  fireEvent.click(screen.getByRole("button", { name: "保存录入卡" }))

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("最多 20 个"))
  expect(mocks.apiRequest.mock.calls.filter(([, options]) => (options as { method?: string })?.method === "PUT")).toHaveLength(0)
})
