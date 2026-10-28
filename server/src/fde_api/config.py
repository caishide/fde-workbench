from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: Literal["development", "test", "production"] = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8010
    database_url: str
    redis_url: str
    jwt_secret: str = Field(min_length=32)
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    storage_backend: Literal["local", "oss"] = "local"
    local_storage_root: Path = Path(".fde-storage")
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_access_key_id: SecretStr | None = Field(default=None, repr=False)
    oss_access_key_secret: SecretStr | None = Field(default=None, repr=False)
    clamav_host: str = "127.0.0.1"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 10
    clamav_socket_timeout_seconds: int = 5
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: SecretStr | None = Field(default=None, repr=False)
    deepseek_industry_template_model: str = "deepseek-v4-pro"
    deepseek_project_presurvey_model: str = "deepseek-v4-pro"
    deepseek_ai_opportunity_model: str = "deepseek-v4-pro"
    deepseek_research_export_model: str = "deepseek-v4-pro"
    deepseek_document_generation_model: str = "deepseek-v4-pro"
    # E5 降级链：主模型瞬时故障（超时/限流/5xx）时切换的备用模型；
    # 留空表示不降级（行为与旧版一致）。主备都失败 → ai_manual_handoff 转人工。
    deepseek_fallback_model: str = "deepseek-v4"
    deepseek_timeout_seconds: int = Field(default=90, ge=5, le=300)
    # E7 月度 token 预算（按用户、自然月，审计表汇总核算）。0 = 不限额——
    # 默认配置不锁死现有用户；设置正数后超限调用被拒且不发起供应商请求。
    ai_monthly_token_budget: int = Field(default=0, ge=0)
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_project_presurvey_api_key: SecretStr | None = Field(default=None, repr=False)
    kimi_project_presurvey_model: str = "kimi-k3"
    kimi_timeout_seconds: int = Field(default=180, ge=10, le=600)
    # Kimi 槽位切到非 Moonshot 供应商（如 MiniMax）时的两个协议开关：
    # - kimi_local_docx_extract=True：供应商不提供 file-extract 文件接口，
    #   改为服务端本地解析 DOCX 取文本后送模型（文件不出本机）
    # - kimi_openai_compatible=True：按通用 OpenAI 兼容端点发请求
    #   （用 max_tokens 而非 max_completion_tokens，不发 reasoning_effort）
    kimi_local_docx_extract: bool = False
    kimi_openai_compatible: bool = False
    dsh_enabled: bool = False
    dsh_base_url: str = "http://127.0.0.1:8020"
    dsh_service_token: SecretStr | None = Field(default=None, repr=False)
    dsh_runtime_version: str = "unconfigured"
    dsh_protocol_version: str = "fde-dsh-v1"
    dsh_timeout_seconds: int = Field(default=300, ge=10, le=1800)
    ai_internal_api_url: str = "http://127.0.0.1:8010"
    weixin_enabled: bool = False
    weixin_credential_key: SecretStr | None = Field(default=None, repr=False)
    dsh_market_enabled: bool = False
    dsh_market_registry_url: str = "https://example.com/plugins.json"
    dsh_market_timeout_seconds: int = Field(default=15, ge=3, le=60)
    dsh_market_max_catalog_bytes: int = Field(default=25_000_000, ge=100_000, le=100_000_000)
    clawbot_enabled: bool = False
    clawbot_gateway_token: SecretStr | None = Field(default=None, repr=False)
    # P2 集成桥：宿主采集器（scripts/bridge-poll.mjs）推快照用的静态令牌；
    # 未配置时 POST /api/v1/bridge/snapshots 返回 503（桥关闭）
    bridge_token: SecretStr | None = Field(default=None, repr=False)
    # G7 登录限流：Redis 不可用时的策略。默认 fail-open（本机回环部署，Redis 挂了
    # 不挡业务登录，记 WARNING 可观测）；对外暴露部署设 true 切 fail-closed（一律 429）。
    login_rate_fail_closed: bool = False

    model_config = SettingsConfigDict(
        env_prefix="FDE_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_storage_environment(self) -> "Settings":
        if self.storage_backend == "local":
            return self

        if not all(
            (
                self.oss_endpoint,
                self.oss_bucket,
                self.oss_access_key_id,
                self.oss_access_key_secret,
            )
        ):
            raise ValueError("missing_oss_configuration")

        return self

    @model_validator(mode="after")
    def validate_dsh_configuration(self) -> "Settings":
        if self.dsh_enabled and self.dsh_service_token is None:
            raise ValueError("missing_dsh_service_token")
        if self.dsh_enabled and not self.dsh_runtime_version.strip():
            raise ValueError("missing_dsh_runtime_version")
        return self

    @model_validator(mode="after")
    def validate_dsh_market_configuration(self) -> "Settings":
        parsed = urlparse(self.dsh_market_registry_url)
        if self.dsh_market_enabled and (
            parsed.scheme not in ({"https"} if self.env == "production" else {"http", "https"})
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("invalid_dsh_market_registry_url")
        return self

    @model_validator(mode="after")
    def validate_clawbot_configuration(self) -> "Settings":
        if self.clawbot_enabled and self.clawbot_gateway_token is None:
            raise ValueError("missing_clawbot_gateway_token")
        return self
