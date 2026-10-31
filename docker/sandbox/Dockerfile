# goal-d3（技术实施方案 §4）：agent 执行沙箱镜像。
# 最小运行时：python + node（agent CLI 的宿主）；非 root 运行；工作目录即
# 一次性 tmpfs /workspace（compose 侧挂载，容器销毁随之回收）。
# goal-d4：apt 加装 iptables——egress allowlist 档的助手容器（--net host +
# NET_ADMIN）在本镜像内执行 per-run 白名单规则（agents/sandbox.py EgressPlan）。
# agent CLI（zcode 等）的版本钉定待试点前评审——真实凭据联调属人工项。
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs iptables \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin runner
USER runner
WORKDIR /workspace

# 默认保活命令仅用于 compose 基线验证；真实 run 由服务端以独立容器拉起并
# 显式传命令（--name agent-run-{run_id}，network none，tmpfs /workspace）。
CMD ["sleep", "infinity"]
