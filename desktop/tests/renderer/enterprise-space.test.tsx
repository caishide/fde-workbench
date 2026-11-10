// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { App } from "../../src/renderer/src/App"
import type { UserDto } from "../../src/shared/contracts"
import { adminUser, authResult, bridge, installBridge, ok } from "./test-utils"

// 企业自助注册创建的账号即 viewer 档（commercial_role=R1）——用 viewer 模拟
// 绑定账号本人视角；他人/admin 的可见性差异由服务端闸把关，桌面只呈现。
const viewerUser: UserDto = {
  ...adminUser,
  id: "viewer-1",
  username: "ent.a",
  displayName: "企业账号",
  role: "viewer",
}

const SUBJECT_KEY = "91110000TEST0000XX"
const SPACE_URL = `/api/v1/commercial/enterprise-spaces/${SUBJECT_KEY}`
const CHOICE_URL = `${SPACE_URL}/paid-option-choices`
const STORAGE_KEY = "fde.enterprise.subject_key"

const space = {
  subject: {
    subject_key: SUBJECT_KEY,
    display_name: "示例企业甲",
    problem_description: "固件交付周期长，需要自动化流水线。",
  },
  quota: {
    subject_key: SUBJECT_KEY,
    state: "available",
    bound_user_id: "viewer-1",
    completed_at: null,
    enterprise_confirmed_at: null,
  },
  engagement_state: "self_service",
  space: {
    registration_entry: { entry_url: "#enterprise-register" },
    projects: [
      { project_id: "p-1", project_code: "PRJ-TEST-001", name: "示例交付项目", status: "active" },
    ],
  },
  triage_decisions: [
    {
      id: "d-1",
      tier: "self_service",
      rationale: "免费诊断额度内",
      decided_at: "2026-11-01T00:00:00+00:00",
    },
  ],
  paid_options: {
    options: {
      standardized: {
        label: "标准化程度高且风险低",
        description: "AI 自助完成候选——适合标准化产品化交付路径。",
        follow_up: "顾问将在 1 个工作日内联系。",
      },
      multi_system: {
        label: "涉及多个业务系统",
        description: "AI 辅助＋企业人员审核——需要双方协同的半自助路径。",
        follow_up: "顾问将在 1 个工作日内联系。",
      },
    },
    current_choice: null,
    advisor_follow_up: "如有疑问请联系顾问。",
  },
  registration_entries: {},
}

function mockSpaceBridge(apiRequest: ReturnType<typeof vi.fn>) {
  installBridge(
    bridge({
      refresh: vi.fn().mockResolvedValue(ok(authResult(viewerUser))),
      apiRequest,
    }),
  )
}

async function loadSpace(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  // 先等会话刷新落地（loading → authenticated），再操作表单
  await screen.findByRole("heading", { name: "企业空间" })
  await user.type(screen.getByLabelText("统一社会信用代码"), SUBJECT_KEY)
  await user.click(screen.getByRole("button", { name: "读取企业空间" }))
  await screen.findByRole("heading", { name: "主体" })
}

beforeEach(() => {
  location.hash = "#enterprise-space"
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  location.hash = ""
  window.localStorage.clear()
})

describe("企业空间视图", () => {
  it("空信用代码直接拦截，零请求", async () => {
    const apiRequest = vi.fn()
    mockSpaceBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    expect(await screen.findByRole("heading", { name: "企业空间" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "读取企业空间" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("请填写统一社会信用代码。")
    expect(apiRequest).not.toHaveBeenCalled()
  })

  it("读取成功呈现主体/额度/交付状态/付费选项/项目五面，GET 面正确", async () => {
    const apiRequest = vi.fn().mockResolvedValue(ok({ status: 200, data: space, error: null }))
    mockSpaceBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await loadSpace(user)

    expect(apiRequest).toHaveBeenCalledTimes(1)
    expect(apiRequest.mock.calls[0][0]).toBe(SPACE_URL)
    expect(apiRequest.mock.calls[0][1].method).toBe("GET")
    // <p>文本混排（React 文本节点按表达式切分）——按整段 p 文本断言
    expect(screen.getByText("企业名称：示例企业甲")).toBeInTheDocument()
    expect(screen.getByText(`统一社会信用代码：${SUBJECT_KEY}`)).toBeInTheDocument()
    expect(screen.getByText("业务问题：固件交付周期长，需要自动化流水线。")).toBeInTheDocument()
    expect(screen.getByText("免费额度状态：available")).toBeInTheDocument()
    expect(screen.getByText("交付状态：自助服务")).toBeInTheDocument()
    expect(screen.getByText("标准化程度高且风险低")).toBeInTheDocument()
    expect(screen.getByText("涉及多个业务系统")).toBeInTheDocument()
    expect(screen.getByText(/PRJ-TEST-001/)).toBeInTheDocument()
    expect(screen.getByText("当前尚未选择付费选项。")).toBeInTheDocument()
  })

  it("读取成功后主体代码入本地记忆，再次进入自动预填", async () => {
    const apiRequest = vi.fn().mockResolvedValue(ok({ status: 200, data: space, error: null }))
    mockSpaceBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await loadSpace(user)
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(SUBJECT_KEY)

    cleanup()
    renderApp(<App />)
    // 再挂载：输入框从本地记忆预填，无需手输（passive effect 刷新用 waitFor 收敛）
    expect(await screen.findByRole("heading", { name: "企业空间" })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByLabelText("统一社会信用代码")).toHaveValue(SUBJECT_KEY),
    )
  })

  it("选择付费选项＝POST 自证选择后复读刷新", async () => {
    const apiRequest = vi
      .fn()
      .mockImplementation((path: string, options?: { method?: string }) => {
        if (path === CHOICE_URL && options?.method === "POST") {
          return Promise.resolve(ok({ status: 200, data: { id: "c-1" }, error: null }))
        }
        return Promise.resolve(ok({ status: 200, data: space, error: null }))
      })
    mockSpaceBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    await loadSpace(user)
    await user.click(screen.getAllByRole("button", { name: "选择此选项" })[0])

    expect(await screen.findByRole("status")).toHaveTextContent("已记录你的付费选项选择")
    const post = apiRequest.mock.calls.find((call) => call[0] === CHOICE_URL)
    expect(post).toBeDefined()
    expect(post![1].method).toBe("POST")
    expect(post![1].body).toEqual({ option_key: "standardized" })
    // GET(读面) → POST(选择) → GET(复读刷新)：三调用且复读在 POST 之后
    expect(apiRequest).toHaveBeenCalledTimes(3)
    expect(apiRequest.mock.calls[2][0]).toBe(SPACE_URL)
  })

  it("读面失败如实呈现错误，不伪造空间内容", async () => {
    const apiRequest = vi.fn().mockRejectedValue(new Error("读取企业空间失败。"))
    mockSpaceBridge(apiRequest)
    const { renderApp } = await import("./test-utils")
    renderApp(<App />)
    const user = userEvent.setup()

    // 等会话刷新落地（loading → authenticated），再操作表单
    await screen.findByRole("heading", { name: "企业空间" })
    await user.type(screen.getByLabelText("统一社会信用代码"), SUBJECT_KEY)
    await user.click(screen.getByRole("button", { name: "读取企业空间" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("读取企业空间失败。")
    expect(screen.queryByRole("heading", { name: "主体" })).not.toBeInTheDocument()
  })
})
