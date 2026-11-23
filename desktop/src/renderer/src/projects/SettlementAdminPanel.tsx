import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"

const SEATS = { platform: "平台", lead: "拉单", delivery: "交付", county: "市县", province: "省级" }
const REASONS = { no_sourcer: "企业自来", no_province_partner: "无省级服务商", self_sourced_self_delivered: "自拉自交，未履行本级组织服务" }
const STATUS = { draft: "待计提", accrued: "已计提", payable: "应付", paid: "已记账", disputed: "争议中" }
const ACTIONS = { allocate: "保存五席分配", payable: "转应付", paid: "登记线下付款", "input-invoice": "登记省级进项票" }
type Action = keyof typeof ACTIONS
const PROVINCE_VACANCY = "no_province_partner"

interface Settlement {
  id: string
  package_code: string
  settlement_key: string
  delivery_user_id: string | null
  status: keyof typeof STATUS
  base_amount: string
  allocation_snapshot: string | null
  version_no: number | null
  requires_versioned_allocation: boolean
  paid_at: string | null
  input_invoice_required: boolean
  input_invoice_recorded: boolean
  allocations: {
    seat_key: keyof typeof SEATS
    payee_user_id: string | null
    amount: string
    status: "paid" | "vacant"
    reason_code: keyof typeof REASONS | null
  }[]
}

