// V3.2 G7 / N4 G-11 · 改进提案（页面）。
//
// 界面须把「只提案不落地」与「受控发布记账」讲清楚：**审批 ≠ 发布**；
// 审批需当前账号密码 + 理由；approved 态可由管理员发起「发布记账」（要求回归计划非空），
// published 态可由管理员发起「回滚」（两者均须管理员密码 + 备注，提交或关闭即清空密码 state）。

import { useCallback, useEffect, useRef, useState, type ReactElement } from "react"

import { ApiClientError } from "../api/client"
import { useAuth } from "../auth/AuthProvider"
import { AsyncButton, EmptyState, Loading, UiButton } from "../components/ui"
import {
  decideProposal,
  listFindings,
  listProposals,
  releaseProposal,
  rollbackProposal,
} from "./api"
import type { FindingDto, ProposalDto } from "./types"

const STATUS_LABEL: Record<ProposalDto["status"], string> = {
  draft: "草稿",
  in_review: "评审中",
  approved: "已批准",
  rejected: "已驳回",
  published: "已发布",
}

function errorText(caught: unknown): string {
  if (caught instanceof ApiClientError) return caught.message
  if (caught instanceof Error) return caught.message
  return "操作失败，请稍后重试。"
}

function hasNonEmptyRegressionPlan(plan: Record<string, unknown> | null | undefined): boolean {
  if (!plan || typeof plan !== "object") return false
  return Object.keys(plan).length > 0
}

