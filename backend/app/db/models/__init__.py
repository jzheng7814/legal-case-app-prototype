from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IntPKMixin, TimestampMixin


class DocumentSetType(str, enum.Enum):
    CLEARINGHOUSE = "clearinghouse"
    MANUAL = "manual"


class DocumentSource(str, enum.Enum):
    CLEARINGHOUSE = "clearinghouse"
    MANUAL = "manual"


class ChecklistTemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ChecklistRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatMessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class User(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[Optional[str]] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    manual_documents: Mapped[List["ManualDocument"]] = relationship(back_populates="owner")
    document_sets: Mapped[List["DocumentSet"]] = relationship(back_populates="user")
    checklist_runs: Mapped[List["ChecklistRun"]] = relationship(back_populates="user")
    checklist_templates: Mapped[List["ChecklistTemplate"]] = relationship(back_populates="owner")
    summaries: Mapped[List["Summary"]] = relationship(back_populates="user")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="user")


class ManualDocument(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "manual_documents"

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    owner: Mapped[Optional[User]] = relationship(back_populates="manual_documents")
    document_links: Mapped[List["DocumentSetDocument"]] = relationship(back_populates="manual_document")


class DocumentSet(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "document_sets"
    __table_args__ = (
        UniqueConstraint("type", "case_identifier", "user_id", "doc_hash", name="uq_document_sets_case_hash"),
    )

    type: Mapped[DocumentSetType] = mapped_column(
        Enum(
            DocumentSetType,
            name="document_set_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    case_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    doc_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional[User]] = relationship(back_populates="document_sets")
    documents: Mapped[List["DocumentSetDocument"]] = relationship(
        back_populates="document_set",
        cascade="all, delete-orphan",
        order_by="DocumentSetDocument.position",
    )
    checklist_runs: Mapped[List["ChecklistRun"]] = relationship(back_populates="document_set")


class DocumentSetDocument(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "document_set_documents"
    __table_args__ = (
        CheckConstraint(
            "(remote_document_id IS NOT NULL AND manual_document_id IS NULL)"
            " OR (remote_document_id IS NULL AND manual_document_id IS NOT NULL)",
            name="ck_document_set_documents_source_pointer",
        ),
        Index("ix_document_set_documents_set_position", "document_set_id", "position"),
    )

    document_set_id: Mapped[int] = mapped_column(ForeignKey("document_sets.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[DocumentSource] = mapped_column(
        Enum(
            DocumentSource,
            name="document_source_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    remote_document_id: Mapped[Optional[str]] = mapped_column(String(255))
    manual_document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manual_documents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_name: Mapped[Optional[str]] = mapped_column(String(512))
    doc_type: Mapped[Optional[str]] = mapped_column(String(128))
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    document_set: Mapped["DocumentSet"] = relationship(back_populates="documents")
    manual_document: Mapped[Optional["ManualDocument"]] = relationship(back_populates="document_links")


class ChecklistTemplate(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "checklist_templates"
    __table_args__ = (
        UniqueConstraint("slug", "version", name="uq_checklist_templates_slug_version"),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ChecklistTemplateStatus] = mapped_column(
        Enum(
            ChecklistTemplateStatus,
            name="checklist_template_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ChecklistTemplateStatus.DRAFT,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    parent_template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("checklist_templates.id", ondelete="SET NULL"))
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    owner: Mapped[Optional[User]] = relationship(back_populates="checklist_templates")
    parent_template: Mapped[Optional["ChecklistTemplate"]] = relationship(remote_side="ChecklistTemplate.id")
    items: Mapped[List["ChecklistTemplateItem"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ChecklistTemplateItem.item_order",
    )
    runs: Mapped[List["ChecklistRun"]] = relationship(back_populates="template")


class ChecklistTemplateItem(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "checklist_template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "item_key", name="uq_checklist_template_items_key"),
    )

    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt: Mapped[Optional[str]] = mapped_column(Text)
    rules_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    template: Mapped["ChecklistTemplate"] = relationship(back_populates="items")
    run_items: Mapped[List["ChecklistRunItem"]] = relationship(back_populates="template_item")


class ChecklistRun(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "checklist_runs"
    __table_args__ = (
        UniqueConstraint("template_id", "document_set_id", "user_id", "prompt_hash", name="uq_checklist_runs_signature"),
    )

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id", ondelete="CASCADE"), nullable=False)
    document_set_id: Mapped[int] = mapped_column(ForeignKey("document_sets.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[ChecklistRunStatus] = mapped_column(
        Enum(
            ChecklistRunStatus,
            name="checklist_run_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ChecklistRunStatus.PENDING,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    model_name: Mapped[Optional[str]] = mapped_column(String(255))
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    error_reason: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional[User]] = relationship(back_populates="checklist_runs")
    template: Mapped["ChecklistTemplate"] = relationship(back_populates="runs")
    document_set: Mapped["DocumentSet"] = relationship(back_populates="checklist_runs")
    items: Mapped[List["ChecklistRunItem"]] = relationship(
        back_populates="checklist_run",
        cascade="all, delete-orphan",
        order_by="ChecklistRunItem.id",
    )


class ChecklistRunItem(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "checklist_run_items"

    checklist_run_id: Mapped[int] = mapped_column(ForeignKey("checklist_runs.id", ondelete="CASCADE"), nullable=False)
    template_item_id: Mapped[int] = mapped_column(
        ForeignKey("checklist_template_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_ref: Mapped[Optional[str]] = mapped_column(String(255))
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    checklist_run: Mapped["ChecklistRun"] = relationship(back_populates="items")
    template_item: Mapped["ChecklistTemplateItem"] = relationship(back_populates="run_items")


class Summary(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "document_identifier", "summary_type", name="uq_summaries_user_document_type"),
    )

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    document_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_type: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("summary_versions.id", ondelete="SET NULL"),
    )
    latest_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    user: Mapped[Optional[User]] = relationship(back_populates="summaries")
    current_version: Mapped[Optional["SummaryVersion"]] = relationship(
        "SummaryVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    versions: Mapped[List["SummaryVersion"]] = relationship(
        back_populates="summary",
        cascade="all, delete-orphan",
        order_by="SummaryVersion.version_number",
        foreign_keys="SummaryVersion.summary_id",
    )


class SummaryVersion(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "summary_versions"
    __table_args__ = (
        UniqueConstraint("summary_id", "version_number", name="uq_summary_versions_version"),
    )

    summary_id: Mapped[int] = mapped_column(ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(255))
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(128))

    summary: Mapped["Summary"] = relationship(
        back_populates="versions",
        foreign_keys=[summary_id],
    )


class ChatSession(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_user_context", "user_id", "context_type", "context_ref"),
    )

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    context_type: Mapped[str] = mapped_column(String(64), nullable=False)
    context_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped[Optional[User]] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="chat_session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(TimestampMixin, IntPKMixin, Base):
    __tablename__ = "chat_messages"

    chat_session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(
            ChatMessageRole,
            name="chat_message_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    attachments: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    chat_session: Mapped["ChatSession"] = relationship(back_populates="messages")


__all__ = [
    "User",
    "ManualDocument",
    "DocumentSet",
    "DocumentSetDocument",
    "ChecklistTemplate",
    "ChecklistTemplateItem",
    "ChecklistRun",
    "ChecklistRunItem",
    "Summary",
    "SummaryVersion",
    "ChatSession",
    "ChatMessage",
    "DocumentSetType",
    "DocumentSource",
    "ChecklistTemplateStatus",
    "ChecklistRunStatus",
    "ChatMessageRole",
]
