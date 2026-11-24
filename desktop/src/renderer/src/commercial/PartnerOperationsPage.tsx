import { useCallback, useEffect, useRef, useState } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"

/**
 * M3 候选 1（D-5① 拍板）：区域伙伴自助运营页（#partner/operations）。
 *
 * 只读消费既有端点＋一个自证申请动作，零角色新增零新角色体系：
 * - `GET /api/v1/commercial/regional-partners`（服务端按「本人申请」收敛）
 * - `GET /api/v1/commercial/regional-partners/<id>`（详情＋阶段注记派生）
 * - `POST /api/v1/commercial/regional-partners`（当事人自证申请，免费）
 * - `GET /api/v1/commercial/regional-partner-tiers`（阶梯目录＋售卖闸状态——
 *   目录可见 ≠ 可签约，闸的开启永远在 admin 面）
 * - `GET /api/v1/ops/todos/mine`（M3 同轮新增：主体收敛只读待办变体）
 */

interface PartnerView {
  id: string
  partner_code: string
  region_name: string
  note: string | null
  stage: string
  stage_note: string | null
  tier_code: string | null
  exclusive_territory: boolean | null
  applied_at: string
  stage_changed_at: string | null
}

export function isPartnerView(value: unknown): value is PartnerView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.id === "string" &&
    typeof row.partner_code === "string" &&
    typeof row.region_name === "string" &&
    typeof row.stage === "string" &&
    typeof row.applied_at === "string"
  )
}

interface TierView {
  tier_code: string
  annual_fee_amount: string
  included_seats: number
  transfer_quota_seats: number
  basis_reference: string | null
}

export function isTierView(value: unknown): value is TierView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.tier_code === "string" &&
    typeof row.annual_fee_amount === "string" &&
    typeof row.included_seats === "number"
  )
}

interface SubjectTodoView {
  domain: string
  object_id: string
  title: string
  deadline_at: string | null
  state: string
  queue: string | null
}

export function isSubjectTodoView(value: unknown): value is SubjectTodoView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.domain === "string" &&
    typeof row.object_id === "string" &&
    typeof row.title === "string" &&
    typeof row.state === "string"
  )
}

const STAGE_LABELS: Record<string, string> = {
  city_observer: "城市观察",
  regional_agent: "区域代理",
  regional_partner: "区域合作商",
}

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] || stage
}

const GATE_STATUS_LABELS: Record<string, string> = {
  closed: "区域售卖未开放",
  opened: "区域售卖已开放",
}

const TODO_DOMAIN_LABELS: Record<string, string> = {
  automation_approval: "审批",
  api_confirmation: "确认",
  dispatch_offer: "派单",
}

