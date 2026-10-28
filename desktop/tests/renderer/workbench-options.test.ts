// WP29/J1：业务枚举选项表的服务端下发 + 本地兜底（前端消费层）。
//
// 缺陷基线：枚举硬编码在渲染层（价格档位/门禁五态/C 分支/SOW/业务阶段），
// 口径变更要改前端代码。本轮选项表下沉服务端，前端消费并保留本地兜底。
//
// 断言覆盖：
// - 服务端下发完整时采用下发值
// - 某组缺失/类型不对时只回退那一组（不整体丢弃）
// - 完全无响应时用本地兜底，界面仍能渲染
// - 门禁状态标签/样式：未知状态兜底显示原值
// - 业务阶段存库值仍是旧中文标签（兼容旧数据）
import { describe, expect, it } from "vitest"

import {
  FALLBACK_OPTIONS,
  gateStatusLabel,
  gateStatusTone,
  mergeOptions,
  type WorkbenchOptions,
} from "../../src/renderer/src/workbench/options"
import {
  BUSINESS_CATEGORY_VALUES,
  businessCategoryKeyOf,
} from "../../src/renderer/src/businessCategory"

function envelope(data: unknown): unknown {
  return { data, error: null }
}

describe("workbench options", () => {
  it("uses server values when the payload is complete", () => {
    const merged = mergeOptions(
      envelope({
        price_tiers: [{ value: "standard", label: "标准（新口径 ¥6,000）" }],
        gate_statuses: [{ value: "passed", label: "已过门", tone: "success" }],
        c_handling_options: [{ value: "scope_cut", label: "① 缩范围" }],
        sow_options: [{ value: "b", label: "B 试点" }],
        business_categories: [{ key: "contract", value: "商务合约", label: "商务合约" }],
      }),
    )

    expect(merged.price_tiers[0].label).toBe("标准（新口径 ¥6,000）")
    expect(merged.gate_statuses[0].label).toBe("已过门")
  })

  it("falls back only for the broken group", () => {
    const merged = mergeOptions(
      envelope({
        price_tiers: [{ value: "standard", label: "标准（新口径）" }],
        gate_statuses: "这不是数组",
      }),
    )

    expect(merged.price_tiers[0].label).toBe("标准（新口径）")
    expect(merged.gate_statuses).toEqual(FALLBACK_OPTIONS.gate_statuses)
    expect(merged.sow_options).toEqual(FALLBACK_OPTIONS.sow_options)
  })

  it("rejects a group whose items have the wrong shape", () => {
    // 形状对但字段缺失（例如服务端漏发 tone）——不得让半截数据覆盖兜底：
    // 少了 tone 的门禁状态渲染出来就是没有样式类的徽标。
    const merged = mergeOptions(
      envelope({
        gate_statuses: [{ value: "passed", label: "已过门" }],
        business_categories: [{ key: "contract", value: "商务合约" }],
      }),
    )

    expect(merged.gate_statuses).toEqual(FALLBACK_OPTIONS.gate_statuses)
    expect(merged.business_categories).toEqual(FALLBACK_OPTIONS.business_categories)
    expect(merged.price_tiers).toEqual(FALLBACK_OPTIONS.price_tiers)
  })

  it("falls back to local options when the server says nothing", () => {
    const merged = mergeOptions(envelope({}))

    expect(merged).toEqual(FALLBACK_OPTIONS)
  })

  it("falls back when the whole payload is unusable", () => {
    expect(mergeOptions(undefined)).toEqual(FALLBACK_OPTIONS)
    expect(mergeOptions(null)).toEqual(FALLBACK_OPTIONS)
  })

  it("keeps the five gate states in the local fallback", () => {
    expect(FALLBACK_OPTIONS.gate_statuses.map((item) => item.value)).toEqual([
      "pending",
      "evidence",
      "passed",
      "conditional_pass",
      "failed",
    ])
  })

  it("labels known gate states and degrades gracefully for unknown ones", () => {
    const options: WorkbenchOptions = FALLBACK_OPTIONS

    expect(gateStatusLabel(options, "conditional_pass")).toBe("有条件通过")
    expect(gateStatusTone(options, "failed")).toBe("danger")
    // 未知状态：显示原值 + muted，不得抛错（服务端加新状态时不炸前端）
    expect(gateStatusLabel(options, "brand_new_state")).toBe("brand_new_state")
    expect(gateStatusTone(options, "brand_new_state")).toBe("muted")
  })

  it("keeps legacy chinese business-category values readable", () => {
    // 旧数据存的就是中文标签（改 key/label 不动存库值）
    expect(BUSINESS_CATEGORY_VALUES.pov).toBe("PoV验证")
    expect(businessCategoryKeyOf("PoV验证")).toBe("pov")
    expect(businessCategoryKeyOf("不存在的阶段")).toBeNull()
  })
})
