# goal-crv r7 轮记录：桌面端·Electron 主进程与安全面（终稿 · 部分覆盖域）

> 循环：goal-crv ｜ 轮：r7 ｜ 域：桌面端（逐行读 19 文件＝main 10＋shared 3＋api-ipc/auth-ipc 2＋auth-store＋fde-web-bridge/PublicDiagnosticPage/AgentsConsole 3；renderer 业务页面 ~169 文件按部分覆盖域申报，BLOCKED 留痕）｜ 审查时点基点：`35ffbea`（四片各自核验 git diff 基点零差异）
> 审读方式：CreateWorkflow 四片（run `dwfrun-bc68ec74`）——主进程安全面 10／IPC 与认证面 3／shared 契约面 3／安全关键 renderer 面 3
> **结论一句话**：Electron 安全四开关（contextIsolation/sandbox/nodeIntegration/webview 拒绝）、双桥请求面 CR-071 单点 8+1 校验、auth-store 原子写与 refresh token 主进程独占、LCSC 三重白名单与 denied 名单、diagnostics consent 硬闸与令牌不入 URL——核心安全边界扎实；缺陷集中在**加固不对称**（主窗口缺 will-redirect／desktop-execute 绕默认关闸／点击时刻无复验）、**web 桥响应面不等价**与**AgentsConsole 整页坍缩**——P2×5／P3×3（合并 17 锚），零 P0 零 P1。

## 1 覆盖声明（§6 三档如实列 · 部分覆盖域）

- **逐行读：19 文件**＝工作流四片（主进程 10＋IPC/认证 3＋shared 3＋安全关键 renderer 3）；Electron 安全边界 100% 覆盖（CSP/preload/contextIsolation/协议注册/spawn/auth-ipc/api-ipc 双桥/consent 硬闸/终审队列）。
- **抽查：~169 文件 renderer 业务页面（research/help/projects/templates/dispatch 表单页等）未逐行读**——任务书 §3 r7 行审读面为「入口锚点，非穷举」；desktop/src 共 190 文件 40,361 行远超单轮容量。已入 BLOCKED.md §1.1（部分覆盖域 1/2 名额），消解条件＝另立 r7b 增补轮。
- **没读：desktop/tests 多数文件**（按各片 nailCheck 定点核对 13 份相关测试，非逐行）。
- 四片合规声明在案（零执行/零写/未触禁区/基点零差异核验）；E0＝P2×5 载重锚点逐一重读（index.ts:78-100/185-232、lcsc-runner.ts:180-196、fde-web-bridge.ts:290-302 ↔ api-ipc.ts:258-294、AgentsConsole.tsx:206-242/424-434）＋P3 归并入族。

## 2 QR 台账（r7 增量 · 单一真身在总报告附录）

**本轮新增 QR-109～116（8 条）**：

### P2（5 条，E0 锚点逐一重读确认）
| QR | 锚点 | 标题 |
|---|---|---|
| QR-109 | index.ts:88-94 | 主窗口 webContents 缺 will-redirect 守卫——lcsc 分支成对注册（:83-84）而特权更高的主窗口只有 will-navigate；30x 重定向不走 will-navigate，dev 态 dev server 302 链出即外域页入特权窗（判级存疑：打包态 file: 无 HTTP 重定向，从严 P2） |
| QR-110 | index.ts:190 | desktop-execute 桥拦截不受 lcscIpcEnabled「默认关」闸——F3 纪律只护 3/4 个 LCSC 面；flag=false 经 API 桥仍拉起自动化执行（服务端 403 兜底＝非越权洞，意图↔实现缺口） |
| QR-111 | lcsc-runner.ts:193 | AI 实时操作循环点击时无文案/语义复验——denied 名单只守观察时刻（TOCTOU）；执行窗与手动内置浏览器共享 partition，登录态共享放大误点后果 |
| QR-112 | fde-web-bridge.ts:295-299 | web 桥响应面解析与桌面 parseApiResponse 四处不等价（ok∧error 拒／!ok∧¬error 拒／!ok data 置空／错误体形态校验＋脱敏全缺）——等价性静态钉 63 样本只护请求面、响应面零钉（判级存疑：现行服务端信封纪律下无现实触发，按双桥同原语承诺从严 P2） |
| QR-113 | AgentsConsole.tsx:428-429 | 顶层 error 早返回把整个控制台坍缩为一行错误且无恢复路径——单件复核 PATCH 撞 409/下载失败即全页阻断（load effect 仅挂载执行一次；同文件 detailError/queueError 均就地呈现，此处不一致；判级存疑） |

