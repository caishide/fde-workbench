// @vitest-environment jsdom
// 项目指引审核：只读草稿模式也必须能直接确认。
//
// 缺陷基线：确认按钮只渲染在编辑模式底部——用户点「查看预调研分析」进的是只读
// 预览（没有编辑），过目后想确认得自己发现右上角「编辑」再进编辑模式才能确认，
// 「过目即确认」的主路径被堵死。
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

import { GuidanceReview } from "../../src/renderer/src/guidance/GuidanceReview"

const LIST_FIELDS = [
  "key_business_problems",
  "priority_departments",
  "priority_roles",
  "priority_processes",
  "success_criteria",
  "out_of_scope",
  "data_security_redlines",
  "systems_and_deployment_constraints",
  "assumptions",
  "open_questions",
  "next_actions",
] as const

function analysisFixture(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    id: "analysis-9",
    project_id: "project-1",
    version_number: 4,
    source_file_id: "file-9",
    source_file_version_id: "ver-9",
    source_filename: "预调研表.docx",
    status: "draft",
    analysis_state: "ready",
    customer_vision: "成为北美家庭理疗设备首选供应商",
    current_phase_objective: "完成试点期获客管道搭建",
    executive_summary: "围绕发现-触达-激活三段推进。",
    failure_code: "",
    failure_message: "",
    source_is_stale: false,
    version: 2,
  }
  for (const field of LIST_FIELDS) {
    base[field] = [{ text: "示例条目", classification: "ai_synthesized", source_refs: ["kimi-file:1"], confirmed: false }]
  }
  return { ...base, ...overrides }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("只读草稿模式直接显示确认按钮，点击按原内容 PATCH 后 confirm", async () => {
  const patched = analysisFixture({ version: 3 })
  const confirmed = analysisFixture({ version: 4, status: "confirmed" })
  mocks.apiRequest.mockImplementation(async (_path: string, options?: { method?: string }) => {
    const method = options?.method ?? "GET"
    if (method === "PATCH") return patched
    if (method === "POST") return confirmed
    return patched
  })

  render(
    <GuidanceReview
      projectId="project-1"
      initial={analysisFixture() as never}
      canManage
      onClose={() => {}}
      onSaved={() => {}}
    />,
  )

  const confirmButton = await screen.findByRole("button", { name: "确认并用于项目指引" })
  fireEvent.click(confirmButton)

  await waitFor(() => expect(mocks.apiRequest).toHaveBeenCalledTimes(2))
  const [patchPath, patchCall] = mocks.apiRequest.mock.calls[0]
  const [confirmPath, confirmCall] = mocks.apiRequest.mock.calls[1]
  expect(patchCall.method).toBe("PATCH")
  expect(confirmCall.method).toBe("POST")
  expect(confirmPath).toContain("/confirm")
})

it("已确认的指引在只读模式不再显示确认按钮", () => {
  render(
    <GuidanceReview
      projectId="project-1"
      initial={analysisFixture({ status: "confirmed" }) as never}
      canManage
      onClose={() => {}}
      onSaved={() => {}}
    />,
  )

  expect(screen.queryByRole("button", { name: "确认并用于项目指引" })).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "关闭" })).toBeInTheDocument()
})

it("编辑模式仍保留取消/保存修改/确认三个按钮", () => {
  render(
    <GuidanceReview
      projectId="project-1"
      initial={analysisFixture() as never}
      canManage
      initialEditing
      onClose={() => {}}
      onSaved={() => {}}
    />,
  )

  expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "保存修改" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "确认并用于项目指引" })).toBeInTheDocument()
})

it("cancelled 终态显示「分析已取消」，不再伪装后台继续（台账五.1）", () => {
  render(
    <GuidanceReview
      projectId="project-1"
      initial={analysisFixture({ analysis_state: "cancelled" }) as never}
      canManage
      onClose={() => {}}
      onSaved={() => {}}
    />,
  )

  expect(screen.getByText("分析已取消")).toBeInTheDocument()
  expect(screen.queryByText("预调研分析正在后台继续")).not.toBeInTheDocument()
})

it("PATCH 成功后 confirm 失败：本地版本立即推进，重试不再携带陈旧 version（台账七.1）", async () => {
  const patched = analysisFixture({ version: 3 })
  const repatched = analysisFixture({ version: 4 })
  const confirmed = analysisFixture({ version: 5, status: "confirmed" })
  let callCount = 0
  mocks.apiRequest.mockImplementation(async (_path: string, options?: { method?: string }) => {
    const method = options?.method ?? "GET"
    if (method === "PATCH") return callCount++ === 0 ? patched : repatched
    if (method === "POST") throw new Error("网络中断")
    return patched
  })

  render(
    <GuidanceReview
      projectId="project-1"
      initial={analysisFixture() as never}
      canManage
      onClose={() => {}}
      onSaved={() => {}}
    />,
  )

  fireEvent.click(await screen.findByRole("button", { name: "确认并用于项目指引" }))
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("项目指引保存失败"))
  // 第一次 PATCH（version 2）已成功，本地基线必须已是 v3——重试不得再发 v2。
  fireEvent.click(screen.getByRole("button", { name: "确认并用于项目指引" }))
  await waitFor(() => expect(mocks.apiRequest).toHaveBeenCalledTimes(4))
  const retryPatchBody = mocks.apiRequest.mock.calls[2][1].body as { version: number }
  expect(retryPatchBody.version).toBe(3)
  const retryConfirmBody = mocks.apiRequest.mock.calls[3][1].body as { version: number }
  expect(retryConfirmBody.version).toBe(4)
  // 第三轮：confirm 成功收口。
  mocks.apiRequest.mockImplementation(async (_path: string, options?: { method?: string }) => {
    const method = options?.method ?? "GET"
    if (method === "PATCH") return analysisFixture({ version: 5 })
    if (method === "POST") return confirmed
    return analysisFixture({ version: 5 })
  })
  fireEvent.click(screen.getByRole("button", { name: "确认并用于项目指引" }))
  await waitFor(() => expect(mocks.apiRequest.mock.calls.length).toBeGreaterThanOrEqual(6))
})
