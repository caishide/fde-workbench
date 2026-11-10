import { useEffect, useState } from "react"

import { useAuth } from "../auth/AuthProvider"

/**
 * 商业化运维就绪度面板（admin）。
 *
 * 呈现服务端汇总面 `GET /api/v1/admin/commercial/readiness`——**只呈现状态，
 * 不呈现也不推导任何商业数值**：配置槽位一律显示「已配置／未配置」，售卖闸
 * 一律显示「已登记／未登记」。数值与证据都在服务端与本地工作目录，桌面端
 * 只是一块屏。
 *
 * 为什么需要这块屏：任务书 §17 的商业数值本期一律不落数，区域售卖闸的四项
 * 合规条件也依赖法务与外部输入——此前这些「缺什么」只活在文档里，管理员在
 * 系统里看不到，「上线才发现没填」全靠人记。
 */

interface ReadinessSlot {
  key: string
  label: string
  value_kind: string | null
  status: string
  configured: boolean
  chargeable: boolean
  waiting_for: string | null
}

interface GateCondition {
  key: string
  label: string
  registered: boolean
  signed_at: string | null
  waiting_for: string | null
}

interface Blocker {
  kind: string
  key: string
  label: string
  severity: "blocking" | "pending"
  waiting_for: string | null
}

interface CommercialReadiness {
  config_slots: {
    fee_configs: ReadinessSlot[]
    opportunity_rules: ReadinessSlot[]
    split_rules: {
      status: string
      rows: number
      configured_rows: number
      waiting_for: string | null
    }
  }
  sale_gate: {
    status: string
    conditions: GateCondition[]
    missing_conditions: string[]
    ready_to_open: boolean
    opened_at: string | null
  }
  blockers: Blocker[]
  summary: {
    unset_fee_configs: number
    unset_opportunity_rules: number
    split_rules_configured: number
    missing_gate_conditions: number
    blocking_count: number
  }
}

const KIND_LABELS: Record<string, string> = {
  amount: "金额",
  days: "天数",
  threshold: "阈值",
  criteria: "判定标准",
}

export function CommercialOpsPage() {
  const { apiRequest } = useAuth()
  const [readiness, setReadiness] = useState<CommercialReadiness | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true
    void apiRequest<CommercialReadiness>("/api/v1/admin/commercial/readiness", { method: "GET" })
      .then((result) => {
        if (active) setReadiness(result)
      })
      .catch((caught) => {
        if (active) setError(messageOf(caught))
      })
    return () => {
      active = false
    }
  }, [apiRequest])

  if (!readiness) {
    return (
      <section className="page">
        <p role="status">正在加载商业化就绪度…</p>
        {error ? <p role="alert" className="form-error">{error}</p> : null}
      </section>
    )
  }

  const slots = [...readiness.config_slots.fee_configs, ...readiness.config_slots.opportunity_rules]
  const split = readiness.config_slots.split_rules
  const gate = readiness.sale_gate

  return (
    <section className="page commercial-ops-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">管理员设置</p>
          <h1>商业化运维</h1>
          <p>汇总对外能力当前缺什么、缺到哪一步。只呈现状态，不呈现也不推导任何商业数值。</p>
        </div>
      </header>
      {error ? <p role="alert" className="form-error banner">{error}</p> : null}

      {readiness.summary.blocking_count > 0 ? (
        <section className="panel" aria-labelledby="commercial-blockers-heading">
          <div className="panel-heading">
            <div>
              <h2 id="commercial-blockers-heading">未就绪项（{readiness.summary.blocking_count}）</h2>
              <p>下列项目未就绪，相关对外能力保持关闭或不可用——缺什么、缺到哪一步都列在这里。</p>
            </div>
          </div>
          <ul className="extension-stack">
            {readiness.blockers.map((item) => (
              <li key={`${item.kind}:${item.key}`}>
                <strong>{item.label}</strong>
                <span className="nav-label">{item.severity === "blocking" ? "阻断" : "待定"}</span>
                {item.waiting_for ? <span>等待：{item.waiting_for}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p role="status" className="notice">当前没有未就绪项。</p>
      )}

      <section className="panel" aria-labelledby="commercial-slots-heading">
        <div className="panel-heading">
          <div>
            <h2 id="commercial-slots-heading">配置槽位</h2>
            <p>费用/周期槽位与商机规则槽位当前状态；未配置即不可收款、不可触限（fail-closed 方向不变）。</p>
          </div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>槽位</th>
              <th>值型</th>
              <th>状态</th>
              <th>可直接收款</th>
            </tr>
          </thead>
          <tbody>
            {slots.map((slot) => (
              <tr key={slot.key}>
                <td>{slot.label}</td>
                <td>{slot.value_kind ? KIND_LABELS[slot.value_kind] ?? slot.value_kind : "—"}</td>
                <td>{slot.configured ? "已配置" : "未配置"}</td>
                <td>{slot.chargeable ? "是" : "否"}</td>
              </tr>
            ))}
            <tr>
              <td>项目分成比例（按角色 × 项目类型）</td>
              <td>比例</td>
              <td>{split.status === "configured" ? "已配置" : "未配置"}</td>
              <td>否</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="panel" aria-labelledby="commercial-gate-heading">
        <div className="panel-heading">
          <div>
            <h2 id="commercial-gate-heading">区域售卖闸</h2>
            <p>对外收费签约的唯一闸门；四项合规条件证据登记齐备才可开启，登记不等于开启。</p>
          </div>
        </div>
        <p role="status">当前状态：{gate.status === "opened" ? "已开启" : "未开启"}</p>
        <ul className="extension-stack">
          {gate.conditions.map((condition) => (
            <li key={condition.key}>
              <strong>{condition.label}</strong>
              <span>{condition.registered ? "已登记" : "未登记"}</span>
              {condition.waiting_for ? <span>等待：{condition.waiting_for}</span> : null}
            </li>
          ))}
        </ul>
      </section>
    </section>
  )
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "读取商业化就绪度失败。"
}
