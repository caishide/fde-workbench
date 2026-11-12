import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"

import { BRAND_NAME, PRODUCT_NAME } from "../../../shared/brand"
import {
  DIAGNOSTIC_ANSWERS_URL,
  DIAGNOSTIC_ASSESSMENT_URL,
  DIAGNOSTIC_LEAD_URL,
  DIAGNOSTIC_QUESTIONNAIRE_URL,
  DIAGNOSTIC_REPORT_URL,
  DIAGNOSTIC_SESSIONS_URL,
  DIAGNOSTIC_SESSION_URL,
  DIAGNOSTIC_SHARE_URL,
  hasAnswer,
  isSlotVisible,
  missingRequiredLabels,
  publicApiRequest,
  shareRouteHash,
  toggleMultiAnswer,
  type AnswerValue,
  type AssessmentCard,
  type DiagnosticSlot,
  type QuestionnairePayload,
  type SessionState,
  type SessionWithToken,
  type ShareLinkPayload,
} from "./publicDiagnosticApi"
import { ReportView } from "./ReportView"

/**
 * 获客诊断访客界面（**公开面**：未登录可达；获客诊断 T-14a）。
 *
 * 外部入口名＝「政策补贴测算」（P-1 拍板口径）。互惠顺序照 D-2 拍板：
 * 首屏 5 题先出**纯规则测算卡**（零 AI、免注册即时可见），13 题深度诊断
 * 可选续填，联系方式在完整报告解锁时才收（consent 硬闸）。
 *
 * 会话令牌只在组件内存（React state）：持有即权凭证，绝不入 URL、不落
 * localStorage——刷新即失效，访客重新开始即可（服务端留存 30 天自然过期）。
 * 承载体是本仓访客 UI（桌面与 web 发行形态共用 main.tsx→App）；官网公开
 * 部署（独立轻部署/域名/开闸）属 D-3 业务决策，挂账 T-14b。
 */

type Stage = "intro" | "first" | "assessment" | "diagnostic" | "lead" | "pending" | "ready" | "failed"

const POLL_INTERVAL_MS = 3_000
const POLL_MAX_ATTEMPTS = 100
const CHANNEL_REF_MAX_CHARS = 80

function readChannelRef(): string | null {
  const raw = new URLSearchParams(window.location.search).get("channel_ref")?.trim() ?? ""
  if (!raw) return null
  return raw.length > CHANNEL_REF_MAX_CHARS ? raw.slice(0, CHANNEL_REF_MAX_CHARS) : raw
}

