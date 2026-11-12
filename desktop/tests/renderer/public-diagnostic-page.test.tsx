// @vitest-environment jsdom
// 获客诊断 T-14a：免注册访客界面用例（公开面）。
//
// 覆盖：公开面调用纪律（一律 accessToken:""；会话令牌只走 X-Diagnostic-Token
// 头）／首屏必填客户端预检／测算卡渲染（原文/解读双层）／条件显隐（show_if）／
// 留资 consent 硬闸／报告轮询（202 受理 → ready/failed）／分享链接明文只此一次／
// 部署闸 404 ⇒ 「暂未开放」／分享只读页（摘要层＋404 失效页）。
import "@testing-library/jest-dom/vitest"

import React from "react"
import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { bridge, installBridge, ok } from "./test-utils"
import {
  PublicDiagnosticPage,
} from "../../src/renderer/src/diagnostics/PublicDiagnosticPage"
import {
  PublicDiagnosticSharePage,
} from "../../src/renderer/src/diagnostics/PublicDiagnosticSharePage"
import {
  parseShareToken,
  type AssessmentCard,
  type QuestionnairePayload,
  type SessionState,
  type ShareView,
} from "../../src/renderer/src/diagnostics/publicDiagnosticApi"

type CallRecord = {
  path: string
  method: string
  accessToken: string
  headers?: Record<string, string>
  body?: unknown
}

const calls: CallRecord[] = []
let routes: Record<string, (init: { method: string; body?: unknown }) => unknown> = {}

function installScriptedBridge(): void {
  calls.length = 0
  routes = {}
  const apiRequest = vi.fn(async (path: string, init: { method: string; body?: unknown; accessToken?: string; headers?: Record<string, string> }) => {
    calls.push({
      path,
      method: init.method,
      accessToken: init.accessToken ?? "",
      headers: init.headers,
      body: init.body,
    })
    const handler = routes[`${init.method} ${path}`]
    if (!handler) throw new Error(`unexpected ${init.method} ${path}`)
    return ok(handler(init))
  })
  installBridge(bridge({ apiRequest }))
}

function route(key: string, data: unknown, status = 200): void {
  routes[key] = () => ({ status, data, error: null })
}

function routeError(key: string, status: number, code: string, message: string): void {
  routes[key] = () => ({ status, data: null, error: { code, message } })
}

function slot(partial: {
  key: string
  label: string
  kind: "single" | "multi" | "text" | "long_text"
  required?: boolean
  options?: string[]
  show_if?: string[]
  hint?: string
  max_chars?: number
}): QuestionnairePayload["first_screen"][number] {
  return {
    key: partial.key,
    label: partial.label,
    kind: partial.kind,
    family: "测试族",
    required: partial.required ?? false,
    ...(partial.options ? { options: partial.options } : {}),
    ...(partial.show_if ? { show_if: partial.show_if } : {}),
    ...(partial.hint ? { hint: partial.hint } : {}),
    ...(partial.max_chars ? { max_chars: partial.max_chars } : {}),
  }
}

const questionnaire: QuestionnairePayload = {
  version: "diag-questionnaire-v0",
  first_screen: [
    slot({ key: "org.industry", label: "你所在的行业是？", kind: "single", required: true, options: ["制造与工业", "零售与消费"] }),
    slot({ key: "org.scale", label: "企业大约多少人？", kind: "single", required: true, options: ["20人以下", "100–499人"] }),
    slot({ key: "pol.qualification", label: "目前已具备哪些资质？（可多选）", kind: "multi", options: ["高新技术企业", "暂无"] }),
    slot({ key: "pol.declaration_history", label: "以前申报过政策项目或补贴吗？", kind: "single", options: ["从未申报过", "申报并通过"] }),
    slot({ key: "pol.digitalization_project", label: "现在有没有在推进的数字化改造？", kind: "single", required: true, options: ["已有在推进的数字化改造", "完全没有"] }),
  ],
  diagnostic: [
    slot({ key: "org.main_business", label: "主营业务是什么？", kind: "text", max_chars: 120 }),
    slot({ key: "sys.systems", label: "现在在用哪些系统？（可多选）", kind: "multi", options: ["ERP", "OA"] }),
    slot({ key: "sys.integration_status", label: "这些系统之间数据通不通？", kind: "single", options: ["互不相通", "部分互通"], show_if: ["sys.systems"] }),
    slot({ key: "ctx.free_text", label: "用你自己的话说说，现在最难的是什么？", kind: "long_text", max_chars: 600 }),
  ],
  total_questions: 9,
  notes: ["首屏 5 题出政策补贴测算卡（纯规则、零 AI、零成本），免注册即时可见。"],
}

