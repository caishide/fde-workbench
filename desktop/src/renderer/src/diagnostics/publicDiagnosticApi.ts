// 获客诊断 T-14a：免注册访客界面的公开面调用层。
//
// 纪律（与 server/src/fde_api/diagnostics/ 的公网写面纪律对齐）：
// - **一律 accessToken: ""**（公开面＝桥不下发 Authorization 头）；会话令牌
//   只走 ``X-Diagnostic-Token`` 自定义头（shared/api-safety.ts 允许名单唯一
//   头）——**绝不入 URL**（URL 进访问日志，令牌是持有即权凭证）。
// - 会话令牌只存在调用方内存（React state），不落 localStorage——刷新即失效，
//   访客重新开始即可（服务端留存期 30 天，孤儿会话自然过期）。
// - ``channel_ref`` 只透传，**不臆造 source_type**——partner 归因由服务端
//   按渠道注册表推导（T-15）。
// - 部署闸默认关 ⇒ 一切端点 404：界面呈现「暂未开放」引导，不猜原因。

import type { ApiMethod } from "../../../shared/contracts"

export const DIAGNOSTIC_QUESTIONNAIRE_URL = "/api/v1/diagnostics/questionnaire"
export const DIAGNOSTIC_SESSIONS_URL = "/api/v1/diagnostics/sessions"
export const DIAGNOSTIC_SESSION_URL = "/api/v1/diagnostics/session"
export const DIAGNOSTIC_ASSESSMENT_URL = "/api/v1/diagnostics/session/assessment"
export const DIAGNOSTIC_ANSWERS_URL = "/api/v1/diagnostics/session/answers"
export const DIAGNOSTIC_LEAD_URL = "/api/v1/diagnostics/session/lead"
export const DIAGNOSTIC_REPORT_URL = "/api/v1/diagnostics/session/report"
export const DIAGNOSTIC_SHARE_URL = "/api/v1/diagnostics/session/share"
/** 分享只读视图的读面基址（写令牌走 /session/share 生成，读令牌走 /share/<token>）。 */
export const DIAGNOSTIC_SHARE_READ_URL = "/api/v1/diagnostics/share"

export function shareRouteHash(shareToken: string): string {
  return `#diagnostics/share/${encodeURIComponent(shareToken)}`
}

export function parseShareToken(raw: string): string | null {
  const decoded = (() => {
    try {
      return decodeURIComponent(raw)
    } catch {
      return null
    }
  })()
  if (!decoded) return null
  // 与服务端 token_urlsafe 同字符集；长度上界与 CUSTOM_HEADER_VALUE_PATTERN 一致。
  return /^[A-Za-z0-9_-]{1,128}$/.test(decoded) ? decoded : null
}

// ── 服务端对外形态（只声明界面消费的字段；服务端是唯一权威） ──────────

export interface DiagnosticSlot {
  key: string
  label: string
  kind: "single" | "multi" | "text" | "long_text"
  family: string
  required: boolean
  options?: string[]
  max_chars?: number
  show_if?: string[]
  hint?: string
}

export interface QuestionnairePayload {
  version: string
  first_screen: DiagnosticSlot[]
  diagnostic: DiagnosticSlot[]
  total_questions: number
  notes: string[]
}

export interface PolicyItem {
  policy_id: string
  label: string
  title: string
  doc_number: string
  issued_on: string
  original_wording: string
  original_basis: string
  official_source_url: string
  snapshot_date: string
  interpretation_basis: string
  interpretation_note: string
}

export interface MissingRequirement {
  policy_id: string
  requirement: string
  basis: string
}

export interface AssessmentCard {
  readiness_tier: string
  matched_policies: PolicyItem[]
  missing_requirements: MissingRequirement[]
  next_actions: string[]
  policy_snapshot_date: string
  basis_labels: { original: string; interpretation: string }
  disclaimers: string[]
  policy_corrections: string[]
}

export interface ReportFinding {
  id: string
  problem: string
  stage: string
}

export interface PolicyOpportunity {
  policy_id: string
  title: string
  doc_number: string
  issued_on: string
  original_basis: string
  official_text: string
  official_source_url: string
  snapshot_date: string
  interpretation_basis: string
  our_reading: string
}

