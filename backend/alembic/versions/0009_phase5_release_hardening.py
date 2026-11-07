"""harden Phase 5 TOTP key rotation and audit tamper evidence

Revision ID: 0009_phase5_hardening
Revises: 0008_phase5_content
Create Date: 2026-11-07 11:30:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_phase5_hardening"
down_revision: str | None = "0008_phase5_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_totp_credentials",
        sa.Column("key_id", sa.String(length=64), server_default=sa.text("'v1'"), nullable=False),
    )
    op.add_column("audit_logs", sa.Column("previous_hash", sa.CHAR(length=64)))
    op.add_column("audit_logs", sa.Column("entry_hash", sa.CHAR(length=64)))
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS bojro_reject_audit_mutation()")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        DO $$
        DECLARE
            audit_row record;
            previous_value text := repeat('0', 64);
            current_value text;
        BEGIN
            FOR audit_row IN
                SELECT id, at, actor, action, entity, entity_id, diff, request_id
                  FROM audit_logs
                 ORDER BY at, id
            LOOP
                current_value := encode(
                    digest(
                        previous_value || '|' || audit_row.id::text || '|' ||
                        audit_row.at::text || '|' || coalesce(audit_row.actor::text, '') || '|' ||
                        audit_row.action || '|' || audit_row.entity || '|' ||
                        coalesce(audit_row.entity_id::text, '') || '|' || audit_row.diff::text || '|' ||
                        coalesce(audit_row.request_id, ''),
                        'sha256'
                    ),
                    'hex'
                );
                UPDATE audit_logs
                   SET previous_hash = previous_value, entry_hash = current_value
                 WHERE id = audit_row.id;
                previous_value := current_value;
            END LOOP;
        END $$;
        """
    )
    op.alter_column("audit_logs", "previous_hash", nullable=False)
    op.alter_column("audit_logs", "entry_hash", nullable=False)
    op.create_unique_constraint("uq_audit_logs_entry_hash", "audit_logs", ["entry_hash"])
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bojro_chain_audit_insert()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            previous_value text;
        BEGIN
            PERFORM pg_advisory_xact_lock(714202605);
            SELECT entry_hash INTO previous_value
              FROM audit_logs
             ORDER BY at DESC, id DESC
             LIMIT 1;
            NEW.previous_hash := coalesce(previous_value, repeat('0', 64));
            NEW.entry_hash := encode(
                digest(
                    NEW.previous_hash || '|' || NEW.id::text || '|' || NEW.at::text || '|' ||
                    coalesce(NEW.actor::text, '') || '|' || NEW.action || '|' || NEW.entity || '|' ||
                    coalesce(NEW.entity_id::text, '') || '|' || NEW.diff::text || '|' ||
                    coalesce(NEW.request_id, ''),
                    'sha256'
                ),
                'hex'
            );
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bojro_reject_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_chain
        BEFORE INSERT ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION bojro_chain_audit_insert()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION bojro_reject_audit_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION bojro_reject_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM audit_logs)
               OR EXISTS (SELECT 1 FROM admin_totp_credentials WHERE key_id <> 'v1') THEN
                RAISE EXCEPTION 'cannot downgrade 0009: audit-chain or rotated TOTP key data would be destroyed';
            END IF;
        END $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_chain ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS bojro_chain_audit_insert()")
    op.execute("DROP FUNCTION IF EXISTS bojro_reject_audit_mutation()")
    op.drop_constraint("uq_audit_logs_entry_hash", "audit_logs", type_="unique")
    op.drop_column("audit_logs", "entry_hash")
    op.drop_column("audit_logs", "previous_hash")
    op.drop_column("admin_totp_credentials", "key_id")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bojro_reject_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION bojro_reject_audit_mutation()
        """
    )
