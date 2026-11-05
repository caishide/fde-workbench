# UI/UX 美化方案 · 实施记录（S2 / S3）

| 项 | 值 |
| --- | --- |
| 状态 | **已实施，验收中** |
| 对应方案 | `docs/UI-UX美化方案-v2.md` §3.1–§3.8、§4「S2 / S3」 |
| 上一轮 | B / S0 / S1 见 `docs/UI-UX实施记录-B-S0-S1.md`（已合入 PR#132） |
| 真源 | `docs/tokens.json`（新增 `decisions.D5` 记录本轮决策） |
| 实施分支 | `feat/ui-ux-blackgold-b-s0-s1`（PR#133） |
| 实施日期 | 2026-11-06 |
| 业务红线 | 不改门禁 G1–G9、审批链、危险确认强制度、客户资料代号化；不改 `server/**`、数据库与迁移；不引入新依赖 / UI 库 / CSS 框架 / 外部字体 / 运行时样式注入；不改路由与导航守卫 |

---

## 1. S2 · 一致性与层级

### 1.1 五个最小 UI 原语（新增 `components/ui/`）

| 文件 | 职责 | 关键约束 |
| --- | --- | --- |
| `Button.tsx` | `UiButton`（variant / compact / busy / busyLabel）+ `AsyncButton`（内含 `useAsyncAction` 状态机） | 沿用 S0 已收敛的按钮族 class，不新增 CSS 契约、不引入 UI 库 |
| `Modal.tsx` | `role="dialog" aria-modal="true"` + `aria-labelledby`/`describedby`；Esc / Tab 陷阱 / 焦点移入 / 焦点归还 | 叠加更上层 aria-modal 时自动让位；只负责呈现层，密码校验与人工确认强度由调用方保留 |
| `Toast.tsx` | 单一 ToastHost；success/info=`role="status"`、error/warning=`role="alert"` | 只新增回执通道，不接管各页行内错误 |
| `Loading.tsx` | `Loading`（统一 `role="status"`）+ `EmptyState`（统一 `.empty-state`） | — |
| `index.ts` | 统一导出 | — |

### 1.2 两个 Provider

| 文件 | 职责 |
| --- | --- |
| `common/ConfirmProvider.tsx` | 普通确认的唯一异步通道，取代散落的原生 `window.confirm`。**不做密码校验**——需二次校验的危险操作仍走 `useDangerConfirm()` |
| `components/ui/Toast.tsx` 的 `ToastProvider` | 全局 ToastHost，已挂载于 `App.tsx` |

两者都额外提供模块级便捷入口 `confirmAsync()` / `showToast()`：部分遗留调用点位于深层 async 回调里，插入 hook 会牵动组件签名；Provider 挂载时注册、卸载即失效。新代码优先用 `useConfirm()` / `useToast()`。

### 1.3 F6 · 原生确认归一：16 → 8 处

| 改造点 | 原 | 新 |
| --- | --- | --- |
| `layout/AppShell.tsx` 退出登录 | `window.confirm` | `useConfirm()` |
| `ai/AIServerChat.tsx` 删除对话 | `window.confirm` | `confirmAsync()`（`tone: "danger"`） |
| `library/ProjectLibrary.tsx` 重新生成 | `window.confirm` | `confirmAsync()` |
| `projects/NewProjectPageV2.tsx` 另存模板草稿 | `window.confirm` | `confirmAsync()` |
| `research/ResearchWorkspace.tsx` 导出调研表 | `window.confirm` | `confirmAsync()` |
| `ai/AIActionConfirmation.tsx` 未确认告警 | `window.alert` | `showToast(..., "warning")` |
| `projects/NewProjectPageV2.tsx` × 2 保存/上传失败 | `window.alert` × 2 | `showToast(..., "error")` × 2 |

**剩余 8 处保留原生确认**，全部位于 `registerHashNavigationGuard` 的守卫回调或同步关闭流程：守卫回调**必须同步返回 boolean**，改成异步 Modal 会让切页保护失效（用户可能在守卫判定前就已跳走）。这是本轮明确记录的取舍（`tokens.json.decisions.D5`）。

静态守卫上限由 16 下调到 **8**。

### 1.4 F3 · 加载与空状态收敛

