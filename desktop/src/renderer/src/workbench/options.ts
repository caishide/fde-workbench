/**
 * 业务枚举选项表（WP29/J1）：服务端下发 + 本地兜底。
 *
 * 口径真源在服务端 `GET /api/v1/workbench/options`（server/src/fde_api/workbench/options.py）。
 * 前端保留一份本地兜底：服务端不可达（离线/后端未起）时界面仍能渲染，
 * 但下发的选项优先——避免两边各改一份却不知谁生效。
 *
 * 契约纪律：value 沿用既有存库值（tier="standard"、status="conditional_pass"、
 * business_category=中文标签），本文件不改任何字段契约。
 */

export interface OptionItem {
  value: string
  label: string
}

export interface GateStatusOption extends OptionItem {
  tone: string
}

export interface BusinessCategoryOption {
  /** 稳定标识（前端按 key 引用，不依赖中文文案） */
  key: string
  /** 存库值——历史数据存的就是中文标签，不可改 */
  value: string
  label: string
}

export interface WorkbenchOptions {
  price_tiers: OptionItem[]
  gate_statuses: GateStatusOption[]
  c_handling_options: OptionItem[]
  sow_options: OptionItem[]
  business_categories: BusinessCategoryOption[]
}

/** 本地兜底：与 server/src/fde_api/workbench/options.py 一致（服务端不可达时用）。 */
export const FALLBACK_OPTIONS: WorkbenchOptions = {
  price_tiers: [
    { value: "light", label: "轻量（25h / 现金 ¥1,500）" },
    { value: "standard", label: "标准（50h / 现金 ¥5,000）" },
    { value: "flagship", label: "旗舰（80h / 现金 ¥9,000）" },
  ],
  gate_statuses: [
    { value: "pending", label: "待证据", tone: "muted" },
    { value: "evidence", label: "待核验", tone: "warning" },
    { value: "passed", label: "已过门", tone: "success" },
    { value: "conditional_pass", label: "有条件通过", tone: "warning" },
    { value: "failed", label: "未过门", tone: "danger" },
  ],
  c_handling_options: [
    { value: "scope_cut", label: "① 缩范围" },
    { value: "split_phases", label: "② 拆分期" },
    { value: "external_collab", label: "③ 外部协作" },
    { value: "ticket_deal", label: "④ 门票单（记亏损与补回路径）" },
  ],
  sow_options: [
    { value: "b", label: "B 试点（50/50）" },
    { value: "c", label: "C 集成（40/40/20）" },
    { value: "a", label: "A 诊断（预付）" },
    { value: "d", label: "D 陪跑（月付预付）" },
  ],
  business_categories: [
    { key: "contract", value: "商务合约", label: "商务合约" },
    { key: "presurvey", value: "预调研", label: "预调研" },
    { key: "research", value: "调研", label: "调研" },
    { key: "pov", value: "PoV验证", label: "PoV验证" },
    { key: "deployment", value: "生产部署", label: "生产部署" },
    { key: "handover", value: "培训预交接", label: "培训预交接" },
  ],
}

interface Envelope<T> {
  data: T
  error: unknown
}

function isOptionItem(value: unknown): value is OptionItem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as OptionItem).value === "string" &&
    typeof (value as OptionItem).label === "string"
  )
}

function isBusinessCategory(value: unknown): value is BusinessCategoryOption {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as BusinessCategoryOption).key === "string" &&
    typeof (value as BusinessCategoryOption).value === "string" &&
    typeof (value as BusinessCategoryOption).label === "string"
  )
}

/**
 * 校验并合并服务端下发：任何一组缺失/类型不对就用本地兜底补齐那一组，
 * 绝不用半截数据覆盖（半个选项表比没有更危险）。
 */
export function mergeOptions(payload: unknown): WorkbenchOptions {
  const data = (payload as Envelope<unknown> | null)?.data
  const source = (data ?? {}) as Partial<WorkbenchOptions>
  const pick = <T>(value: unknown, guard: (item: unknown) => item is T, fallback: T[]): T[] =>
    Array.isArray(value) && value.length > 0 && value.every(guard) ? (value as T[]) : fallback
  return {
    price_tiers: pick(source.price_tiers, isOptionItem, FALLBACK_OPTIONS.price_tiers),
    gate_statuses: pick(
      source.gate_statuses,
      (item): item is GateStatusOption =>
        isOptionItem(item) && typeof (item as GateStatusOption).tone === "string",
      FALLBACK_OPTIONS.gate_statuses,
    ),
    c_handling_options: pick(
      source.c_handling_options,
      isOptionItem,
      FALLBACK_OPTIONS.c_handling_options,
    ),
    sow_options: pick(source.sow_options, isOptionItem, FALLBACK_OPTIONS.sow_options),
    business_categories: pick(
      source.business_categories,
      isBusinessCategory,
      FALLBACK_OPTIONS.business_categories,
    ),
  }
}

/** 门禁状态 → 显示标签（含未知状态兜底显示原值）。 */
export function gateStatusLabel(options: WorkbenchOptions, status: string): string {
  return options.gate_statuses.find((item) => item.value === status)?.label ?? status
}

/** 门禁状态 → 徽标样式（未知状态用 muted）。 */
export function gateStatusTone(options: WorkbenchOptions, status: string): string {
  return options.gate_statuses.find((item) => item.value === status)?.tone ?? "muted"
}
