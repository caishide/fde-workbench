import { useCallback, useEffect, useRef, useState } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"
import { useConfirm } from "../common/ConfirmProvider"

/** 获客诊断 T-15：渠道链接管理（admin 专属；任务书 §3 T-15）。
 *
 * 服务端语义（本面板只消费不臆造）：
 * - ``partner`` 归因（A 档＝未来收费档种子）**只能**由有效渠道链接 token
 *   服务端推导——链接是渠道报备的唯一凭证，面板是平台发链接的唯一入口；
 * - **明文 token 只此一次**：创建响应返回明文（拼进专属链接交付渠道方），
 *   库里只有 sha256——关闭提示后不再可见；
 * - 停用是**软撤**：历史归因不改写（归因在会话创建时刻定格），新会话不再
 *   解析为 partner（降档 direct）；
 * - ``lead_count``＝经该链接归因的在册线索数（渠道方对账可见）。 */

export interface ChannelLinkRow {
  id: string
  region_name: string | null
  note: string | null
  is_active: boolean
  deactivated_at: string | null
  created_by_user_id: string | null
  created_at: string | null
  lead_count: number
}

export function isChannelLinkRow(value: unknown): value is ChannelLinkRow {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return typeof row.id === "string" && typeof row.is_active === "boolean"
}

const LINKS_PREFIX = "/api/v1/diagnostics/leads/channel-links"

export function ChannelLinksPanel() {
  const { apiRequest } = useAuth()
  const confirm = useConfirm()

  const [links, setLinks] = useState<ChannelLinkRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState("")
  const [unavailable, setUnavailable] = useState(false)

  const [region, setRegion] = useState("")
  const [note, setNote] = useState("")
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")
  // 明文 token 只此一次：创建成功后就地呈现，用户复制后手动关闭。
  const [freshToken, setFreshToken] = useState("")

  const [busyLinkId, setBusyLinkId] = useState("")
  const [actionError, setActionError] = useState("")
  const [actionNotice, setActionNotice] = useState("")

  const requestSequence = useRef(0)

  const load = useCallback(() => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setLoadError("")
    setUnavailable(false)
    void apiRequest<unknown>(LINKS_PREFIX, { method: "GET" })
      .then((payload) => {
        if (sequence !== requestSequence.current) return
        setLinks(Array.isArray(payload) ? payload.filter(isChannelLinkRow) : [])
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return
        if (caught instanceof ApiClientError && caught.status === 404) {
          setUnavailable(true)
        } else {
          setLoadError(
            caught instanceof ApiClientError ? caught.message : "渠道链接清单加载失败，请稍后重试。",
          )
        }
      })
      .finally(() => {
        if (sequence !== requestSequence.current) return
        setLoading(false)
      })
  }, [apiRequest])

  useEffect(() => {
    load()
  }, [load])

  function createLink(): void {
    setCreating(true)
    setCreateError("")
    setActionError("")
    setActionNotice("")
    void apiRequest<unknown>(LINKS_PREFIX, {
      method: "POST",
      body: {
        ...(region.trim() ? { region_name: region.trim() } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      },
    })
      .then((payload) => {
        const row = payload as { token?: unknown }
        const token = typeof row?.token === "string" ? row.token : ""
        setCreating(false)
        if (!token) {
          setCreateError("创建成功但响应缺少 token——请刷新清单并重试。")
          load()
          return
        }
        setFreshToken(token)
        setRegion("")
        setNote("")
        load()
      })
      .catch((caught: unknown) => {
        setCreating(false)
        setCreateError(
          caught instanceof ApiClientError ? caught.message : "链接创建失败，请稍后重试。",
        )
      })
  }

  function deactivateLink(link: ChannelLinkRow): void {
    void confirm({
      title: "停用渠道链接",
      description:
        "停用后新会话不再按渠道归因（历史归因不改写）。确定停用吗？",
      confirmLabel: "停用",
    }).then((accepted) => {
      if (!accepted) return
      setBusyLinkId(link.id)
      setActionError("")
      setActionNotice("")
      void apiRequest<unknown>(`${LINKS_PREFIX}/${link.id}/deactivate`, {
        method: "POST",
        body: {},
      })
        .then(() => {
          setBusyLinkId("")
          setActionNotice("已停用：新线索不再按该链接归因，历史归因保持不变。")
          load()
        })
        .catch((caught: unknown) => {
          setBusyLinkId("")
          setActionError(
            caught instanceof ApiClientError ? caught.message : "停用失败，请稍后重试。",
          )
        })
    })
  }

  return (
    <section className="channel-links-panel" aria-label="渠道链接管理">
      <h2 className="page-heading">渠道链接（T-15 渠道接线）</h2>
      <p className="page-subtitle">
        渠道报备归因（A 档）只认专属链接：访客带链接标识进来即机械落「渠道报备」，
        无链接或链接已停用则落「平台自来」，零手工记账。
      </p>

      <div className="lead-pool-controls" role="group" aria-label="新建渠道链接">
        <label className="lead-pool-field">
          区域（可选）
          <input
            type="text"
            value={region}
            placeholder="如：浙江省（限定给某区域合作商）"
            onChange={(event) => setRegion(event.target.value)}
          />
        </label>
        <label className="lead-pool-field">
          备注（可选）
          <input
            type="text"
            value={note}
            placeholder="渠道方代号或说明（不写真实姓名/联系方式）"
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <button
          className="primary-button"
          type="button"
          disabled={creating}
          onClick={createLink}
        >
          生成专属链接
        </button>
      </div>
      {createError ? (
        <p className="error-text" role="alert">
          {createError}
        </p>
      ) : null}
      {freshToken ? (
        <div className="channel-links-token" role="status">
          <p>
            <strong>链接标识已生成（明文只此一次，关闭后不再可见）</strong>
            ——把它拼到诊断入口链接后交付渠道方：
            <code>…?channel_ref={freshToken}</code>
          </p>
          <button className="secondary-button" type="button" onClick={() => setFreshToken("")}>
            我已保存，关闭
          </button>
        </div>
      ) : null}

      {actionNotice ? (
        <p className="notice" role="status">
          {actionNotice}
        </p>
      ) : null}
      {actionError ? (
        <p className="error-text" role="alert">
          {actionError}
        </p>
      ) : null}

      {unavailable ? (
        <p className="muted" role="note">
          诊断面未启用（部署闸默认关闭）——渠道链接在诊断面开闸后可用。
        </p>
      ) : null}
      {loadError ? (
        <p className="error-text" role="alert">
          {loadError}
        </p>
      ) : null}
      {loading && !unavailable ? <p className="muted">加载中…</p> : null}
      {!loading && !unavailable && !loadError && links.length === 0 ? (
        <p className="muted">还没有渠道链接。</p>
      ) : null}

      <ul className="dispatch-package-list">
        {links.map((link) => (
          <li key={link.id} className="dispatch-package-card">
            <div className="dispatch-offer-summary">
              <strong>{link.region_name ?? "区域未限定"}</strong>
              <span className="muted">{link.note ?? "无备注"}</span>
              <span className="muted">归因线索 {link.lead_count} 条</span>
              {link.is_active ? (
                <span className="lead-pool-status-ok" role="status">
                  在用
                </span>
              ) : (
                <span className="muted">已停用</span>
              )}
            </div>
            {link.is_active ? (
              <div className="lead-pool-decision">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busyLinkId === link.id}
                  onClick={() => deactivateLink(link)}
                >
                  停用
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
