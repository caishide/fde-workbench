import { CapabilityProfilesPage } from "./CapabilityProfilesPage"
import { DispatchPoolPage } from "./DispatchPoolPage"
import { RuleVersionsPage } from "./RuleVersionsPage"

/** P2-1 派单页簇容器：三个子页 tab（派单池 / 能力档案与产能 / 权重与规则版本）。
 *  tab 状态由 hash 路由承载（#dispatch[/(pool|profiles|rules)]）。 */

export type DispatchTab = "pool" | "profiles" | "rules"

const TABS: { key: DispatchTab; label: string }[] = [
  { key: "pool", label: "派单池" },
  { key: "profiles", label: "能力档案与产能" },
  { key: "rules", label: "权重与规则版本" },
]

export function DispatchPage({
  tab,
  onTabChange,
}: {
  tab: DispatchTab
  onTabChange: (tab: DispatchTab) => void
}) {
  return (
    <div className="dispatch-page">
      <nav className="dispatch-tabs" aria-label="派单子页">
        {TABS.map((item) => (
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
      {tab === "profiles" ? <CapabilityProfilesPage /> : null}
      {tab === "rules" ? <RuleVersionsPage /> : null}
    </div>
  )
}
