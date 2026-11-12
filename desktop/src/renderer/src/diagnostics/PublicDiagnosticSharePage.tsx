import { useEffect, useState } from "react"

import { BRAND_NAME } from "../../../shared/brand"
import { DIAGNOSTIC_SHARE_READ_URL, publicApiRequest, type ShareView } from "./publicDiagnosticApi"

/**
 * 诊断报告分享只读页（**公开面**：可入 URL 的只读凭证）。
 *
 * 服务端只给**摘要层**（结论＋第一步＋政策机会＋问题标题＋闭环存在性），
 * 不含企业自填原文与联系方式——留资闸不被分享链接绕过（D-2）。令牌轮换
 * 后旧链接 404：呈现「链接已失效」而不是猜测原因。
 */
export function PublicDiagnosticSharePage({ shareToken }: { shareToken: string }) {
  const [view, setView] = useState<ShareView | null>(null)
  const [state, setState] = useState<"loading" | "ready" | "gone" | "error">("loading")
  const [message, setMessage] = useState("")

  useEffect(() => {
    let cancelled = false
    async function load(): Promise<void> {
      const result = await publicApiRequest<ShareView>(`${DIAGNOSTIC_SHARE_READ_URL}/${encodeURIComponent(shareToken)}`, {
        method: "GET",
      })
      if (cancelled) return
      if (result.ok) {
        setView(result.data)
        setState("ready")
        return
      }
      if (result.status === 404) {
        setState("gone")
        return
      }
      setState("error")
      setMessage(result.error.message)
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [shareToken])

  if (state === "loading") {
    return (
      <section className="page public-diagnostic-page">
        <p role="status">正在读取诊断摘要……</p>
      </section>
    )
  }
  if (state === "gone") {
    return (
      <section className="page public-diagnostic-page">
        <header className="page-heading">
          <p className="eyebrow">{BRAND_NAME} · 诊断分享</p>
          <h1>链接已失效</h1>
          <p>分享链接可能已被重新生成（每次生成会使旧链接失效），或该诊断会话已过期。</p>
        </header>
      </section>
    )
  }
  if (state === "error" || !view) {
    return (
      <section className="page public-diagnostic-page">
        <p role="alert" className="form-error banner">{message || "读取失败，请稍后重试。"}</p>
      </section>
    )
  }

  return (
    <section className="page public-diagnostic-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">{BRAND_NAME} · 诊断摘要（只读）</p>
          <h1>{view.headline ?? "诊断摘要"}</h1>
          <p className="diag-share-notice">{view.notice}</p>
        </div>
      </header>
      <div className="public-diagnostic-stack">
        {view.findings.length > 0 ? (
          <div className="public-diagnostic-card">
            <h2>识别到的问题</h2>
            <ul className="diag-findings">
              {view.findings.map((finding) => (
                <li key={finding.id}>
                  <strong>{finding.stage}</strong>
                  <span>{finding.title}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {view.first_step ? (
          <div className="public-diagnostic-card">
            <h2>第一步</h2>
            <p className="diag-first-step">
              {view.first_step.when}：{view.first_step.what}——产出：{view.first_step.output}
            </p>
          </div>
        ) : null}
        {view.policy_opportunities.length > 0 ? (
          <div className="public-diagnostic-card">
            <h2>政策与申报机会</h2>
            {view.policy_opportunities.map((opportunity) => (
              <article key={opportunity.policy_id} className="diag-policy-card">
                <h3>{opportunity.title}</h3>
                <p className="diag-policy-meta">{opportunity.doc_number} · {opportunity.issued_on}</p>
                <div className="diag-basis">
                  <p className="diag-basis-original">
                    <strong>{opportunity.original_basis}</strong>
                    <span>{opportunity.official_text}</span>
                  </p>
                  <p className="diag-basis-interpretation">
                    <strong>{opportunity.interpretation_basis}</strong>
                    <span>{opportunity.our_reading}</span>
                  </p>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        <div className="public-diagnostic-card">
          <h2>诊断闭环</h2>
          <ul className="diag-loop-state">
            <li className={view.loop_completed.identified ? "done" : "todo"}>{view.loop_completed.identified ? "✓" : "○"} 已识别</li>
            <li className={view.loop_completed.located ? "done" : "todo"}>{view.loop_completed.located ? "✓" : "○"} 已定位</li>
            <li className={view.loop_completed.handled ? "done" : "todo"}>{view.loop_completed.handled ? "✓" : "○"} 已处置</li>
            <li className={view.loop_completed.written_back ? "done" : "todo"}>{view.loop_completed.written_back ? "✓" : "○"} 已回写</li>
          </ul>
        </div>
      </div>
      <footer className="public-diagnostic-footer">
        <span>完整报告需留资后在本人的诊断会话内查看。</span>
      </footer>
    </section>
  )
}
