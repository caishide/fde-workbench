// @vitest-environment jsdom
// 验收场景矩阵（docs/验收场景矩阵-G3.md）链 1 的用例落地：
// 分析中→ready 自动开审（1.2）、失败态可见（1.3）、cancelled/进行中展示（1.4）、
// confirmed 卡片展示与旧版重分析提示（1.6）。上传/认领（1.1）与只读确认（1.5）
// 分别由 presurvey-mount-claim / guidance-review-confirm 覆盖。
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

import { GuidanceReview } from "../../src/renderer/src/guidance/GuidanceReview"
import { PresurveyAnalysisAction } from "../../src/renderer/src/guidance/PresurveyAnalysisAction"
import { ProjectGuidanceCard } from "../../src/renderer/src/guidance/ProjectGuidanceCard"

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

it("场景 1.2/A：轮询到 ready+draft 时自动打开审核面板并进入编辑态", async () => {
  // 列表给 analyzing；轮询（带 id 的 GET）第一次就返回 ready+draft
  let polled = false
  mocks.apiRequest.mockImplementation(async (path: string) => {
    const target = String(path)
    if (target.endsWith("/guidance-analyses")) return { items: [analysisFixture()] }
    if (target.includes("/guidance-analyses/")) {
      polled = true
      return analysisFixture({ analysis_state: "ready", status: "draft" })
    }
    return { items: [] }
  })

  render(
    <PresurveyAnalysisAction projectId="project-1" fileVersionId="file-1" canManage />,
  )

  // GuidanceReview 以真实组件渲染：编辑态应出现表单标签（而非只读网格）
  const visionField = await screen.findByText("客户长期愿景", {}, { timeout: 6000 })
  expect(polled).toBe(true)
  expect(screen.getByRole("dialog", { name: "审核客户目标与项目指引" })).toBeInTheDocument()
  // ready+draft：确认按钮直接可用（场景 1.5 主路径在 guidance-review-confirm 已钉）
  expect(screen.getByRole("button", { name: "确认并用于项目指引" })).toBeInTheDocument()
  expect(visionField).toBeInTheDocument()
})

it("场景 1.3/B：轮询到 failed 时打开面板，failure_message 以 role=alert 可见且无确认按钮", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    const target = String(path)
    if (target.endsWith("/guidance-analyses")) return { items: [analysisFixture()] }
    if (target.includes("/guidance-analyses/")) {
      return analysisFixture({
        analysis_state: "failed",
        failure_code: "ai_output_invalid",
        failure_message: "AI 输出不符合项目指引合同，请重试或人工录入。",
      })
    }
    return { items: [] }
  })

  render(
    <PresurveyAnalysisAction projectId="project-1" fileVersionId="file-1" canManage />,
  )

  const alert = await screen.findByRole("alert", {}, { timeout: 6000 })
  expect(alert).toHaveTextContent("AI 输出不符合项目指引合同")
  expect(screen.queryByRole("button", { name: "确认并用于项目指引" })).not.toBeInTheDocument()
})

it("场景 1.3/C：start() 轮询到 failed 时以 inline 提示暴露失败原因，不再打开审核", async () => {
  mocks.runTask.mockImplementation(async ({ task }: { task: () => Promise<unknown> }) => task())
  let created = false
  mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
    const method = options?.method ?? "GET"
    const target = String(path)
    if (method === "POST" && target.endsWith("/guidance-analyses")) {
      created = true
      return analysisFixture({ analysis_state: "queued" })
    }
    if (target.includes("/guidance-analyses/")) {
      return analysisFixture({
        analysis_state: "failed",
        failure_code: "ai_authentication_failed",
        failure_message: "模型服务认证失败",
      })
    }
    return { items: [] }
  })

  render(
    <PresurveyAnalysisAction projectId="project-1" fileVersionId="file-1" canManage />,
  )
  fireEvent.click(screen.getByRole("button", { name: "AI 分析预调研表" }))

  // start() 的 catch 对非 ApiClientError 显示通用文案（failure_message 明细
  // 由场景 B 的面板 role=alert 承担）——此处钉住「失败必须用户可见」这一底线
  const inline = await screen.findByTitle("无法开始 AI 分析，请稍后重试。", {}, { timeout: 6000 })
  expect(inline).toHaveTextContent("分析失败")
  expect(created).toBe(true)
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

it.each([
  ["cancelled", "终态：当前实现仍显示进行中占位（已记台账）"],
  ["queued", "排队中显示进行中占位"],
  ["extracting", "抽取中显示进行中占位"],
])(
  "场景 1.4/D：%s 状态显示进行中占位（role=status）而非表单/确认按钮（%s）",
  (state: string, _note: string) => {
    render(
      <GuidanceReview
        projectId="project-1"
        initial={analysisFixture({ analysis_state: state }) as never}
        canManage
        onClose={() => {}}
        onSaved={() => {}}
      />,
    )

    const status = screen.getByRole("status")
    expect(status).toHaveTextContent("预调研分析正在后台继续")
    expect(screen.queryByRole("button", { name: "确认并用于项目指引" })).not.toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  },
)

it("场景 1.6/E：confirmed 指引在卡片显示摘要，source_is_stale 时出现旧版重分析横幅", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path).endsWith("/guidance")) {
      return analysisFixture({
        analysis_state: "ready",
        status: "confirmed",
        source_is_stale: true,
        customer_vision: "成为北美家庭理疗设备首选供应商",
        current_phase_objective: "完成试点期获客管道搭建",
        key_business_problems: [{ text: "询盘转化率低", classification: "ai_synthesized", source_refs: ["kimi-file:1"], confirmed: false }],
      })
    }
    return { items: [] }
  })

  render(<ProjectGuidanceCard projectId="project-1" canManage={false} />)

  const banner = await screen.findByText("当前指引基于旧版预调研表，最新启用版本尚未重新分析。")
  expect(banner).toBeInTheDocument()
  expect(screen.getByText("客户长期愿景")).toBeInTheDocument()
  expect(screen.getByText("成为北美家庭理疗设备首选供应商")).toBeInTheDocument()
  expect(screen.getByText("完成试点期获客管道搭建")).toBeInTheDocument()
  expect(screen.getByText("询盘转化率低")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "查看详情" })).toBeInTheDocument()
})

it("场景 1.6/F：source_is_stale=false 时卡片不出现旧版横幅", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path).endsWith("/guidance")) {
      return analysisFixture({
        analysis_state: "ready",
        status: "confirmed",
        source_is_stale: false,
        customer_vision: "成为北美家庭理疗设备首选供应商",
      })
    }
    return { items: [] }
  })

  render(<ProjectGuidanceCard projectId="project-1" canManage={false} />)

  await screen.findByText("客户长期愿景")
  expect(
    screen.queryByText("当前指引基于旧版预调研表，最新启用版本尚未重新分析。"),
  ).not.toBeInTheDocument()
})
