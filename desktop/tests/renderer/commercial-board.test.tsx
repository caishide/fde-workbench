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

import { CommercialBoard, clampBScore } from "../../src/renderer/src/projects/CommercialBoard"

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

// 变异测试记录（评审会 2026-10-26，M6）：把回调 `mutate(async () =>` 改成
// `mutate(() =>` 字面存活——async 关键字不是承重墙，mutate 的 try/catch 包住
// `await run()`，同步 thunk 抛错同样被捕获。本测试钉住的真正不变量是
// 「校验抛错必须落进 mutate 的 catch 并展示」：若有人去掉 `await run()` 的
// await 或把 parsePositive 挪出回调，本用例 findByText 超时变红。裁定
// async 语义非修复本体，无需单独补钉。

it("J4: the ×1.40 integration tier sends c_handling (single constant, no silent drop)", async () => {
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  // 展开「自定义系数」并选档内偏离 ×1.40（唯一触发 C 分支的档位）
  await user.click(await screen.findByText("自定义系数"))
  await user.selectOptions(await screen.findByLabelText("档内偏离"), "1.4")

  await user.click(screen.getByRole("button", { name: "按上述系数建报价" }))

  await waitFor(() => expect(quoteBodies().length).toBeGreaterThan(0))
  const body = quoteBodies()[0] as Record<string, unknown>
  expect(body.integration_factor).toBe(1.4)
  // 关键：×1.40 必须带上 c_handling（漏传服务端直接 400）
  expect(body.c_handling).toBeTruthy()
})

it("J5: B layer score is clamped on both ends", async () => {
  const user = userEvent.setup()
  render(<CommercialBoard projectId={PROJECT_ID} canManage />)

  await user.click(await screen.findByText("自定义系数"))
  const score = await screen.findByLabelText(/B 层分/)

  // 负数：键盘输入拦不住 min，必须在提交前夹到 0
  await user.clear(score)
  await user.type(score, "-3")
  await user.click(screen.getByRole("button", { name: "按上述系数建报价" }))

  await waitFor(() => expect(quoteBodies().length).toBeGreaterThan(0))
  const body = quoteBodies()[0] as Record<string, unknown>
  expect(body.b_layer_score).toBeGreaterThanOrEqual(0)
})

it("J5b: clampBScore clamps both ends (negative and over-max)", () => {
  // 直接验夹取函数：HTML min/max 只挡鼠标点选，键盘输入照样能填负数
  expect(clampBScore(-3, "cold_start")).toBe(0)
  expect(clampBScore(99, "cold_start")).toBe(5)
  expect(clampBScore(99, "steady")).toBe(10)
  expect(clampBScore(Number.NaN, "steady")).toBe(0)
  expect(clampBScore(4, "cold_start")).toBe(4)
})
