import type { ReactElement } from "react"
import { render } from "@testing-library/react"
import { vi, type Mock } from "vitest"

import type {
  AuthResult,
  BridgeResult,
  FdeBridge,
  UserDto,
} from "../../src/shared/contracts"

export const adminUser: UserDto = {
  id: "1b7a50b8-5f95-4ad5-b1a0-b72d0a86c345",
  username: "admin",
  displayName: "管理员",
  role: "admin",
  mustChangePassword: false,
  isActive: true,
}

export const engineerUser: UserDto = {
  id: "2c8b61c9-60a6-4be6-a2b1-c83e1b97d456",
  username: "engineer.li",
  displayName: "李工程师",
  role: "fde_engineer",
  mustChangePassword: false,
  isActive: true,
}

export function authResult(
  user: UserDto,
  accessToken = "access-token",
): AuthResult {
  return {
    accessToken,
    accessExpiresAt: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    refreshExpiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
    user,
  }
}

export function ok<T>(data: T): BridgeResult<T> {
  return { ok: true, data }
}

/**
 * 测试侧的 bridge 适配层。
 *
 * `FdeBridge["api"]["request"]` 是泛型签名（`<T>(path, options) => Promise<
 * BridgeResult<ApiResponse<T>>>`），而 vitest 的 `vi.fn()` 产出的是
 * `Mock<Procedure>` 或具体实现的 mock——两者在类型层不可互相赋值。
 * 这里在适配层做一次收敛：入参接受任意 mock，内部转成契约签名。
 * 生产代码的类型约束不变（bridge 契约本身仍被严格 typecheck）。
 */
export function bridge(
  overrides: Partial<FdeBridge["auth"]> & {
    apiRequest?: FdeBridge["api"]["request"] | Mock<any> | ((...args: any[]) => any)
  } = {},
): FdeBridge {
  return {
    auth: {
      login: vi.fn().mockResolvedValue(ok(authResult(adminUser))),
      refresh: vi.fn().mockResolvedValue(ok(null)),
      changePassword: vi.fn().mockResolvedValue(ok(authResult(adminUser))),
      logout: vi.fn().mockResolvedValue(ok(null)),
      ...overrides,
    },
    api: {
      request: (overrides.apiRequest ??
        vi.fn().mockResolvedValue(
          ok({ status: 200, data: {}, error: null }),
        )) as unknown as FdeBridge["api"]["request"],
    },
    app: { version: vi.fn().mockResolvedValue("0.0.0") },
  }
}

export function installBridge(value: FdeBridge): void {
  Object.defineProperty(window, "fde", {
    configurable: true,
    value,
  })
}

export function renderApp(element: ReactElement): ReturnType<typeof render> {
  return render(element)
}

export function deferred<T>(): {
  promise: Promise<T>
  resolve(value: T): void
} {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolver) => {
    resolve = resolver
  })
  return { promise, resolve }
}
