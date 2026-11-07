"""add the phase 5 admin security and transactional foundation

Revision ID: 0006_phase5_admin
Revises: 0005_phase4_p1
Create Date: 2026-11-07 04:45:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase5_admin"
down_revision: str | None = "0005_phase4_p1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

auth_session_kind = postgresql.ENUM(
    "customer", "admin", name="auth_session_kind", create_type=False
)
outbox_status = postgresql.ENUM(
    "pending",
    "processing",
    "delivered",
    "failed",
    name="outbox_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    auth_session_kind.create(bind, checkfirst=True)
    outbox_status.create(bind, checkfirst=True)
    op.execute("ALTER TYPE courier_provider ADD VALUE IF NOT EXISTS 'mock'")

    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("disabled_reason", sa.String(length=500)))
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True)))
    op.add_column(
        "auth_sessions",
        sa.Column(
            "kind",
            auth_session_kind,
            nullable=False,
            server_default=sa.text("'customer'"),
        ),
    )
    op.add_column("auth_sessions", sa.Column("absolute_expires_at", sa.DateTime(timezone=True)))
    op.add_column("auth_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("auth_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE auth_sessions SET absolute_expires_at = expires_at, "
        "last_seen_at = last_rotated_at WHERE absolute_expires_at IS NULL"
    )
    op.execute(
        "UPDATE auth_sessions AS session SET revoked_at = now() "
        "FROM users AS account WHERE account.id = session.user_id "
        "AND account.role = 'admin' AND session.revoked_at IS NULL"
    )
    op.create_index(
        "ix_auth_sessions_user_kind_expires",
        "auth_sessions",
        ["user_id", "kind", "expires_at"],
    )

    op.create_table(
        "admin_totp_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_secret", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("last_accepted_timestep", sa.BigInteger()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "last_accepted_timestep IS NULL OR last_accepted_timestep >= 0",
            name=op.f("ck_admin_totp_credentials_timestep_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_totp_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_totp_credentials")),
        sa.UniqueConstraint("user_id", name=op.f("uq_admin_totp_credentials_user_id")),
    )
    op.create_table(
        "admin_recovery_codes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=512), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_recovery_codes")),
    )
    op.create_index(
        "ix_admin_recovery_codes_user_unused", "admin_recovery_codes", ["user_id", "used_at"]
    )
    op.create_table(
        "admin_auth_challenges",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("ip_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("user_agent_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 5", name=op.f("ck_admin_auth_challenges_attempts_range")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_admin_auth_challenges_expiry_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_auth_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_auth_challenges")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_admin_auth_challenges_token_hash")),
    )
    op.create_index("ix_admin_auth_challenges_expiry", "admin_auth_challenges", ["expires_at"])
    op.create_index(
        "ix_admin_auth_challenges_user_created",
        "admin_auth_challenges",
        ["user_id", "created_at"],
    )

    op.add_column("idempotency_records", sa.Column("response_body", postgresql.JSONB()))
    op.add_column(
        "idempotency_records",
        sa.Column(
            "response_headers",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "idempotency_records",
        sa.Column(
            "state", sa.String(length=24), server_default=sa.text("'processing'"), nullable=False
        ),
    )
    op.add_column(
        "idempotency_records",
        sa.Column(
            "retention_class",
            sa.String(length=32),
            server_default=sa.text("'standard'"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE idempotency_records SET state = CASE WHEN completed_at IS NULL "
        "THEN 'processing' ELSE 'completed' END"
    )
    op.drop_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        "resource_id IS NULL OR resource_kind IS NOT NULL",
    )

    for name, column in (
        (
            "event_kind",
            sa.Column(
                "event_kind",
                sa.String(length=32),
                server_default=sa.text("'mutation'"),
                nullable=False,
            ),
        ),
        (
            "actor_snapshot",
            sa.Column(
                "actor_snapshot",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        ),
        ("method", sa.Column("method", sa.String(length=12))),
        ("path", sa.Column("path", sa.String(length=500))),
        ("status_code", sa.Column("status_code", sa.SmallInteger())),
        ("user_agent_hash", sa.Column("user_agent_hash", sa.CHAR(length=64))),
    ):
        del name
        op.add_column("audit_logs", column)
    op.create_index("ix_audit_logs_request_id_at", "audit_logs", ["request_id", "at"])
    op.create_index("ix_audit_logs_ip_at", "audit_logs", ["ip_address", "at"])
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

    op.create_table(
        "outbox_events",
        sa.Column("topic", sa.String(length=160), nullable=False),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", outbox_status, server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=500)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("deduplication_key", name="uq_outbox_events_deduplication_key"),
    )
    op.create_index(
        "ix_outbox_events_delivery",
        "outbox_events",
        ["status", "next_attempt_at", "created_at"],
    )

    op.add_column(
        "orders", sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False)
    )
    op.add_column(
        "orders",
        sa.Column(
            "merchant_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE orders
           SET merchant_snapshot = jsonb_build_object(
               'branding', coalesce((SELECT value FROM site_settings WHERE key = 'branding'), '{}'::jsonb),
               'contact', coalesce((SELECT value FROM site_settings WHERE key = 'contact'), '{}'::jsonb)
           )
         WHERE merchant_snapshot = '{}'::jsonb
        """
    )
    op.add_column(
        "shipments",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("shipments", sa.Column("booking_idempotency_key", sa.String(length=128)))
    op.add_column("shipments", sa.Column("failure_reason", sa.String(length=500)))
    op.create_unique_constraint(
        "uq_shipments_booking_idempotency_key", "shipments", ["booking_idempotency_key"]
    )
    op.create_index("ix_shipments_reconcile", "shipments", ["status", "updated_at"])

    op.create_table(
        "order_notes",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "customer_visible", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_order_notes_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_notes_order_id_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_notes")),
    )
    op.create_index(
        "ix_order_notes_order_created_id", "order_notes", ["order_id", "created_at", "id"]
    )

    op.create_table(
        "inventory_movements",
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("order_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.String(length=160), nullable=False),
        sa.Column("note", sa.String(length=500)),
        sa.Column("delta_on_hand", sa.Integer(), nullable=False),
        sa.Column("delta_reserved", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("balance_on_hand", sa.Integer(), nullable=False),
        sa.Column("balance_reserved", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason = 'opening_balance' OR delta_on_hand <> 0 OR delta_reserved <> 0",
            name=op.f("ck_inventory_movements_nonzero_delta"),
        ),
        sa.CheckConstraint(
            "balance_on_hand >= 0", name=op.f("ck_inventory_movements_on_hand_nonnegative")
        ),
        sa.CheckConstraint(
            "balance_reserved >= 0", name=op.f("ck_inventory_movements_reserved_nonnegative")
        ),
        sa.CheckConstraint(
            "balance_reserved <= balance_on_hand",
            name=op.f("ck_inventory_movements_reserved_within_on_hand"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_inventory_movements_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_inventory_movements_order_id_orders"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name=op.f("fk_inventory_movements_variant_id_product_variants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_movements")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_inventory_movements_idempotency_key")),
    )
    op.create_index(
        "ix_inventory_movements_variant_created_id",
        "inventory_movements",
        ["variant_id", "created_at", "id"],
    )
    op.execute(
        """
        INSERT INTO inventory_movements (
            id, variant_id, reason, delta_on_hand, delta_reserved,
            balance_on_hand, balance_reserved, created_at
        )
        SELECT gen_random_uuid(), id, 'opening_balance', stock_on_hand, stock_reserved,
               stock_on_hand, stock_reserved, created_at
          FROM product_variants
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM admin_totp_credentials WHERE confirmed_at IS NOT NULL)
               OR EXISTS (SELECT 1 FROM admin_recovery_codes)
               OR EXISTS (
                   SELECT 1 FROM users
                    WHERE disabled_reason IS NOT NULL OR disabled_at IS NOT NULL
               )
               OR EXISTS (SELECT 1 FROM order_notes)
               OR EXISTS (SELECT 1 FROM orders)
               OR EXISTS (
                   SELECT 1 FROM shipments
                    WHERE booking_idempotency_key IS NOT NULL OR failure_reason IS NOT NULL
               )
               OR EXISTS (SELECT 1 FROM outbox_events)
               OR EXISTS (
                   SELECT 1 FROM idempotency_records
                    WHERE response_body IS NOT NULL
                       OR response_headers <> '{}'::jsonb
                       OR retention_class <> 'standard'
               )
               OR EXISTS (
                   SELECT 1 FROM audit_logs
                    WHERE event_kind <> 'mutation'
                       OR actor_snapshot <> '{}'::jsonb
                       OR method IS NOT NULL OR path IS NOT NULL
                       OR status_code IS NOT NULL OR user_agent_hash IS NOT NULL
               )
               OR EXISTS (SELECT 1 FROM inventory_movements WHERE reason <> 'opening_balance') THEN
                RAISE EXCEPTION 'cannot downgrade 0006: Phase 5 security or business history would be destroyed';
            END IF;
        END $$;
        """
    )
    op.drop_table("inventory_movements")
    op.drop_index("ix_order_notes_order_created_id", table_name="order_notes")
    op.drop_table("order_notes")
    op.drop_index("ix_shipments_reconcile", table_name="shipments")
    op.drop_constraint("uq_shipments_booking_idempotency_key", "shipments", type_="unique")
    op.drop_column("shipments", "failure_reason")
    op.drop_column("shipments", "booking_idempotency_key")
    op.drop_column("shipments", "revision")
    op.drop_column("orders", "merchant_snapshot")
    op.drop_column("orders", "revision")
    op.drop_index("ix_outbox_events_delivery", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS bojro_reject_audit_mutation()")
    op.drop_index("ix_audit_logs_ip_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_request_id_at", table_name="audit_logs")
    for name in (
        "user_agent_hash",
        "status_code",
        "path",
        "method",
        "actor_snapshot",
        "event_kind",
    ):
        op.drop_column("audit_logs", name)
    for name in ("retention_class", "state", "response_headers", "response_body"):
        op.drop_column("idempotency_records", name)
    op.execute("UPDATE idempotency_records SET resource_kind = NULL WHERE resource_id IS NULL")
    op.drop_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        "(resource_kind IS NULL) = (resource_id IS NULL)",
    )
    op.drop_index("ix_admin_auth_challenges_user_created", table_name="admin_auth_challenges")
    op.drop_index("ix_admin_auth_challenges_expiry", table_name="admin_auth_challenges")
    op.drop_table("admin_auth_challenges")
    op.drop_index("ix_admin_recovery_codes_user_unused", table_name="admin_recovery_codes")
    op.drop_table("admin_recovery_codes")
    op.drop_table("admin_totp_credentials")
    op.drop_index("ix_auth_sessions_user_kind_expires", table_name="auth_sessions")
    for name in ("mfa_verified_at", "last_seen_at", "absolute_expires_at", "kind"):
        op.drop_column("auth_sessions", name)
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "disabled_reason")
    op.drop_column("users", "password_changed_at")
    outbox_status.drop(op.get_bind(), checkfirst=True)
    auth_session_kind.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove an enum label without rewriting dependent values. The harmless
    # courier_provider.mock label is intentionally preserved on downgrade.
