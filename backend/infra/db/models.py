from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infra.db.database import Base

_BJ_TZ = timezone(timedelta(hours=8))


def local_now() -> datetime:
    """返回当前北京时间（UTC+8，不带时区信息，与数据库 DateTime 类型匹配）。"""
    return datetime.now(_BJ_TZ).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_user_session"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_ref_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)
    rag_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("ChatSession", back_populates="messages")


class DocumentParseMeta(Base):
    __tablename__ = "document_parse_meta"
    __table_args__ = {"extend_existing": True}

    document_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    parse_engine: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    parse_engine_version: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    parse_duration_ms: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    watermark_filter_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_confidence_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    hierarchy_validation_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    parse_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    parse_path: Mapped[str | None] = mapped_column(String(20), nullable=True)  # M8
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)


class TerminologyEntryModel(Base):
    __tablename__ = "terminology_entries"
    __table_args__ = (
        UniqueConstraint("entity_type", "canonical", name="uq_terminology_canonical"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    canonical: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    variants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, onupdate=local_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    snapshot_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)


class RescanTaskModel(Base):
    __tablename__ = "rescan_tasks"
    __table_args__ = {"extend_existing": True}

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ParentChunk(Base):
    __tablename__ = "parent_chunks"
    __table_args__ = {"extend_existing": True}

    chunk_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    index_profile: Mapped[str] = mapped_column(String(120), default="legacy", nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_chunk_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    root_chunk_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    chunk_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    term_matches: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    protected_tokens: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    parent_extras: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now, nullable=False)