export function PublicDiagnosticPage() {
  const [stage, setStage] = useState<Stage>("intro")
  const [questionnaire, setQuestionnaire] = useState<QuestionnairePayload | null>(null)
  const [session, setSession] = useState<SessionWithToken | null>(null)
  // token 用 ref 转手给轮询闭包：session state 更新不重挂轮询。
  const tokenRef = useRef<string | null>(null)
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [gateClosed, setGateClosed] = useState(false)
  // 留资表单
  const [contact, setContact] = useState("")
  const [leadName, setLeadName] = useState("")
  const [leadRegion, setLeadRegion] = useState("")
  const [consent, setConsent] = useState(false)
  const [shareLink, setShareLink] = useState("")

  const call = useCallback(
    async <T,>(path: string, method: "GET" | "POST", body?: unknown): Promise<
      { ok: true; data: T } | { ok: false; message: string; gateClosed?: boolean }
    > => {
      const result = await publicApiRequest<T>(path, {
        method,
        ...(body === undefined ? {} : { body }),
        ...(tokenRef.current ? { token: tokenRef.current } : {}),
      })
      if (!result.ok) {
        return {
          ok: false,
          message: result.error.message,
          gateClosed: result.status === 404,
        }
      }
      return { ok: true, data: result.data }
    },
    [],
  )

  async function start(): Promise<void> {
    if (busy) return
    setBusy(true)
    setError("")
    setGateClosed(false)
    try {
      const questionnaireResult = await call<QuestionnairePayload>(DIAGNOSTIC_QUESTIONNAIRE_URL, "GET")
      if (!questionnaireResult.ok) {
        setGateClosed(Boolean(questionnaireResult.gateClosed))
        setError(questionnaireResult.gateClosed ? "" : questionnaireResult.message)
        return
      }
      const channelRef = readChannelRef()
      const sessionResult = await call<SessionWithToken>(DIAGNOSTIC_SESSIONS_URL, "POST", {
        // source_type 不臆造（缺省 direct）——partner 归因由服务端按渠道注册表推导。
        ...(channelRef ? { channel_ref: channelRef } : {}),
      })
      if (!sessionResult.ok) {
        setGateClosed(Boolean(sessionResult.gateClosed))
        setError(sessionResult.gateClosed ? "" : sessionResult.message)
        return
      }
      const created = sessionResult.data
      setQuestionnaire(questionnaireResult.data)
      setSession(created)
      tokenRef.current = created.token
      setStage("first")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接服务，请稍后重试。")
    } finally {
      setBusy(false)
    }
  }

  async function submitFirstScreen(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!questionnaire || busy) return
    const missing = missingRequiredLabels(questionnaire.first_screen, answers)
    if (missing.length > 0) {
      setError(`请先回答：${missing.join("、")}`)
      return
    }
    await submitAnswers(DIAGNOSTIC_ASSESSMENT_URL, "first", questionnaire.first_screen)
  }

  async function submitDiagnostic(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!questionnaire || busy) return
    const missing = missingRequiredLabels(questionnaire.diagnostic, answers)
    if (missing.length > 0) {
      setError(`请先回答：${missing.join("、")}`)
      return
    }
    await submitAnswers(DIAGNOSTIC_ANSWERS_URL, "lead", questionnaire.diagnostic)
  }

  async function submitAnswers(url: string, next: Stage, slots: DiagnosticSlot[]): Promise<void> {
    if (!session || busy) return
    setBusy(true)
    setError("")
    try {
      // 只上传本轮表单的可见且已答槽位（不回传其他阶段旧答案；服务端闭集
      // 校验仍是权威，这里只是最小提交面）。
      const keys = new Set(slots.map((slot) => slot.key))
      const scoped = Object.fromEntries(
        Object.entries(answers).filter(([key, value]) => keys.has(key) && hasAnswer(value)),
      )
      const result = await call<SessionState>(url, "POST", { answers: scoped })
      if (!result.ok) {
        setError(result.message)
        return
      }
      setSession({ ...session, ...result.data, token: session.token })
      if (next === "first") setStage("assessment")
      else setStage("lead")
    } finally {
      setBusy(false)
    }
  }

  async function submitLead(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!session || busy) return
    if (!contact.trim()) {
      setError("请填写联系方式。")
      return
    }
    // consent 硬闸：客户端与服务端双闸（服务端 consent_required 400 兜底）。
    if (!consent) {
      setError("需同意隐私政策与用途说明后才能获取完整报告。")
      return
    }
    setBusy(true)
    setError("")
    try {
      const leadResult = await call<SessionState>(DIAGNOSTIC_LEAD_URL, "POST", {
        contact: contact.trim(),
        ...(leadName.trim() ? { name: leadName.trim() } : {}),
        ...(leadRegion.trim() ? { region: leadRegion.trim() } : {}),
        consent: true,
      })
      if (!leadResult.ok) {
        setError(leadResult.message)
        return
      }
      setSession({ ...session, ...leadResult.data, token: session.token })
      const reportResult = await call<SessionState>(DIAGNOSTIC_REPORT_URL, "POST")
      if (!reportResult.ok) {
        setError(reportResult.message)
        return
      }
      setSession({ ...session, ...reportResult.data, token: session.token })
      setStage("pending")
    } finally {
      setBusy(false)
    }
  }

  // 报告轮询：202 受理后 3s 一次，直到 ready／failed／超时上限。
  useEffect(() => {
    if (stage !== "pending" || !session) return
    let cancelled = false
    let attempts = 0
    const timer = window.setInterval(async () => {
      if (cancelled || !tokenRef.current) return
      attempts += 1
      if (attempts > POLL_MAX_ATTEMPTS) {
        cancelled = true
        window.clearInterval(timer)
        setError("报告生成时间较长，请稍后刷新页面重试（会话仍在生成中）。")
        setStage("failed")
        return
      }
      const result = await publicApiRequest<SessionState>(DIAGNOSTIC_SESSION_URL, {
        method: "GET",
        token: tokenRef.current,
      })
      if (cancelled || !result.ok) return
      const current = result.data
      if (current.report_state === "ready") {
        cancelled = true
        window.clearInterval(timer)
        setSession({ ...session, ...current, token: session.token })
        setStage("ready")
      } else if (current.report_state === "failed") {
        cancelled = true
        window.clearInterval(timer)
        setSession({ ...session, ...current, token: session.token })
        setStage("failed")
      }
    }, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [stage, session])

  async function requestShare(): Promise<void> {
    if (!session || busy) return
    setBusy(true)
    setError("")
    try {
      const result = await call<ShareLinkPayload>(DIAGNOSTIC_SHARE_URL, "POST")
      if (!result.ok) {
        setError(result.message)
        return
      }
      setShareLink(`${window.location.origin}${window.location.pathname}${shareRouteHash(result.data.share_token)}`)
    } finally {
      setBusy(false)
    }
  }

  async function retryReport(): Promise<void> {
    if (!session || busy) return
    setBusy(true)
    setError("")
    try {
      const reportResult = await call<SessionState>(DIAGNOSTIC_REPORT_URL, "POST")
      if (!reportResult.ok) {
        setError(reportResult.message)
        return
      }
      setSession({ ...session, ...reportResult.data, token: session.token })
      setStage("pending")
    } finally {
      setBusy(false)
    }
  }

  if (gateClosed) {
    return (
      <section className="page public-diagnostic-page">
        <header className="page-heading">
          <p className="eyebrow">{BRAND_NAME} · 政策补贴测算</p>
          <h1>诊断服务暂未开放</h1>
          <p>该服务正在部署准备中，暂未对外开放。开放后可免注册使用。</p>
        </header>
      </section>
    )
  }

  return (
    <section className="page public-diagnostic-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">{BRAND_NAME} · 免注册诊断</p>
          <h1>政策补贴测算</h1>
          <p>回答 5 个问题，立即得到一份政策补贴资格测算卡；完整诊断报告需要留资解锁。</p>
        </div>
      </header>
      {error ? <p role="alert" className="form-error banner">{error}</p> : null}

      {stage === "intro" ? (
        <div className="public-diagnostic-card">
          <ol className="diag-steps">
            <li>回答首屏 5 题（行业、规模、资质、申报历史、数字化改造）</li>
            <li>立即看到政策补贴测算卡——只算资格与准备度，不编造金额</li>
            <li>可选：再答 13 题深度诊断，报告更准</li>
            <li>留下联系方式并同意用途说明，解锁完整诊断报告</li>
          </ol>
          <ul className="diag-notes">
            {(questionnaire?.notes ?? [
              "首屏 5 题出政策补贴测算卡（纯规则、零 AI、零成本），免注册即时可见。",
              "联系方式不在问卷里问——完整报告解锁时才收。",
              "留空的槽位会在报告里标「待澄清」，不会被编造补齐。",
            ]).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div className="form-actions">
            <button className="primary-button" type="button" onClick={() => void start()} disabled={busy}>
              {busy ? "正在准备…" : "开始测算"}
            </button>
            <a className="secondary-button diag-sample-entry" href="#diagnostics/sample">
              先看示例报告
            </a>
          </div>
        </div>
      ) : null}

      {stage === "first" && questionnaire ? (
        <form className="public-diagnostic-card" onSubmit={submitFirstScreen}>
          <SlotFields
            slots={questionnaire.first_screen}
            answers={answers}
            onAnswer={(key, value) => setAnswers((current) => ({ ...current, [key]: value }))}
          />
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "正在测算…" : "生成测算卡"}
            </button>
          </div>
        </form>
      ) : null}

      {stage === "assessment" && session?.assessment ? (
        <div className="public-diagnostic-stack">
          <AssessmentCardView card={session.assessment} />
          <div className="public-diagnostic-card">
            <p>想更准？再答 {questionnaire?.diagnostic.length ?? 13} 题深度诊断（约 5 分钟，可留空），或直接留资解锁完整报告。</p>
            <div className="form-actions">
              <button className="primary-button" type="button" onClick={() => setStage("diagnostic")}>
                继续深度诊断
              </button>
              <button className="secondary-button" type="button" onClick={() => setStage("lead")}>
                跳过，直接留资
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {stage === "diagnostic" && questionnaire ? (
        <form className="public-diagnostic-card" onSubmit={submitDiagnostic}>
          <SlotFields
            slots={questionnaire.diagnostic.filter((slot) => isSlotVisible(slot, answers))}
            answers={answers}
            onAnswer={(key, value) => setAnswers((current) => ({ ...current, [key]: value }))}
          />
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "正在提交…" : "提交深度诊断"}
            </button>
            <button className="secondary-button" type="button" onClick={() => setStage("lead")}>
              留空跳过，直接留资
            </button>
          </div>
        </form>
      ) : null}

      {stage === "lead" ? (
        <form className="public-diagnostic-card" onSubmit={submitLead}>
          <p>完整诊断报告（AI 生成，约几分钟）将在提交后开始准备。</p>
          <label className="field">
            <span>联系方式 *</span>
            <input
              value={contact}
              onChange={(event) => setContact(event.target.value)}
              maxLength={200}
              placeholder="手机号或微信号"
              required
            />
          </label>
          <label className="field">
            <span>怎么称呼（可选）</span>
            <input value={leadName} onChange={(event) => setLeadName(event.target.value)} maxLength={80} />
          </label>
          <label className="field">
            <span>所在区域（可选）</span>
            <input value={leadRegion} onChange={(event) => setLeadRegion(event.target.value)} maxLength={80} placeholder="如：浙江省" />
          </label>
          <label className="diag-consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              我已阅读并同意：联系方式仅用于本次诊断结果的跟进与交付沟通，不作其他用途；
              企业信息按代号化口径存储，自填原文不出分享页。
            </span>
          </label>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "正在提交…" : "提交并生成完整报告"}
            </button>
          </div>
        </form>
      ) : null}

      {stage === "pending" ? (
        <div className="public-diagnostic-card">
          <p role="status">报告正在生成，通常需要几分钟……页面会自动刷新，请勿关闭。</p>
        </div>
      ) : null}

      {stage === "failed" ? (
        <div className="public-diagnostic-card">
          <p role="alert">
            {session?.report_failure
              ? `报告生成失败：${session.report_failure.message}`
              : "报告生成尚未完成。"}
          </p>
          <div className="form-actions">
            <button className="primary-button" type="button" onClick={() => void retryReport()} disabled={busy}>
              重试生成
            </button>
          </div>
        </div>
      ) : null}

      {stage === "ready" && session?.report ? (
        <div className="public-diagnostic-stack">
          <ReportView report={session.report} />
          <div className="public-diagnostic-card diag-share-box">
            <p>想把这份诊断转给同事或合伙人？生成只读分享链接（含摘要，不含你的自填原文与联系方式；每次生成会使旧链接失效）。</p>
            {shareLink ? (
              <p className="diag-share-link" role="status">
                <span>分享链接（只此一次，请立即复制）：</span>
                <code>{shareLink}</code>
              </p>
            ) : null}
            <div className="form-actions">
              <button className="primary-button" type="button" onClick={() => void requestShare()} disabled={busy}>
                {shareLink ? "重新生成分享链接" : "生成分享链接"}
              </button>
              {shareLink ? (
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void navigator.clipboard?.writeText(shareLink)}
                >
                  复制链接
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      <footer className="public-diagnostic-footer">
        <span>{PRODUCT_NAME} · 本测算为规则生成，不构成申报结论；申报口径以当地主管部门为准。</span>
      </footer>
    </section>
  )
}

function SlotFields({
  slots,
  answers,
  onAnswer,
}: {
  slots: DiagnosticSlot[]
  answers: Record<string, AnswerValue>
  onAnswer: (key: string, value: AnswerValue) => void
}) {
  return (
    <div className="diag-slot-list">
      {slots.map((slot) => (
        <SlotField key={slot.key} slot={slot} answers={answers} onAnswer={onAnswer} />
      ))}
    </div>
  )
}

function SlotField({
  slot,
  answers,
  onAnswer,
}: {
  slot: DiagnosticSlot
  answers: Record<string, AnswerValue>
  onAnswer: (key: string, value: AnswerValue) => void
}) {
  const current = answers[slot.key]
  const inputId = `diag-slot-${slot.key.replace(/[^\w.-]/g, "_")}`
  return (
    <div className="diag-slot">
      <label className="diag-slot-label" htmlFor={inputId}>
        <span>
          {slot.label}
          {slot.required ? " *" : ""}
        </span>
        {slot.hint ? <em className="diag-slot-hint">{slot.hint}</em> : null}
      </label>
      {slot.kind === "single" ? (
        <select
          id={inputId}
          className="diag-input"
          value={typeof current === "string" ? current : ""}
          onChange={(event) => onAnswer(slot.key, event.target.value)}
        >
          <option value="">请选择…</option>
          {(slot.options ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      ) : null}
      {slot.kind === "multi" ? (
        <div className="diag-option-group" role="group" aria-label={slot.label}>
          {(slot.options ?? []).map((option) => {
            const checked = Array.isArray(current) && current.includes(option)
            return (
              <label key={option} className="diag-option">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onAnswer(slot.key, toggleMultiAnswer(current, option))}
                />
                <span>{option}</span>
              </label>
            )
          })}
        </div>
      ) : null}
      {slot.kind === "text" ? (
        <input
          id={inputId}
          className="diag-input"
          value={typeof current === "string" ? current : ""}
          maxLength={slot.max_chars || 200}
          onChange={(event) => onAnswer(slot.key, event.target.value)}
        />
      ) : null}
      {slot.kind === "long_text" ? (
        <textarea
          id={inputId}
          className="diag-input"
          rows={3}
          value={typeof current === "string" ? current : ""}
          maxLength={slot.max_chars || 600}
          onChange={(event) => onAnswer(slot.key, event.target.value)}
        />
      ) : null}
    </div>
  )
}

/** 测算卡：定性档位＋政策条目（原文口径/我方解读双层）——无分数无金额。 */
function AssessmentCardView({ card }: { card: AssessmentCard }) {
  return (
    <div className="public-diagnostic-card diag-assessment">
      <p className="diag-tier" role="status">
        <span className="diag-tier-label">测算档位</span>
        <strong>{card.readiness_tier}</strong>
      </p>
      {card.matched_policies.length > 0 ? (
        <section className="diag-section">
          <h2>可能匹配的政策（{card.matched_policies.length} 条）</h2>
          {card.matched_policies.map((policy) => (
            <article key={policy.policy_id} className="diag-policy-card">
              <h3>{policy.title}</h3>
              <p className="diag-policy-meta">
                {policy.doc_number} · {policy.issued_on} · {policy.label}
              </p>
              <div className="diag-basis">
                <p className="diag-basis-original">
                  <strong>{policy.original_basis}</strong>
                  <span>{policy.original_wording}</span>
                </p>
                <p className="diag-basis-interpretation">
                  <strong>{policy.interpretation_basis}</strong>
                  <span>{policy.interpretation_note}</span>
                </p>
              </div>
              <p className="diag-policy-meta">
                出处：<a href={policy.official_source_url} target="_blank" rel="noreferrer noopener">{policy.official_source_url}</a>
                （快照 {policy.snapshot_date}）
              </p>
            </article>
          ))}
        </section>
      ) : (
        <section className="diag-section">
          <p>按当前答案没有匹配到政策条目——先做基础准备，再回来测算。</p>
        </section>
      )}
      {card.missing_requirements.length > 0 ? (
        <section className="diag-section">
          <h2>尚缺的前提</h2>
          <ul>
            {card.missing_requirements.map((item) => (
              <li key={`${item.policy_id}:${item.requirement}`}>{item.requirement}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {card.next_actions.length > 0 ? (
        <section className="diag-section">
          <h2>下一步建议</h2>
          <ol>
            {card.next_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
        </section>
      ) : null}
      <section className="diag-disclaimers">
        <ul>
          {card.disclaimers.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>
    </div>
  )
}
