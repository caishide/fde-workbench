// @vitest-environment node
// CR-071（夜审 r8 设计稿推荐 A，r9 实施轮）：桌面 IPC 桥等价性静态钉。
//
// 共享样本集 tests/shared/api-safety-samples.ts 的判定在**桌面侧**
// （main/api-ipc.ts::createApiRequestHandler，经 shared/api-safety.ts 原语）
// 逐位断言；web 侧镜像断言在 tests/renderer/fde-web-bridge-equivalence.test.ts。
// 两桥消费同一 shared 原语 ⇒ 样本判定恒同；任一侧未来单独加/减校验项
// 造成漂移，对应侧测试即红。

import { describe, expect, it } from "vitest"

import {
  BODY_SAMPLES,
  METHOD_SAMPLES,
  PATH_SAMPLES,
} from "../shared/api-safety-samples"

const API_BASE_URL = "http://127.0.0.1:8010"

async function loadApiModule(): Promise<{
  createApiRequestHandler(options: {
    apiBaseUrl: string
    fetch: typeof fetch
    timeoutMs: number
  }): (input: unknown) => Promise<unknown>
}> {
  return import("../../src/main/api-ipc")
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

async function desktopJudge(
  kind: "path" | "method" | "body",
  input: string | unknown,
): Promise<boolean> {
  const { createApiRequestHandler } = await loadApiModule()
  let fetchCalled = false
  const fakeFetch: typeof fetch = () => {
    fetchCalled = true
    return Promise.resolve(jsonResponse({ data: {}, error: null }))
  }
  const request = createApiRequestHandler({
    apiBaseUrl: API_BASE_URL,
    fetch: fakeFetch,
    timeoutMs: 5_000,
  })
  const base: Record<string, unknown> = {
    path: kind === "path" ? input : "/api/v1/projects",
    // path 与 body 样本统一用 POST 判：verify-password 例外分支（需 POST）在
    // 两侧 origin 下都可被样本命中；method 样本用自己的 input。
    method: kind === "method" ? (input as string) : "POST",
    accessToken: "equivalence-probe",
  }
  try {
    if (kind === "body") base.body = input
    await request(base)
    return fetchCalled
  } catch (error) {
    // 校验拒绝面：invalid_request；放行面但 fetch 桩异常（不应发生）→ 抛出让用例红
    const code = (error as { code?: unknown }).code
    if (code !== undefined) {
      expect(code, `桌面侧非 invalid_request 错误码：${String(code)}`).toBe("invalid_request")
      return false
    }
    throw error
  }
}

describe("CR-071 桌面 IPC 桥等价性判定（共享样本集）", () => {
  it("路径样本：判定与 expected 逐位一致", async () => {
    for (const sample of PATH_SAMPLES) {
      const actual = await desktopJudge("path", sample.path)
      expect(
        actual,
        `路径样本判定漂移：${sample.path}（${sample.note}）`,
      ).toBe(sample.expected)
    }
  })

  it("method 样本：判定与 expected 逐位一致", async () => {
    for (const sample of METHOD_SAMPLES) {
      const actual = await desktopJudge("method", sample.method)
      expect(
        actual,
        `method 样本判定漂移：${JSON.stringify(sample.method)}`,
      ).toBe(sample.expected)
    }
  })

  it("body 样本：判定与 expected 逐位一致", async () => {
    for (const sample of BODY_SAMPLES) {
      const actual = await desktopJudge("body", sample.body)
      expect(
        actual,
        `body 样本判定漂移：${sample.note}`,
      ).toBe(sample.expected)
    }
  })
})
