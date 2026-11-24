# Ecosystem OS M3 — 角色工作台与伙伴自助运营 · 实施进度

**状态行**：**D-5 轮（候选 1＋2）已合并并活体部署完成（2026-11-24，PR #590 squash `1d2da122`＝fork/main 顶）**；候选 3–6 未排期（导师角色落法仍待拍板——矩阵 §7-2）。

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
| 1 | 候选 3（企业登录落点）／候选 4（我的商机页）／候选 6（学员训练入口） | 未排期（矩阵 §5 有估算）。**2026-11-25 OWNER 裁定：等 M1 人工待办第 1 条走查结果再定，现在不开候选 3–6 任何批次**；届时按实际卡点定范围与起草席 |
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

## 三、合并与活体重部署回执（2026-11-24 晚）

**合并**：PR **#590** squash `1d2da122`＝fork/main 顶（CI 四 job × 双 run 全绿；分支 `feat/ecosystem-m3-partner-inbox` 与隔离树 `fde-wt-ecosystem-m3` 已清；origin 上游零触碰）。

**活体重部署三验全绿**（2026-11-24 晚，从 main 顶重建）：
- 活体 `url_map` non-static＝**573**（572→573，本轮 +1 `GET /api/v1/ops/todos/mine`）／蓝图 59 ≡ inventory 口径真身；
- 容器内 `alembic current`＝`b8d2f6a0c4e8 (head)`（本轮零迁移，升级 no-op）；
- 三镜像 ID 逐位一致＝本席构建 `c0522cced0ef`（aliyun shim 单构建三次 tag）；★**21:06 收口席等价重建覆盖**＝Windows 宿主预下 68 wheels＋临时 Dockerfile `--no-index` 离线安装（同 CDN 拥塞家族绕行、路径不同：wheels 离线 vs aliyun shim），活体三容器现跑 **`706940af2635`**（单构建 tag×3）——两镜像同为 `1d2da122` 的 `server/` 代码（pip check 无损／lock 67 包 missing NONE／关键导入 OK）＝运行时等价；**收口席 21:1x 三验复测全绿＋本席对 `706940af` 复跑 HTTP 探针全过**（todos 401／todos/mine 401／briefs/generate 401／dispatch 401×2／ready-live 200）；migrations 挂载源＝主树 `/mnt/d/test/fde-workbench/server/migrations`；三容器 healthy。**镜像 ID 属时点值，以活体 `docker inspect` 为准（当前 `706940af2635`）。**

**部署态验收判据全过**（容器内 HTTP 探针）：`/api/v1/ops/todos` GET ⇒ 401／**`/api/v1/ops/todos/mine` GET ⇒ 401**（本轮新端点：路由在场＋鉴权闸生效）／`/api/v1/ops/briefs/generate` POST ⇒ 401／dispatch profiles 两入口 ⇒ 401／ready-live ⇒ 200。部署态简报分层探针（probe_brief_v3）＝`by_data_origin` 分层在位、`- 交付包：drill accepted 4`＋`- 派单 offer：drill accepted 4` 在场、来源 token 闭集、旧未分层声明退役、funnel 三层嵌套形状（批次四回执口径复测过）。

**桌面交付物（DoD 补齐）**：正式便携包 **r61**（`蔡工FDE-0.3.0-便携版-r61`，asar sha256 `f3d88767b74fa30e1c0d805cf69d128f4b37d8099b19337c7cf5663b374b1e10`；`0.3.0-r61` 正向 1／`0.3.0-r60` 反向 0，python bytes.find＋GNU grep 双证；本轮 marker「伙伴运营」「临期待响应」「我的运营待办」「ops/todos/mine」全正向命中，r60 特征「生成运营简报」保留＝回归确认；EBUSY 句柄锁按 r51 先例以独立输出目录 `release-r61` 绕行；r60 包目录已被清理，反向验证以登记 sha256 `8f14fd87…` 差异替代逐字节比对）。三源 bump：RELEASE-COUNTER＝61＋`desktop/package.json`＋`fde-web-bridge.ts`。

**部署排障留痕（PyPI/debian CDN 晚高峰拥塞家族）**：晚间部署窗口撞跨境 CDN 拥塞——`files.pythonhosted.org` 与 `deb.debian.org`（同为 fastly）实测 40–60 kB/s 且长连接**静默断连**（pip/apt 各挂死一次：进程零 TCP 零 CPU 不超时；首例 37 分钟「假挂真慢」被误杀，第二例由「日志停滞 5 分钟＋pip 零 TCP＋脚本仍在跑」三信号守望判中）。**处置＝构建期临时 shim Dockerfile**（不入仓，差异仅两处：apt 源 sed 至 aliyun＋`ENV PIP_INDEX_URL=aliyun pypi 镜像`；镜像实测 8.76 MB/s ≈ 200×），直构单镜像 tag×3 后走原链 recreate→alembic→三验→探针。**该 shim 属构建期偏差，运行时行为与原版 Dockerfile 产物一致；网络健康窗口可用原版 Dockerfile 重建收敛（可推翻）。**并发会话（收口席）的重复部署线（`redeploy_m3.sh`＋`server/wheels/` wheelhouse）与本线同时撞同款拥塞：其 compose build 卡死后改道 **Windows 宿主预下 68 wheels＋临时 Dockerfile `--no-index` 离线安装**，21:06:35 build＋recreate 完成＝活体被其等价镜像 `706940af2635` 覆盖（其重建时未知本线在途，非抢收口）；两轮构建同为 `1d2da122` 代码运行时等价（pip check 无损／lock missing NONE），两席各自三验＋HTTP 探针全绿。`.tmp-deploy/` 与 `server/wheels/` 留痕归收口席处置。

**收口席补注（2026-11-25）**：`.tmp-deploy/` 与 `server/wheels/` 已于 11-24 清除。活体镜像 `706940af2635` 经 `docker history` 实查，相对仓版 Dockerfile 少一步 `pip install --upgrade pip`、多一层 94.1MB 的 wheels，且无构建提交标签；上段所称「等价」指依赖集合与 `requirements.lock` 一致（容器内 `pip check` 通过），不指逐层相同。下次因 `server/` 改动按仓版 Dockerfile 重建即收敛。

**COORDINATION**：并发会话（收口席）对本席 staged 快照完成核查＋钉换代收强（`DESKTOP_OPS_PANELS` 许可面闭集）并以同一 PR #590 合入，P1 四项拍板（M3 同轮开工批准／BLOCKED 清理／O-01 维持挂账／DIFF-09 维持待业务＋财务）随轮留痕（见「开工拍板与收口补录」节）。