export function SettlementAdminPanel({ projectId, refreshKey }: { projectId: string; refreshKey: number }) {
  const { apiRequest } = useAuth()
  const path = `/api/v1/admin/dispatch/projects/${encodeURIComponent(projectId)}/settlements`
  const [rows, setRows] = useState<Settlement[]>([])
  const [selected, setSelected] = useState<{ row: Settlement; action: Action } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const generation = useRef(0)
  const load = useCallback(async () => {
    const requestId = ++generation.current
    setLoading(true)
    setError("")
    try {
      const data = await apiRequest<{ settlements: Settlement[] }>(path, { method: "GET" })
      if (!Array.isArray(data?.settlements)) throw new Error("无法读取结算列表。")
      if (requestId === generation.current) setRows(data.settlements)
    } catch (caught) {
      if (requestId === generation.current) setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      if (requestId === generation.current) setLoading(false)
    }
  }, [apiRequest, path])

  useEffect(() => {
    void load()
    return () => { generation.current += 1 }
  }, [load, refreshKey])

  function choose(row: Settlement, action: Action) {
    setNotice("")
    setSelected({ row, action })
  }

  return (
    <section className="panel" aria-label="管理员结算记账">
      <h3>结算记账（管理员）</h3>
      <p className="supporting-copy">在外部完成付款后登记凭证。此处操作仅更新内部账目，不发起转账。</p>
      {error ? <p role="alert" className="form-error banner">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {loading ? <p>加载结算记录……</p> : error ? (
        <button type="button" onClick={() => void load()}>重试读取结算</button>
      ) : rows.length === 0 ? (
        <p className="supporting-copy">暂无结算。回填交付包对应里程碑的实际收款后生成草稿。</p>
      ) : (
        <table className="payment-table">
          <thead><tr><th>交付包 / 里程碑</th><th>实收基数</th><th>状态 / 规则版本</th><th>操作</th></tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.id}>
              <td>{row.package_code} · {row.settlement_key}</td>
              <td>¥{row.base_amount}</td>
              <td>
                {STATUS[row.status]}{row.version_no !== null ? ` · v${row.version_no}` : ""}
                {row.allocations.length > 0 ? (
                  <details>
                    <summary>五席明细</summary>
                    <ul>{row.allocations.map((item) => (
                      <li key={item.seat_key}>
                        {SEATS[item.seat_key]} · ¥{item.amount}
                        {item.payee_user_id ? ` · ${item.payee_user_id}` : ""}
                        {item.reason_code ? ` · ${REASONS[item.reason_code]}` : ""}
                      </li>
                    ))}</ul>
                  </details>
                ) : null}
              </td>
              <td>
                {row.status === "draft" ? (
                  <button type="button" disabled={selected !== null || !row.delivery_user_id || !row.allocation_snapshot} onClick={() => choose(row, "allocate")}>五席分配</button>
                ) : null}
                {row.status === "draft" && !row.delivery_user_id ? <span>待确认交付人</span> : null}
                {row.status === "draft" && row.delivery_user_id && !row.allocation_snapshot ? <span>缺少分配确认快照</span> : null}
                {row.status === "accrued" ? (
                  row.requires_versioned_allocation && row.version_no === null ? <span>缺完整的版本化五席明细</span> :
                  row.input_invoice_required && !row.input_invoice_recorded ? (
                    <button type="button" disabled={selected !== null} onClick={() => choose(row, "input-invoice")}>登记省级进项票</button>
                  ) : (
                    <button type="button" disabled={selected !== null} onClick={() => choose(row, "payable")}>转应付</button>
                  )
                ) : null}
                {row.status === "payable" ? (
                  <button type="button" disabled={selected !== null} onClick={() => choose(row, "paid")}>登记线下付款</button>
                ) : null}
                {row.status === "paid" && row.paid_at ? <time dateTime={row.paid_at}>{new Date(row.paid_at).toLocaleString("zh-CN")}</time> : null}
              </td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {!loading && !error && selected ? (
        <SettlementActionForm
          {...selected}
          onCancel={() => setSelected(null)}
          onSubmit={async (body) => {
            try {
              await apiRequest(`${path}/${encodeURIComponent(selected.row.id)}/${selected.action}`, { method: "POST", body })
            } catch (caught) {
              if (selected.action === "allocate" && caught instanceof ApiClientError && caught.code === "allocation_snapshot_conflict") {
                setSelected(null)
                setNotice("结算已变更。请核对最新实收基数后重新确认五席分配。")
                await load()
                return
              }
              throw caught
            }
            setSelected(null)
            setNotice(`${ACTIONS[selected.action]}成功。`)
            await load()
          }}
        />
      ) : null}
    </section>
  )
}

function SettlementActionForm({ row, action, onSubmit, onCancel }: {
  row: Settlement
  action: Action
  onSubmit: (body: object) => Promise<void>
  onCancel: () => void
}) {
  const [password, setPassword] = useState("")
  const [proof, setProof] = useState("")
  const [digest, setDigest] = useState("")
  const county = row.allocations.find((item) => item.seat_key === "county")
  const [countyPayee, setCountyPayee] = useState(county?.payee_user_id ?? "")
  const [countyReason, setCountyReason] = useState(county?.reason_code ?? "")
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [error, setError] = useState("")
  const ready = password.length > 0
    && (action !== "paid" || proof.trim().length > 0)
    && (action !== "input-invoice" || (proof.trim().length > 0 && /^[a-f0-9]{64}$/i.test(digest.trim())))
    && (action !== "allocate" || Boolean(row.allocation_snapshot && (countyReason || countyPayee.trim())))

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || !ready) return
    pending.current = true
    setBusy(true)
    setError("")
    const seatPayees = countyReason ? {} : { county: countyPayee.trim() }
    const vacantReasons = { province: PROVINCE_VACANCY, ...(countyReason ? { county: countyReason } : {}) }
    try {
      await onSubmit({
        confirm_password: password,
        ...(action === "allocate" ? {
          expected_allocation_snapshot: row.allocation_snapshot,
          seat_payees: seatPayees,
          vacant_reasons: vacantReasons,
        } : {}),
        ...(action === "paid" ? { paid_proof_source_uri: proof.trim() } : {}),
        ...(action === "input-invoice" ? { source_uri: proof.trim(), content_hash: digest.trim().toLowerCase() } : {}),
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setPassword("")
      setBusy(false)
      pending.current = false
    }
  }

  return (
    <form className="gate-form" onSubmit={(event) => void submit(event)}>
      <fieldset disabled={busy}>
        <legend>{ACTIONS[action]} · {row.package_code} · {row.settlement_key} · ¥{row.base_amount}</legend>
        {action === "allocate" ? <>
          <p className="supporting-copy">拉单席按已确认归属计算。交付席使用交付包的交付人 {row.delivery_user_id}。</p>
          <p className="supporting-copy">省级席本期固定为无省级服务商，份额计入平台。</p>
          <div className="gate-form-row">
            <label>市县席安排
              <select value={countyReason} onChange={(event) => {
                setCountyReason(event.target.value)
                setCountyPayee("")
              }}>
                <option value="">指定已启用的城市服务伙伴</option>
                <option value="self_sourced_self_delivered">{REASONS.self_sourced_self_delivered}</option>
              </select>
            </label>
            {!countyReason ? <label>市县收款人账号 ID
              <input required maxLength={36} value={countyPayee} onChange={(event) => setCountyPayee(event.target.value)} />
            </label> : null}
          </div>
        </> : null}
        {action === "paid" ? <label>付款凭证指针
          <input required maxLength={500} placeholder="fdeops://…" value={proof} onChange={(event) => setProof(event.target.value)} />
        </label> : null}
        {action === "input-invoice" ? <>
          <label>进项票凭证指针
            <input required maxLength={500} placeholder="fdeops://…" value={proof} onChange={(event) => setProof(event.target.value)} />
          </label>
          <label>进项票 SHA-256 指纹
            <input required maxLength={64} value={digest} onChange={(event) => setDigest(event.target.value)} />
          </label>
        </> : null}
        <label>当前账号密码<input required type="password" autoComplete="current-password" maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error ? <p role="alert" className="form-error banner">{error}</p> : null}
        <div className="gate-form-row">
          <button className="primary-button compact" type="submit" disabled={!ready}>确认{ACTIONS[action]}</button>
          <button className="secondary-button compact" type="button" onClick={onCancel}>取消结算操作</button>
        </div>
      </fieldset>
    </form>
  )
}
