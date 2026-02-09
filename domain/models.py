import uuid
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Float

class Base(DeclarativeBase):
    pass

class TranslationJob(Base):
    __tablename__ = "translation_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)

    source_lang: Mapped[str] = mapped_column(String(16))
    target_lang: Mapped[str] = mapped_column(String(16))

    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # store as JSON-ish text (simple, portable)
    request_texts: Mapped[str] = mapped_column(Text)          # json string
    response_texts: Mapped[str | None] = mapped_column(Text, nullable=True)  # json string

    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
