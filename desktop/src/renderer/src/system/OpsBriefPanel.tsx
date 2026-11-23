import { useEffect, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { useAuth } from "../auth/AuthProvider"

// 运营待办与简报卡（Ecosystem OS M2 WP-5）：系统配置页运行治理卡下方的
// admin 只读监控＋简报生成。立项书口径「仅在现有页面挂入口，不新增导航
// 结构」——挂载于 #system-configuration（路由闸已 admin-only，组件内不
// 重复判角色）。
// ① 运营待办（GET /api/v1/ops/todos，admin 只读）：四域六字段投影；域
//    过滤为本地 select（闭集防御性过滤，对齐 PlatformGovernancePanel）。
//    读失败不阻任何保存——独立加载、独立呈现错误。
// ② 生成简报（POST /api/v1/ops/briefs/generate，admin）：服务端确定性聚
//    合返件式——正文只呈现不落库；sha256 指纹与生成时刻旁注；下载走
//    blob anchor（.md，文件名带日期）。系统无简报直发通道，分发走既有
//    文档/发信面（人工决策仍走既有审批/确认/响应闸）。
const TODO_DOMAIN_LABEL: Record<string, string> = {
  automation_approval: "自动化审批",
  api_confirmation: "AI 确认",
  dispatch_offer: "派单响应",
  meeting_todo: "纪要待办",
}

const TODO_FETCH_LIMIT = 100

interface TodoItem {
  domain: string
  object_id: string
  title: string
  deadline_at: string | null
  state: string
  queue: string | null
}

interface TodoList {
  items: TodoItem[]
  total: number
}

interface BriefResult {
  brief_markdown: string
  brief_sha256: string
  todo_total: number
  due_total: number
  generated_at: string
}

function formatDeadline(iso: string | null | undefined, fallback = "—"): string {
  return iso ? iso.replace("T", " ").slice(0, 19) : fallback
}

function downloadBrief(markdown: string, generatedAt: string): void {
  const day = generatedAt.slice(0, 10).replace(/-/g, "")
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `运营简报-${day}.md`
  anchor.click()
  URL.revokeObjectURL(url)
}

export function OpsBriefPanel() {
  const { apiRequest } = useAuth()
  const [todos, setTodos] = useState<TodoList | null>(null)
  const [todoError, setTodoError] = useState("")
  const [domainFilter, setDomainFilter] = useState("all")
  const [brief, setBrief] = useState<BriefResult | null>(null)
  const [briefBusy, setBriefBusy] = useState(false)
  const [briefError, setBriefError] = useState("")
  const [briefNotice, setBriefNotice] = useState("")

  useEffect(() => {
    let active = true
    async function loadTodos(): Promise<void> {
      try {
        const data = await apiRequest<TodoList>(`/api/v1/ops/todos?limit=${TODO_FETCH_LIMIT}`, { method: "GET" })
        if (!active) return
        setTodos({
          items: (Array.isArray(data.items) ? data.items : []).filter((row) => row.domain in TODO_DOMAIN_LABEL),
          total: typeof data.total === "number" ? data.total : 0,
        })
      } catch (caught) {
        if (!active) return
        setTodos(null)
        setTodoError(caught instanceof Error ? caught.message : "运营待办加载失败，请稍后重试。")
      }
    }
    void loadTodos()
    return () => { active = false }
  }, [apiRequest])

  async function generateBrief(): Promise<void> {
    if (briefBusy) return
    setBriefBusy(true); setBriefError(""); setBriefNotice("")
    try {
      const data = await apiRequest<BriefResult>("/api/v1/ops/briefs/generate", { method: "POST", body: {} })
      setBrief(data)
      setBriefNotice(`简报已生成（待办 ${data.todo_total} 项，其中已到期 ${data.due_total} 项）。`)
    } catch (caught) {
      setBriefError(caught instanceof Error ? caught.message : "简报生成失败，请稍后重试。")
    } finally {
      setBriefBusy(false)
    }
  }

  const visible = todos === null ? [] : domainFilter === "all"
    ? todos.items
    : todos.items.filter((row) => row.domain === domainFilter)

  return <>
    <section className="panel" role="region" aria-label="运营待办">
      <div className="panel-heading"><div><h2>运营待办</h2><p>跨域待办聚合（AI 自动化审批 / AI 确认 / 派单响应 / 纪要待办）：只读监控，人工决策仍走既有审批、确认与派单响应入口。</p></div></div>
      {todoError ? <p className="form-error" role="alert">{todoError}</p> : null}
      {todos === null && !todoError ? <p role="status">正在读取运营待办…</p> : null}
      {todos !== null ? <>
        <p className="field-hint">
          共 <strong>{todos.total}</strong> 项
          {todos.total >= TODO_FETCH_LIMIT ? `（已达单次拉取上限 ${TODO_FETCH_LIMIT}，可用过滤缩小范围）` : ""}
          ，当前显示 <strong>{visible.length}</strong> 项。
        </p>
        <label className="field"><span>按域过滤</span>
          <select aria-label="按域过滤" value={domainFilter} onChange={(event) => setDomainFilter(event.target.value)}>
            <option value="all">全部域</option>
            {Object.entries(TODO_DOMAIN_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {visible.length ? (
          <table className="data-table">
            <thead><tr><th scope="col">域</th><th scope="col">事项</th><th scope="col">截止时间</th><th scope="col">状态</th><th scope="col">审批队列</th></tr></thead>
            <tbody>
              {visible.map((item) => (
                <tr key={`${item.domain}:${item.object_id}`}>
                  <td>{TODO_DOMAIN_LABEL[item.domain] ?? item.domain}</td>
                  <td>{item.title}</td>
                  <td>{formatDeadline(item.deadline_at, "无期限")}</td>
                  <td>{item.state}</td>
                  <td>{item.queue ?? "运营协调"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="empty-copy">没有符合条件的待办。</p>}
      </> : null}
    </section>
    <section className="panel" role="region" aria-label="运营简报">
      <div className="panel-heading">
        <div><h2>运营简报</h2><p>确定性聚合生成（待办清单＋招商漏斗＋需总部介入事项）：数字全部来自数据库现算，不含模型生成内容；正文不落库，人工分发走既有文档与发信面。</p></div>
        <div className="plugin-actions">
          <button type="button" className="primary-button" disabled={briefBusy} onClick={() => void generateBrief()}>
            {briefBusy ? "正在生成…" : "生成运营简报"}
          </button>
        </div>
      </div>
      {briefError ? <p className="form-error" role="alert">{briefError}</p> : null}
      {briefNotice ? <p className="notice" role="status">{briefNotice}</p> : null}
      {brief !== null ? <>
        <p className="field-hint">
          生成于 {formatDeadline(brief.generated_at)} ｜ 待办 {brief.todo_total} 项（已到期 {brief.due_total} 项）｜ 指纹 <code>{brief.brief_sha256}</code>
          {" "}
          <button type="button" className="secondary-button" onClick={() => downloadBrief(brief.brief_markdown, brief.generated_at)}>下载 Markdown</button>
        </p>
        <div className="page-stack">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
            {brief.brief_markdown}
          </ReactMarkdown>
        </div>
      </> : <p className="empty-copy">尚未生成简报。</p>}
    </section>
  </>
}
