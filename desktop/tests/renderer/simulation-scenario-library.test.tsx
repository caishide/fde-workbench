// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  user: { id: "fde-1", role: "fde_engineer" },
}))
vi.mock("../../src/renderer/src/auth/AuthProvider", () => ({ useAuth: () => mocks }))

import { parseScenarioImportText, ScenarioLibrary } from "../../src/renderer/src/SimulationLab/ScenarioLibrary"
import { SimulationDashboard } from "../../src/renderer/src/SimulationLab/SimulationDashboard"

const BASE = "/api/v1/simulation"

function scenario(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "scn-1",
    scenario_key: "CASE-A-QUALITY-TRACE",
    name: "汽车零部件质量追溯",
    industry: "automotive_parts",
    variant: "normal",
    difficulty: "standard",
    split: "train",
    status: "active",
    tags: ["质量", "追溯"],
    version: 1,
    rubric_version: "rubric-v1",
    source_kind: "seed",
    source_ref: "CASE-A-QUALITY-TRACE.json",
    note: null,
    created_at: "2026-11-08T01:00:00",
    updated_at: "2026-11-08T01:00:00",
    ...overrides,
  }
}

function listDto(items: unknown[]): Record<string, unknown> {
  return { items, total: items.length, truncated: false }
}

beforeEach(() => {
  mocks.apiRequest.mockReset()
})

afterEach(() => {
  cleanup()
})

it("呈现案例库列表（名称/业务键/客户行为/数据集/版本/标签）", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([scenario()]))

  render(<ScenarioLibrary />)

  const table = await screen.findByRole("table")
  const row = within(table).getByText("汽车零部件质量追溯").closest("tr")
  expect(row).not.toBeNull()
  expect(within(row as HTMLElement).getByText("CASE-A-QUALITY-TRACE")).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText("正常客户")).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText("训练集")).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText("v1")).toBeInTheDocument()
  expect(within(row as HTMLElement).getByText("质量、追溯")).toBeInTheDocument()
})

it("切换客户行为过滤会带 variant 参数重新请求", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([scenario()]))
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByRole("table")

  await user.selectOptions(screen.getByLabelText("客户行为"), "complex")

  await waitFor(() => {
    const calls = mocks.apiRequest.mock.calls
    expect(calls.some(([path]) => String(path).includes("variant=complex"))).toBe(true)
  })
})

it("空库时呈现空态而非空白页", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([]))

  render(<ScenarioLibrary />)

  expect(await screen.findByText("案例库为空")).toBeInTheDocument()
})

it("数据格式异常（缺字段）时呈现错误而不是静默渲染", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([{ id: "scn-1" }]))

  render(<ScenarioLibrary />)

  expect(await screen.findByRole("alert")).toHaveTextContent("数据格式异常")
})

it("服务端 403 时原样呈现错误文案", async () => {
  mocks.apiRequest.mockRejectedValue(
    Object.assign(new Error("当前账号无权访问模拟训练场。"), { code: "forbidden", status: 403 }),
  )

  render(<ScenarioLibrary />)

  expect(await screen.findByRole("alert")).toHaveTextContent("当前账号无权访问模拟训练场。")
})

it("新建场景走 POST 且携带内容", async () => {
  mocks.apiRequest.mockImplementation((path: string, options: { method: string }) => {
    if (options.method === "POST") return Promise.resolve(scenario({ id: "scn-new", version: 1 }))
    return Promise.resolve(listDto([]))
  })
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByRole("button", { name: "新建场景" })
  await user.click(screen.getByRole("button", { name: "新建场景" }))

  expect(await screen.findByRole("dialog")).toBeInTheDocument()
  await user.type(screen.getByLabelText("案例名称"), "新案例")
  await user.click(screen.getByRole("button", { name: "保存" }))

  await waitFor(() => {
    const post = mocks.apiRequest.mock.calls.find(([, options]) => options.method === "POST")
    expect(post).toBeTruthy()
    const [, options] = post as [string, { method: string; body?: { name?: string } }]
    expect(options.body?.name).toBe("新案例")
  })
})

it("总览按客户行为与数据集给出盘点", async () => {
  mocks.apiRequest.mockResolvedValue(
    listDto([
      scenario(),
      scenario({ id: "scn-2", variant: "vague", split: "regression" }),
    ]),
  )

  render(<SimulationDashboard />)

  await waitFor(() => {
    expect(screen.getByText("案例分支")).toBeInTheDocument()
    // 「正常客户」同时出现在 KPI 卡与分布清单里，故用 getAllByText
    expect(screen.getAllByText("正常客户").length).toBeGreaterThan(0)
    expect(screen.getAllByText("模糊客户").length).toBeGreaterThan(0)
    expect(screen.getAllByText("回归集").length).toBeGreaterThan(0)
  })
})

it("场景编辑弹层：分区标题 + × 关闭钮可关 + 可滚弹层类", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([scenario()]))
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByRole("table")
  await user.click(screen.getByRole("button", { name: "编辑" }))

  const dialog = await screen.findByRole("dialog")
  // 弹层类：宽弹层 + 内部滚动（否则高表单超出视口且无法下滚）
  expect(dialog.className).toContain("simulation-scenario-dialog")
  // 四分区标题在文档里按 ①→④ 顺序出现
  expect(screen.getByText("① 基本资料")).toBeInTheDocument()
  expect(screen.getByText("② 客户可见面（Tester / Customer 视角）")).toBeInTheDocument()
  expect(screen.getByText(/③ 隐藏事实/)).toBeInTheDocument()
  expect(screen.getByText(/④ 评分侧/)).toBeInTheDocument()
  // × 关闭钮（Esc 之外始终可见的关闭出口）
  await user.click(within(dialog).getByRole("button", { name: "关闭弹窗" }))
  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 批量导入（L 线 round2：案例库界面直导，替代裸 curl 底单）
