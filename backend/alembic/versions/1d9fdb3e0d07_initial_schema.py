"""Initial relational schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "1d9fdb3e0d07"
down_revision = None
branch_labels = None
depends_on = None

DOCUMENT_SET_TYPE = ("clearinghouse", "manual")
DOCUMENT_SOURCE_TYPE = ("clearinghouse", "manual")
CHECKLIST_TEMPLATE_STATUS = ("draft", "published", "deprecated")
CHECKLIST_RUN_STATUS = ("pending", "running", "completed", "failed")
CHAT_MESSAGE_ROLE = ("system", "user", "assistant")


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    joined = ", ".join(f"'{value}'" for value in values)
    op.execute(
        sa.text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
            f"CREATE TYPE {name} AS ENUM ({joined}); END IF; END $$;"
        )
    )


def _drop_enum(name: str) -> None:
    op.execute(sa.text(f"DROP TYPE IF EXISTS {name} CASCADE;"))


def upgrade() -> None:
    _create_enum("document_set_type", DOCUMENT_SET_TYPE)
    _create_enum("document_source_type", DOCUMENT_SOURCE_TYPE)
    _create_enum("checklist_template_status", CHECKLIST_TEMPLATE_STATUS)
    _create_enum("checklist_run_status", CHECKLIST_RUN_STATUS)
    _create_enum("chat_message_role", CHAT_MESSAGE_ROLE)

    document_set_type_enum = postgresql.ENUM(
        *DOCUMENT_SET_TYPE,
        name="document_set_type",
        create_type=False,
    )
    document_source_enum = postgresql.ENUM(
        *DOCUMENT_SOURCE_TYPE,
        name="document_source_type",
        create_type=False,
    )
    checklist_template_status_enum = postgresql.ENUM(
        *CHECKLIST_TEMPLATE_STATUS,
        name="checklist_template_status",
        create_type=False,
    )
    checklist_run_status_enum = postgresql.ENUM(
        *CHECKLIST_RUN_STATUS,
        name="checklist_run_status",
        create_type=False,
    )
    chat_message_role_enum = postgresql.ENUM(
        *CHAT_MESSAGE_ROLE,
        name="chat_message_role",
        create_type=False,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "manual_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "document_sets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("type", document_set_type_enum, nullable=False),
        sa.Column("case_identifier", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("doc_hash", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("type", "case_identifier", "user_id", "doc_hash", name="uq_document_sets_case_hash"),
    )

    op.create_table(
        "checklist_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            checklist_template_status_enum,
            nullable=False,
            server_default=sa.text("'draft'::checklist_template_status"),
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("parent_template_id", sa.BigInteger(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_template_id"], ["checklist_templates.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", "version", name="uq_checklist_templates_slug_version"),
    )

    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("document_identifier", sa.String(length=255), nullable=False),
        sa.Column("summary_type", sa.String(length=64), nullable=False),
        sa.Column("current_version_id", sa.BigInteger(), nullable=True),
        sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "document_identifier", "summary_type", name="uq_summaries_user_document_type"),
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("context_type", sa.String(length=64), nullable=False),
        sa.Column("context_ref", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_chat_sessions_user_context", "chat_sessions", ["user_id", "context_type", "context_ref"], unique=False)

    op.create_table(
        "document_set_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_set_id", sa.BigInteger(), nullable=False),
        sa.Column("source", document_source_enum, nullable=False),
        sa.Column("remote_document_id", sa.String(length=255), nullable=True),
        sa.Column("manual_document_id", sa.BigInteger(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("doc_type", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_set_id"], ["document_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_document_id"], ["manual_documents.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(remote_document_id IS NOT NULL AND manual_document_id IS NULL) OR "
            "(remote_document_id IS NULL AND manual_document_id IS NOT NULL)",
            name="ck_document_set_documents_source_pointer",
        ),
    )
    op.create_index(
        "ix_document_set_documents_set_position",
        "document_set_documents",
        ["document_set_id", "position"],
        unique=False,
    )

    op.create_table(
        "checklist_template_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("item_key", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_templates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("template_id", "item_key", name="uq_checklist_template_items_key"),
    )

    op.create_table(
        "checklist_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("document_set_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            checklist_run_status_enum,
            nullable=False,
            server_default=sa.text("'pending'::checklist_run_status"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_set_id"], ["document_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("template_id", "document_set_id", "user_id", "prompt_hash", name="uq_checklist_runs_signature"),
    )

    op.create_table(
        "summary_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("summary_id", sa.BigInteger(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("summary_id", "version_number", name="uq_summary_versions_version"),
    )

    op.create_foreign_key(
        "fk_summaries_current_version_id",
        "summaries",
        "summary_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "checklist_run_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("checklist_run_id", sa.BigInteger(), nullable=False),
        sa.Column("template_item_id", sa.BigInteger(), nullable=False),
        sa.Column("document_ref", sa.String(length=255), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["checklist_run_id"], ["checklist_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_item_id"], ["checklist_template_items.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("chat_session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", chat_message_role_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("checklist_run_items")
    op.drop_constraint("fk_summaries_current_version_id", "summaries", type_="foreignkey")
    op.drop_table("summary_versions")
    op.drop_table("checklist_runs")
    op.drop_table("checklist_template_items")
    op.drop_index("ix_document_set_documents_set_position", table_name="document_set_documents")
    op.drop_table("document_set_documents")
    op.drop_index("ix_chat_sessions_user_context", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_table("summaries")
    op.drop_table("checklist_templates")
    op.drop_table("document_sets")
    op.drop_table("manual_documents")
    op.drop_table("users")

    _drop_enum("chat_message_role")
    _drop_enum("checklist_run_status")
    _drop_enum("checklist_template_status")
    _drop_enum("document_source_type")
    _drop_enum("document_set_type")
