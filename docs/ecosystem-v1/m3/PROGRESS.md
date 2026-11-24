# Ecosystem OS M3 — 角色工作台与伙伴自助运营 · 实施进度

**状态行**：**D-5 轮（候选 1＋2）实施完成（2026-11-24，分支 `feat/ecosystem-m3-partner-inbox`）**；候选 3–6 未排期（导师角色落法仍待拍板——矩阵 §7-2）。

---

## 一、D-5 轮：区域伙伴自助运营页 ＋ 派单收件箱三态分流（2026-11-24）

**拍板依据**：M2 批次四同日交互式 D-5＝①M3 候选 1＋2（伙伴页＋收件箱）——零角色新增零新角色体系；端策略＝伙伴 web 优先（桌面与 web 共用同一套 React UI，仓内零 Nginx 变更——vhost 属宿主动作，矩阵 §7-4 留待部署负责人）。

### 候选 1：伙伴自助运营页（`#partner/operations`）

| 面 | 内容 | 锚点 |
|---|---|---|
| 页面 | NEW `PartnerOperationsPage.tsx`——我的伙伴申请（列表＋详情展开＋自证申请表单）＋区域合作阶梯目录（含售卖闸状态徽标：目录可见 ≠ 可签约）＋我的运营待办（主体收敛只读区）；零新 CSS（复用既有 class） | `desktop/src/renderer/src/commercial/` |
| 接线 | 路由四件套（RouteKind union／parse／routeHash）＋App 渲染＋AppShell 导航项（「交付与商业」组，登录即可见——申请是当事人自证语义） | `routing/useHashRoute.ts`·`App.tsx`·`layout/AppShell.tsx` |
| 服务端 | 页面消费**全部既有端点**（`GET/POST /commercial/regional-partners` 本人收敛／`GET /regional-partners/<id>` 阶段注记派生／`GET /regional-partner-tiers` 阶梯＋`sale_gate_status`）——伙伴页面零新商业端点 | `commercial/routes.py`（既有） |

### 候选 2：派单收件箱三态分流（纯前端）

- `MyOffersPage.tsx`：平铺列表 → **四组分段**（临期待响应／待响应／已超时／已处理；空组不渲染）。NEW `INBOX_SOON_WINDOW_HOURS = 2`（**纯视觉阈值**——过期判定权威仍是服务端状态机 offered→expired，临期不参与任何接单/拒单可行性判定，B1 时间窗纪律不破）；OfferRow 动作区零改动。

### 服务端：`GET /api/v1/ops/todos/mine`（唯一新端点，+1 路由）

| 面 | 内容 |
|---|---|
| 主体收敛闭集 | `SUBJECT_SCOPED_DOMAINS = (automation_approval, api_confirmation, dispatch_offer)`——审批按 `requested_by_user_id`／AI 确认按 `OperationEvent.actor_user_id`（确认义务人＝发起人本人）／offer 按 `candidate_user_id`，**三域全部硬 FK** |
| meeting_todo 显式排除 | owner 是纪要内自由文本，无用户 FK，不可作主体口径（与「文本前缀不可作分层口径」同纪律）；模块头留痕＋静态钉 |
| 实现形态 | 四 collector 加 `actor_id=None` 可选参（None＝admin 全量视图**逐字节原行为零回归**）；投影/排序抽 `_project` 单一权威两视图共用 |
| 纪律 | 零 DDL／零写路径／零事件追加（WP-2 A4/A6 纪律沿袭）；无 admin 门但每人只见自己的条目，天然无越权面 |

### 验收证据

- **服务端**：NEW `test_ecosystem_m3_partner_inbox.py` **7 钉**（三域收敛两向／meeting_todo 排除＋admin 版在场证伪／域闭集 400／401／A4 只读快照／闭集字面＋路由单点静态钉／服务函数≡路由投影）；**变异四连全杀 fragment 级**（M1 闭集收编 meeting_todo→静态闭集钉／M2 路由主体过滤拆→收敛钉／M3 审批谓词翻转→收敛钉／M4 401 闸摘→401 钉）＋字节级还原复绿。定向：新钉 7＋M2 todos 30＋brief 30＋regional partners 回归全绿；mypy 基线 274 零新增；ruff 清。
- **桌面**：typecheck 零错；NEW `partner-operations.test.tsx` 3 例（三分卡渲染＋申请表单 POST 载荷／三态分组归属 with 断言）；dispatch-mine＋dispatch-page 既有回归 16 passed；桌面全量 vitest 见回执。
- **口径**：**573 路由／59 蓝图／172 表／102 迁移单头 `b8d2f6a0c4e8`**（inventory/route CSV 已刷新 +1 行 `GET /api/v1/ops/todos/mine`；archify candidate 换代 573＋finalize review-7 四闸＋preview 整页实拍）。