function assessmentCard(overrides: Partial<AssessmentCard> = {}): AssessmentCard {
  return {
    readiness_tier: "方向契合但缺前提",
    matched_policies: [
      {
        policy_id: "POL-1",
        label: "中小企业数字化改造补贴（方向契合）",
        title: "中小企业数字化转型扶持政策",
        doc_number: "测试发〔2026〕1 号",
        issued_on: "2026-01-15",
        original_wording: "对实施数字化改造的中小企业按程序给予支持。",
        original_basis: "原文口径",
        official_source_url: "https://example.gov.cn/policy/1",
        snapshot_date: "2026-10-19",
        interpretation_basis: "我方解读",
        interpretation_note: "制造业企业且在推进数字化改造的，方向契合。",
      },
    ],
    missing_requirements: [{ policy_id: "POL-1", requirement: "规上工业企业资质", basis: "我方解读" }],
    next_actions: ["确认企业规模与资质口径"],
    policy_snapshot_date: "2026-10-19",
    basis_labels: { original: "原文口径", interpretation: "我方解读" },
    disclaimers: ["本卡只算资格与准备度，不涉及补贴金额。"],
    policy_corrections: [],
    ...overrides,
  }
}

function sessionState(overrides: Partial<SessionState> = {}): SessionState {
  return {
    id: "s-1",
    status: "draft",
    assessment: null,
    answered_slots: [],
    lead_captured: false,
    report: null,
    report_state: "none",
    report_requested_at: null,
    report_failure: null,
    share_available: false,
    source_type: "direct",
    expires_at: "2026-12-12T00:00:00+00:00",
    claim_window_expires_at: "2027-02-09T00:00:00+00:00",
    ...overrides,
  }
}

const createdSession = { ...sessionState(), token: "tok-123" }

function shareView(): ShareView {
  return {
    version: "diag-report-v2",
    generated_at: "2026-11-12T10:00:00+00:00",
    headline: "现状一句话：报价靠老师傅",
    findings: [{ id: "F1", title: "报价要问老工程师，一单两三天", stage: "报价与方案" }],
    first_step: { when: "一周内", what: "整理最近 10 单报价记录", output: "一页报价瓶颈清单" },
    policy_opportunities: [
      {
        policy_id: "POL-1",
        title: "中小企业数字化转型扶持政策",
        doc_number: "测试发〔2026〕1 号",
        issued_on: "2026-01-15",
        original_basis: "原文口径",
        official_text: "对实施数字化改造的中小企业按程序给予支持。",
        official_source_url: "https://example.gov.cn/policy/1",
        snapshot_date: "2026-10-19",
        interpretation_basis: "我方解读",
        our_reading: "制造业企业且在推进数字化改造的，方向契合。",
      },
    ],
    loop_completed: { identified: true, located: true, handled: false, written_back: false },
    notice: "这是诊断摘要。完整报告需留资后在本人的诊断会话内查看。",
  }
}

const readyReport = {
  version: "diag-report-v2",
  prompt_version: "diagnostic-report-prompt-v2",
  number_gate_version: "number-gate-v2",
  generated_at: "2026-11-12T10:00:00+00:00",
  layers: {
    situation: {
      headline: "现状一句话：报价靠老师傅",
      findings: [{ id: "F1", problem: "报价要问老工程师，一单两三天", stage: "报价与方案" }],
      open_questions: ["每月报价单量待澄清"],
    },
    action: {
      first_step: { when: "一周内", what: "整理最近 10 单报价记录", output: "一页报价瓶颈清单" },
      actions: [{ finding_id: "F1", action: "把报价口径写成清单", expected_output: "报价口径 v1" }],
      closing_loop: {
        identified: "报价瓶颈已识别",
        located: "卡在老师傅经验未沉淀",
        handled: "先做口径清单",
        written_back: "由平台回写台账",
      },
    },
    policy: { opportunities: shareView().policy_opportunities },
  },
  assessment_tier: "方向契合但缺前提",
  model: {},
}

