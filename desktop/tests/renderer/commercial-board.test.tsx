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

import { CommercialBoard } from "../../src/renderer/src/projects/CommercialBoard"

const PROJECT_ID = "comm-project"

function boardPaths(): string[] {
  return mocks.apiRequest.mock.calls.map((call) => String(call[0]))
}

function quoteBodies(): Array<Record<string, unknown>> {
  return mocks.apiRequest.mock.calls
    .filter((call) => String(call[0]).endsWith("/quotes") && (call[1] as { method?: string })?.method === "POST")
    .map((call) => (call[1] as { body: Record<string, unknown> }).body)
}

function happyResponses(): unknown[] {
  return [
    { quotes: [] },
    { payments: [], summary: { receivable: 0, received: 0, outstanding: 0, overdue: 0, dunning_counts: {} } },
    { contracts: [] },
  ]
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path).endsWith("/quotes")) return happyResponses()[0]
    if (String(path).endsWith("/payments")) return happyResponses()[1]
    if (String(path).endsWith("/contracts")) return happyResponses()[2]
    return {}
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("shows the failure banner when any board segment fails to load", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path).endsWith("/payments")) throw new Error("收款计划加载失败")
    return { quotes: [], contracts: [] }
  })
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("收款计划加载失败")
  expect(screen.queryByRole("button", { name: /首单默认参数/ })).not.toBeInTheDocument()
})

it("renders the empty payment plan hint and the manager-only create controls", async () => {
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  expect(await screen.findByText("暂无收款计划。B 试点按 50/50 生成两行（G4 预付 / G8 尾款）。")).toBeVisible()
  expect(screen.getByRole("button", { name: /首单默认参数/ })).toBeVisible()
  // 三个台账段各拉一次
  expect(boardPaths().filter((path) => path.endsWith("/quotes") && !path.endsWith("/quotes/draft"))).toContain(
    `/api/v1/projects/${PROJECT_ID}/quotes`,
  )
})

it("viewer cannot see quote creation controls", async () => {
  mocks.user = { id: "viewer-1", role: "viewer" }
  render(<CommercialBoard projectId={PROJECT_ID} canManage={false} />)

  await screen.findByText("暂无收款计划。B 试点按 50/50 生成两行（G4 预付 / G8 尾款）。")
  expect(screen.queryByRole("button", { name: /首单默认参数/ })).not.toBeInTheDocument()
})

it("creates a first-order preset quote with the exact server contract", async () => {
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  await user.click(await screen.findByRole("button", { name: /首单默认参数/ }))

  await waitFor(() => expect(quoteBodies()).toHaveLength(1))
  expect(quoteBodies()[0]).toEqual({ preset: "first_order_defaults" })
  expect(mocks.apiRequest).toHaveBeenCalledWith(`/api/v1/projects/${PROJECT_ID}/quotes`, expect.objectContaining({ method: "POST" }))
  // 成功后重载台账
  await waitFor(() => {
    expect(boardPaths().filter((path) => path.endsWith("/payments"))).toHaveLength(2)
  })
})

it("surfaces the server rejection next to the create form", async () => {
  const user = userEvent.setup()
  let calls = 0
  mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (String(path).endsWith("/quotes") && options?.method === "POST") {
      calls += 1
      throw new Error("报价创建失败：档位参数不合法")
    }
    if (String(path).endsWith("/quotes")) return { quotes: [] }
    if (String(path).endsWith("/payments")) {
      return { payments: [], summary: { receivable: 0, received: 0, outstanding: 0, overdue: 0, dunning_counts: {} } }
    }
    return { contracts: [] }
  })
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  await user.click(await screen.findByRole("button", { name: /首单默认参数/ }))

  await screen.findByText("报价创建失败：档位参数不合法")
  expect(calls).toBe(1)
})

it("C1: invalid numeric input surfaces a visible Chinese error instead of a silent rejection", async () => {
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  const base = await screen.findByPlaceholderText("合同基数金额 ¥")
  await user.type(base, "0")
  await user.click(screen.getByRole("button", { name: "生成收款计划" }))

  // parsePositive 的抛错发生在 post() 之前——修复后由 mutate 捕获并展示
  await screen.findByText("合同基数金额 必须是正数")
  // 未发起任何请求
  expect(
    mocks.apiRequest.mock.calls.filter(
      (call) => String(call[0]).endsWith("/payments/plan"),
    ),
  ).toHaveLength(0)
})
