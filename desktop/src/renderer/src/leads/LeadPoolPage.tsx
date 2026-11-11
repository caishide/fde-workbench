import { useCallback, useEffect, useRef, useState } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"
import { useConfirm } from "../common/ConfirmProvider"
import { Modal } from "../components/ui"

/** 获客诊断 T-12：线索池控制台（任务书 §3 T-12）。
 *
 * 服务端语义（T-11，本页只消费不臆造）：
 * - 线索池**按区可见**：R4 只看本区域；R2 看全部未认领线索；池内
 *   **不含联系方式与姓名**（代号化投影）；
 * - **认领 ≠ 生效**（P-6）：POST claims 只落 pending，平台（admin）
 *   接受才转 claimed ＋ 落档位 ＋ 出台账行；
 * - admin 裁定面与 `require_role("admin")` 同构（canManage 显隐）；
 * - 部署闸默认关 ⇒ 404（不确认面存在）——本页对此给引导文案。
 *
 * 任务书旧句「认领 → 一键转 presurvey 项目」是 P-6 拍板前的旧语义：
 * 服务端尚无认领→项目转化端点，本页不臆造，转化留待后续轮。 */

export type ClaimantKind = "r2_entrepreneur" | "r4_partner"
export type ClaimStatusFilter = "pending" | "accepted" | "rejected" | "all"

export const CLAIMANT_KINDS: readonly ClaimantKind[] = ["r2_entrepreneur", "r4_partner"]

export const CLAIMANT_KIND_LABELS: Record<ClaimantKind, string> = {
  r2_entrepreneur: "R2 创业者（看全部未认领线索）",
  r4_partner: "R4 区域合作商（只看本区域）",
}

export const CLAIMANT_KIND_SHORT: Record<ClaimantKind, string> = {
  r2_entrepreneur: "R2 创业者",
  r4_partner: "R4 区域合作商",
}

export const CLAIM_STATUS_LABELS: Record<string, string> = {
  pending: "待平台接受",
  accepted: "已接受（生效）",
  rejected: "已驳回",
}

export const ATTRIBUTION_LABELS: Record<string, string> = {
  A: "A 渠道报备",
  B: "B 认领转化",
  C: "C 平台留存",
}

export const FEE_BASIS_LABELS: Record<string, string> = {
  none: "零转化费",
  pending_pricing: "转化费比例待价格轮",
}

export interface LeadPoolEntry {
  id: string
  status: string
  source_type: string | null
  channel_ref: string | null
  region_name: string | null
  industry: string | null
  scale: string | null
  pain_summary: string | null
  report_ready: boolean
  created_at: string | null
  claim_window_expires_at: string | null
  attribution_tier: string | null
}

export interface LeadClaimView {
  id: string
  session_id: string
  claimant_username: string | null
  claimant_kind: string
  region_name: string | null
  status: string
  attribution_tier: string | null
  fee_basis: string | null
  self_claim: boolean
  self_claim_signals: string[]
  ledger_line_no: string | null
  ledger_written_at: string | null
  decided_at: string | null
  decision_note: string | null
  note: string | null
  created_at: string | null
  lead: LeadPoolEntry | null
}

export function isLeadPoolEntry(value: unknown): value is LeadPoolEntry {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return typeof row.id === "string" && typeof row.status === "string"
}

export function isLeadClaimView(value: unknown): value is LeadClaimView {
  if (typeof value !== "object" || value === null) return false
  const row = value as Record<string, unknown>
  return (
    typeof row.id === "string" &&
    typeof row.session_id === "string" &&
    typeof row.status === "string" &&
    typeof row.claimant_kind === "string"
  )
}

export const CLAIM_STATUS_FILTERS: readonly ClaimStatusFilter[] = [
  "pending",
  "accepted",
  "rejected",
  "all",
]

export function isClaimStatusFilter(value: string): value is ClaimStatusFilter {
  return (CLAIM_STATUS_FILTERS as readonly string[]).includes(value)
}