20 处散落的 `<p role="status">正在加载…</p>` 统一为 `<Loading label="…" />`；覆盖 `App.tsx`、`AccountPage`、`ExtensionsPage`、`SkillVersionsPage`、`FilePreview`、`FileVersionTimeline`、`PresurveyIntakeCard`、`MetricsReportPage`、`ModulesPage`、`GlossaryPage`、`PilotReportPage`、`GanttChart`、`GateBoard`、`ProjectDocuments`、`ProjectFiles`、`DocumentTemplatesPage`、`ProjectsPage`、`ProjectTemplateStep`、`TaskCenterPage`。

### 1.5 F4 · 统一错误码表

新增 `common/errorMessages.ts`：收录**跨页复用**的错误码（实测 `forbidden` 20 处、`stale_version` 10 处、`authentication_refreshed_resubmit` 6 处、`stale_session_response` 5 处、`project_not_found` 4 处、`network_error` 3 处等），提供 `errorMessage(error, fallback)`。

**保留页面专属措辞的两处**（不丢上下文）：
- `ModulesPage` 的 `stale_version` → 「模块已被其他人更新；**已保留当前表单**，请刷新版本后重试。」
- `TemplatesPage` 的 `stale_version` → 「模板已被其他操作更新；**本地状态未改变**，请刷新后重试。」

### 1.6 N1 · 侧栏四组

侧栏 15 项按方案分四组并加分隔：**工作区**（项目工作台 / 集成桥 / 任务中心 / 翻译器）、**交付与商业**（派单池 / 指标报表 / 试点报告）、**资源**（AI 与扩展 / 使用帮助 / 行业模板 / 文档模板）、**管理**（模块管理 / 用户管理 / 系统配置）。`isPlatform` / `isAdmin` 条件与顺序原样保留；折叠态隐藏分组标题但**保留每个链接的 `aria-label` / `title`**。

### 1.7 S2 验收

- `npm run typecheck` 通过。
- 全量回归：**68 文件 / 806 用例全绿**。
- 新增守卫 `tests/renderer/ui-primitives.test.tsx`（6 例）：统一确认 Modal 的 resolve true / resolve false、Toast 的 `role=status` vs `role=alert`、模块级 `showToast`、`Loading` 的 `role=status`、统一错误码表。

---

## 2. S3 · 治理与文档

### 2.1 G1 · z-index 收编

