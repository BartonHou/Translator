import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Timezone-aware UTC now (replaces deprecated datetime.utcnow)."""
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    # The full key is shown once at creation; we persist only a hash + prefix.
    key_prefix: Mapped[str] = mapped_column(String(12), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=60)
    monthly_quota_chars: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Glossary(Base):
    """User-owned term dictionary. Entries stored as a JSON string mapping
    source term -> forced target term."""

    __tablename__ = "glossaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    entries_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class UsageRecord(Base):
    """Per-key daily usage aggregate (one row per key per day)."""

    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("api_key_id", "day", name="uq_usage_key_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    api_key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    chars_in: Mapped[int] = mapped_column(BigInteger, default=0)
    chars_out: Mapped[int] = mapped_column(BigInteger, default=0)

class TranslationJob(Base):
    __tablename__ = "translation_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    # Owning API key (nullable for backward compat with pre-auth rows).
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True, index=True)

    source_lang: Mapped[str] = mapped_column(String(16))
    target_lang: Mapped[str] = mapped_column(String(16))

    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # store as JSON-ish text (simple, portable)
    request_texts: Mapped[str] = mapped_column(Text)          # json string
    response_texts: Mapped[str | None] = mapped_column(Text, nullable=True)  # json string

    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    chars_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chars_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File-translation support (null for plain text jobs). skeleton_json holds
    # the structure needed to reassemble the translated file in its original format.
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    skeleton_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Webhook to POST on completion (nullable). See workers.tasks.
    callback_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
