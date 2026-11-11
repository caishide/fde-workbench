// @vitest-environment jsdom
// CR-071（夜审 r8 设计稿推荐 A，r9 实施轮）：web 桥等价性静态钉。
//
// 与桌面侧 tests/main/api-safety-equivalence.test.ts 共享同一份样本集
// （tests/shared/api-safety-samples.ts）——两桥消费同一 shared/api-safety.ts
// 原语 ⇒ 样本判定恒同；web 侧未来单独加/减校验项造成漂移，本测试即红
// （桌面侧样本集漂移由桌面等价性测试捕获，两侧互为镜像）。
//
// 旧 web 桥六缺口（method 白名单／auth 排除／编码双重解码／multipart 静默降级／
// 控制字符区间／body 可序列化）在本轮接共享原语后全部封堵；样本判定
// 「拒」的期望即封堵验收。

import { afterEach, describe, expect, it, vi } from "vitest"

import "../../src/renderer/src/fde-web-bridge" // 注入 window.fde

import type { ApiMethod } from "../../src/shared/contracts"
import {
  BODY_SAMPLES,
  METHOD_SAMPLES,
  PATH_SAMPLES,
} from "../shared/api-safety-samples"

function stubFetch(payload: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => payload,
  }))
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

async function webJudge(
  kind: "path" | "method" | "body",
  input: string | unknown,
): Promise<boolean> {
  const fetchMock = stubFetch({ data: {}, error: null })
  const path = kind === "path" ? (input as string) : "/api/v1/projects"
  // method 样本含白名单外值（OPTIONS/TRACE 等）——契约类型是 ApiMethod，
  // 探测面刻意越类型边界喂入，cast 留痕。
  const method = (kind === "method" ? (input as string) : "POST") as ApiMethod
  const request = window.fde.api.request
  const result = kind === "body"
    ? await request(path, { method: "POST", accessToken: "equivalence-probe", body: input })
    : await request(path, { method, accessToken: "equivalence-probe" })
  const allowed = result.ok === true
  if (allowed) {
    // 放行面必须真实到达 fetch（裸发降级路径的判别信号）
    expect(fetchMock).toHaveBeenCalled()
  }
  return allowed
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("CR-071 web 桥等价性判定（共享样本集，与桌面恒同）", () => {
  it("路径样本：判定与 expected 逐位一致", async () => {
    for (const sample of PATH_SAMPLES) {
      const actual = await webJudge("path", sample.path)
      expect(
        actual,
        `web 桥路径判定漂移：${sample.path}（${sample.note}）`,
      ).toBe(sample.expected)
    }
  })

  it("method 样本：判定与 expected 逐位一致（旧缺口 1 封堵）", async () => {
    for (const sample of METHOD_SAMPLES) {
      const actual = await webJudge("method", sample.method)
      expect(
        actual,
        `web 桥 method 判定漂移：${JSON.stringify(sample.method)}`,
      ).toBe(sample.expected)
    }
  })

  it("body 样本：判定与 expected 逐位一致（旧缺口 5/7 封堵：非法 multipart 不再无 body 裸发）", async () => {
    for (const sample of BODY_SAMPLES) {
      const actual = await webJudge("body", sample.body)
      expect(
        actual,
        `web 桥 body 判定漂移：${sample.note}`,
      ).toBe(sample.expected)
    }
  })

  it("非法 multipart 形状拒绝时零 fetch（不裸发）", async () => {
    const fetchMock = stubFetch({ data: {}, error: null })
    const result = await window.fde.api.request("/api/v1/projects", {
      method: "POST",
      accessToken: "equivalence-probe",
      body: { kind: "multipart_file", fields: "not-a-record", file: {} },
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.code).toBe("invalid_request")
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