export function ImprovementProposals(): ReactElement {
  const { apiRequest, user } = useAuth()
  const isAdmin = user?.role === "admin"
  const [proposals, setProposals] = useState<ProposalDto[]>([])
  const [findings, setFindings] = useState<FindingDto[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [password, setPassword] = useState("")
  const [note, setNote] = useState("")
  const [channelTarget, setChannelTarget] = useState<{
    proposalId: string
    mode: "release" | "rollback"
  } | null>(null)
  const [channelPassword, setChannelPassword] = useState("")
  const [channelNote, setChannelNote] = useState("")
  const [channelError, setChannelError] = useState("")
  const sequence = useRef(0)

  const clearChannelState = useCallback(() => {
    setChannelTarget(null)
    setChannelPassword("")
    setChannelNote("")
    setChannelError("")
  }, [])

  const openChannelForm = useCallback((proposalId: string, mode: "release" | "rollback") => {
    setChannelTarget({ proposalId, mode })
    setChannelPassword("")
    setChannelNote("")
    setChannelError("")
  }, [])

  const load = useCallback(async () => {
    const requestSequence = ++sequence.current
    try {
      const [proposalPayload, findingPayload] = await Promise.all([
        listProposals(apiRequest),
        listFindings(apiRequest),
      ])
      if (requestSequence !== sequence.current) return
      setProposals(proposalPayload.items)
      setFindings(findingPayload.items)
      setError("")
    } catch (caught) {
      if (requestSequence !== sequence.current) return
      setError(errorText(caught))
    } finally {
      if (requestSequence === sequence.current) setLoading(false)
    }
  }, [apiRequest])

  useEffect(() => {
    void load()
  }, [load])

  async function handleDecide(proposal: ProposalDto, approve: boolean): Promise<void> {
    setBusy(true)
    try {
      await decideProposal(apiRequest, proposal.id, { approve, password, note })
      setNotice(approve ? "已批准（未发布——落地由人工在治理面执行）。" : "已驳回。")
      setPassword("")
      setNote("")
      await load()
    } catch (caught) {
      setNotice(errorText(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleChannelSubmit(
    proposal: ProposalDto,
    mode: "release" | "rollback",
  ): Promise<void> {
    const pwd = channelPassword
    const trimmedNote = channelNote.trim()
    setChannelPassword("")
    if (!pwd || !trimmedNote) {
      setChannelError("管理员密码与备注均为必填。")
      return
    }
    setBusy(true)
    setChannelError("")
    try {
      if (mode === "release") {
        await releaseProposal(apiRequest, proposal.id, {
          password: pwd,
          note: trimmedNote,
        })
        setNotice(`提案 ${proposal.proposal_key} 已完成发布记账（版本 ${proposal.proposed_version}）。`)
      } else {
        await rollbackProposal(apiRequest, proposal.id, {
          password: pwd,
          note: trimmedNote,
        })
        setNotice(`提案 ${proposal.proposal_key} 已回滚至已批准状态。`)
      }
      clearChannelState()
      await load()
    } catch (caught) {
      const message = errorText(caught)
      setChannelError(message)
      setNotice(message)
    } finally {
      setBusy(false)
    }
  }

  const confirmedFindings = findings.filter((finding) =>
    finding.root_causes.some((cause) => cause.confidence === "confirmed"),
  )

  return (
    <section className="simulation-proposals" aria-label="改进提案">
      <header className="simulation-section-header">
        <h3>改进提案</h3>
        <span className="simulation-hint">
          提案只记录改进方向，不自动修改任何生产 Prompt / Skill / Workflow / 本体；
          审批通过后仍需人工在治理面落地。
        </span>
      </header>

      {notice ? (
        <p className="simulation-notice" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="simulation-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="simulation-approval-form">
        <label>
          <span>当前账号密码（审批用）</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label>
          <span>审批理由（必填）</span>
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
      </div>

      {loading ? <Loading label="正在加载提案…" /> : null}
      {!loading && proposals.length === 0 ? (
        <EmptyState
          title="尚无改进提案"
          description={`从失败发现生成提案（当前有 ${confirmedFindings.length} 条根因已确认的发现可提）。`}
        />
      ) : null}

      <ul className="simulation-proposal-list">
        {proposals.map((proposal) => {
          const canReleasePlan = hasNonEmptyRegressionPlan(proposal.regression_plan)
          const activeChannelMode =
            channelTarget?.proposalId === proposal.id ? channelTarget.mode : null
          const releaseInfo = proposal.release

          return (
            <li key={proposal.id} className="simulation-proposal">
              <header>
                <code>{proposal.proposal_key}</code>
                <strong>{proposal.title}</strong>
                <span className={`simulation-proposal-status simulation-status-${proposal.status}`}>
                  {STATUS_LABEL[proposal.status]}
                </span>
              </header>
              <p>{proposal.problem}</p>
              <dl className="simulation-proposal-meta">
                <dt>改进对象</dt>
                <dd>
                  {proposal.target.kind} · {proposal.target.ref}
                </dd>
                <dt>版本</dt>
                <dd>
                  {proposal.current_version} → {proposal.proposed_version}
                </dd>
                <dt>失败分类</dt>
                <dd>{proposal.finding_codes.join("、") || "—"}</dd>
                <dt>变更摘要</dt>
                <dd>{proposal.change_summary}</dd>
                {proposal.candidate_payload &&
                Object.keys(proposal.candidate_payload).length > 0 ? (
                  <>
                    <dt>候选载荷</dt>
                    <dd>
                      <code>{JSON.stringify(proposal.candidate_payload)}</code>
                    </dd>
                  </>
                ) : null}
                <dt>回归计划</dt>
                <dd>{JSON.stringify(proposal.regression_plan)}</dd>
                {proposal.note ? (
                  <>
                    <dt>审批意见</dt>
                    <dd>{proposal.note}</dd>
                  </>
                ) : null}
                {releaseInfo ? (
                  <>
                    <dt>发布记录</dt>
                    <dd>
                      版本 {releaseInfo.released_version} · {releaseInfo.released_at} · 备注：
                      {releaseInfo.release_note}
                    </dd>
                    {releaseInfo.rollback ? (
                      <>
                        <dt>回滚记录</dt>
                        <dd>
                          {releaseInfo.rollback.rolled_back_at} · 备注：
                          {releaseInfo.rollback.rollback_note}
                        </dd>
                      </>
                    ) : null}
                  </>
                ) : null}
              </dl>

              {proposal.status === "draft" || proposal.status === "in_review" ? (
                <div className="simulation-row-actions">
                  <AsyncButton
                    variant="primary"
                    actionKey={`proposal-approve-${proposal.id}`}
                    onRun={async () => {
                      await handleDecide(proposal, true)
                    }}
                  >
                    批准（不发布）
                  </AsyncButton>
                  <AsyncButton
                    variant="danger"
                    actionKey={`proposal-reject-${proposal.id}`}
                    onRun={async () => {
                      await handleDecide(proposal, false)
                    }}
                  >
                    驳回
                  </AsyncButton>
                </div>
              ) : (
                <div className="simulation-proposal-governance">
                  <p className="simulation-hint">
                    已审批（{STATUS_LABEL[proposal.status]}）——落地由人工在治理面执行。
                  </p>
                  {isAdmin && proposal.status === "approved" ? (
                    <div className="simulation-row-actions">
                      <UiButton
                        variant="primary"
                        disabled={busy || !canReleasePlan}
                        onClick={() => openChannelForm(proposal.id, "release")}
                      >
                        发布记账
                      </UiButton>
                      {!canReleasePlan ? (
                        <span className="simulation-hint">
                          回归计划为空，无法发起发布记账。
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {isAdmin && proposal.status === "published" ? (
                    <div className="simulation-row-actions">
                      <UiButton
                        variant="danger"
                        disabled={busy}
                        onClick={() => openChannelForm(proposal.id, "rollback")}
                      >
                        回滚
                      </UiButton>
                    </div>
                  ) : null}

                  {isAdmin && activeChannelMode ? (
                    <div
                      className="simulation-release-inline-form"
                      role="region"
                      aria-label={
                        activeChannelMode === "release" ? "发布记账确认" : "发布回滚确认"
                      }
                    >
                      <label>
                        <span>
                          {activeChannelMode === "release"
                            ? "管理员密码（发布记账必填）"
                            : "管理员密码（回滚必填）"}
                        </span>
                        <input
                          type="password"
                          value={channelPassword}
                          onChange={(event) => setChannelPassword(event.target.value)}
                        />
                      </label>
                      <label>
                        <span>
                          {activeChannelMode === "release"
                            ? "发布备注（必填）"
                            : "回滚备注（必填）"}
                        </span>
                        <input
                          value={channelNote}
                          onChange={(event) => setChannelNote(event.target.value)}
                        />
                      </label>
                      {channelError ? (
                        <p className="simulation-error" role="alert">
                          {channelError}
                        </p>
                      ) : null}
                      <div className="simulation-row-actions">
                        <AsyncButton
                          variant={activeChannelMode === "release" ? "primary" : "danger"}
                          disabled={busy || !channelPassword || !channelNote.trim()}
                          actionKey={`proposal-${activeChannelMode}-${proposal.id}`}
                          onRun={async () => {
                            await handleChannelSubmit(proposal, activeChannelMode)
                          }}
                        >
                          {activeChannelMode === "release" ? "确认发布记账" : "确认回滚"}
                        </AsyncButton>
                        <UiButton disabled={busy} onClick={clearChannelState}>
                          取消
                        </UiButton>
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <UiButton onClick={() => void load()}>刷新</UiButton>
    </section>
  )
}
