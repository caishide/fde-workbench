// CR-071（夜审 r8 设计稿推荐 A，r9 实施轮）：桌面 IPC 桥与 web 桥等价性静态钉
// 的共享样本集（单一来源）。
//
// 机制：samples 与期望判定是**两桥共用的同一份**——
//   - tests/main/api-safety-equivalence.test.ts（node）驱动桌面
//     main/api-ipc.ts::createApiRequestHandler，断言判定与 expected 逐位一致；
//   - tests/renderer/fde-web-bridge-equivalence.test.ts（jsdom）驱动 web 桥
//     fde-web-bridge.ts::apiRequest，断言判定与 expected 逐位一致。
// 任一侧未来单独加/减校验项导致两桥判定漂移，**对应侧测试即红**——
// 共享样本集保证漂移必然被其中一侧捕获（家族性教训「同一坑复发三次」的
// 结构性处置）。
//
// 纯数据＋纯类型：零 electron／零 DOM 导入，node 与 jsdom 环境双侧可 import。

/**
 * 路径样本：expected=true＝该路径经校验原语放行；false＝拒绝。
 * 期望判定与 origin 无关（全部为相对 /api/v1/ 路径或外部绝对 URL／遍历形态，
 * 在 127.0.0.1:8010（桌面 apiOrigin）与 http://localhost:3000（jsdom location）
 * 两侧 origin 下判定逐位一致）。
 */
export interface ApiSafetyPathSample {
  path: string
  expected: boolean
  /** 样本意图（留痕）：哪一类校验项在起作用 */
  note: string
}

export const PATH_SAMPLES: readonly ApiSafetyPathSample[] = [
  // —— 放行面 ——
  { path: "/api/v1/projects", expected: true, note: "常规相对路径" },
  { path: "/api/v1/projects/p1/research?limit=10", expected: true, note: "带查询串" },
  { path: "/api/v1/auth/verify-password", expected: true, note: "auth 排除唯一例外（配合 POST method）" },
  // —— 前缀/遍历面 ——
  { path: "../etc/passwd", expected: false, note: "不以 /api/v1/ 开头" },
  { path: "/api/v1/../../admin", expected: false, note: "路径遍历" },
  { path: "/api/v1/projects/..", expected: false, note: "尾遍历" },
  { path: "//evil.example/api/v1/projects", expected: false, note: "双斜杠协议相对" },
  { path: "https://evil.example/api/v1/projects", expected: false, note: "绝对外域（origin 不匹配）" },
  { path: "http://127.0.0.1:8010/../etc/passwd", expected: false, note: "同 host 越权相对（pathname 遍历）" },
  // —— 编码结构逃逸面（raw 检查可被编码穿透——旧 web 桥缺口 3）——
  { path: "/api/v1/a%252fb", expected: false, note: "%25 双重编码 %2f" },
  { path: "/api/v1/a%253f", expected: false, note: "%25 双重编码 %3f" },
  { path: "/api/v1/a%2523", expected: false, note: "%25 双重编码 %23" },
  { path: "/api/v1/a%255cb", expected: false, note: "%25 双重编码 %5c" },
  { path: "/api/v1/%2e%2e/admin", expected: false, note: "%2e 编码点（raw 路径拒绝）" },
  { path: "/api/v1/a%252e%252e/admin", expected: false, note: "双重编码点" },
  { path: "/api/v1/projects?x=%2e%2e", expected: true, note: "查询值 %2e 解码为 '..'——桌面原语义放行（PATH_TRAVERSAL 只查 pathname 段，查询值非路径段；桌面 api-ipc 旧实现同判定，等价性钉按原样钉住）" },
  // —— 控制字符面（旧 web 桥缺口 4：旧版查 \\ 与 #，无 \\u0000-\\u001f 区间）——
  { path: "/api/v1/projects/x#y", expected: false, note: "fragment" },
  { path: "/api/v1/projects\\x", expected: false, note: "反斜杠" },
  { path: "/api/v1/p\0rojects", expected: false, note: "NUL 控制字符" },
  { path: "/api/v1/p\u0001rojects", expected: false, note: "SOH 控制字符" },
  { path: "/api/v1/p\u007frojects", expected: false, note: "DEL 控制字符" },
  // —— auth 排除面（旧 web 桥缺口 2：无 auth 分支——桌面语义「auth 不走通用桥」）——
  { path: "/api/v1/auth/login", expected: false, note: "auth 非 verify-password 排除" },
  { path: "/api/v1/auth/refresh", expected: false, note: "auth refresh 排除" },
  { path: "/api/v1/auth/logout", expected: false, note: "auth logout 排除" },
  { path: "/api/v1/auth/changepassword", expected: false, note: "auth 前缀变体排除" },
]

/**
 * method 样本：expected=true＝白名单放行；false＝拒绝。
 * （web 桥旧缺口 1：options.method 直传 fetch 零校验。）
 */
export interface ApiSafetyMethodSample {
  method: string
  expected: boolean
}

export const METHOD_SAMPLES: readonly ApiSafetyMethodSample[] = [
  { method: "GET", expected: true },
  { method: "POST", expected: true },
  { method: "PUT", expected: true },
  { method: "PATCH", expected: true },
  { method: "DELETE", expected: true },
  { method: "OPTIONS", expected: false },
  { method: "TRACE", expected: false },
  { method: "get", expected: false },
  { method: "", expected: false },
]

