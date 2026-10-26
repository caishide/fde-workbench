import { spawnSync } from "node:child_process"
import { Socket, createServer } from "node:net"

export async function findUnavailableRedisPort() {
  const server = createServer()
  const port = await new Promise((resolvePort, rejectPort) => {
    server.once("error", rejectPort)
    server.listen(0, "127.0.0.1", () => {
      const address = server.address()
      if (!address || typeof address === "string") {
        rejectPort(new Error("Could not resolve an ephemeral local port."))
        return
      }
      resolvePort(address.port)
    })
  })
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose())
  })

  // redis-cli 在 PATH 时用它探测；缺失（如 Windows 开发机）时退化为 TCP
  // 连接探测——端口上没有任何监听者 = 连接被拒 = 该端口对 Redis 不可用。
  const probe = spawnSync(
    "redis-cli",
    ["-h", "127.0.0.1", "-p", String(port), "ping"],
    { stdio: "ignore", timeout: 1_000 },
  )
  if (probe.error) {
    const rejected = await new Promise((resolve) => {
      const socket = new Socket()
      const finish = (value) => {
        socket.destroy()
        resolve(value)
      }
      socket.once("error", () => finish(true))
      socket.once("connect", () => finish(false))
      socket.setTimeout(500, () => finish(true))
      socket.connect(port, "127.0.0.1")
    })
    if (!rejected) {
      throw new Error("The selected Redis degradation port unexpectedly accepted a TCP connection.")
    }
    return port
  }
  if (probe.status === 0) {
    throw new Error("The selected Redis degradation port unexpectedly accepted a ping.")
  }
  return port
}
