import { CapabilityProfilesPage } from "./CapabilityProfilesPage"
import { DispatchPoolPage } from "./DispatchPoolPage"
import { MyOffersPage } from "./MyOffersPage"
import { MySettlementsPage } from "./MySettlementsPage"
import { RuleVersionsPage } from "./RuleVersionsPage"

/** P2-1 派单页簇容器 + B1 接单工作台：五个子页 tab（派单池 / 我的接单 /
 *  我的结算 / 能力档案与产能 / 权重与规则版本）。
 *  tab 状态由 hash 路由承载（#dispatch[/(pool|mine|settlements|profiles|rules)]）。
 *  「我的接单/我的结算」是交付工程师视角（授权可见 + offer 流，§9.2/§6.3）；
 *  派单池/档案/规则沿用平台侧只读视图。 */

export type DispatchTab = "pool" | "mine" | "settlements" | "profiles" | "rules"

const TABS: { key: DispatchTab; label: string }[] = [
  { key: "pool", label: "派单池" },
  { key: "mine", label: "我的接单" },
  { key: "settlements", label: "我的结算" },
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
      {tab === "mine" ? <MyOffersPage /> : null}
      {tab === "settlements" ? <MySettlementsPage /> : null}
      {tab === "profiles" ? <CapabilityProfilesPage /> : null}
      {tab === "rules" ? <RuleVersionsPage /> : null}
    </div>
  )
}