/** 认领窗口倒计时（纯函数，导出供测试）：过期 / 今天 / N 天。 */
export function formatClaimWindow(iso: string | null, now = new Date()): string {
  if (!iso) return "窗口未知"
  const deadline = new Date(iso)
  if (Number.isNaN(deadline.getTime())) return "窗口未知"
  const diffMs = deadline.getTime() - now.getTime()
  if (diffMs <= 0) return "窗口已过期"
  const days = Math.floor(diffMs / 86_400_000)
  if (days >= 1) return `剩 ${days} 天`
  return "不足 1 天"
}

const SELF_CLAIM_SIGNAL_LABELS: Record<string, string> = {
  ip: "同一 IP",
  contact: "同一联系方式",
  subject: "同一主体",
}

export function describeSelfClaimSignals(signals: string[]): string {
  if (signals.length === 0) return ""
  return signals
    .map((signal) => SELF_CLAIM_SIGNAL_LABELS[signal] ?? signal)
    .join("／")
}

interface ClaimDialogState {
  entry: LeadPoolEntry
  subjectKey: string
  note: string
}

export function LeadPoolPage() {
  const { apiRequest, user } = useAuth()
  const confirm = useConfirm()
  const isAdmin = user?.role === "admin"

  const [claimantKind, setClaimantKind] = useState<ClaimantKind>("r2_entrepreneur")
  const [region, setRegion] = useState("")
  const [pool, setPool] = useState<LeadPoolEntry[]>([])
  const [poolLoading, setPoolLoading] = useState(true)
  const [poolError, setPoolError] = useState("")
  const [poolUnavailable, setPoolUnavailable] = useState(false)

  const [claims, setClaims] = useState<LeadClaimView[]>([])
  const [claimsLoading, setClaimsLoading] = useState(true)
  const [claimsError, setClaimsError] = useState("")
  const [claimsStatus, setClaimsStatus] = useState<ClaimStatusFilter>(
    isAdmin ? "pending" : "all",
  )

  const [dialog, setDialog] = useState<ClaimDialogState | null>(null)
  const [dialogBusy, setDialogBusy] = useState(false)
  const [dialogError, setDialogError] = useState("")
  const [submittedSessionIds, setSubmittedSessionIds] = useState<ReadonlySet<string>>(new Set())
  const [actionNotice, setActionNotice] = useState("")
  const [actionError, setActionError] = useState("")
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({})
  const [busyClaimId, setBusyClaimId] = useState("")

  const requestSequence = useRef(0)

  const load = useCallback(
    (kind: ClaimantKind, regionName: string, status: ClaimStatusFilter) => {
      const sequence = ++requestSequence.current
      setPoolLoading(true)
      setPoolError("")
      setPoolUnavailable(false)
      setClaimsLoading(true)
      setClaimsError("")
      const poolQuery = new URLSearchParams({ claimant_kind: kind })
      if (kind === "r4_partner" && regionName.trim()) {
        poolQuery.set("region_name", regionName.trim())
      }
      const claimsQuery = new URLSearchParams({ status })
      void Promise.all([
        apiRequest<unknown>(`/api/v1/diagnostics/leads?${poolQuery.toString()}`, {
          method: "GET",
        }),
        apiRequest<unknown>(`/api/v1/diagnostics/leads/claims?${claimsQuery.toString()}`, {
          method: "GET",
        }),
      ])
        .then(([poolPayload, claimsPayload]) => {
          if (sequence !== requestSequence.current) return
          setPool(Array.isArray(poolPayload) ? poolPayload.filter(isLeadPoolEntry) : [])
          setClaims(Array.isArray(claimsPayload) ? claimsPayload.filter(isLeadClaimView) : [])
        })
        .catch((caught: unknown) => {
          if (sequence !== requestSequence.current) return
          const message =
            caught instanceof ApiClientError ? caught.message : "线索池加载失败，请稍后重试。"
          if (caught instanceof ApiClientError && caught.status === 404) {
            setPoolUnavailable(true)
          } else {
            setPoolError(message)
          }
          setClaimsError(caught instanceof ApiClientError ? caught.message : "认领单加载失败。")
        })
        .finally(() => {
          if (sequence !== requestSequence.current) return
          setPoolLoading(false)
          setClaimsLoading(false)
        })
    },
    [apiRequest],
  )

  useEffect(() => {
    load(claimantKind, region, claimsStatus)
    // region 刻意不在依赖里：只随身份/状态切换或点「按区域查询」时拉取，
    // 避免每敲一个字打一次服务端。
  }, [load, claimantKind, claimsStatus])

  function applyClaimResult(sessionId: string): void {
    setSubmittedSessionIds((current) => new Set(current).add(sessionId))
    setActionNotice("认领申请已提交（待平台接受后生效）。")
    setActionError("")
    setDialog(null)
    load(claimantKind, region, claimsStatus)
  }

  function submitClaim(): void {
    if (!dialog) return
    const trimmedRegion = region.trim()
    if (claimantKind === "r4_partner" && !trimmedRegion) {
      setDialogError("区域合作商认领必须填写所在区域。")
      return
    }
    setDialogBusy(true)
    setDialogError("")
    void apiRequest<unknown>(`/api/v1/diagnostics/leads/${dialog.entry.id}/claims`, {
      method: "POST",
      body: {
        claimant_kind: claimantKind,
        ...(claimantKind === "r4_partner" ? { region_name: trimmedRegion } : {}),
        ...(dialog.subjectKey.trim() ? { subject_key: dialog.subjectKey.trim() } : {}),
        ...(dialog.note.trim() ? { note: dialog.note.trim() } : {}),
      },
    })
      .then(() => applyClaimResult(dialog.entry.id))
      .catch((caught: unknown) => {
        setDialogBusy(false)
        setDialogError(
          caught instanceof ApiClientError ? caught.message : "认领申请提交失败，请稍后重试。",
        )
      })
  }

  function decideClaim(claimId: string, decision: "accept" | "reject"): void {
    const note = (decisionNotes[claimId] ?? "").trim()
    const run = () => {
      setBusyClaimId(claimId)
      setActionError("")
      setActionNotice("")
      void apiRequest<unknown>(
        `/api/v1/diagnostics/leads/claims/${claimId}/${decision}`,
        {
          method: "POST",
          body: note ? { decision_note: note } : {},
        },
      )
        .then(() => {
          setBusyClaimId("")
          setActionNotice(
            decision === "accept"
              ? "已接受：认领生效，台账行已生成（宿主侧落账后回写行号）。"
              : "已驳回：线索释放，仍可被他人认领。",
          )
          load(claimantKind, region, claimsStatus)
        })
        .catch((caught: unknown) => {
          setBusyClaimId("")
          setActionError(
            caught instanceof ApiClientError ? caught.message : "裁定操作失败，请稍后重试。",
          )
        })
    }
    if (decision === "reject") {
      void confirm({
        title: "驳回认领申请",
        description: "驳回后线索释放，仍可被其他认领方申请。确定驳回吗？",
        confirmLabel: "驳回",
      }).then((accepted) => {
        if (accepted) run()
      })
      return
    }
    run()
  }

  return (
    <section className="page" aria-label="线索池">
      <header className="page-header">
        <div>
          <h1>线索池</h1>
          <p className="page-subtitle">
            获客诊断线索（代号化：不含联系方式与姓名）。认领申请经平台接受后生效并生成台账行
            （L-YYYYMMDD-NN，宿主侧落账到本地 leads.md）。
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => load(claimantKind, region, claimsStatus)}>
          刷新
        </button>
      </header>

      <div className="lead-pool-controls" role="group" aria-label="认领身份与区域">
        <label className="lead-pool-field">
          认领身份
          <select
            value={claimantKind}
            onChange={(event) => {
              const next = event.target.value
              if (isClaimantKindValue(next)) setClaimantKind(next)
            }}
          >
            {CLAIMANT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {CLAIMANT_KIND_LABELS[kind]}
              </option>
            ))}
          </select>
        </label>
        <label className="lead-pool-field">
          所在区域{claimantKind === "r4_partner" ? "（必填）" : "（可选）"}
          <input
            type="text"
            value={region}
            placeholder={claimantKind === "r4_partner" ? "如：浙江省" : "不填看全部"}
            onChange={(event) => setRegion(event.target.value)}
          />
        </label>
        <button
          className="secondary-button"
          type="button"
          onClick={() => load(claimantKind, region, claimsStatus)}
        >
          按区域查询
        </button>
      </div>

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

      {poolUnavailable ? (
        <p className="muted" role="note">
          诊断面未启用（部署闸默认关闭）——线索池在诊断面开闸后可用。
        </p>
      ) : null}
      {poolError ? (
        <p className="error-text" role="alert">
          {poolError}
        </p>
      ) : null}
      {poolLoading && !poolUnavailable ? <p className="muted">加载中…</p> : null}
      {!poolLoading && !poolUnavailable && !poolError && pool.length === 0 ? (
        <p className="muted">暂无可认领线索。</p>
      ) : null}

      <ul className="dispatch-package-list">
        {pool.map((entry) => {
          const submitted = submittedSessionIds.has(entry.id)
          return (
            <li key={entry.id} className="dispatch-package-card">
              <div className="dispatch-offer-summary">
                <strong>{entry.industry ?? "行业未登记"}</strong>
                <span className="muted">{entry.scale ?? "规模未填"}</span>
                <span className="muted">{entry.region_name ?? "区域未登记"}</span>
                {entry.report_ready ? (
                  <span className="muted">报告已生成</span>
                ) : (
                  <span className="muted">报告未生成</span>
                )}
                <span className="muted">{formatClaimWindow(entry.claim_window_expires_at)}</span>
                {submitted ? (
                  <span className="lead-pool-submitted" role="status">
                    认领申请已提交（待平台接受）
                  </span>
                ) : (
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => {
                      setDialogError("")
                      setDialog({ entry, subjectKey: "", note: "" })
                    }}
                  >
                    认领
                  </button>
                )}
              </div>
              {entry.pain_summary ? <p className="muted">{entry.pain_summary}</p> : null}
            </li>
          )
        })}
      </ul>

      <h2 className="page-heading">{isAdmin ? "认领裁定" : "我的认领申请"}</h2>
      {isAdmin ? (
        <div className="lead-pool-controls" role="group" aria-label="认领单状态过滤">
          <label className="lead-pool-field">
            状态
            <select
              value={claimsStatus}
              onChange={(event) => {
                const next = event.target.value
                if (isClaimStatusFilter(next)) setClaimsStatus(next)
              }}
            >
              <option value="pending">待平台接受</option>
              <option value="accepted">已接受</option>
              <option value="rejected">已驳回</option>
              <option value="all">全部</option>
            </select>
          </label>
        </div>
      ) : null}
      {claimsError ? (
        <p className="error-text" role="alert">
          {claimsError}
        </p>
      ) : null}
      {claimsLoading ? <p className="muted">加载中…</p> : null}
      {!claimsLoading && !claimsError && claims.length === 0 ? (
        <p className="muted">{isAdmin ? "没有符合条件的认领单。" : "还没有认领申请。"}</p>
      ) : null}
      <ul className="dispatch-package-list">
        {claims.map((claim) => (
          <li key={claim.id} className="dispatch-package-card">
            <div className="dispatch-offer-summary">
              <strong>{CLAIMANT_KIND_SHORT[claim.claimant_kind as ClaimantKind] ?? claim.claimant_kind}</strong>
              {claim.claimant_username ? (
                <span className="muted">认领人 {claim.claimant_username}</span>
              ) : null}
              <span
                className={claim.status === "accepted" ? "lead-pool-status-ok" : "muted"}
                role="status"
              >
                {CLAIM_STATUS_LABELS[claim.status] ?? claim.status}
              </span>
              {claim.attribution_tier ? (
                <span className="muted">
                  {ATTRIBUTION_LABELS[claim.attribution_tier] ?? claim.attribution_tier}
                  {claim.fee_basis ? ` · ${FEE_BASIS_LABELS[claim.fee_basis] ?? claim.fee_basis}` : ""}
                </span>
              ) : null}
              {claim.self_claim ? (
                <span className="muted">
                  自认领信号：{describeSelfClaimSignals(claim.self_claim_signals) || "命中"}
                </span>
              ) : null}
            </div>
            {claim.lead ? (
              <p className="muted">
                线索：{claim.lead.industry ?? "行业未登记"} ·{" "}
                {claim.lead.region_name ?? "区域未登记"}
                {claim.lead.pain_summary ? ` · ${claim.lead.pain_summary}` : ""}
              </p>
            ) : null}
            {claim.note ? <p className="muted">认领留言：{claim.note}</p> : null}
            {claim.ledger_line_no ? (
              <p className="muted">
                台账行 {claim.ledger_line_no}
                {claim.ledger_written_at ? "（已落账）" : "（待宿主侧落账）"}
              </p>
            ) : null}
            {claim.decision_note ? (
              <p className="muted">裁定备注：{claim.decision_note}</p>
            ) : null}
            {isAdmin && claim.status === "pending" ? (
              <div className="lead-pool-decision">
                <input
                  type="text"
                  aria-label={`裁定备注（${CLAIMANT_KIND_SHORT[claim.claimant_kind as ClaimantKind] ?? claim.claimant_kind}）`}
                  placeholder="裁定备注（可留档说明，如：同网段自认领）"
                  value={decisionNotes[claim.id] ?? ""}
                  onChange={(event) =>
                    setDecisionNotes((current) => ({ ...current, [claim.id]: event.target.value }))
                  }
                />
                <button
                  className="primary-button"
                  type="button"
                  disabled={busyClaimId === claim.id}
                  onClick={() => decideClaim(claim.id, "accept")}
                >
                  接受
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busyClaimId === claim.id}
                  onClick={() => decideClaim(claim.id, "reject")}
                >
                  驳回
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {dialog ? (
        <Modal
          title="发起认领申请"
          description="认领申请提交后待平台接受；接受即生效并生成台账行。"
          busy={dialogBusy}
          dismissable
          onClose={() => setDialog(null)}
          footer={
            <>
              <button
                className="primary-button"
                type="button"
                disabled={dialogBusy}
                onClick={submitClaim}
              >
                提交认领申请
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={dialogBusy}
                onClick={() => setDialog(null)}
              >
                取消
              </button>
            </>
          }
        >
          <div className="lead-pool-dialog-body">
            <p className="muted">
              认领身份：{CLAIMANT_KIND_LABELS[claimantKind]}
              {claimantKind === "r4_partner" ? ` · 区域：${region.trim() || "（未填）"}` : ""}
            </p>
            <label className="lead-pool-field">
              声明联系方式（可选；用于识别「自诊自认领」——命中自动降 C 档零转化费）
              <input
                type="text"
                value={dialog.subjectKey}
                onChange={(event) =>
                  setDialog((current) =>
                    current ? { ...current, subjectKey: event.target.value } : current,
                  )
                }
              />
            </label>
            <label className="lead-pool-field">
              留言（可选）
              <input
                type="text"
                value={dialog.note}
                onChange={(event) =>
                  setDialog((current) =>
                    current ? { ...current, note: event.target.value } : current,
                  )
                }
              />
            </label>
            {dialogError ? (
              <p className="error-text" role="alert">
                {dialogError}
              </p>
            ) : null}
          </div>
        </Modal>
      ) : null}
    </section>
  )
}

function isClaimantKindValue(value: string): value is ClaimantKind {
  return (CLAIMANT_KINDS as readonly string[]).includes(value)
}