export interface ReportDoc {
  version: string
  prompt_version: string
  number_gate_version: string
  generated_at: string
  layers: {
    situation: {
      headline: string
      findings: ReportFinding[]
      open_questions: string[]
    }
    action: {
      first_step: { when: string; what: string; output: string }
      actions: { finding_id: string; action: string; expected_output: string }[]
      closing_loop: {
        identified: string
        located: string
        handled: string
        written_back: string
      }
    }
    policy: { opportunities: PolicyOpportunity[] }
  }
  assessment_tier?: string
  model: Record<string, unknown>
}

export type ReportState = "none" | "requested" | "ready" | "failed"

export interface SessionState {
  id: string
  status: string
  assessment: AssessmentCard | null
  answered_slots: string[]
  lead_captured: boolean
  report: ReportDoc | null
  report_state: ReportState
  report_requested_at: string | null
  report_failure: { code: string; message: string } | null
  share_available: boolean
  source_type: string
  expires_at: string | null
  claim_window_expires_at: string | null
}

export interface SessionWithToken extends SessionState {
  /** 明文令牌：创建响应**只此一次**，此后只走 X-Diagnostic-Token 头。 */
  token: string
}

export interface ShareLinkPayload extends SessionState {
  share_token: string
  share_path: string
}

export interface ShareView {
  version: string | null
  generated_at: string | null
  headline: string | null
  findings: { id: string; title: string | null; stage: string | null }[]
  first_step: { when: string; what: string; output: string } | null
  policy_opportunities: PolicyOpportunity[]
  loop_completed: {
    identified: boolean
    located: boolean
    handled: boolean
    written_back: boolean
  }
  notice: string
}

// ── 调用层 ──────────────────────────────────────────────────────────

export interface PublicApiError {
  code: string
  message: string
}

export type PublicCall<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number | null; error: PublicApiError }

export interface PublicRequestInit {
  method: ApiMethod
  body?: unknown
  /** 匿名会话令牌：只在内存里转手，只进请求头。 */
  token?: string
}

export async function publicApiRequest<T>(
  path: string,
  init: PublicRequestInit,
): Promise<PublicCall<T>> {
  const result = await window.fde.api.request<T>(path, {
    method: init.method,
    // 公开面：空令牌＝桥不下发 Authorization 头。
    accessToken: "",
    ...(init.body === undefined ? {} : { body: init.body }),
    ...(init.token ? { headers: { "x-diagnostic-token": init.token } } : {}),
  })
  if (!result.ok) {
    return { ok: false, status: null, error: result.error }
  }
  const payload = result.data
  if (payload.error !== null || payload.data === null) {
    return {
      ok: false,
      status: payload.status,
      error: payload.error ?? { code: "invalid_api_response", message: "服务返回了无效响应。" },
    }
  }
  return { ok: true, status: payload.status, data: payload.data }
}

// ── 问卷答案的客户端形状与显隐判定 ────────────────────────────────

/** 答案值：single/text/long_text 是字符串，multi 是字符串数组。 */
export type AnswerValue = string | string[]

export function hasAnswer(value: AnswerValue | undefined): boolean {
  if (value === undefined) return false
  if (Array.isArray(value)) return value.some((item) => item.trim() !== "")
  return value.trim() !== ""
}

/** 条件显隐：依赖槽位任一有值即显示（服务端 to_dict 的 show_if 语义）。 */
export function isSlotVisible(slot: DiagnosticSlot, answers: Record<string, AnswerValue>): boolean {
  if (!slot.show_if || slot.show_if.length === 0) return true
  return slot.show_if.some((key) => hasAnswer(answers[key]))
}

/** 服务端闭集校验的客户端预检：required 槽位必须有值（服务端仍是权威）。 */
export function missingRequiredLabels(
  slots: DiagnosticSlot[],
  answers: Record<string, AnswerValue>,
): string[] {
  return slots
    .filter((slot) => slot.required && isSlotVisible(slot, answers) && !hasAnswer(answers[slot.key]))
    .map((slot) => slot.label)
}

/** multi 槽位的 toggle 帮手（不可变更新）。 */
export function toggleMultiAnswer(current: AnswerValue | undefined, option: string): string[] {
  const list = Array.isArray(current) ? current : []
  return list.includes(option) ? list.filter((item) => item !== option) : [...list, option]
}
