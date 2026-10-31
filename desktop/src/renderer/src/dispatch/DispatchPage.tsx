import { CapabilityProfilesPage } from "./CapabilityProfilesPage"
import { ConsolePage } from "./ConsolePage"
import { DispatchPoolPage } from "./DispatchPoolPage"
import { MyOffersPage } from "./MyOffersPage"
import { MySettlementsPage } from "./MySettlementsPage"
import { RuleVersionsPage } from "./RuleVersionsPage"
import { useAuth } from "../auth/AuthProvider"

/** P2-1 派单页簇容器 + B1 接单工作台 + B2 调度台：六个子页 tab（派单池 /
 *  我的接单 / 我的结算 / 能力档案与产能 / 权重与规则版本 / 调度台）。
 *  tab 状态由 hash 路由承载（#dispatch[/(pool|mine|settlements|profiles|rules|console)]）。
 *  「我的接单/我的结算」是交付工程师视角（授权可见 + offer 流，§9.2/§6.3）；
 *  派单池/档案/规则沿用平台侧只读视图；「调度台」仅平台侧角色可见
 *  （admin/project_lead，B2 操作面——动作权限在服务端复核）。 */

export type DispatchTab =
  | "pool"
  | "mine"
  | "settlements"
  | "profiles"
  | "rules"
  | "console"

const TABS: { key: DispatchTab; label: string; platformOnly?: boolean }[] = [
  { key: "pool", label: "派单池" },
  { key: "mine", label: "我的接单" },
  { key: "settlements", label: "我的结算" },
  { key: "profiles", label: "能力档案与产能" },
  { key: "rules", label: "权重与规则版本" },
  { key: "console", label: "调度台", platformOnly: true },
]

export function DispatchPage({
  tab,
  onTabChange,
}: {
  tab: DispatchTab
  onTabChange: (tab: DispatchTab) => void
}) {
  const { user } = useAuth()
  const isPlatform = user?.role === "admin" || user?.role === "project_lead"
  const visibleTabs = TABS.filter((item) => !item.platformOnly || isPlatform)
  return (
    <div className="dispatch-page">
      <nav className="dispatch-tabs" aria-label="派单子页">
        {visibleTabs.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`dispatch-tab${tab === item.key ? " active" : ""}`}
            aria-current={tab === item.key ? "page" : undefined}
            onClick={() => onTabChange(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {tab === "pool" ? <DispatchPoolPage /> : null}
      {tab === "mine" ? <MyOffersPage /> : null}
      {tab === "settlements" ? <MySettlementsPage /> : null}
      {tab === "profiles" ? <CapabilityProfilesPage /> : null}
      {tab === "rules" ? <RuleVersionsPage /> : null}
      {tab === "console" ? (
        isPlatform ? (
          <ConsolePage />
        ) : (
          <p className="muted">调度台仅对平台侧角色（admin/project_lead）开放。</p>
        )
      ) : null}
    </div>
  )
}
