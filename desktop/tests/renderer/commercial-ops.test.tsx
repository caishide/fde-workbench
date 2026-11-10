// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { App } from "../../src/renderer/src/App"
import { adminUser, authResult, bridge, installBridge, ok, renderApp } from "./test-utils"

beforeEach(() => {
  location.hash = "#commercial-ops"
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  location.hash = ""
})

const readiness = {
  config_slots: {
    fee_configs: [
      {
        key: "certification_fee",
        label: "认证费金额",
        value_kind: "amount",
        status: "unset",
        configured: false,
        chargeable: true,
        waiting_for: "任务书 §17 商业数值拍板（数值本期一律不落数）",
      },
      {
        key: "mentoring_period_days",
        label: "陪跑期限",
        value_kind: "days",
        status: "unset",
        configured: false,
        chargeable: false,
        waiting_for: "任务书 §17 商业数值拍板（数值本期一律不落数）",
      },
    ],
    opportunity_rules: [
      {
        key: "protection_period_days",
        label: "保护期长度",
        value_kind: "days",
        status: "unset",
        configured: false,
        chargeable: false,
        waiting_for: "任务书 §17 商业数值拍板（数值本期一律不落数）",
      },
    ],
    split_rules: {
      status: "unset",
      rows: 0,
      configured_rows: 0,
      waiting_for: "任务书 §17 分成比例拍板",
    },
  },
  sale_gate: {
    status: "closed",
    conditions: [
      {
        key: "filing",
        label: "特许经营合同备案",
        registered: false,
        signed_at: null,
        waiting_for: "法务/合规外部输入（ADR-005 §2.2 合规条件登记）",
      },
      {
        key: "qualification",
        label: "主体资格（至少 2 个直营店且经营满 1 年）",
        registered: true,
        signed_at: "2026-11-01T00:00:00+00:00",
        waiting_for: null,
      },
    ],
    missing_conditions: ["filing"],
    ready_to_open: false,
    opened_at: null,
  },
  blockers: [
    {
      kind: "fee_config",
      key: "certification_fee",
      label: "认证费金额",
      severity: "blocking",
      waiting_for: "任务书 §17 商业数值拍板（数值本期一律不落数）",
    },
    {
      kind: "sale_gate_condition",
      key: "filing",
      label: "特许经营合同备案",
      severity: "blocking",
      waiting_for: "法务/合规外部输入（ADR-005 §2.2 合规条件登记）",
    },
  ],
  summary: {
    unset_fee_configs: 2,
    unset_opportunity_rules: 1,
    split_rules_configured: 0,
    missing_gate_conditions: 1,
    blocking_count: 2,
  },
}

function mockReadiness(payload: unknown) {
  const apiRequest = vi.fn().mockResolvedValue(ok({ status: 200, data: payload, error: null }))
  installBridge(
    bridge({
      refresh: vi.fn().mockResolvedValue(ok(authResult(adminUser))),
      apiRequest,
    }),
  )
  return apiRequest
}

describe("商业化运维就绪度面板", () => {
  it("呈现未就绪横幅与阻塞清单（含等待来源）", async () => {
    mockReadiness(readiness)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    expect(await screen.findByRole("heading", { name: "商业化运维" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "未就绪项（2）" })).toBeInTheDocument()
    expect(screen.getAllByText("认证费金额").length).toBeGreaterThan(0)
    expect(screen.getAllByText("特许经营合同备案").length).toBeGreaterThan(0)
    expect(
      screen.getAllByText("等待：法务/合规外部输入（ADR-005 §2.2 合规条件登记）").length,
    ).toBeGreaterThan(0)
  })

  it("配置槽位按状态呈现，不显示任何商业数值", async () => {
    mockReadiness(readiness)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    const table = await screen.findByRole("table")
    expect(table).toHaveTextContent("认证费金额")
    expect(table).toHaveTextContent("未配置")
    expect(table).toHaveTextContent("金额")
    // 未配置即不可收款：金额槽位不得被呈现成任何数字
    expect(table.textContent).not.toMatch(/¥|\d+\.\d{2}/)
  })

  it("售卖闸呈现开关状态与逐项登记态", async () => {
    mockReadiness(readiness)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    expect(await screen.findByRole("heading", { name: "区域售卖闸" })).toBeInTheDocument()
    expect(screen.getByText("当前状态：未开启")).toBeInTheDocument()
    expect(screen.getByText("未登记")).toBeInTheDocument()
    expect(screen.getByText("已登记")).toBeInTheDocument()
  })

  it("只读：仅发起一次 GET 汇总请求，无任何写请求", async () => {
    const apiRequest = mockReadiness(readiness)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    await screen.findByRole("heading", { name: "商业化运维" })
    expect(apiRequest).toHaveBeenCalledTimes(1)
    expect(apiRequest.mock.calls[0][0]).toBe("/api/v1/admin/commercial/readiness")
    expect(apiRequest.mock.calls[0][1].method).toBe("GET")
  })

  it("读面失败时如实呈现错误，不伪造就绪状态", async () => {
    const apiRequest = vi.fn().mockRejectedValue(new Error("读取商业化就绪度失败。"))
    installBridge(
      bridge({
        refresh: vi.fn().mockResolvedValue(ok(authResult(adminUser))),
        apiRequest,
      }),
    )
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    expect(await screen.findByRole("alert")).toHaveTextContent("读取商业化就绪度失败。")
    expect(screen.queryByRole("heading", { name: "未就绪项（2）" })).not.toBeInTheDocument()
  })
})
