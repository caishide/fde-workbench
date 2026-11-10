// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { App } from "../../src/renderer/src/App"
import { bridge, installBridge, ok } from "./test-utils"

const REGISTER_URL = "/api/v1/commercial/enterprise-registrations"

/**
 * 企业自助注册页（**公开面**；ADR-010 §3）：未登录可达、免鉴权直连
 * （`accessToken: ""`）、只提交代号与必要登记信息。
 */

function mockBridge(apiRequest: ReturnType<typeof vi.fn>) {
  // refresh → ok(null)：未登录态——公开注册面必须顶替登录页可达
  installBridge(bridge({ refresh: vi.fn().mockResolvedValue(ok(null)), apiRequest }))
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("企业名称（代号）"), "示例企业甲")
  await user.type(screen.getByLabelText("统一社会信用代码"), "91110000TEST0000XX")
  await user.type(screen.getByLabelText("账号"), "ent.a")
  await user.type(screen.getByLabelText("邮箱"), "ent.a@example.com")
  await user.type(screen.getByLabelText("密码"), "entropy-1")
  await user.type(screen.getByLabelText("要解决的业务问题"), "固件交付周期长，需要自动化流水线。")
  await user.click(screen.getByRole("button", { name: "提交注册" }))
}

beforeEach(() => {
  location.hash = "#enterprise-register"
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  location.hash = ""
})

describe("企业自助注册页（公开面）", () => {
  it("未登录时可达且顶替登录页（公开面不引登录墙）", async () => {
    const apiRequest = vi.fn().mockResolvedValue(ok({ status: 200, data: null, error: null }))
    mockBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)

    expect(await screen.findByRole("heading", { name: "企业注册" })).toBeInTheDocument()
    // 登录页不得同时出现（注册页顶替登录页，而非叠加）
    expect(screen.queryByRole("button", { name: "登录" })).not.toBeInTheDocument()
    // 公开面挂载期零请求（提交前不发探测）
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it("提交走免鉴权直连：accessToken 为空串且 URL/载荷逐键正确", async () => {
    const apiRequest = vi.fn().mockResolvedValue(
      ok({
        status: 200,
        data: {
          user_id: "u-1",
          username: "ent.a",
          subject_key: "91110000TEST0000XX",
          quota_created: true,
          quota_state: "available",
        },
        error: null,
      }),
    )
    mockBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await screen.findByRole("heading", { name: "企业注册" })
    await fillAndSubmit(user)

    expect(await screen.findByRole("status")).toHaveTextContent("注册成功")
    expect(apiRequest).toHaveBeenCalledTimes(1)
    const [path, options] = apiRequest.mock.calls[0]
    expect(path).toBe(REGISTER_URL)
    expect(options.method).toBe("POST")
    // 免鉴权入口的钉子：不带任何会话令牌（api client 会拒无会话请求，故走直连）
    expect(options.accessToken).toBe("")
    expect(options.body).toEqual({
      username: "ent.a",
      display_name: "示例企业甲",
      password: "entropy-1",
      email: "ent.a@example.com",
      subject_key: "91110000TEST0000XX",
      problem_description: "固件交付周期长，需要自动化流水线。",
    })
    expect(screen.getByRole("status")).toHaveTextContent("ent.a")
    expect(screen.getByRole("status")).toHaveTextContent("91110000TEST0000XX")
  })

  it("M2 收拢语义：email 必填字段在场，成功提示告知需邮箱验证后才可登录", async () => {
    const apiRequest = vi.fn().mockResolvedValue(
      ok({
        status: 200,
        data: {
          user_id: "u-2",
          username: "ent.b",
          subject_key: "91110000TEST0000XX",
          quota_created: true,
          quota_state: "available",
          registration_state: "pending_email",
        },
        error: null,
      }),
    )
    mockBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await screen.findByRole("heading", { name: "企业注册" })
    // 邮箱字段必填（M2 邮箱验证通道）
    const emailInput = screen.getByLabelText("邮箱")
    expect(emailInput).toHaveAttribute("type", "email")
    expect(emailInput).toHaveAttribute("required")
    await user.type(screen.getByLabelText("企业名称（代号）"), "示例企业甲")
    await user.type(screen.getByLabelText("统一社会信用代码"), "91110000TEST0000XX")
    await user.type(screen.getByLabelText("账号"), "ent.b")
    await user.type(screen.getByLabelText("邮箱"), "ent.b@example.com")
    await user.type(screen.getByLabelText("密码"), "entropy-1")
    await user.type(screen.getByLabelText("要解决的业务问题"), "固件交付周期长。")
    await user.click(screen.getByRole("button", { name: "提交注册" }))

    const notice = await screen.findByRole("status")
    expect(notice).toHaveTextContent("验证邮件")
    expect(notice).toHaveTextContent("不可登录")
  })

  it("服务端拒绝（限流 429）如实呈现，不伪造成功", async () => {
    const apiRequest = vi.fn().mockResolvedValue(
      ok({
        status: 429,
        data: null,
        error: {
          code: "registration_rate_limited",
          message: "注册尝试过于频繁，请约 1 分钟后再试。",
        },
      }),
    )
    mockBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await screen.findByRole("heading", { name: "企业注册" })
    await fillAndSubmit(user)

    expect(await screen.findByRole("alert")).toHaveTextContent("注册尝试过于频繁")
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("桥层失败如实呈现错误", async () => {
    const apiRequest = vi.fn().mockRejectedValue(new Error("网络不可达。"))
    mockBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await screen.findByRole("heading", { name: "企业注册" })
    await fillAndSubmit(user)

    expect(await screen.findByRole("alert")).toHaveTextContent("网络不可达。")
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })
})
