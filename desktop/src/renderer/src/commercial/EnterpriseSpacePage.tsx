import { useEffect, useState } from "react"

import { useAuth } from "../auth/AuthProvider"

/**
 * 企业空间视图（登录后；绑定账号本人或 admin）。
 *
 * 读面 `GET /api/v1/commercial/enterprise-spaces/<subject_key>`：主体登记、
 * 免费额度状态、交付状态（自助／已选付费）、三档分流入口、付费选项与当前
 * 选择、交付项目、分流决定历史。
 *
 * **零数值呈现**：付费选项的标签与描述由服务端单一权威下发，桌面端原样呈现，
 * 不自造第二份措辞，也不推导任何金额。
 */

interface SpaceQuota {
  subject_key: string
  state: string
  bound_user_id: string | null
  completed_at: string | null
  enterprise_confirmed_at: string | null
}

interface SpacePayload {
  subject: { subject_key: string; display_name: string; problem_description: string | null }
  quota: SpaceQuota
  engagement_state: "self_service" | "paid_delivery"
  space: {
    registration_entry: Record<string, string>
    projects: { project_id: string; project_code: string; name: string; status: string }[]
  }
  triage_decisions: { id: string; tier: string; rationale: string | null; decided_at: string | null }[]
  paid_options: {
    options: Record<string, { label: string; description: string; follow_up: string }>
    current_choice: { id: string; option_key: string; option_label: string; chosen_at: string | null } | null
    advisor_follow_up: string
  }
  registration_entries: Record<string, Record<string, string>>
}

const SUBJECT_STORAGE_KEY = "fde.enterprise.subject_key"

export function EnterpriseSpacePage() {
  const { apiRequest } = useAuth()
  const [subjectKey, setSubjectKey] = useState("")
  const [space, setSpace] = useState<SpacePayload | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    try {
      const remembered = window.localStorage.getItem(SUBJECT_STORAGE_KEY)
      if (remembered) setSubjectKey(remembered)
    } catch {
      // 本地存储不可用——不阻断（用户可手填）
    }
  }, [])

  async function load(key: string): Promise<void> {
    const trimmed = key.trim()
    if (!trimmed) {
      setError("请填写统一社会信用代码。")
      return
    }
    setBusy(true)
    setError("")
    setNotice("")
    try {
      const payload = await apiRequest<SpacePayload>(
        `/api/v1/commercial/enterprise-spaces/${encodeURIComponent(trimmed)}`,
        { method: "GET" },
      )
      setSpace(payload)
      try {
        window.localStorage.setItem(SUBJECT_STORAGE_KEY, trimmed)
      } catch {
        // 本地存储不可用——不阻断
      }
    } catch (caught) {
      setSpace(null)
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  async function chooseOption(optionKey: string): Promise<void> {
    if (!space || busy) return
    setBusy(true)
    setError("")
    setNotice("")
    try {
      await apiRequest<unknown>(
        `/api/v1/commercial/enterprise-spaces/${encodeURIComponent(space.subject.subject_key)}/paid-option-choices`,
        { method: "POST", body: { option_key: optionKey } },
      )
      // 先复读刷新再落提示——load() 会清空提示位，顺序颠倒则成功提示被吞
      await load(space.subject.subject_key)
      setNotice("已记录你的付费选项选择。")
    } catch (caught) {
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="page enterprise-space-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">企业自助</p>
          <h1>企业空间</h1>
          <p>查看本主体的免费诊断额度、当前分流与已选付费选项。</p>
        </div>
      </header>
      {error ? <p role="alert" className="form-error banner">{error}</p> : null}
      {notice ? <p role="status" className="notice">{notice}</p> : null}
      <form
        className="extension-stack"
        onSubmit={(event) => {
          event.preventDefault()
          void load(subjectKey)
        }}
      >
        <label className="field">
          <span>统一社会信用代码</span>
          <input value={subjectKey} onChange={(event) => setSubjectKey(event.target.value)} />
        </label>
        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "正在读取…" : "读取企业空间"}
          </button>
        </div>
      </form>

      {space ? (
        <>
          <section className="panel" aria-labelledby="enterprise-subject-heading">
            <div className="panel-heading">
              <div>
                <h2 id="enterprise-subject-heading">主体</h2>
              </div>
            </div>
            <p>企业名称：{space.subject.display_name}</p>
            <p>统一社会信用代码：{space.subject.subject_key}</p>
            <p>业务问题：{space.subject.problem_description ?? "未登记"}</p>
            <p>免费额度状态：{space.quota.state}</p>
            <p>交付状态：{space.engagement_state === "paid_delivery" ? "已选付费交付" : "自助服务"}</p>
          </section>

          <section className="panel" aria-labelledby="enterprise-options-heading">
            <div className="panel-heading">
              <div>
                <h2 id="enterprise-options-heading">付费选项</h2>
                <p>诊断完成后可选；选项措辞由服务端单一权威下发，此处原样呈现。</p>
              </div>
            </div>
            {space.paid_options.current_choice ? (
              <p>当前选择：{space.paid_options.current_choice.option_label}</p>
            ) : (
              <p>当前尚未选择付费选项。</p>
            )}
            <ul className="extension-stack">
              {Object.entries(space.paid_options.options).map(([key, option]) => (
                <li key={key}>
                  <strong>{option.label}</strong>
                  <span>{option.description}</span>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void chooseOption(key)}
                  >
                    选择此选项
                  </button>
                </li>
              ))}
            </ul>
            <p>{space.paid_options.advisor_follow_up}</p>
          </section>

          <section className="panel" aria-labelledby="enterprise-projects-heading">
            <div className="panel-heading">
              <div>
                <h2 id="enterprise-projects-heading">交付项目</h2>
              </div>
            </div>
            {space.space.projects.length === 0 ? (
              <p>暂无关联交付项目。</p>
            ) : (
              <ul className="extension-stack">
                {space.space.projects.map((item) => (
                  <li key={item.project_id}>
                    {item.project_code} · {item.name}（{item.status}）
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </section>
  )
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "读取企业空间失败。"
}