async function fillFirstScreen(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.selectOptions(screen.getByLabelText(/你所在的行业是？/), "制造与工业")
  await user.selectOptions(screen.getByLabelText(/企业大约多少人？/), "100–499人")
  await user.click(screen.getByRole("checkbox", { name: "高新技术企业" }))
  await user.selectOptions(screen.getByLabelText(/以前申报过政策项目或补贴吗？/), "从未申报过")
  await user.selectOptions(screen.getByLabelText(/现在有没有在推进的数字化改造？/), "已有在推进的数字化改造")
}

beforeEach(() => {
  installScriptedBridge()
  route("GET /api/v1/diagnostics/questionnaire", questionnaire)
  route("POST /api/v1/diagnostics/sessions", createdSession)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe("获客诊断访客界面（公开面）", () => {
  it("parseShareToken 只放行 token_urlsafe 形态", () => {
    expect(parseShareToken("AbC_123-x")).toBe("AbC_123-x")
    expect(parseShareToken("a".repeat(128))).toBe("a".repeat(128))
    expect(parseShareToken("a".repeat(129))).toBeNull()
    expect(parseShareToken("bad token")).toBeNull()
    expect(parseShareToken("")).toBeNull()
    expect(parseShareToken("%E0%A4%A")).toBeNull()
  })

  it("开始测算：免注册建会话（空 accessToken、无自定义头），渲染首屏 5 题", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    expect(await screen.findByLabelText(/你所在的行业是？/)).toBeVisible()

    const questionnaireCall = calls.find((item) => item.path.endsWith("/questionnaire"))
    expect(questionnaireCall?.method).toBe("GET")
    expect(questionnaireCall?.accessToken).toBe("")
    expect(questionnaireCall?.headers).toBeUndefined()

    const sessionCall = calls.find((item) => item.path.endsWith("/sessions"))
    expect(sessionCall?.method).toBe("POST")
    expect(sessionCall?.accessToken).toBe("")
    expect(sessionCall?.headers).toBeUndefined()
    // 不臆造 source_type；channel_ref 只在 URL 带 ?channel_ref= 时透传。
    expect(sessionCall?.body).toEqual({})
  })

  it("首屏带「先看示例报告」入口（只读样例页，不采集访客信息）", async () => {
    render(<PublicDiagnosticPage />)
    const link = await screen.findByRole("link", { name: "先看示例报告" })
    expect(link).toHaveAttribute("href", "#diagnostics/sample")
  })

  it("首屏必填预检：缺必填不上传，提示缺的题", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    await screen.findByLabelText(/你所在的行业是？/)
    await user.click(screen.getByRole("button", { name: "生成测算卡" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "请先回答：你所在的行业是？、企业大约多少人？、现在有没有在推进的数字化改造？",
    )
    expect(calls.find((item) => item.path.endsWith("/session/assessment"))).toBeUndefined()
  })

  it("提交首屏：令牌只走 X-Diagnostic-Token 头，测算卡渲染档位＋原文/解读双层", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    await screen.findByLabelText(/你所在的行业是？/)
    await fillFirstScreen(user)
    route("POST /api/v1/diagnostics/session/assessment", { ...sessionState(), assessment: assessmentCard(), status: "submitted" })
    await user.click(screen.getByRole("button", { name: "生成测算卡" }))

    expect(await screen.findByText("方向契合但缺前提")).toBeVisible()
    const assessmentCall = calls.find((item) => item.path.endsWith("/session/assessment"))
    expect(assessmentCall?.accessToken).toBe("")
    expect(assessmentCall?.headers?.["x-diagnostic-token"]).toBe("tok-123")
    expect(assessmentCall?.body).toEqual({
      answers: {
        "org.industry": "制造与工业",
        "org.scale": "100–499人",
        "pol.qualification": ["高新技术企业"],
        "pol.declaration_history": "从未申报过",
        "pol.digitalization_project": "已有在推进的数字化改造",
      },
    })
    // 原文口径/我方解读双层分键渲染，出处与快照日期在场。
    expect(screen.getByText("对实施数字化改造的中小企业按程序给予支持。")).toBeVisible()
    expect(screen.getByText(/制造业企业且在推进数字化改造的，方向契合。/)).toBeVisible()
    expect(screen.getByText("本卡只算资格与准备度，不涉及补贴金额。")).toBeVisible()
  })

  it("深度诊断：show_if 条件显隐（未答 sys.systems 不问互通性），提交只带上本轮槽位", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    await screen.findByLabelText(/你所在的行业是？/)
    await fillFirstScreen(user)
    route("POST /api/v1/diagnostics/session/assessment", { ...sessionState(), assessment: assessmentCard(), status: "submitted" })
    await user.click(screen.getByRole("button", { name: "生成测算卡" }))
    await user.click(await screen.findByRole("button", { name: "继续深度诊断" }))

    expect(screen.queryByLabelText(/这些系统之间数据通不通？/)).toBeNull()
    await user.click(screen.getByRole("checkbox", { name: "ERP" }))
    expect(await screen.findByLabelText(/这些系统之间数据通不通？/)).toBeVisible()

    route("POST /api/v1/diagnostics/session/answers", { ...sessionState(), assessment: assessmentCard(), answered_slots: ["sys.systems"], status: "submitted" })
    await user.click(screen.getByRole("button", { name: "提交深度诊断" }))
    await screen.findByText(/提交并生成完整报告/)

    const answersCall = calls.find((item) => item.path.endsWith("/session/answers"))
    expect(answersCall?.headers?.["x-diagnostic-token"]).toBe("tok-123")
    expect(answersCall?.body).toEqual({ answers: { "sys.systems": ["ERP"] } })
  })

  it("留资 consent 硬闸＋报告轮询 ready：完整报告渲染，分享链接明文只此一次", async () => {
    // 轮询是 3s 真实 interval：用真实定时器＋放宽 findBy 超时（假定时器会停摆
    // RTL 的 waitFor；仓内惯例见 ai-execution——fake timers 只用于纯定时渲染）。
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    await screen.findByLabelText(/你所在的行业是？/)
    await fillFirstScreen(user)
    route("POST /api/v1/diagnostics/session/assessment", { ...sessionState(), assessment: assessmentCard(), status: "submitted" })
    await user.click(screen.getByRole("button", { name: "生成测算卡" }))
    await user.click(await screen.findByRole("button", { name: "跳过，直接留资" }))

    // consent 未勾：客户端先拦（服务端 consent_required 400 是兜底闸）。
    await user.type(await screen.findByLabelText("联系方式 *"), "13800000000")
    await user.click(screen.getByRole("button", { name: "提交并生成完整报告" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("需同意隐私政策与用途说明后才能获取完整报告。")
    expect(calls.find((item) => item.path.endsWith("/session/lead"))).toBeUndefined()

    await user.click(screen.getByRole("checkbox", { name: /我已阅读并同意/ }))
    route("POST /api/v1/diagnostics/session/lead", { ...sessionState(), lead_captured: true, status: "submitted" })
    route("POST /api/v1/diagnostics/session/report", { ...sessionState(), lead_captured: true, report_state: "requested", report_requested_at: "2026-11-12T10:00:00+00:00" }, 202)
    route("GET /api/v1/diagnostics/session", {
      ...sessionState(),
      lead_captured: true,
      report_state: "ready",
      report: readyReport,
      status: "report_ready",
    })
    await user.click(screen.getByRole("button", { name: "提交并生成完整报告" }))

    expect(await screen.findByText(/报告正在生成/)).toBeVisible()
    // 第一跳轮询（~3s）即 ready。
    expect(
      await screen.findByRole("heading", { name: "现状一句话：报价靠老师傅" }, { timeout: 8_000 }),
    ).toBeVisible()
    expect(screen.getByText(/每月报价单量待澄清/)).toBeVisible()
    expect(screen.getByText(/识别：报价瓶颈已识别/)).toBeVisible()

    const leadCall = calls.find((item) => item.path.endsWith("/session/lead"))
    expect(leadCall?.body).toEqual({ contact: "13800000000", consent: true })
    const reportCall = calls.find((item) => item.path.endsWith("/session/report"))
    expect(reportCall?.headers?.["x-diagnostic-token"]).toBe("tok-123")
    // 恰一跳轮询即就绪（未空转）。
    expect(calls.filter((item) => item.method === "GET" && item.path.endsWith("/session"))).toHaveLength(1)

    // 分享：明文只此一次；页面生成的是 hash 路由链接（令牌可入 URL 的只读凭证）。
    route("POST /api/v1/diagnostics/session/share", {
      ...sessionState(),
      lead_captured: true,
      report_state: "ready",
      report: readyReport,
      share_available: true,
      share_token: "share-tok-1",
      share_path: "/api/v1/diagnostics/share/share-tok-1",
      status: "report_ready",
    })
    await user.click(screen.getByRole("button", { name: "生成分享链接" }))
    expect(await screen.findByText(/分享链接（只此一次，请立即复制）/)).toBeVisible()
    expect(screen.getByText(/#diagnostics\/share\/share-tok-1/)).toBeVisible()
  })

  it("报告失败：失败原因就地呈现，重试按钮重新受理", async () => {
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    await screen.findByLabelText(/你所在的行业是？/)
    await fillFirstScreen(user)
    route("POST /api/v1/diagnostics/session/assessment", { ...sessionState(), assessment: assessmentCard(), status: "submitted" })
    await user.click(screen.getByRole("button", { name: "生成测算卡" }))
    await user.click(await screen.findByRole("button", { name: "跳过，直接留资" }))
    await user.type(await screen.findByLabelText("联系方式 *"), "13800000000")
    await user.click(screen.getByRole("checkbox", { name: /我已阅读并同意/ }))
    route("POST /api/v1/diagnostics/session/lead", { ...sessionState(), lead_captured: true, status: "submitted" })
    route("POST /api/v1/diagnostics/session/report", { ...sessionState(), lead_captured: true, report_state: "requested" }, 202)
    route("GET /api/v1/diagnostics/session", {
      ...sessionState(),
      lead_captured: true,
      report_state: "failed",
      report_failure: { code: "report_model_unavailable", message: "诊断服务暂不可用，请稍后重试。" },
      status: "submitted",
    })
    await user.click(screen.getByRole("button", { name: "提交并生成完整报告" }))
    expect(
      await screen.findByText(/报告生成失败：诊断服务暂不可用/, undefined, { timeout: 8_000 }),
    ).toBeVisible()

    let retryCount = 0
    routes["POST /api/v1/diagnostics/session/report"] = () => {
      retryCount += 1
      return { status: 202, data: { ...sessionState(), lead_captured: true, report_state: "requested" }, error: null }
    }
    await user.click(screen.getByRole("button", { name: "重试生成" }))
    expect(await screen.findByText(/报告正在生成/)).toBeVisible()
    expect(retryCount).toBe(1)
  })

  it("部署闸默认关：404 ⇒ 「暂未开放」引导，不猜原因", async () => {
    routeError("GET /api/v1/diagnostics/questionnaire", 404, "not_found", "")
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    expect(await screen.findByRole("heading", { name: "诊断服务暂未开放" })).toBeVisible()
    expect(calls.find((item) => item.path.endsWith("/sessions"))).toBeUndefined()
  })

  it("闸关时仍给示例报告入口（示例页是静态展示面，不依赖诊断服务开闸）", async () => {
    routeError("GET /api/v1/diagnostics/questionnaire", 404, "not_found", "")
    const user = userEvent.setup()
    render(<PublicDiagnosticPage />)
    await user.click(await screen.findByRole("button", { name: "开始测算" }))
    expect(await screen.findByRole("heading", { name: "诊断服务暂未开放" })).toBeVisible()
    const entry = screen.getByRole("link", { name: "先看示例报告" })
    expect(entry).toHaveAttribute("href", "#diagnostics/sample")
  })
})

describe("分享只读页（公开面摘要层）", () => {
  it("渲染摘要：结论＋第一步＋政策机会＋闭环存在性，不含自填原文", async () => {
    route("GET /api/v1/diagnostics/share/share-tok-1", shareView())
    render(<PublicDiagnosticSharePage shareToken="share-tok-1" />)
    expect(await screen.findByRole("heading", { name: "现状一句话：报价靠老师傅" })).toBeVisible()
    expect(screen.getByText("这是诊断摘要。完整报告需留资后在本人的诊断会话内查看。")).toBeVisible()
    expect(screen.getByText(/整理最近 10 单报价记录/)).toBeVisible()
    expect(screen.getByText("○ 已处置")).toBeVisible()
    expect(screen.getByText("✓ 已识别")).toBeVisible()
    const call = calls.find((item) => item.path.endsWith("/share/share-tok-1"))
    expect(call?.accessToken).toBe("")
    expect(call?.headers).toBeUndefined()
  })

  it("令牌失效（404）⇒ 链接已失效页", async () => {
    routeError("GET /api/v1/diagnostics/share/gone", 404, "share_not_found", "分享链接不存在或已轮换。")
    render(<PublicDiagnosticSharePage shareToken="gone" />)
    expect(await screen.findByRole("heading", { name: "链接已失效" })).toBeVisible()
  })
})