export function PartnerOperationsPage() {
  const { apiRequest } = useAuth()
  const [partners, setPartners] = useState<PartnerView[]>([])
  const [tiers, setTiers] = useState<TierView[]>([])
  const [gateStatus, setGateStatus] = useState<string>("")
  const [todos, setTodos] = useState<SubjectTodoView[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PartnerView | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [partnerCode, setPartnerCode] = useState("")
  const [regionName, setRegionName] = useState("")
  const [note, setNote] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")
  const requestSequence = useRef(0)

  const load = useCallback(() => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError("")
    Promise.all([
      apiRequest<unknown>("/api/v1/commercial/regional-partners", { method: "GET" }),
      apiRequest<unknown>("/api/v1/commercial/regional-partner-tiers", { method: "GET" }),
      apiRequest<unknown>("/api/v1/ops/todos/mine", { method: "GET" }),
    ])
      .then(([partnersPayload, tiersPayload, todosPayload]) => {
        if (sequence !== requestSequence.current) return
        const partnerRows = Array.isArray(partnersPayload)
          ? partnersPayload
          : (partnersPayload as { data?: unknown })?.data
        setPartners(
          Array.isArray(partnerRows) ? partnerRows.filter(isPartnerView) : []
        )
        const tiersBody = (tiersPayload as { tiers?: unknown; sale_gate_status?: unknown }) || {}
        setTiers(Array.isArray(tiersBody.tiers) ? tiersBody.tiers.filter(isTierView) : [])
        setGateStatus(typeof tiersBody.sale_gate_status === "string" ? tiersBody.sale_gate_status : "")
        const todosBody = (todosPayload as { items?: unknown }) || {}
        setTodos(Array.isArray(todosBody.items) ? todosBody.items.filter(isSubjectTodoView) : [])
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return
        setError(
          caught instanceof ApiClientError ? caught.message : "伙伴运营数据加载失败，请稍后重试。"
        )
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false)
      })
  }, [apiRequest])

  useEffect(() => {
    load()
  }, [load])

  const toggleDetail = useCallback(
    (partner: PartnerView) => {
      if (expandedId === partner.id) {
        setExpandedId(null)
        setDetail(null)
        return
      }
      setExpandedId(partner.id)
      setDetail(null)
      void apiRequest<unknown>(`/api/v1/commercial/regional-partners/${encodeURIComponent(partner.id)}`, {
        method: "GET",
      })
        .then((payload) => {
          const row = (payload as { data?: unknown })?.data ?? payload
          if (isPartnerView(row)) setDetail(row)
        })
        .catch(() => {
          setDetail(null)
        })
    },
    [apiRequest, expandedId]
  )

  const submit = useCallback(() => {
    if (!partnerCode.trim() || !regionName.trim()) return
    setSubmitting(true)
    setSubmitError("")
    void apiRequest<unknown>("/api/v1/commercial/regional-partners", {
      method: "POST",
      body: {
        partner_code: partnerCode.trim(),
        region_name: regionName.trim(),
        note: note.trim() ? note.trim() : undefined,
      },
    })
      .then(() => {
        setFormOpen(false)
        setPartnerCode("")
        setRegionName("")
        setNote("")
        load()
      })
      .catch((caught: unknown) => {
        setSubmitError(
          caught instanceof ApiClientError ? caught.message : "申请提交失败，请稍后重试。"
        )
      })
      .finally(() => {
        setSubmitting(false)
      })
  }, [apiRequest, load, note, partnerCode, regionName])

  return (
    <section className="page" aria-label="伙伴运营">
      <header className="page-header">
        <div>
          <h1>伙伴运营</h1>
          <p className="page-subtitle">
            区域伙伴自助运营：申请与阶段、阶梯目录、我名下的运营待办（只读收敛视图）。
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={load}>
          刷新
        </button>
      </header>

      {loading ? <p className="muted">加载中…</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      <div className="dispatch-package-card">
        <div className="dispatch-package-summary">
          <strong>我的伙伴申请</strong>
          <span className="muted">申请为当事人自证动作（免费）；阶段晋升由平台侧裁定。</span>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setFormOpen((open) => !open)}
          >
            {formOpen ? "收起申请表单" : "申请成为城市观察伙伴"}
          </button>
        </div>
        {formOpen ? (
          <div className="gate-form-row">
            <input
              placeholder="伙伴代号（唯一）"
              value={partnerCode}
              maxLength={80}
              onChange={(event) => setPartnerCode(event.target.value)}
            />
            <input
              placeholder="区域名称（如：深圳市南山区）"
              value={regionName}
              maxLength={120}
              onChange={(event) => setRegionName(event.target.value)}
            />
            <input
              placeholder="备注（可选）"
              value={note}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
            />
            <button
              type="button"
              className="primary-button compact"
              disabled={submitting || !partnerCode.trim() || !regionName.trim()}
              onClick={submit}
            >
              提交申请
            </button>
          </div>
        ) : null}
        {submitError ? (
          <p className="error-text" role="alert">
            {submitError}
          </p>
        ) : null}
        {!loading && partners.length === 0 ? (
          <p className="muted">暂无申请记录；提交申请后会出现在这里。</p>
        ) : null}
        <ul className="dispatch-package-list">
          {partners.map((partner) => (
            <li key={partner.id} className="dispatch-package-card">
              <div className="dispatch-package-summary">
                <strong>{partner.partner_code}</strong>
                <span>{partner.region_name}</span>
                <span className="muted">
                  {stageLabel(partner.stage)} · 申请于 {partner.applied_at.slice(0, 10)}
                </span>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => toggleDetail(partner)}
                >
                  {expandedId === partner.id ? "收起详情" : "查看详情"}
                </button>
              </div>
              {expandedId === partner.id ? (
                <dl className="dispatch-package-detail">
                  {detail && detail.id === partner.id ? (
                    <>
                      <dt>当前阶段</dt>
                      <dd>
                        {stageLabel(detail.stage)}
                        {detail.stage_note ? `（${detail.stage_note}）` : ""}
                      </dd>
                      <dt>阶段变更</dt>
                      <dd>{detail.stage_changed_at ? detail.stage_changed_at.slice(0, 10) : "—"}</dd>
                      <dt>档位</dt>
                      <dd>{detail.tier_code || "—"}</dd>
                      <dt>独家区域</dt>
                      <dd>{detail.exclusive_territory ? "是" : "否"}</dd>
                      <dt>备注</dt>
                      <dd>{detail.note || "—"}</dd>
                    </>
                  ) : (
                    <dt>详情加载中…</dt>
                  )}
                </dl>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="dispatch-package-card">
        <div className="dispatch-package-summary">
          <strong>区域合作阶梯目录</strong>
          <span className="muted">
            {GATE_STATUS_LABELS[gateStatus] || "售卖闸状态未知"}；目录可见 ≠ 可签约（开启在平台侧）。
          </span>
        </div>
        <ul className="dispatch-package-list">
          {tiers.map((tier) => (
            <li key={tier.tier_code} className="dispatch-package-card">
              <div className="dispatch-package-summary">
                <strong>{tier.tier_code}</strong>
                <span>年费 ¥{tier.annual_fee_amount}</span>
                <span className="muted">
                  含 {tier.included_seats} 席位 · 转介绍配额 {tier.transfer_quota_seats} 席
                </span>
                {tier.basis_reference ? (
                  <span className="muted">依据：{tier.basis_reference}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="dispatch-package-card">
        <div className="dispatch-package-summary">
          <strong>我的运营待办</strong>
          <span className="muted">
            只显示与你名下主体相关的未决事项（审批／确认／派单）；全量运营视图见平台侧。
          </span>
        </div>
        {todos.length === 0 ? (
          <p className="muted">暂无与你相关的待办。</p>
        ) : (
          <ul className="dispatch-package-list">
            {todos.map((todo) => (
              <li key={`${todo.domain}:${todo.object_id}`} className="dispatch-package-card">
                <div className="dispatch-package-summary">
                  <strong>{TODO_DOMAIN_LABELS[todo.domain] || todo.domain}</strong>
                  <span>{todo.title}</span>
                  <span className="muted">
                    {todo.state}
                    {todo.deadline_at ? ` · 截止 ${todo.deadline_at.replace("T", " ").slice(0, 16)}` : ""}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

