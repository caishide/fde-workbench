import type { ReportDoc } from "./publicDiagnosticApi"

/**
 * 报告渲染的**单一真身**——活体诊断报告、工具内示例报告共用这一份组件，
 * 两边不会各长各的（结构改一处两边同时生效）。
 */

/** 诊断闭环四步（服务端契约闭集）→ 展示层中文标签。 */
const STAGE_LABELS: Record<string, string> = {
  identify: "识别",
  locate: "定位",
  handle: "处置",
  writeback: "回写",
}

/**
 * 阶段标签展示：闭集值翻成中文；**未命中闭集的值原样透传**——
 * 不臆造译名，也不吞掉未知值（自由文本阶段名照原样显示）。
 */
export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

export type ReportViewProps = {
  report: ReportDoc
  /**
   * 报告底部说明覆盖。示例报告传「示例整理日期 …」——
   * 不得写成「生成于」（示例不是实时诊断结果）。
   */
  footerNote?: string
}

/** 完整报告三层渲染（现状与问题／定位与处置／政策与申报机会）。 */
export function ReportView({ report, footerNote }: ReportViewProps) {
  const situation = report.layers.situation
  const action = report.layers.action
  const closing = action.closing_loop
  return (
    <article className="public-diagnostic-card diag-report">
      <h2 className="diag-report-headline">{situation.headline}</h2>
      <section className="diag-section">
        <h3>现状与问题</h3>
        <ul className="diag-findings">
          {situation.findings.map((finding) => (
            <li key={finding.id}>
              <strong>{stageLabel(finding.stage)}</strong>
              <span>{finding.problem}</span>
            </li>
          ))}
        </ul>
        {situation.open_questions.length > 0 ? (
          <div className="diag-open-questions">
            <h4>待澄清</h4>
            <ul>
              {situation.open_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
      <section className="diag-section">
        <h3>第一步</h3>
        <p className="diag-first-step">
          {action.first_step.when}：{action.first_step.what}——产出：{action.first_step.output}
        </p>
        {action.actions.length > 0 ? (
          <ol className="diag-actions">
            {action.actions.map((item) => (
              <li key={`${item.finding_id}:${item.action}`}>
                {item.action}
                <em>产出：{item.expected_output}</em>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
      <section className="diag-section">
        <h3>闭环四步</h3>
        <ol className="diag-loop">
          <li>识别：{closing.identified}</li>
          <li>定位：{closing.located}</li>
          <li>处置：{closing.handled}</li>
          <li>回写：{closing.written_back}</li>
        </ol>
      </section>
      {report.layers.policy.opportunities.length > 0 ? (
        <section className="diag-section">
          <h3>政策与申报机会</h3>
          {report.layers.policy.opportunities.map((opportunity) => (
            <article key={opportunity.policy_id} className="diag-policy-card">
              <h4>{opportunity.title}</h4>
              <p className="diag-policy-meta">
                {opportunity.doc_number} · {opportunity.issued_on}
              </p>
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
              <p className="diag-policy-meta">
                出处：<a href={opportunity.official_source_url} target="_blank" rel="noreferrer noopener">{opportunity.official_source_url}</a>
                （快照 {opportunity.snapshot_date}）
              </p>
            </article>
          ))}
        </section>
      ) : null}
      <p className="diag-report-meta">
        报告版本 {report.version} · {footerNote ?? `生成于 ${report.generated_at}`}
      </p>
    </article>
  )
}
