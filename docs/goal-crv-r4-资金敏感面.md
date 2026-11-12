# goal-crv r4 轮记录：资金敏感面（终稿）

> 循环：goal-crv ｜ 轮：r4 ｜ 域：资金敏感面（commercial 全域 16 文件）｜ 审查时点基点：`35ffbea`
> 审读方式：CreateWorkflow 四片（16 文件逐行读档，run `dwfrun-d42e5be6`）＋主会话资金红线横扫（首单扣费闸三条件/售卖闸 closed/CR-028 域定位 dispatch/settlements.py:545 归 r5）
> **结论一句话**：首单扣费闸六序完整＋行锁双钉、记账口径 Numeric/引用不重算/USCC 校验位全绿、售卖闸 fail-closed 结构性排除缺件开门——资金核心闸扎实；真实缺陷集中在**结构性缺口**（席位到期可缺省＝永久席位、无包科目行结算归属失守）与**校验/留痕面脱节**——P1×3／P2×10／P3×3（合并 16 锚），零 P0。

## 1 覆盖声明（§6 三档如实列）

- **逐行读：16 文件**（分配表 r4 主域 `commercial` 全闭合）＝工作流四片（计量与账本面 5／商机归属与区域面 3〔attribution 1420 行两次覆盖〕／模型与权益面 4〔models 1460 行两段读毕〕／席位角色与路由面 4）＋主会话横扫（首单扣费闸/售卖闸态/CR-028 域归属）。
- **抽查：0**（依赖面锚点核实计入 notes 不占逐行档）｜**没读：0**。
- 四片合规声明在案：零执行、零写、未触禁区；判级存疑 5 处如实标注；「观察后未上报」清单 9 项留档防复核重查。

## 2 QR 台账（r4 增量 · 单一真身在总报告附录）

**本轮新增 QR-055～070**。摘要：

### P1（3 条，E0 双证据过闸）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-055 | commercial/models.py:110 | 席位订阅「active⇒必有到期时刻」无结构保证——expires_at 可缺省，NULL＝永不过期：3980 缴费口径的拉单资格闸对永久席位恒放行（attribution:704/716「NULL 视为未设到期不算过期」逐字在场）；与同文件保护窗「结构性不可能永久锁定」纪律相悖、倒挂缺省 fail-closed 惯例；三个既有测试钉恰好钉住「可缺省」——修复须换钉（判级存疑：admin 密码门后主动动作、续期未实现，可辩 P2） |
| QR-056 | commercial/attribution_service.py:1248 | record_settlement 张冠李戴闸对「无交付包」project_share 科目行整体失效——包比对两 non-None 前置使无包行跳过全部归属校验，无包行（属任意企业）可结算任意已撮合商机＝别家收入挂本商机渠道归属；regional_service.py:470-479 同尺守卫在场对照 |
| QR-057 | commercial/role_assignment_service.py:64 | source_uri 校验 ≤500 与列宽 String(255) 不一致——契约内 256-500 字符输入 flush 撞列宽 DataError→500（同族 _require_uri 五处全 ≤500 配 String(500)，唯 T4 表掉队；判级存疑：admin-only 可辩 P2） |

