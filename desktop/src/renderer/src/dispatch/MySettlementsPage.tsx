import { useCallback, useEffect, useRef, useState } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"
import { formatSeatAmount } from "./DispatchPoolPage"

/** 本人席位结算支持五席明细与历史四席。预扣仅展示给交付席收款人。 */

export interface MySettlementView {
  settlement_id: string
  package_code: string
  settlement_key: string
  status: string
  base_amount: number | null
  my_roles: string[]
  my_amount: number
  withholding_tax: number
  acceptance_passed_at: string | null
  paid_at: string | null
}

export const SETTLEMENT_STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  accrued: "已计提",
  payable: "待打款",
  paid: "已打款",
  disputed: "争议中",
}

export const SEAT_ROLE_LABELS: Record<string, string> = {
  platform: "平台席位",
  region: "区域合伙人",
  city: "城市合伙人",
  delivery: "交付方",
  lead: "拉单方",
  county: "市县级服务商",
  province: "省级服务商",
}

export function isMySettlementView(value: unknown): value is MySettlementView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.settlement_id === "string" &&
    typeof row.package_code === "string" &&
    typeof row.my_amount === "number" &&
    Array.isArray(row.my_roles)
  )
}

export function MySettlementsPage() {
  const { apiRequest } = useAuth()
  const [settlements, setSettlements] = useState<MySettlementView[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const requestSequence = useRef(0)

  const load = useCallback(() => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setError("")
    void apiRequest<unknown>("/api/v1/dispatch/settlements/mine", { method: "GET" })
      .then((payload) => {
        if (sequence !== requestSequence.current) return
        // goal-d9 fix: apiRequest already unwraps the {data,error} envelope (latent bug family)
        setSettlements(Array.isArray(payload) ? payload.filter(isMySettlementView) : [])
      })
      .catch((caught: unknown) => {
        if (sequence !== requestSequence.current) return
        setError(
          caught instanceof ApiClientError ? caught.message : "结算加载失败，请稍后重试。"
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
    <section className="page" aria-label="我的结算">
      <header className="page-header">
        <div>
          <h1>我的结算</h1>
          <p className="page-subtitle">
            查看本人席位的税前分成。交付席收款人可查看本笔预扣税。
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
      {!loading && !error && settlements.length === 0 ? (
        <p className="muted">暂无结算记录；接单交付并通过验收计提后出现在这里。</p>
      ) : null}
      <ul className="dispatch-package-list">
        {settlements.map((row) => (
          <li key={row.settlement_id} className="dispatch-package-card">
            <div className="dispatch-package-summary dispatch-offer-summary">
              <strong>
                {row.package_code} · {row.settlement_key}
              </strong>
              <span>
                {SETTLEMENT_STATUS_LABELS[row.status] || row.status} ·{" "}
                {row.my_roles.map((role) => SEAT_ROLE_LABELS[role] || role).join(" + ")}
              </span>
              <span className="dispatch-seat-amount">
                我的分成 {formatSeatAmount(row.my_amount)}
              </span>
              {typeof row.base_amount === "number" ? (
                <span className="muted">计提基数 {formatSeatAmount(row.base_amount)}</span>
              ) : null}
              {row.my_roles.includes("delivery") ? (
                <span className="muted">预扣税 {formatSeatAmount(row.withholding_tax)}</span>
              ) : null}
              <span className="muted">
                {row.paid_at ? `打款于 ${row.paid_at}` : "尚未打款"}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
