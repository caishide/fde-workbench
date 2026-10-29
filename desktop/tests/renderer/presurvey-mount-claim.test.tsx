// @vitest-environment jsdom
// 项目指引审核入口：挂载时认领已上传但尚未确认的预调研源。
//
// 缺陷基线：分析/审核入口此前只在「本次会话内上传」后出现——卡片只认已确认指引，
// 服务端（定时任务/历史会话）跑出的 ready 草稿在界面上没有任何入口，用户永远看不到「待审核」。
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  runTask: vi.fn(),
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({
  useAuth: () => ({ apiRequest: mocks.apiRequest }),
}))
vi.mock("../../src/renderer/src/ai/AIExecutionProvider", () => ({
  useAIExecution: () => ({ runTask: mocks.runTask }),
}))
vi.mock("../../src/renderer/src/guidance/GuidanceReview", () => ({
  GuidanceReview: () => <div data-testid="guidance-review">审核面板</div>,
}))

import { PresurveyUploadAction } from "../../src/renderer/src/guidance/PresurveyUploadAction"

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
    customer_vision: "",
    current_phase_objective: "",
    executive_summary: "",
    failure_code: "",
    failure_message: "",
    source_is_stale: false,
    version: 2,
  }
  for (const field of LIST_FIELDS) base[field] = []
  return { ...base, ...overrides }
}

function fileFixture(): Record<string, unknown> {
  return {
    id: "file-9",
    project_id: "project-1",
    display_name: "预调研表",
    category: "document",
    business_category: "预调研",
    status: "active",
    current_version_id: "ver-9",
    current_version: { id: "ver-9", version_number: 2, status: "available", scan_status: "not_required" },
    created_by: null,
  }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.runTask.mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("挂载认领已上传未确认的预调研源，待审核分析出现审核入口且不自动重跑", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    const target = String(path)
    if (target.includes("/guidance-analyses/")) return analysisFixture()
    if (target.endsWith("/guidance-analyses")) return { items: [analysisFixture()] }
    if (target.includes("/files?business_category=")) return { items: [fileFixture()] }
    return { items: [] }
  })

  render(<PresurveyUploadAction projectId="project-1" hasGuidance={false} onConfirmed={() => {}} />)

  // 认领的版本 autoStart=false：不触发 runTask（不自动新建分析），只展示入口
  const entry = await screen.findByRole("button", { name: "查看预调研分析" }, { timeout: 5000 })
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(mocks.runTask).not.toHaveBeenCalled()

  fireEvent.click(entry)
  await waitFor(() => expect(screen.getByTestId("guidance-review")).toBeInTheDocument())
})

it("没有已上传的预调研源时不显示审核入口，只保留上传按钮", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    const target = String(path)
    if (target.includes("/files?business_category=")) return { items: [] }
    return { items: [] }
  })

  render(<PresurveyUploadAction projectId="project-1" hasGuidance={false} onConfirmed={() => {}} />)

  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(screen.queryByRole("button", { name: "查看预调研分析" })).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "上传预调研表" })).toBeInTheDocument()
})

it("已有已确认指引时不再认领（不发文件请求）", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    const target = String(path)
    if (target.includes("/files?business_category=")) return { items: [fileFixture()] }
    return { items: [] }
  })

  render(<PresurveyUploadAction projectId="project-1" hasGuidance={true} onConfirmed={() => {}} />)

  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(mocks.apiRequest).not.toHaveBeenCalled()
  expect(screen.queryByRole("button", { name: "查看预调研分析" })).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "上传新版本" })).toBeInTheDocument()
})
