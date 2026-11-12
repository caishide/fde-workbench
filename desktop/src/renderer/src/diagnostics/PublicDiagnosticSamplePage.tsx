import { useState } from "react"

import { BRAND_NAME, PRODUCT_NAME } from "../../../shared/brand"
import { ReportView } from "./ReportView"
import { SAMPLE_CASES, type SampleCase } from "./sampleReport"

/**
 * 工具内**示例报告**页（**公开面**：未登录可达；获客诊断 T-13′）。
 *
 * 纪律（任务书 R-6「展示不冒充实测」／P-8「案例集一池三用」）：
 *
 * 1. 每则示例都带**角标**（示例案例 · 据公开案例整理／脱敏真实交付 · 代号化），
 *    角标与页面顶部声明同时在场——任何场合都不得呈现为实时诊断结果。
 * 2. 页脚写明「非实时生成」，报告底部写「示例整理日期」而不是「生成于」。
 * 3. 示例内容**无分数、无评级百分比、无补贴金额**（R-1／R-4）；政策条目里的
 *    数字只来自政策引文原文。
 * 4. 页面只读：不收集任何访客信息；去测算的入口另给。
 */
export function PublicDiagnosticSamplePage() {
  const [activeCaseId, setActiveCaseId] = useState<string>(SAMPLE_CASES[0]?.caseId ?? "")
  const activeCase: SampleCase | undefined =
    SAMPLE_CASES.find((item) => item.caseId === activeCaseId) ?? SAMPLE_CASES[0]

  return (
    <section className="page public-diagnostic-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">{BRAND_NAME} · 示例报告</p>
          <h1>诊断报告长什么样</h1>
          <p>下面是按公开案例整理与内部交付件脱敏改写的示例报告，结构与真实诊断报告一致。</p>
        </div>
      </header>

      <div className="diag-sample-notice" role="note">
        <p className="diag-sample-notice-title">示例内容 · 非实时诊断结果</p>
        <ul>
          <li>下列报告均为<strong>示例</strong>：由公开案例整理或内部交付件脱敏改写而来，不是对任何企业的实时诊断。</li>
          <li>示例内不含评分、评级百分比与补贴金额——未溯源的数字一律不写。</li>
          <li>报告中的政策条目逐条给出原文口径与我方解读，并附官方出处与快照日期。</li>
        </ul>
      </div>

      <div className="diag-sample-switch" role="group" aria-label="示例案例切换">
        {SAMPLE_CASES.map((item) => (
          <button
            key={item.caseId}
            type="button"
            className={item.caseId === activeCase?.caseId ? "primary-button" : "secondary-button"}
            aria-pressed={item.caseId === activeCase?.caseId}
            onClick={() => setActiveCaseId(item.caseId)}
          >
            {item.title}
          </button>
        ))}
      </div>

      {activeCase ? (
        <div className="public-diagnostic-stack">
          <div className="public-diagnostic-card diag-sample-meta">
            <p className="diag-sample-badge">{activeCase.badge}</p>
            <h2 className="diag-sample-title">{activeCase.title}</h2>
            <p className="diag-sample-summary">{activeCase.summary}</p>
            <p className="diag-sample-attribution">{activeCase.attribution}</p>
            {activeCase.note ? <p className="diag-sample-note">{activeCase.note}</p> : null}
          </div>
          <ReportView report={activeCase.report} footerNote={`示例整理日期 ${activeCase.report.generated_at}（非实时生成）`} />
        </div>
      ) : null}

      <div className="public-diagnostic-card">
        <p>想看针对你自己情况的测算？走一遍免注册测算，首屏 5 题即可看到政策补贴测算卡。</p>
        <div className="form-actions">
          <a className="primary-button" href="#diagnostics">去做测算</a>
        </div>
      </div>

      <footer className="public-diagnostic-footer">
        {PRODUCT_NAME} · 示例报告由公开案例与脱敏交付件整理而成，不构成申报结论；申报口径以当地主管部门为准。
      </footer>
    </section>
  )
}
