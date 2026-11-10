import { useState, type FormEvent } from "react"

import type { ApiResponse, BridgeResult } from "../../../shared/contracts"

/**
 * 企业自助注册（**公开面**：未登录可达）。
 *
 * 走 `window.fde.api.request` 直连而不经 api client——api client 无会话即
 * 抛 ``authentication_required``，而注册入口本就是免鉴权入口（服务端按
 * 来源 IP 限流 ＋ 当事人自证 USCC）。
 *
 * **只提交代号与必要登记信息**：企业名称按工作台口径以代号登记；真实资料
 * 留在客户本地工作目录，工作台不存正文。
 */

interface RegistrationResult {
  user_id: string
  username: string
  subject_key: string
  quota_created: boolean
  quota_state: string | null
}

const REGISTRATION_URL = "/api/v1/commercial/enterprise-registrations"

export function EnterpriseRegisterPage() {
  const [displayName, setDisplayName] = useState("")
  const [subjectKey, setSubjectKey] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [problemDescription, setProblemDescription] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError("")
    setNotice("")
    try {
      const result = await window.fde.api.request<RegistrationResult>(REGISTRATION_URL, {
        method: "POST",
        accessToken: "",
        body: {
          username,
          display_name: displayName,
          password,
          subject_key: subjectKey,
          problem_description: problemDescription,
        },
      })
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      const payload: ApiResponse<RegistrationResult> = result.data
      if (payload.status !== 200 || !payload.data) {
        setError(payload.error?.message ?? "注册失败，请稍后重试。")
        return
      }
      setNotice(
        `注册成功：账号 ${payload.data.username}，主体 ${payload.data.subject_key}。` +
          "请用该账号登录后进入企业空间查看额度与分流。",
      )
      setPassword("")
    } catch (caught) {
      setError(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="page enterprise-register-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">企业自助</p>
          <h1>企业注册</h1>
          <p>一个主体一份免费诊断额度；企业名称请以代号登记，真实资料留在贵方工作目录。</p>
        </div>
      </header>
      {error ? <p role="alert" className="form-error banner">{error}</p> : null}
      {notice ? <p role="status" className="notice">{notice}</p> : null}
      <form onSubmit={submit} className="extension-stack">
        <label className="field">
          <span>企业名称（代号）</span>
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
        </label>
        <label className="field">
          <span>统一社会信用代码</span>
          <input value={subjectKey} onChange={(event) => setSubjectKey(event.target.value)} required />
        </label>
        <label className="field">
          <span>账号</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} required autoComplete="username" />
        </label>
        <label className="field">
          <span>密码</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required autoComplete="new-password" />
        </label>
        <label className="field">
          <span>要解决的业务问题</span>
          <textarea value={problemDescription} onChange={(event) => setProblemDescription(event.target.value)} required />
        </label>
        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? "正在提交…" : "提交注册"}
          </button>
        </div>
      </form>
    </section>
  )
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "注册失败，请稍后重试。"
}
