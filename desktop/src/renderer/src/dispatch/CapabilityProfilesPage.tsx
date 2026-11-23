import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"

import { PASSWORD_MAX_LENGTH } from "../../../shared/contracts"
import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"
import { Modal, UiButton } from "../components/ui"

/** P2-1（派单设计 §3.2/§6.5）：能力档案 + 产能看板——四域分只用于等级晋级
 *  评定（短板决定），不进排序；同时接单上限=产能÷单均自动算（不可手工设）。 */

export interface CapabilityProfileView {
  user_id: string
  username: string
  display_name: string
  level: string | null
  status: string
  is_active?: boolean
  can_enable?: boolean
  scores: {
    biz_cognition: number
    scenario_eng: number
    ai_tech: number
    delivery_assure: number
  }
  industry_tags: string[]
  module_tags: string[]
  home_city: string | null
  geo_fence_km: number
  monthly_capacity_hours: number | null
  avg_delivery_hours: number | null
  in_hand: number
  capacity_cap: number
}

const LEVEL_LABELS: Record<string, string> = {
  L1: "L1 助理场景工程师",
  L2: "L2 场景工程师",
  L3: "L3 高级场景工程师",
  L4: "L4 首席场景工程师",
}

export function isProfileView(value: unknown): value is CapabilityProfileView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return typeof row.user_id === "string" && typeof row.username === "string"
}

export function loadLevel(profile: CapabilityProfileView): number {
  // 负载率 = 在途 ÷ 上限（§6.5 容量过滤口径；只做硬过滤展示，不进排序）
  if (profile.capacity_cap <= 0) return 1
  return Math.min(profile.in_hand / profile.capacity_cap, 1)
}