新增 6 个层级令牌并把 **8 个 CSS 文件里的全部裸 z-index** 收编：

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--z-base` | 1 | 同层内定位 |
| `--z-sticky` | 10 | sticky 表头 / 粘性操作条 |
| `--z-dropdown` | 40 | 下拉浮层 |
| `--z-rail` | 90 | 侧边栏 / 看板覆盖层 |
| `--z-float` | 1000 | 弹窗遮罩 |
| `--z-float-top` | 1200 | Toast / AI 执行面板 |

### 2.2 G6 · 阴影令牌误用修复

修复 2 处**语法错误级**误用——把整个阴影值当颜色拼进 `box-shadow`：

```
box-shadow: 0 1px 3px var(--shadow-sm);   →  box-shadow: var(--shadow-xs);
```

同时把散落的硬编码阴影收编为 `--shadow-focus-gold` / `--shadow-inset-gold` / `--shadow-sticky-bottom` / `--shadow-modal` / `--shadow-panel` / `--shadow-brand-hover` / `--shadow-tab-brand` / `--shadow-icon-tile` / `--shadow-dropdown-neutral` / `--shadow-drop-marker(-before)` / `--shadow-ai-*` 等令牌。

**剩余裸 box-shadow 归零**（焦点环 `0 0 0 Npx var(--brand-*)` 与 inset 描边属方向性/聚焦语义，保留）。

### 2.3 C7 · 字阶收编

新增 `--font-tiny 10px` / `--font-micro 11px` / `--font-title 20px` 三档，把 **144 处硬编码字号**归入语义档位。残留 15 处非标准值（15/17/18/19/22/23/24/26px）属遗留、不属任何档位，**已登记为已知差距**并写进守卫白名单。

### 2.4 窄屏断点：**保留而非删除**

方案 §3.6 称「13 处 ≤900px 是死 `@media`」。本轮核实**该判断不成立**：

- 主窗口 `minWidth: 960`（`desktop/src/main/index.ts:103`）；
- 但 Electron 用户可用 `Ctrl +/-` 缩放，viewport 随之变窄 → 这些断点在缩放下**仍会生效**；
- 删除会造成缩放场景下的视觉回归。

因此 S3 改为**在 5 个含窄屏断点的 CSS 顶部加注释说明**，并写进 `UI规范-v1.md §6`。此取舍记录在 `tokens.json.decisions.D5`。

### 2.5 两份规范文档（新增）

| 文档 | 内容 |
| --- | --- |
| `desktop/UI规范-v1.md` | 色板 / 对比度判据 / 字阶 / 间距圆角 / 阴影与层级 / 组件样式契约 / 响应式 / 禁止事项 / 深色模式结论 |
| `desktop/无障碍规范-v1.md` | 判据总表 / 键盘（焦点环、弹窗契约、导航守卫不可异步）/ 语义播报 / 表单 / 对比度 / 守卫清单 / 已知差距 |

### 2.6 S3 静态守卫

`design-tokens.test.ts` 由 10 例扩到 **15 例**，新增 5 例：

1. z-index 全部取自 `--z-*`，无裸数值；
2. `--z-*` 令牌已在 `:root` 定义；
3. 字号不再出现裸 px（非标准遗留值走白名单）；
4. 阴影不出现令牌误用（按逗号分段判定，避免误判合法的多段阴影）；
5. box-shadow 不出现裸 rgba 阴影（焦点环与 inset 描边除外）。

---

## 3. 本轮修复的问题

| 问题 | 修复 |
| --- | --- |
| S2 引入 8 个既有测试失败 | ① 2 个是 `stale_version` 措辞被统一表覆盖、丢了页面上下文 → 恢复页面专属措辞；② 6 个是用 `vi.spyOn(window, "confirm")` 驱动确认，改为操作统一 Modal（新增 `test-utils.answerConfirmDialog` 助手），**断言意图保持不变** |
| `new-project` 路由跳转被 Modal 阻塞 | 原生 confirm 是同步的，异步 Modal 会阻塞后续跳转 → 断言顺序改为「先答 Modal，再断言路由」 |
| `test-utils` 缺 `cleanup` 导致测试间 DOM 残留 | `getByRole` 撞到多个元素 → 补 `afterEach(cleanup)` |
| import 脚本误插到多行 import 语句中间 | 3 个文件语法错 → 脚本化复原，并改用「末行单行 import」作为锚点 |
| `errorMessage` 曾回退到服务端原文 | 会把英文技术信息暴露给用户 → 改为「公共表优先，未收录走页面兜底」 |
| 守卫正则误判合法的多段阴影 | 改为按逗号分段判定 |
| `tokens.json` 出现重复键（`typography`/`elevation`） | 合并进既有 `font.scale` / `shadow` / `zIndex` 结构 |

---

## 4. 已知差距与未做

| 项 | 说明 |
| --- | --- |
| 15 处非标准字号 | 15/17/18/19/22/23/24/26px，不属任何语义档位；已登记、可后续补档 |
| 8 处原生确认 | 同步导航守卫，不可异步化；已锁上限 |
| 少量表单缺 `htmlFor` | 已在部分页面存在，未逐页补齐 |
| 深色模式 | 按方案**仅评估不实施**（见 `UI规范-v1.md §8`） |
| 屏幕阅读器实机验证 | 未做，需真实 NVDA / VoiceOver 环境 |
| 便携版重打包 + asar 字节验证 | 仍按 2026-11-06 拍板暂缓，等工作树收口或明确发行时机 |
| 品牌生成脚本（7 个 `.py`） | 从 PR#132 移出（会误触发服务端类型/测试钩子），另开 PR |

---

📌 下次迭代卡
- 本次已交付：S2（5 原语 / 2 Provider / 确认归一 16→8 / 加载与空状态收敛 / 统一错误码表 / 侧栏四组）+ S3（z-index 与字号与阴影收编 / 2 份规范文档 / 5 条新守卫）
- 下次回来做什么：把 15 处非标准字号补进字阶档位；做一次真实读屏（NVDA / VoiceOver）全流程回归，逐项销账「已知差距」表；启动深色模式评估（先出语义色暗色版方案）
- 需带来的材料：日常使用中「看不清 / 太挤 / 找不到」的具体页面截图；一次完整操作录屏
