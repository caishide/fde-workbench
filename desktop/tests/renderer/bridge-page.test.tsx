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

import { BridgePage } from "../../src/renderer/src/bridge/BridgePage"

function bridgeView(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    captured_at: "2026-10-26T08:00:00+00:00",
    engagements: [
      {
        slug: "demo-engagement",
        openfde_synced_at: "2026-10-26T08:00:00+00:00",
        openfde_status: { entities: 12, active_facts: 30, open_tasks: 2 },
        fdeops_synced_at: "2026-10-26T07:00:00+00:00",
        fdeops_state: { fde_initialized: true, bound_path: "D:/fdeops/demo" },
        linked_projects: [{ project_id: "p-1", project_name: "星河试点" }],
        flags: [],
      },
    ],
    projects: [],
    ...overrides,
  }
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
  mocks.user = { id: "actor-1", role: "project_lead" }
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path) === "/api/v1/bridge/engagements") return bridgeView()
    if (String(path) === "/api/v1/bridge/status") return { runs: [] }
    return {}
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it("shows the failure banner when the engagement projection cannot load", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path) === "/api/v1/bridge/engagements") throw new Error("集成桥投影不可用")
    return { runs: [] }
  })
  render(<BridgePage />)

  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("集成桥投影不可用")
  expect(screen.queryByText("demo-engagement")).not.toBeInTheDocument()
})

it("renders engagement projections with track status and flags", async () => {
  mocks.apiRequest.mockImplementation(async (path: string) => {
    if (String(path) === "/api/v1/bridge/engagements") {
      return bridgeView({
        engagements: [
          {
            slug: "stale-one",
            openfde_synced_at: "2026-10-26T08:00:00+00:00",
            openfde_status: { entities: 3, active_facts: 5, open_tasks: 0 },
            fdeops_synced_at: null,
            fdeops_state: {},
            linked_projects: [],
            flags: ["stale"],
          },
        ],
      })
    }
    if (String(path) === "/api/v1/bridge/status") return { runs: [] }
    return {}
  })
  render(<BridgePage />)

  expect(await screen.findByText("stale-one")).toBeVisible()
  expect(screen.getByText("采集断连")).toBeVisible()
  expect(screen.getByText(/⚠ 采集断连/)).toBeVisible()
  const trackCell = await screen.findByText(
    (_, element) =>
      element?.tagName === "TD" &&
      (element.textContent ?? "").includes("3 实体 / 5 活事实 / 0 开放任务"),
  )
  expect(trackCell).toBeVisible()
})

it("manager can reproject and the board reloads afterwards", async () => {
  const user = userEvent.setup()
  render(<BridgePage />)

  await screen.findByText("demo-engagement")
  expect(callCount("/api/v1/bridge/reconcile", "POST")).toBe(0)

  await user.click(screen.getByRole("button", { name: "重新投影" }))

  await waitFor(() => expect(callCount("/api/v1/bridge/reconcile", "POST")).toBe(1))
  // 重投影成功后回读投影
  await waitFor(() => expect(callCount("/api/v1/bridge/engagements", "GET")).toBeGreaterThanOrEqual(2))
})

it("viewer neither sees reproject nor clear controls", async () => {
  mocks.user = { id: "viewer-1", role: "viewer" }
  render(<BridgePage />)

  await screen.findByText("demo-engagement")
  expect(screen.queryByRole("button", { name: "重新投影" })).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "清投影" })).not.toBeInTheDocument()
})

it("clears a vanished projection via DELETE and reloads", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (String(path) === "/api/v1/bridge/engagements" && options?.method !== "DELETE") {
      return bridgeView({
        engagements: [
          {
            slug: "gone-engagement",
            openfde_synced_at: null,
            openfde_status: {},
            fdeops_synced_at: null,
            fdeops_state: {},
            linked_projects: [],
            flags: ["vanished"],
          },
        ],
      })
    }
    if (String(path) === "/api/v1/bridge/status") return { runs: [] }
    return {}
  })
  render(<BridgePage />)

  await user.click(await screen.findByRole("button", { name: "清投影" }))

  await waitFor(() =>
    expect(callCount("/api/v1/bridge/engagements/gone-engagement", "DELETE")).toBe(1),
  )
  await waitFor(() => expect(callCount("/api/v1/bridge/engagements", "GET")).toBeGreaterThanOrEqual(2))
})

it("surfaces clear failures without wiping the table", async () => {
  const user = userEvent.setup()
  mocks.apiRequest.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (String(path).includes("/bridge/engagements/gone-engagement")) {
      throw new Error("清投影失败：文件仍存活")
    }
    if (String(path) === "/api/v1/bridge/engagements") {
      return bridgeView({
        engagements: [
          {
            slug: "gone-engagement",
            openfde_synced_at: null,
            openfde_status: {},
            fdeops_synced_at: null,
            fdeops_state: {},
            linked_projects: [],
            flags: ["vanished"],
          },
        ],
      })
    }
    if (String(path) === "/api/v1/bridge/status") return { runs: [] }
    return {}
  })
  render(<BridgePage />)

  await user.click(await screen.findByRole("button", { name: "清投影" }))

  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("清投影失败：文件仍存活")
  expect(screen.getByText("gone-engagement")).toBeVisible()
})
