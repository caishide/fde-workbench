// @vitest-environment jsdom
// WP31/J7：预调研分析的轮询失败必须让用户看见。
//
// 缺陷基线：PresurveyAnalysisAction 的轮询 catch{} 静默吞错——网络持续失败时
// 界面永远停在「分析中」，用户既看不到提示也没法判断是否还在跑。
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
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
  GuidanceReview: () => null,
}))

import { PresurveyAnalysisAction } from "../../src/renderer/src/guidance/PresurveyAnalysisAction"

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
    id: "analysis-1",
    project_id: "project-1",
    version_number: 1,
    source_file_id: "file-1",
    source_file_version_id: "file-1",
    source_filename: "预调研表.docx",
    status: "draft",
    analysis_state: "analyzing",
    customer_vision: "",
    current_phase_objective: "",
    executive_summary: "",
    failure_code: "",
    failure_message: "",
    source_is_stale: false,
    version: 1,
  }
  for (const field of LIST_FIELDS) base[field] = []
  return { ...base, ...overrides }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.runTask.mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("J7: shows a visible hint when polling the analysis keeps failing", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    // 列表接口返回一条「分析中」的记录；轮询（带 id 的路径）一律失败
    if (String(path).endsWith("/guidance-analyses")) {
      return { items: [analysisFixture()] }
    }
    if (String(path).includes("/guidance-analyses/")) {
      throw new Error("网关不可达")
    }
    return { items: [] }
  })

  render(
    <PresurveyAnalysisAction
      projectId="project-1"
      fileVersionId="file-1"
      canManage
    />,
  )

  // 轮询失败后必须出现用户可见提示（role=status 的可访问元素）
  const hint = await screen.findByRole("status", {}, { timeout: 5000 })
  expect(hint).toHaveTextContent("暂时读不到分析进度")
})
