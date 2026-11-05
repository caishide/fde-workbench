# 蔡工 FDE 智能交付系统 · UI 规范 v1

> 状态：**v1（2026-11-06 随 S3 落地）** ｜ 真源：`docs/tokens.json` ｜ 运行时镜像：`desktop/src/renderer/src/styles.css` 的 `:root`
>
> 本文件与 `docs/tokens.json` **同源**：`tokens.json` 是机器可读真源，本文件是人读口径。
> 改色值 / 间距 / 字阶 → 改 `tokens.json` 与 `:root`，并跑 `desktop/tests/main/design-tokens.test.ts` 复核。

---

## 1. 色彩

### 1.1 品牌色阶（黑金）

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--brand-ink` | `#14181C` | 石墨黑：主文字、主按钮文字、深底前景 |
| `--gold-5` | `#A3721F` | 深金：主按钮描边、hover 激活 |
| `--gold-4` | `#C98F2B` | 金墨：辅助强调（**不作描边**，对白底仅 2.82:1） |
| `--brand-gold-bright` | `#F5B44A` | 亮金：焦点环、深底提亮 |
| `--brand-ink` | `#14181C` | 深底底色 |

### 1.2 对比度判据（可测量，非目测）

| 用途 | 阈值 | 示例 |
| --- | --- | --- |
| 正文 | ≥4.5:1（WCAG AA） | `#14181C` on `#FFFFFF` = 17.84:1 |
| 大字 / UI 组件 / 焦点环 | ≥3:1 | `#A3721F` on `#FFFFFF` = 4.21:1 |

**红线**：`#C98F2B`（`--gold-4`）对白底 2.82:1，**不得用作描边或文字色**。描边一律用 `--gold-5`。

### 1.3 语义色

| 语义 | 主色 | 浅底 | 边框 | 深墨文字 |
| --- | --- | --- | --- | --- |
| 成功 | `--success` | `--success-soft` | `--success-border` | `--success-ink` `#0B6E3D` |
| 警告 | `--warning` | `--warning-soft` | `--warning-border` | `--warning-ink` `#8A3F06` |
| 危险 | `--danger` | `--danger-soft` | `--danger-border` | `--danger-ink` `#96261A` |
| 信息 | `--info` | `--info-soft` | `--info-border` | `--info-ink` `#2B3340` |

**规则**：小字（浅底上的说明、徽标、错误文案）必须用 `*-ink`，不用主色。

---

## 2. 排版

### 2.1 字阶

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--font-tiny` | 10px | 极小徽标（极少用） |
| `--font-micro` | 11px | 超小辅助字 |
| `--font-caption` | 12px | 注释、次要说明、版本号 |
| `--font-label` | 13px | 表单标签、表格次要列 |
| `--font-body` | 14px | 正文、按钮 |
| `--font-section` | 16px | 小节标题 |
| `--font-title` | 20px | 卡片标题 |
| `--font-page` | 24px | 页面标题 |

**规则**：CSS 里**不允许**再写裸 `font-size: Npx`（现存 15 处非标准值属遗留，新增一律用令牌）。

### 2.2 字重与行高

`--weight-regular / --weight-medium / --weight-semibold / --weight-bold`；正文行高 1.5–1.6，标题 1.45。

---

## 3. 间距与圆角

- 间距：`--space-1` 至 `--space-8`，4px 基准。
- 圆角：`--radius-xs 7 / --radius-sm 9 / --radius-md 12 / --radius 14 / --radius-lg 20 / --radius-pill 999`。
- 组件内边距优先用 `--space-*`；卡片内 16px、表单块 24px。

---

## 4. 阴影与层级

### 4.1 阴影

统一走 `--shadow-xs / --shadow-sm / --shadow / --shadow-md / --shadow-lg / --shadow-xl`（静态卡片→浮层）与 `--shadow-brand`（品牌强调）。
**S3 已把散落的硬编码阴影收敛为 `--shadow-focus-gold` / `--shadow-inset-gold` / `--shadow-sticky-bottom` / `--shadow-modal` / `--shadow-panel` / `--shadow-ai-*` 等令牌。**

**不得**把阴影令牌拼进 `box-shadow` 当颜色用（如 `0 1px 3px var(--shadow-sm)`）—— 这是 S3 已修的 G6 令牌误用，属语法错误。

### 4.2 层级

`z-index` **只能**取自 `:root` 的 `--z-*`：

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--z-base` | 1 | 同层内定位 |
| `--z-sticky` | 10 | sticky 表头 / 粘性操作条 |
| `--z-dropdown` | 40 | 下拉浮层 |
| `--z-rail` | 90 | 侧边栏 / 看板覆盖层 |
| `--z-float` | 1000 | 弹窗遮罩 |
| `--z-float-top` | 1200 | 弹窗之上的浮层（Toast、AI 执行面板） |

