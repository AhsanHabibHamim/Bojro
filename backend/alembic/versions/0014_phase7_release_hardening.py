"""harden Phase 7 delivery retention and assistant idempotency

Revision ID: 0014_phase7_release_hardening
Revises: 0013_phase7_engagement
Create Date: 2026-11-08 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_phase7_release_hardening"
down_revision: str | None = "0013_phase7_engagement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "analytics_events",
        sa.Column("capi_terminal_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "assistant_request_idempotency",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("key_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("key_hash_key_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("request_hash_key_id", sa.String(length=64), nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_message_id", UUID, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('processing','completed')",
            name=op.f("ck_assistant_request_idempotency_state_allowed"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_assistant_request_idempotency_expiry_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["assistant_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["response_message_id"],
            ["assistant_messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_request_idempotency")),
        sa.UniqueConstraint(
            "session_id",
            "key_hash",
            name="uq_assistant_request_idempotency_key",
        ),
        sa.UniqueConstraint(
            "session_id",
            "client_message_id",
            name="uq_assistant_request_idempotency_client_message",
        ),
    )
    op.create_index(
        "ix_assistant_request_idempotency_expiry",
        "assistant_request_idempotency",
        ["expires_at"],
    )
    op.create_index(
        "ix_assistant_request_idempotency_lease",
        "assistant_request_idempotency",
        ["state", "lease_expires_at"],
        postgresql_where=sa.text("state = 'processing'"),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM assistant_request_idempotency)
             OR EXISTS (SELECT 1 FROM analytics_events WHERE capi_terminal_at IS NOT NULL) THEN
            RAISE EXCEPTION 'cannot downgrade 0014: assistant idempotency data would be lost';
          END IF;
        END $$;
        """
    )
    op.drop_index(
        "ix_assistant_request_idempotency_lease",
        table_name="assistant_request_idempotency",
    )
    op.drop_index(
        "ix_assistant_request_idempotency_expiry",
        table_name="assistant_request_idempotency",
    )
    op.drop_table("assistant_request_idempotency")
    op.drop_column("analytics_events", "capi_terminal_at")