### P2（10 条，E0 锚点确认/双片交叉核）
QR-058 ledger_service.py:756 payee-only 科目行事件无跨 org 前缀且 changes 不含 payee_user_id——M3a 留痕红线在资金写面不成立（判级存疑：结构就绪·待授权态从严注记后 P2）｜QR-059 attribution:1239 同一 project_share 科目行可被多商机重复结算引用（区域面同款有 UNIQUE 钉；判级存疑可 P1）｜QR-060 attribution:684 商机列表（M6 org 域）与详情（三列本人判定）语义不同＝幽灵行（org_read_scope.resource_visibility 未接线）｜QR-061 attribution:978 set_protection 无「已 active」守卫——保护期可反复重置无限延长绕开续期闸｜QR-062 regional:394 `bool(exclusive_territory)` 类型混淆——字符串 "false" 真值 ⇒ 独家区域权误授固化（阶梯只前进无降级）｜QR-063 regional:461 record_service_settlement 无 voided 守卫（兄弟面 attribution 同款守卫在场；当前 voided 零写路径 latent）｜QR-064 org_read_scope.py:121 多关联账号「首个非 None org 即返回」——可见性结论随传参列序翻转（fail-closed 聚合口径未成文）｜QR-065 models.py:1173 regional_sale_gate 条件原子性 CHECK 未实现注释宣称的三元组同有同无（缺 signed_at 方向；判级存疑可 P3）｜QR-066 role_assignment:156 并发双写插入重叠生效区间——行锁锁不住 phantom insert，注释自decl「并发安全」失效（F 线席位归账上游）｜QR-067 admin_routes.py:291 四个 GET 读面无 admin 门（fee-configs/split-rules/opportunity-rules/regional-sale-gate——docstring 自称 admin 面、同蓝图 readiness 有门有钉；判级存疑：按 M3b R1 红线可 P1）

### P3（3 条合并条目，16 锚点——§5 规矩 5）
- **QR-068 并发插入 500 族**（4 锚）：billing:168 elect／quota:133 grant／enterprise:650 accept-revoke-invite-register／regional:105 惰性补建——「行不存在→插入」与并发窗口未统一 lock_entitlement 已示范的 savepoint/锁兜底
- **QR-069 读面写库被回滚＋容量脱节族**（4 锚）：routes.py:365 gate GET 补建永不落库／service.py:457 ensure_entitlement GET 同族／admin_routes:354 人工金额无整数位上限撞 Numeric(12,2)→500／billing:348 首单 settlement 关联无里程碑对齐（对账指针错位）
- **QR-070 声明与实现漂移族**（8 锚）：enterprise:536 邀请邮箱「NFKC 同口径」声明为假（全角邀请永久 403 死端）／enterprise:270 空间交付项目 join 键 enterprise_code==display_name 双侧零校验静默欠报／models:484 split rule 无 configured_has_evidence CHECK（姊妹表两处同形在场）／models:818 保护期 revoked 零写路径（撤回商机后保护仍封堵直签）／attribution:1296 mark_disputed 可覆盖销毁前次争议证据指针／attribution:645 enterprise_code 文案「≤80」无校验／regional:115 serialize_gate 不出 content_hash（合规件指纹读面不可核对）／regional:410 区域四事件 target=actor ⇒ cross_org_ 接线恒不触发

## 3 清白亮点（供总报告引用）

- 首单扣费闸六序完整（验收→席位归属→实收里程碑→已购含席位→已激活→已扣→选定且可实现→Decimal(3980) 记账），行锁＋双并发行为钉（test_commercial_concurrency.py:227/285）；方法 B fail-closed（未实现方法 409 不误按 A 扣）。
- 记账口径：ledger.amount Numeric 一致＋≥0 CHECK；seat_shares_for 引用不重算（ADR-003 §2.2）；首单直记反向封死 409；fee 缺省不可用 409。
- USCC 校验位独立验算与 GB 32100-2015 一致；认证通过线未配置⇒pending_threshold 不判通过；ladder 纯函数映射＋双静态钉。
- 售卖闸 fail-closed 结构＋CHECK 结构性排除缺件开门＋formal 写点唯一源钉。
- 商机保护窗 CHECK「结构性不可能永久锁定」为同文件最优形态（对照 QR-055 席位面的缺口）。

## 4 口径数字变化

零生产 diff 轮：485/52/153/73 全不变。

## 5 备注

1. 按量付费 key 红线 grep（.env.example）控制台下未现测命中——r5 前用 python 直读复核（.env.example 非禁区）。
2. CR-028 累计预扣真身＝dispatch/settlements.py:545（r5 域）——r5 时按规矩 4 续注。
3. 同一 project_share 科目行可跨域双引用（区域结算表×商机 settled_ledger_entry_id）——互斥口径属分成规则（unset）成文时拍板项，QR-059 修数据洞、业务口径留授权层。