S3 已把 8 个 CSS 文件里的**全部裸 z-index 收敛为令牌**，静态守卫会拦新增。

---

## 5. 组件样式契约

| 组件 | class | 要点 |
| --- | --- | --- |
| 主按钮 | `.primary-button` | **白底 + 金描边（`--gold-5`）+ 石墨黑文字**；hover 用同色 1px 外圈 + 阴影，不铺深金底 |
| 次按钮 | `.secondary-button` | 描边按钮；`.compact` 为小尺寸 |
| 危险按钮 | `.danger-button` | 破坏性操作 |
| 卡片 | `.card` / `.panel` | 描边 + `--shadow-sm` |
| 徽标 | `.badge` | `.warning` / `.danger` / `.muted` |
| 提示 | `.notice` | success/info 语义；`.notice.warning` 为警告 |
| 错误 | `.form-error` | 配 `role="alert"` |
| 空状态 | `.empty-state` | 统一形态 |
| 弹窗 | `.dialog` / `.dialog-backdrop` | 必须配 `role="dialog" aria-modal="true"` |

**主按钮渐变禁令**：`--brand-gradient` 只允许用于**非交互展示面**（品牌区、装饰图形）。交互控件（按钮、tab、导航激活态）一律不得铺渐变。

---

## 6. 响应式

- 主机制：`@container workspace` + 侧栏折叠 + `clamp()` padding。
- 窄屏断点（`max-width: 560–900px`）**保留**：主窗口 `minWidth=960px`，但用户可用 `Ctrl +/-` 缩放使 viewport 变窄，这些断点在缩放下仍生效。S3 已核实并加注释，不是「死 @media」。
- 折叠态侧栏仅剩图标，**必须保留 `aria-label` / `title`**。

---

## 7. 禁止事项（会被静态守卫拦下）

| 禁止 | 守卫 |
| --- | --- |
| 新增 `window.confirm` / `window.alert` | `design-tokens.test.ts`（上限 8 处，均为同步导航守卫） |
| 未定义 `var(--primary)` | `design-tokens.test.ts` |
| 裸 `z-index` | S3 新增断言 |
| 裸 `font-size: Npx` | S3 新增断言 |
| 阴影令牌误用 | S3 新增断言 |
| 主按钮铺渐变 | `design-tokens.test.ts` |
| 硬编码产品全名 | `brand-hardcode.test.ts`（红线①） |

---

## 8. 深色模式

**仅评估，不实施**（方案 §4 拍板）。当前所有语义色、阴影、`rgba(255,255,255,...)` 半透明叠加均为浅底假设；深色模式需要重新定义 6 组语义色 + 8 个阴影 + 半透明叠加，工作量等同一次 S0–S3 全量改造，不在当前迭代。

---

📌 下次迭代卡
- 本次已交付：UI 规范 v1（色板 / 字阶 / 间距 / 阴影 / 层级 / 组件契约 / 响应式 / 禁止事项）+ 无障碍规范 v1
- 下次回来做什么：按「深色模式」评估结论排期（先出语义色暗色版方案，再决定是否实施）；或补齐 8 个 CSS 中残留的 15 处非标准字号
- 需带来的材料：日常使用中「看不清 / 太挤 / 想统一」的具体页面截图
