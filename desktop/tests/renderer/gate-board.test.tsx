// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  user: { id: "actor-1", role: "project_lead" },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))

import { GateBoard } from "../../src/renderer/src/projects/GateBoard"

function gatesPath(projectId = "gate-project"): string {
  return `/api/v1/projects/${projectId}/gates`
}

function gateView(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    project_id: "gate-project",
    sop_phase: "S3",
    events: [],
    gates: [
      {
        gate_key: "G3",
        status: "pending",
        decision: null,
        submitted_at: null,
        decided_at: null,
        checklist: [
          { label: "深度诊断报告", claim_status: null, source_uri: null, content_hash: null },
          { label: "现状与痛点清单", claim_status: null, source_uri: null, content_hash: null },
        ],
        gate_name: "深度诊断完成门",
        node_key: "S3",
        exit_condition: "诊断报告双方确认",
        evidence_location: "fdeops .fde/",
        contract_payment: null,
        signer_role: null,
        fail_exit: null,
        decision_semantics: null,
        template_source_uri: null,
      },
    ],
    ...overrides,
  }
}

function evidenceRequestBodies(): Array<Record<string, unknown>> {
  return mocks.apiRequest.mock.calls
    .filter((call) => String(call[0]).endsWith("/gates/G3/evidence"))
    .map((call) => (call[1] as { body: Record<string, unknown> }).body)
}

function callCount(path: string, method?: string): number {
  return mocks.apiRequest.mock.calls.filter(
    (call) =>
      String(call[0]) === path &&
      (method === undefined || (call[1] as { method?: string } | undefined)?.method === method),
  ).length
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.apiRequest.mockResolvedValue(gateView())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("shows the failure banner instead of the board when loading fails", async () => {
  mocks.apiRequest.mockRejectedValue(new Error("网关不可达"))
  render(<GateBoard projectId="gate-project" canManage />)

  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("门禁数据加载失败，请稍后重试。")
  expect(screen.queryByText("深度诊断完成门")).not.toBeInTheDocument()
})

it("renders gate status and claim badges for read-only viewers", async () => {
  mocks.apiRequest.mockResolvedValue(
    gateView({
      gates: [
        {
          gate_key: "G6",
          status: "evidence",
          decision: null,
          submitted_at: "2026-10-20T08:00:00+00:00",
          decided_at: null,
          checklist: [
            { label: "问题陈述（SCQA）", claim_status: "claimed", source_uri: "fdeops://x/y", content_hash: "a".repeat(64) },
          ],
          gate_name: "提案门",
          node_key: "S4",
          exit_condition: "提案书确认",
          evidence_location: "openfde assets/",
          contract_payment: null,
          signer_role: "客户负责人",
          fail_exit: null,
          decision_semantics: null,
          template_source_uri: null,
        },
      ],
    }),
  )
  render(<GateBoard projectId="gate-project" canManage={false} />)

  expect(await screen.findByRole("heading", { name: /G6 · 提案门/ })).toBeVisible()
  expect(screen.getByText("待核验")).toBeVisible()
  expect(screen.getByText("claimed")).toBeVisible()
  // 只读视图不出现提交/拍板操作
  expect(screen.queryByRole("button", { name: "提交证据" })).not.toBeInTheDocument()
})

it("submits per-item evidence pointers and reloads the board", async () => {
  const user = userEvent.setup()
  render(<GateBoard projectId="gate-project" canManage />)

  await user.click(await screen.findByRole("button", { name: "提交证据" }))

  const uris = screen.getAllByPlaceholderText("fdeops://engagements/<代号>/.fde/…")
  const hashes = screen.getAllByPlaceholderText("sha256（64 位）")
  expect(uris).toHaveLength(2)
  await user.type(uris[0], "fdeops://engagements/demo/.fde/report.md")
  await user.type(hashes[0], "a".repeat(64))
  await user.type(uris[1], "fdeops://engagements/demo/.fde/painpoints.md")
  await user.type(hashes[1], "b".repeat(64))

  await user.click(screen.getByRole("button", { name: "提交证据（标 claimed）" }))

  await waitFor(() => expect(evidenceRequestBodies()).toHaveLength(1))
  expect(evidenceRequestBodies()[0]).toEqual({
    items: [
      {
        label: "深度诊断报告",
        source_uri: "fdeops://engagements/demo/.fde/report.md",
        content_hash: "a".repeat(64),
      },
      {
        label: "现状与痛点清单",
        source_uri: "fdeops://engagements/demo/.fde/painpoints.md",
        content_hash: "b".repeat(64),
      },
    ],
  })
  // 提交成功后回读面板（第二次 GET）
  await waitFor(() => {
    expect(callCount(gatesPath(), "GET")).toBeGreaterThanOrEqual(2)
  })
})

it("keeps the filled evidence form and shows the error when the server rejects", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (String(path).endsWith("/gates/G3/evidence")) {
      throw new Error("证据校验失败：sha256 与文件不符")
    }
    return gateView()
  })
  render(<GateBoard projectId="gate-project" canManage />)

  await user.click(await screen.findByRole("button", { name: "提交证据" }))
  const uris = screen.getAllByPlaceholderText("fdeops://engagements/<代号>/.fde/…")
  const hashes = screen.getAllByPlaceholderText("sha256（64 位）")
  await user.type(uris[0], "fdeops://engagements/demo/.fde/report.md")
  await user.type(hashes[0], "a".repeat(64))
  await user.type(uris[1], "fdeops://engagements/demo/.fde/painpoints.md")
  await user.type(hashes[1], "b".repeat(64))

  await user.click(screen.getByRole("button", { name: "提交证据（标 claimed）" }))

  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("门禁数据加载失败，请稍后重试。")
  // 失败不收表单：已填的指针与 sha256 保留
  expect((screen.getAllByPlaceholderText("fdeops://engagements/<代号>/.fde/…")[0] as HTMLInputElement).value).toBe(
    "fdeops://engagements/demo/.fde/report.md",
  )
  expect(evidenceRequestBodies()).toHaveLength(1)
})

it("C2: opening the verify panel defaults every checklist item to unchecked", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockResolvedValue(
    gateView({
      gates: [
        {
          gate_key: "G6",
          status: "evidence",
          decision: null,
          submitted_at: "2026-10-20T08:00:00+00:00",
          decided_at: null,
          checklist: [
            { label: "问题陈述（SCQA）", claim_status: "claimed", source_uri: "fdeops://x/y", content_hash: "a".repeat(64) },
            { label: "解决方案概要", claim_status: "claimed", source_uri: "fdeops://x/z", content_hash: "b".repeat(64) },
          ],
          gate_name: "提案门",
          node_key: "S4",
          exit_condition: "提案书确认",
          evidence_location: "openfde assets/",
          contract_payment: null,
          signer_role: null,
          fail_exit: null,
          decision_semantics: null,
          template_source_uri: null,
        },
      ],
    }),
  )
  render(<GateBoard projectId="gate-project" canManage />)

  await user.click(await screen.findByRole("button", { name: "人工核验拍板" }))

  // claimed ≠ accepted：打开面板时默认全不勾（人工逐项核验后才算 accepted）
  const boxes = screen
    .getAllByRole("checkbox")
    .filter((el) => (el as HTMLInputElement).type === "checkbox") as HTMLInputElement[]
  expect(boxes.length).toBe(2)
  expect(boxes.every((el) => !el.checked)).toBe(true)
  // pass 过门要求全部接受：全不勾时拍板按钮禁用
  expect(screen.getByRole("button", { name: /拍板（接受 0\/2）/ })).toBeDisabled()
})
