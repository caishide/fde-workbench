export interface ProjectBasics {
  name: string
  enterpriseCode: string
  projectCode: string
  openfdeEngagement: string
  fdeopsWorkspace: string
  background: string
  notes: string
  plannedStartDate: string
  plannedEndDate: string
}

export const emptyProjectBasics: ProjectBasics = {
  name: "",
  enterpriseCode: "",
  projectCode: "",
  openfdeEngagement: "",
  fdeopsWorkspace: "",
  background: "",
  notes: "",
  plannedStartDate: "",
  plannedEndDate: "",
}

export function ProjectBasicsStep({
  value,
  onChange,
}: {
  value: ProjectBasics
  onChange(value: ProjectBasics): void
}) {
  return (
    <section className="panel wizard-panel" aria-labelledby="project-basics-title">
      <h2 id="project-basics-title">1. 基础信息</h2>
      <p className="supporting-copy">先确定项目和客户代号；联系人/电话/地址等实名信息不进本系统（A2 代号化），只在 fdeops/openfde 里维护。</p>
      <div className="wizard-form-grid">
        <Field label="项目名称" id="project-name" required>
          <input id="project-name" required maxLength={160} value={value.name} onChange={(event) => onChange({ ...value, name: event.target.value })} />
        </Field>
        <Field label="客户代号" id="enterprise-code" required>
          <input id="enterprise-code" required maxLength={80} placeholder="客户A·行业·城市" value={value.enterpriseCode} onChange={(event) => onChange({ ...value, enterpriseCode: event.target.value })} />
          <small className="field-hint">格式「客户A·行业·城市」，三段两枚「·」；实名映射只在 fdeops/openfde。</small>
        </Field>
        <Field label="项目编号" id="project-code">
          <input id="project-code" maxLength={40} value={value.projectCode} onChange={(event) => onChange({ ...value, projectCode: event.target.value })} />
        </Field>
        <Field label="openfde engagement" id="openfde-engagement">
          <input id="openfde-engagement" maxLength={100} placeholder="知识轨 slug（可后补）" value={value.openfdeEngagement} onChange={(event) => onChange({ ...value, openfdeEngagement: event.target.value })} />
        </Field>
        <Field label="fdeops 工作区" id="fdeops-workspace">
          <input id="fdeops-workspace" maxLength={160} placeholder="流程轨目录名（可后补）" value={value.fdeopsWorkspace} onChange={(event) => onChange({ ...value, fdeopsWorkspace: event.target.value })} />
        </Field>
        <Field label="计划开始日期" id="planned-start-date" required>
          <input id="planned-start-date" required type="date" value={value.plannedStartDate} onChange={(event) => onChange({ ...value, plannedStartDate: event.target.value })} />
        </Field>
        <Field label="计划结束日期" id="planned-end-date">
          <input id="planned-end-date" type="date" min={value.plannedStartDate || undefined} value={value.plannedEndDate} onChange={(event) => onChange({ ...value, plannedEndDate: event.target.value })} />
        </Field>
        <Field label="项目背景" id="project-background" wide>
          <textarea id="project-background" rows={3} value={value.background} onChange={(event) => onChange({ ...value, background: event.target.value })} />
        </Field>
        <Field label="备注" id="project-notes" wide>
          <textarea id="project-notes" rows={3} value={value.notes} onChange={(event) => onChange({ ...value, notes: event.target.value })} />
        </Field>
      </div>
    </section>
  )
}

function Field({
  id,
  label,
  required = false,
  wide = false,
  children,
}: {
  id: string
  label: string
  required?: boolean
  wide?: boolean
  children: React.ReactNode
}) {
  return (
    <div className={`field${wide ? " wide-field" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  )
}
