// @vitest-environment node
/**
 * CR-058 防复发静态闸：web 桥版本号是版本列车的第三个源（此前不在任何
 * 同步纪律清单内，列车推进必然漂移）——本闸把「fde-web-bridge.ts 的
 * version 字面量 === desktop/package.json version + "-web"」钉成测试，
 * 列车推进漏改此文件即红。
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

import { describe, expect, it } from "vitest"

const DESKTOP_ROOT = join(fileURLToPath(new URL("../..", import.meta.url)))

describe("web 桥版本与版本列车对账（CR-058）", () => {
  it("web 桥 version 字面量必须等于 package.json version + '-web'", () => {
    const pkg = JSON.parse(
      readFileSync(join(DESKTOP_ROOT, "package.json"), "utf-8"),
    ) as { version: string }
    const bridgeSource = readFileSync(
      join(DESKTOP_ROOT, "src/renderer/src/fde-web-bridge.ts"),
      "utf-8",
    )
    expect(bridgeSource).toContain(
      `version: async () => "${pkg.version}-web"`,
    )
  })
})