/**
 * body 样本：expected=true＝该 body 可随请求发出；false＝拒绝。
 * multipart 样本即「旧 web 桥缺口 5（非法形状 return null ⇒ 无 body 裸发）」
 * 的封堵钉：expected=false 的 multipart 形状在 web 侧必须**显式 fail**，
 * 绝不允许降级为无 body 裸发。
 */
export interface ApiSafetyBodySample {
  body: unknown
  expected: boolean
  note: string
}

const multipartValid = {
  kind: "multipart_file",
  fields: { note: "附件说明" },
  file: {
    field_name: "file",
    name: "evidence.txt",
    type: "text/plain",
    bytes: new Uint8Array([0x61, 0x62]),
  },
}

export const BODY_SAMPLES: readonly ApiSafetyBodySample[] = [
  { body: { name: "代号项目" }, expected: true, note: "普通 JSON 对象" },
  { body: null, expected: true, note: "null body（可序列化）" },
  { body: [1, 2, 3], expected: true, note: "数组 body" },
  { body: multipartValid, expected: true, note: "合法 multipart 形状" },
  // —— multipart 非法形状：桌面拒／web 显式 fail（不裸发）——
  {
    body: { kind: "multipart_file", fields: "not-a-record", file: multipartValid.file },
    expected: false,
    note: "multipart fields 非对象",
  },
  {
    body: { kind: "multipart_file", fields: {}, file: { field_name: "f", name: "n", type: "t" } },
    expected: false,
    note: "multipart file 缺 bytes 键（extra-keys 形状拒绝）",
  },
  {
    body: { ...multipartValid, file: { ...multipartValid.file, name: ".." } },
    expected: false,
    note: "multipart 文件名遍历",
  },
  {
    body: { ...multipartValid, file: { ...multipartValid.file, name: "a\\b" } },
    expected: false,
    note: "multipart 文件名含反斜杠",
  },
  {
    body: { kind: "other", fields: {}, file: {} },
    expected: true,
    note: "非 multipart kind＝普通可序列化对象（两桥同放行；桌面 isMultipartFileBody 仅认 multipart_file 字面量）",
  },
  { body: 1n, expected: false, note: "BigInt 不可 JSON 序列化（两桥同拒）" },
  { body: "plain-string", expected: true, note: "字符串 body（可序列化；body 契约静态闸另行约束）" },
]

/**
 * 自定义请求头样本（获客诊断 T-14a，校验项 9）：expected=true＝该 headers
 * 可随请求发出；false＝拒绝。允许名单只有一个 ``x-diagnostic-token``——
 * authorization／cookie／content-type 等桥自带头不可由渲染层覆写。
 */
export interface ApiSafetyHeaderSample {
  headers: unknown
  expected: boolean
  note: string
}

export const HEADER_SAMPLES: readonly ApiSafetyHeaderSample[] = [
  { headers: undefined, expected: true, note: "未带自定义头（缺省）" },
  { headers: null, expected: true, note: "null＝未带自定义头（显式放行）" },
  { headers: {}, expected: true, note: "空对象＝无自定义头" },
  {
    headers: { "x-diagnostic-token": "diag_tok-123_abc" },
    expected: true,
    note: "允许名单唯一头（token_urlsafe 字符集）",
  },
  {
    headers: { "X-Diagnostic-Token": "diag_tok" },
    expected: true,
    note: "头名大小写不敏感（HTTP 语义；两桥透传原样）",
  },
  {
    headers: { "x-diagnostic-token": "a".repeat(128) },
    expected: true,
    note: "取值上限 128 字（含）",
  },
  {
    headers: { "x-diagnostic-token": "a".repeat(129) },
    expected: false,
    note: "取值超 128 字",
  },
  {
    headers: { "x-diagnostic-token": "" },
    expected: false,
    note: "空取值（持有即权凭证不许为空串）",
  },
  {
    headers: { "x-diagnostic-token": "bad value" },
    expected: false,
    note: "取值含空格",
  },
  {
    headers: { "x-diagnostic-token": "bad;value" },
    expected: false,
    note: "取值含分号（头注入面）",
  },
  {
    headers: { "x-diagnostic-token": 123 },
    expected: false,
    note: "取值非字符串",
  },
  {
    headers: { authorization: "Bearer attacker" },
    expected: false,
    note: "authorization 是桥自带头，不可由渲染层覆写",
  },
  {
    headers: { cookie: "sid=1" },
    expected: false,
    note: "cookie 不在允许名单（会话语义不可借桥携带）",
  },
  {
    headers: { "content-type": "text/plain" },
    expected: false,
    note: "content-type 是桥自带头，不可覆写",
  },
  {
    headers: { "x-custom": "v" },
    expected: false,
    note: "未知头名拒绝",
  },
  {
    headers: "x-diagnostic-token",
    expected: false,
    note: "形状非对象（字符串）",
  },
  {
    headers: ["x-diagnostic-token"],
    expected: false,
    note: "数组形状拒绝",
  },
  {
    headers: {
      "x-diagnostic-token": "t1",
      "x-a": "1",
      "x-b": "2",
      "x-c": "3",
      "x-d": "4",
    },
    expected: false,
    note: "数量超限（>4；单允许名单下首个未知头也拒——数量闸是纵深防御，两侧判定恒同）",
  },
]