### D-6 按建议备件（同轮 docs）

NEW `docs/ecosystem-v1/m3/02-human-pilot-walkthrough-kit.md`＝人工首片试点走查手册（目标与判停线／三方人选位待蔡工亲定／七步分步脚本含预期与留痕／观察表字段激活）——**只备件不代办**（场次与人选归蔡工）。

## 二、待决与留账

| # | 事项 | 状态 |
|---|---|---|
| 1 | 候选 3（企业登录落点）／候选 4（我的商机页）／候选 6（学员训练入口） | 未排期（矩阵 §5 有估算） |
| 2 | 候选 5 导师训练队列 | **须先拍板角色落法**（R1–R4＋兼任＋audit 席位只读的组合建议在矩阵 §7-2；不新增角色枚举） |
| 3 | web 伙伴端公网 vhost | 宿主动作，与部署负责人对齐（矩阵 §7-4） |
| 4 | SMTP 真发信轮 | **已授权待凭据**（蔡工亲手填部署态 `server/.env` 后 AI 验证＋真发测试邮件） |

---

## 开工拍板与收口补录（2026-11-24，协调席盘点轮）

**P1 拍板（交互式选择题四项全推荐项）**：
1. **M3 候选 1＋2 同轮开工批准**（范围/预算/验收草案见决策单②：`05_AI方案/EcosystemOS_决策单_M2遗留收敛与M3开工_呈P1_20261124.md`）；
2. **BLOCKED 清理**：optimization O-04（UX P0）／O-05（N1 关窗）两条过时行销项；O-01 与 goal-regtrial B1/B2/B3 合并为单一「发信通道与公网注册开闸」待决项（随本轮 PR 落 `docs/optimization/BLOCKED.md`）；
3. **O-01 维持挂账本轮不启动**（SMTP 真凭据带外另行提供；AI 不代持凭据不入库）；
4. **D-3 DIFF-09 实签维持待业务＋财务**（方向预拍板「披露改写为落库口径」在案，材料随取）。

**收口核查（本会话对 staged 快照的只读符合性核查，全过）**：
- 范围符合 D-5：候选 1＝`GET /api/v1/ops/todos/mine`（主体收敛只读变体）＋`PartnerOperationsPage`（三分卡＋申请表单）；候选 2＝`MyOffersPage` 四组分流（临期/待响应/已超时/已处理，`INBOX_SOON_WINDOW_HOURS=2` 字面导出，过期判定权威＝服务端状态机——B1 纪律写明）；
- **申请表单越权核查**：POST 打的是既有 `apply_regional_partner_route`（免费当事人自证动作，require_auth）——非 admin 面，不越权；
- 服务端投影：三域硬 FK 主体收敛（审批=requested_by／确认=actor／offer=candidate）、`meeting_todo` 显式排除（owner 自由文本无 FK 不可作主体口径）、`_project` 投影单一权威抽出、admin 全量视图显式传 `None` 零回归；
- 口径：572→**573** 路由（+1 `todos/mine`），inventory/route CSV/archify 已刷；
- 测试：服务端 7 例（主体三域收敛／meeting 排除／闭集拒绝／401／零写副作用／闭集字面钉＋路由单点／collect≡路由投影）＋桌面 3 例（三分卡＋申请载荷＋四组分流）。

**收口补强（本会话）**：
- **引用闭集钉再换代**（#581 家族第二次）：M3 伙伴页消费 `/todos/mine`（含 `/todos` 子串）⇒ WP-5 的「闭集＝{OpsBriefPanel}」按设计转红 ⇒ 换代为**许可面闭集** `DESKTOP_OPS_PANELS`＝{admin 呈现面板, 伙伴运营页}（新消费点必须显式登记）；briefs 钉保持单点语义（伙伴页不消费 briefs，未来要生成简报须显式扩闭集）。**三向变异全杀**（未登记第三调用点／许可面引用抽走／briefs 闭集未扩先引用）＋字节还原复绿。
- 定向 68 passed（m3 7＋m2 ops 17＋brief 9＋cards 30）＋桌面定向 8 passed＋typecheck 零错＋mypy 274 零新增＋ruff 清。

**流程教训（第二次同族）**：跨端引用面钉是「活清单」——每加一个桌面消费点都会转红，这是设计行为；新消费点的实施轮必须**同步登记闭集**并跑引用面扫描类钉（#581 教训的复利：本次在本地定向跑出，未进 CI）。