// ---------------------------------------------------------------------------

function importFile(content: unknown): File {
  return new File([JSON.stringify(content)], "batch.json", { type: "application/json" })
}

async function pickImportFile(user: ReturnType<typeof userEvent.setup>, file: File): Promise<void> {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  expect(input).not.toBeNull()
  fireEvent.change(input, { target: { files: [file] } })
}

it("导入解析纯函数：裸数组与 scenarios 包裹两形态都收，非法形状拒", () => {
  expect(parseScenarioImportText('[{"a":1}]')).toEqual([{ a: 1 }])
  expect(parseScenarioImportText('{"scenarios":[{"a":1}]}')).toEqual([{ a: 1 }])
  expect(() => parseScenarioImportText('{"a":1}')).toThrow(/scenarios/)
  expect(() => parseScenarioImportText("not-json")).toThrow(/JSON/)
})

it("导入 JSON：裸列表文件走 POST {scenarios} 并刷新列表", async () => {
  const batch = [
    scenario({
      id: "scn-imp-1",
      scenario_key: "IMP-HC-001",
      name: "民营医院病历数字化",
      status: "draft",
      source_kind: "import",
    }),
  ]
  mocks.apiRequest.mockImplementation((path: string, options: { method: string }) => {
    if (options.method === "POST" && String(path).endsWith("/scenarios/import")) {
      return Promise.resolve({ created: batch, created_count: 1, failures: [] })
    }
    return Promise.resolve(listDto(batch))
  })
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByRole("table")
  await pickImportFile(user, importFile(batch))

  await screen.findByText("已导入 1 个场景。")
  const post = mocks.apiRequest.mock.calls.find(
    ([path, options]) =>
      String(path).endsWith("/scenarios/import") && options.method === "POST",
  )
  expect(post).toBeTruthy()
  const [, options] = post as [string, { method: string; body?: unknown }]
  expect(options.body).toEqual({ scenarios: batch })
  // 刷新后草稿场景在列表可见
  expect(screen.getByText("民营医院病历数字化")).toBeInTheDocument()
})

it("空数组文件不发请求就地提示", async () => {
  mocks.apiRequest.mockResolvedValue(listDto([]))
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByText("案例库为空")
  await pickImportFile(user, importFile([]))


  expect(await screen.findByText(/没有场景/)).toBeInTheDocument()
  expect(mocks.apiRequest.mock.calls.some(([, options]) => options.method === "POST")).toBe(false)
})

it("导入部分失败时逐条回显失败详情", async () => {
  mocks.apiRequest.mockImplementation((_path: string, options: { method: string }) => {
    if (options.method === "POST") {
      return Promise.resolve({
        created: [],
        created_count: 0,
        failures: [
          { index: 1, code: "invalid_scenario", message: "场景内容校验未通过。" },
        ],
      })
    }
    return Promise.resolve(listDto([]))
  })
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  await screen.findByText("案例库为空")
  await pickImportFile(user, importFile([scenario(), { broken: true }]))

  const notice = await screen.findByRole("status")
  expect(notice).toHaveTextContent("已导入 0 个场景；失败 1 条")
  expect(notice).toHaveTextContent("#1 invalid_scenario：场景内容校验未通过。")
})

// ---------------------------------------------------------------------------
// 行内启用/停用（激活的界面化：PATCH status 追加不可变新版本）
// ---------------------------------------------------------------------------

it("草稿行显示「启用」，点击走 PATCH status=active", async () => {
  mocks.apiRequest.mockImplementation((_path: string, options: { method: string }) => {
    if (options.method === "PATCH") {
      return Promise.resolve(scenario({ status: "active", version: 2 }))
    }
    return Promise.resolve(listDto([scenario({ status: "draft" })]))
  })
  const user = userEvent.setup()

  render(<ScenarioLibrary />)
  const table = await screen.findByRole("table")
  const row = within(table).getByText("汽车零部件质量追溯").closest("tr") as HTMLElement
  await user.click(within(row).getByRole("button", { name: "启用" }))

  expect(await screen.findByRole("status")).toHaveTextContent("已启用「汽车零部件质量追溯」")
  const patch = mocks.apiRequest.mock.calls.find(([, options]) => options.method === "PATCH")
  expect(patch).toBeTruthy()
  const [, options] = patch as [string, { method: string; body?: unknown }]
  expect(options.body).toEqual({ status: "active" })
})

it("启用行显示「停用」；已归档行无状态钮", async () => {
  mocks.apiRequest.mockResolvedValue(
    listDto([
      scenario({ status: "active" }),
      scenario({ id: "scn-arc", scenario_key: "CASE-ARC", name: "归档案例", status: "archived" }),
    ]),
  )

  render(<ScenarioLibrary />)
  const table = await screen.findByRole("table")
  const activeRow = within(table).getByText("汽车零部件质量追溯").closest("tr") as HTMLElement
  expect(within(activeRow).getByRole("button", { name: "停用" })).toBeInTheDocument()
  const archivedRow = within(table).getByText("归档案例").closest("tr") as HTMLElement
  expect(within(archivedRow).queryByRole("button", { name: "启用" })).not.toBeInTheDocument()
  expect(within(archivedRow).queryByRole("button", { name: "停用" })).not.toBeInTheDocument()
})
