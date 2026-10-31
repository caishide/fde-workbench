import { useCallback, useEffect, useRef, useState } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"

/** P2-1（派单设计 §8.5）：派单池页——交付包白名单字段只读视图（§9.2 十二项
 *  + 交付方席位金额）。跨主体语义=「只看我被授权的包」，金额只有
 *  delivery_seat_amount 一个（显示义务），报价/收款明细永不出现在响应里。 */

export interface DispatchPackageView {
  package_code: string
  scope_summary: string | null
  deliverables_json: string | null
  acceptance_criteria: string | null
  data_systems: string | null
  schedule_text: string | null
  risks_dependencies: string | null
  business_category: string | null
  client_code: string
  client_city: string | null
  onsite_required: boolean
  onsite_visits: number | null
  deadline: string | null
  delivery_seat_amount: number | null
  dispatch_status: string
  dispatch_round: number
  dispatch_mode: string
  response_window_hours: number
  published_at: string | null
}

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  offered: "已发 offer",
  assigned: "已指派",
  accepted: "已接单",
  rejected: "已拒绝",
  expired: "已超时",
  withdrawn: "已撤回",
}

const MODE_LABELS: Record<string, string> = {
  assign: "指派制",
  claim: "抢单制",
}

export function isPackageView(value: unknown): value is DispatchPackageView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return typeof row.package_code === "string" && typeof row.client_code === "string"
}

export function formatSeatAmount(amount: number | null): string {
  if (amount === null) return "—"
  return `¥${amount.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}`
}

export function DispatchPoolPage() {
  const { apiRequest } = useAuth()
  const [packages, setPackages] = useState<DispatchPackageView[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [expanded, setExpanded] = useState<string | null>(null)
  const requestSequence = useRef(0)

  const load = useCallback(() => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError("")
    void apiRequest<unknown>("/api/v1/dispatch/packages", { method: "GET" })
      .then((payload) => {
        if (sequence !== requestSequence.current) return
        const rows = (payload as { data?: unknown } | null)?.data
        setPackages(Array.isArray(rows) ? rows.filter(isPackageView) : [])
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return
        setError(
          caught instanceof ApiClientError ? caught.message : "派单池加载失败，请稍后重试。"
        )
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false)
      })
  }, [apiRequest])

  useEffect(() => {
    load()
  }, [load])

  return (
    <section className="page" aria-label="派单池">
      <header className="page-header">
        <div>
          <h1>派单池</h1>
          <p className="page-subtitle">
            只显示被授权查看的交付包；字段为脱敏白名单，金额仅为交付方席位份额（显示义务）。
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
      {!loading && !error && packages.length === 0 ? (
        <p className="muted">暂无被授权的交付包。</p>
      ) : null}
      <ul className="dispatch-package-list">
        {packages.map((row) => (
          <li key={row.package_code} className="dispatch-package-card">
            <button
              type="button"
              className="dispatch-package-summary"
              aria-expanded={expanded === row.package_code}
              onClick={() =>
                setExpanded(expanded === row.package_code ? null : row.package_code)
              }
            >
              <strong>{row.package_code}</strong>
              <span>{row.scope_summary || "（无范围摘要）"}</span>
              <span className="muted">
                {STATUS_LABELS[row.dispatch_status] || row.dispatch_status} ·{" "}
                {MODE_LABELS[row.dispatch_mode] || row.dispatch_mode} · 第 {row.dispatch_round} 轮
              </span>
              <span className="dispatch-seat-amount">
                交付方席位 {formatSeatAmount(row.delivery_seat_amount)}
              </span>
            </button>
            {expanded === row.package_code ? (
              <dl className="dispatch-package-detail">
                <dt>客户代号</dt>
                <dd>{row.client_code}</dd>
                <dt>客户城市</dt>
                <dd>{row.client_city || "—"}</dd>
                <dt>验收口径</dt>
                <dd>{row.acceptance_criteria || "—"}</dd>
                <dt>数据系统</dt>
                <dd>{row.data_systems || "—"}</dd>
                <dt>排期</dt>
                <dd>{row.schedule_text || "—"}</dd>
                <dt>风险依赖</dt>
                <dd>{row.risks_dependencies || "—"}</dd>
                <dt>业务类目</dt>
                <dd>{row.business_category || "—"}</dd>
                <dt>是否到场</dt>
                <dd>
                  {row.onsite_required
                    ? `是（${row.onsite_visits ?? 0} 次）`
                    : "否（远程）"}
                </dd>
                <dt>截止</dt>
                <dd>{row.deadline || "—"}</dd>
                <dt>响应窗</dt>
                <dd>{row.response_window_hours} 小时</dd>
                <dt>发布时刻</dt>
                <dd>{row.published_at || "—"}</dd>
              </dl>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