export function CapabilityProfilesPage() {
  const { apiRequest, user } = useAuth()
  const isAdmin = user?.role === "admin"
  const [profiles, setProfiles] = useState<CapabilityProfileView[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [target, setTarget] = useState<CapabilityProfileView | null>(null)
  const [password, setPassword] = useState("")
  const [actionError, setActionError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState("")
  const [registering, setRegistering] = useState(false)
  const [userId, setUserId] = useState("")
  const [city, setCity] = useState("")
  const actionOpen = registering || target !== null
  const requestSequence = useRef(0)

  const load = useCallback(() => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError("")
    void apiRequest<unknown>("/api/v1/dispatch/profiles", { method: "GET" })
      .then((payload) => {
        if (sequence !== requestSequence.current) return
        // goal-d9 fix: apiRequest already unwraps the {data,error} envelope (latent bug family)
        setProfiles(Array.isArray(payload) ? payload.filter(isProfileView) : [])
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return
        setError(
          caught instanceof ApiClientError ? caught.message : "能力档案加载失败，请稍后重试。"
        )
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false)
      })
  }, [apiRequest])

  useEffect(() => {
    load()
  }, [load])

  function closeDialog(): void {
    setPassword("")
    setActionError("")
    setTarget(null)
    setRegistering(false)
    setUserId("")
    setCity("")
  }

  async function submitProfileAction(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!isAdmin || !password || submitting) return
    const requestedId = registering ? userId.trim() : target?.user_id
    if (!requestedId || (!registering && target?.can_enable !== true)) return
    setSubmitting(true)
    setActionError("")
    try {
      const data = await apiRequest<{ user_id: string; is_active: boolean; changed: boolean }>(
        registering
          ? "/api/v1/admin/dispatch/profiles"
          : `/api/v1/admin/dispatch/profiles/${encodeURIComponent(requestedId)}/enable`,
        {
          method: "POST",
          body: registering
            ? { user_id: requestedId, home_city: city.trim() || null, confirm_password: password }
            : { confirm_password: password },
        },
      )
      if (data?.user_id !== requestedId || typeof data.changed !== "boolean") {
        throw new Error("Invalid profile action response")
      }
      if (registering) {
        setNotice(data.changed ? "已登记派单档案。" : "该账号已有派单档案。")
        load()
      } else {
        if (data.is_active !== true) throw new Error("Invalid profile enable response")
        setProfiles((rows) => rows.map((row) => (
          row.user_id === requestedId ? { ...row, is_active: true, can_enable: false } : row
        )))
        setNotice(data.changed ? "已启用派单档案。" : "该派单档案已启用。")
      }
      closeDialog()
    } catch (caught) {
      setActionError(
        caught instanceof ApiClientError ? caught.message : "未能确认操作结果，请刷新档案核对。",
      )
    } finally {
      setPassword("")
      setSubmitting(false)
    }
  }

  return (
    <section className="page" aria-label="能力档案与产能看板">
      <header className="page-header">
        <div>
          <h1>能力档案与产能看板</h1>
          <p className="page-subtitle">
            四域分是等级晋级评定维度（短板决定），不进派单排序；负载=在途÷上限，仅作容量硬过滤。
            等级核验证据链（goal-d11 M10）支持引用工作台评审会纪要：source_uri 填
            <code>workbench-minutes:&lt;meeting_id&gt;</code>，sha256 必须等于该纪要 sealed_sha256。
          </p>
        </div>
        <div className="dialog-actions">
          <button className="secondary-button" type="button" onClick={load} disabled={actionOpen}>
            刷新
          </button>
          {isAdmin ? (
            <UiButton
              variant="primary"
              disabled={actionOpen}
              onClick={() => {
                setNotice("")
                setRegistering(true)
              }}
            >
              登记派单档案
            </UiButton>
          ) : null}
        </div>
      </header>
      {loading ? <p className="muted">加载中…</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {!loading && !error && profiles.length === 0 ? (
        <p className="muted">供给池暂无档案。</p>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      <table className="dispatch-profile-table">
        <thead>
          <tr>
            <th>交付方</th>
            <th>等级</th>
            <th>四域（认知/场景/AI/保障）</th>
            <th>常驻城市</th>
            <th>行业标签</th>
            <th>在途/上限</th>
            <th>负载</th>
            <th>档案状态</th>
            <th>派单启用</th>
            {isAdmin ? <th>操作</th> : null}
          </tr>
        </thead>
        <tbody>
          {profiles.map((row) => (
            <tr key={row.user_id}>
              <td>{row.display_name || row.username}</td>
              <td>{row.level ? LEVEL_LABELS[row.level] || row.level : "未定级"}</td>
              <td>
                {row.scores.biz_cognition}/{row.scores.scenario_eng}/
                {row.scores.ai_tech}/{row.scores.delivery_assure}
              </td>
              <td>{row.home_city || "—"}</td>
              <td>{row.industry_tags.length ? row.industry_tags.join("、") : "—"}</td>
              <td>
                {row.in_hand}/{row.capacity_cap}
              </td>
              <td>
                <span
                  className={`load-bar${loadLevel(row) >= 1 ? " load-full" : ""}`}
                  role="img"
                  aria-label={`负载 ${Math.round(loadLevel(row) * 100)}%`}
                >
                  {Math.round(loadLevel(row) * 100)}%
                </span>
              </td>
              <td>{row.status}</td>
              <td>{row.is_active === true ? "已启用" : row.is_active === false ? "未启用" : "未知"}</td>
              {isAdmin ? (
                <td>
                  {row.can_enable === true && row.is_active === false && row.status === "active" ? (
                    <UiButton
                      disabled={loading || Boolean(error) || actionOpen}
                      onClick={() => {
                        setNotice("")
                        setTarget(row)
                      }}
                      aria-label={`启用派单档案：${row.display_name || row.username}`}
                    >
                      启用派单档案
                    </UiButton>
                  ) : "—"}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
      {actionOpen && isAdmin ? (
        <Modal
          title={registering ? "登记派单档案" : "启用派单档案"}
          description={target
            ? `确认启用 ${target.display_name || target.username}（${target.username}）的派单档案。`
            : "交付者账号须通过供给池审核，并已获得商业交付资格。登记后可按档案状态另行启用。"}
          busy={submitting}
          onClose={closeDialog}
        >
          <form onSubmit={(event) => void submitProfileAction(event)}>
            {registering ? (
              <>
                <label className="field">
                  <span>交付者账号 ID</span>
                  <input
                    type="text"
                    maxLength={36}
                    value={userId}
                    disabled={submitting}
                    onChange={(event) => setUserId(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>常驻城市（选填）</span>
                  <input
                    type="text"
                    maxLength={32}
                    value={city}
                    disabled={submitting}
                    onChange={(event) => setCity(event.target.value)}
                  />
                </label>
              </>
            ) : null}
            <label className="field">
              <span>当前账号密码</span>
              <input
                type="password"
                autoComplete="current-password"
                maxLength={PASSWORD_MAX_LENGTH}
                value={password}
                disabled={submitting}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
            <div className="dialog-actions">
              <UiButton disabled={submitting} onClick={closeDialog}>取消</UiButton>
              <UiButton
                variant="primary"
                type="submit"
                disabled={!password || submitting || (registering && !userId.trim())}
              >
                {submitting ? "正在提交…" : registering ? "确认登记" : "确认启用"}
              </UiButton>
            </div>
          </form>
        </Modal>
      ) : null}
    </section>
  )
}
