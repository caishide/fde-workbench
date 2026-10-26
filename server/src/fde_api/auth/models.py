from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unicodedata import normalize
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates
from sqlalchemy.types import TypeDecorator


ROLE_ADMIN = "admin"
ROLE_PROJECT_LEAD = "project_lead"
ROLE_FDE_ENGINEER = "fde_engineer"
ROLE_VIEWER = "viewer"
VALID_ROLES = frozenset(
    {ROLE_ADMIN, ROLE_PROJECT_LEAD, ROLE_FDE_ENGINEER, ROLE_VIEWER}
)


class InvalidRoleError(ValueError):
    """Raised when application code attempts to assign an unsupported user role."""


class UTCDateTime(TypeDecorator[datetime]):
    """Persist UTC datetimes while restoring timezone information on read.

    v0.2 (PG 迁移): on PostgreSQL both UTCDateTime and UTCTimestamp render as
    TIMESTAMP(timezone=True), matching the deployed baseline schema; the UTC
    normalization lives in bind/result processing, not the storage type.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, _: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, _: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def compare_against_backend(self, dialect: Any, conn_type: Any) -> bool | None:
        """Tell autogenerate this custom type matches the backend column type.

        Without this hook `alembic check` flags every timestamp column as
        modify_type drift (TypeDecorator vs reflected timestamptz).
        """
        if dialect.name == "postgresql":
            return isinstance(conn_type, DateTime) and bool(conn_type.timezone)
        return None


class UTCTimestamp(UTCDateTime):
    """Portable UTC-normalized TIMESTAMP storage."""


class Base(DeclarativeBase):
    pass


# v0.2 (PG 迁移): MySQL 的 UTC_TIMESTAMP(6) 在 PG 不存在，改用 func.now()（PG 返回带时区）。
UTC_TIMESTAMP_SQL = func.now()
CURRENT_TIMESTAMP_SQL = func.now()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'project_lead', 'fde_engineer', 'viewer')",
            name="ck_users_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=UTC_TIMESTAMP_SQL
    )
    # v0.2 (PG 迁移): PG 没有 ON UPDATE CURRENT_TIMESTAMP，server_onupdate 不生效；
    # 与 workbench.TimestampMixin 同口径，改为 ORM 层 onupdate=func.now()。
    updated_at: Mapped[datetime] = mapped_column(
        UTCTimestamp(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_SQL,
        onupdate=func.now(),
    )

    refresh_sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.id is None:
            self.id = str(uuid4())
        if self.auth_version is None:
            self.auth_version = 1

    @validates("username")
    def normalize_username(self, _: str, value: str) -> str:
        return normalize("NFKC", value).strip().lower()

    @validates("role")
    def validate_role(self, _: str, value: str) -> str:
        if value not in VALID_ROLES:
            raise InvalidRoleError(f"unsupported role: {value}")
        return value


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=UTC_TIMESTAMP_SQL
    )
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    device_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    user: Mapped[User] = relationship(back_populates="refresh_sessions")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.id is None:
            self.id = str(uuid4())
