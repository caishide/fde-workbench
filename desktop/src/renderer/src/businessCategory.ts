/**
 * The fixed business stage shared by project files and project documents.
 *
 * The stored value is still the Chinese label (legacy data compatibility — the
 * column holds 中文标签, see server/src/fde_api/workbench/options.py); the
 * `key` is a stable identifier for referencing a stage in code, so display
 * wording can change without touching stored rows.
 *
 * `BUSINESS_CATEGORY_UNCATEGORIZED_LABEL` (未分类) is only a filter token for
 * the list dropdowns, never a stored column value (uncategorized is stored as
 * `NULL`).
 */
export const BUSINESS_CATEGORIES = [
  "商务合约",
  "预调研",
  "调研",
  "PoV验证",
  "生产部署",
  "培训预交接",
] as const

export type BusinessCategory = (typeof BUSINESS_CATEGORIES)[number]

/** Filter token meaning "no business stage assigned" (stored as `NULL`). */
export const BUSINESS_CATEGORY_UNCATEGORIZED_LABEL = "未分类"

/** Stable identifier per business stage (J1: 稳定 key + 显示标签分离). */
export const BUSINESS_CATEGORY_KEYS = [
  "contract",
  "presurvey",
  "research",
  "pov",
  "deployment",
  "handover",
] as const

export type BusinessCategoryKey = (typeof BUSINESS_CATEGORY_KEYS)[number]

/** Human-readable select/chip labels for the six business stages. */
export const BUSINESS_CATEGORY_LABELS: Record<BusinessCategory, string> = {
  商务合约: "商务合约",
  预调研: "预调研",
  调研: "调研",
  PoV验证: "PoV验证",
  生产部署: "生产部署",
  培训预交接: "培训预交接",
}

/** Stable key → stored value（按 key 取存库值，旧中文数据照常可读）。 */
export const BUSINESS_CATEGORY_VALUES: Record<BusinessCategoryKey, BusinessCategory> = {
  contract: "商务合约",
  presurvey: "预调研",
  research: "调研",
  pov: "PoV验证",
  deployment: "生产部署",
  handover: "培训预交接",
}

/** 存库值 → 稳定 key（读取旧数据时反查用；未知值返回 null，不猜）。 */
export function businessCategoryKeyOf(value: string): BusinessCategoryKey | null {
  const entry = (Object.entries(BUSINESS_CATEGORY_VALUES) as [BusinessCategoryKey, string][])
    .find(([, stored]) => stored === value)
  return entry ? entry[0] : null
}
