# v0.2 (PG 迁移): server 容器化
# ============================================================
# 为什么容器化: PG 在 Docker 网络 automation_qiflow-net 内（别名 twenty-db），
#   WSL 宿主机上解析不了该别名（Docker DNS 只在网络内生效）。
#   把 server 放进同一网络即可用稳定别名连库，不依赖会变的容器 IP，
#   也不需要改 Twenty 的任何配置或暴露 PG 端口到宿主机。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统依赖：psycopg[binary] 自带 libpq，无需额外装；
# 但 cryptography / argon2 等可能需要 build 工具，先装 gcc 再清理。
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./
RUN pip install --upgrade pip && pip install -r requirements.lock

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e . --no-deps

COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8010

CMD ["gunicorn", "--bind", "0.0.0.0:8010", "--workers", "2", "--timeout", "120", "fde_api.wsgi:app"]