### P3（3 条合并 17 锚——§5 规矩 5）
- **QR-114 主进程 LCSC 卫生族**（4 锚）：lcsc-runner.ts:11 全文件零测试钉（三主机白名单/PDF 闸/文件名净化回归裸奔；CR-033 静默退化前科）｜index.ts:50 立创主机白名单三处字面复制（漂移即半坏执法面）｜index.ts:106 打包态默认菜单未去（DevTools 交付态可达；全 src 唯一 setMenu(null) 在 finish-dialog）｜api-ipc.ts:79-81 pluginDecision 330s 魔法分支零注释零钉（服务端路由形状硬编码进桥）
- **QR-115 桥与脱敏族**（5 锚）：api-ipc.ts:324-337 collectSensitiveValues 顶层数组 body 零走查（等价钉恰好放行该形状——放行钉有、脱敏钉无）｜auth-ipc.ts:527-540 脱敏四件套双桥逐行复制且已漂移（缺 ArrayBuffer.isView 守卫；CR-071 提升校验族未提升脱敏族）｜auth-ipc.ts:451-468 mapStorageError 双分支零钉零消费（keyring 故障端到端不可观测，重试文案误导）｜fde-web-bridge.ts:198-205 logout fetch 缺 redirect:"error"（携带 refresh_token 的请求；另两处 fetch 恒有）｜:277-289 web apiRequest 无超时面（桌面 AbortController 语义缺位，长请求 UI 悬死）
- **QR-116 renderer 呈现与契约族**（8 锚）：fde-web-bridge.ts:159 web 会话恒标「桌面端」（fallback 死分支）｜PublicDiagnosticPage.tsx:218-229 轮询把一切失败混同「仍在生成中」（5 分钟误导等待＋不可证实断言）｜:153-158 提交已隐藏槽位陈旧答案（与自身注释矛盾；服务端 validate_answers 不查可见性）｜:605 政策外链裸 href 无 scheme 白名单（数据污染前置，纵深缺口）｜AgentsConsole.tsx:278-294 setState updater 内网络副作用（StrictMode dev 双触发）｜:255-268 Promise.all fail-fast 丢弃整批队列｜api-safety.ts:66 MAX_FIELD_VALUE_BYTES 名实不符（按 UTF-16 code unit 计，CJK 上界松 3 倍）｜brand.ts:1 头注「双侧共享」与红线①双单点口径自相矛盾

## 3 清白亮点（供总报告引用）

- **主进程安全基座全清白**：build-csp 纯函数派生（CR-057 回归确认；OSS 域只加显式 origin 绝不通配）；config.ts resolveApiBaseUrl 强制 https＋origin-only 校验（renderer-url 六组钉）；close-guard 纯函数矩阵＋接线静态钉（CR-034 家族钉在场）；lcsc-finish-dialog 全套加固（sandbox+CSP+setMenu(null)+windowOpen deny）；bridge-capture win32 平台闸可注入＋execFile 参数数组无注参面。
- **auth-store.ts 零发现**（170 行）：CR-072 收口面回归确认（明文降级显式前缀非静默）；三态判别顺序正确；原子写 mkdir 0700→wx 0600→rename；clear 双路径 allSettled。
- **双桥请求面 CR-071 单点成立**：8+1 校验全走 shared/api-safety.ts（method 白名单/路径 raw+decoded 双查/auth 排除/multipart 严格 schema/body 可序列化/自定义头允许名单）；等价性静态钉 63 样本（25 路径＋9 method＋11 body＋18 header）双侧驱动真实入口；公开面行为钉（空 accessToken 零 Authorization＋x-diagnostic-token 透传）在位。★口径注记：任务书引「45 样本」为 r9 时点值，T-14a 增 HEADER_SAMPLES 18 条后现测 63——r10/收口轮校正。
- **contracts.ts 逐位对齐**：USER_ROLES ≡ 服务端 CHECK（system_operator 是 AI 档不入 role）；长度常量 ≡ auth/limits.py；IPC_CHANNELS 13 条 ≡ main 注册 ≡ preload ≡ web 桥 window.fde 零字面量漂移。
- **refresh token 主进程独占**：stripRefreshToken 三出口剥除＋save 先于 return 顺序钉＋四处 stringify not.toContain 钉；会话变更全链串行化无 rotate 双写窗口。
- **安全关键 renderer 面**：consent 客户端硬闸＋服务端 400 兜底；分享 token 只走 URL fragment 不进访问日志；X-Diagnostic-Token 恒 accessToken:"" 公开面；AgentsConsole 终审不可绕过（批量＝逐件同端点零新写路径）＋T-A10 content 错误原样呈现；doc 预览 react-markdown 无 dangerouslySetInnerHTML（grep 零命中）无 XSS→桥提权面。

## 4 口径数字变化

零生产 diff 轮：结构口径全不变；vitest 96 文件/1100 例基线不变（零测试改动）。

## 5 备注

1. **部分覆盖域**（1/2 名额）：renderer 业务页面 ~169 文件降抽查档——BLOCKED.md §1.1 留痕，消解条件＝蔡工裁定后另立 r7b 增补轮（预计 2-3 轮工作流）。
2. 判级存疑 3 处如实标注（QR-109/112/113）；QR-110/111 补偿控制已注明（服务端 403／denied 名单观察期在位）。
3. qr 复用引用：CR-033（lcsc-runner 静默退化前科）、CR-056/057/058/070/071/072/073 全部回归确认在位不重报；QR-005 isSensitiveKey 窄键表双桥同型——收口轮统一扩键表时置于同一变更面（QR-115 关联）。
4. 非发现备查（分片评估后不立案）：index.ts:185 mutating 多计方向保守；iframe src 宽松匹配被 isLcscPdf 严格闸兜住；pointAt 表达式形态内插当前全字面量调用（未来易踩面已留痕）；web 桥缺 accessToken 长度闸（IPC 信任边界外影响趋零）。
