"""expand the Phase 6 payment, refund, courier, webhook, and worker contract

Revision ID: 0010_phase6_expand
Revises: 0009_phase5_hardening
Create Date: 2026-11-07 17:20:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase6_expand"
down_revision: str | None = "0009_phase5_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

refund_status = postgresql.ENUM(
    "pending",
    "processing",
    "succeeded",
    "failed",
    "cancelled",
    "unknown",
    name="refund_status",
    create_type=False,
)
refund_mode = postgresql.ENUM("provider", "manual", name="refund_mode", create_type=False)
webhook_kind = postgresql.ENUM("payment", "courier", name="webhook_kind", create_type=False)
webhook_verification_status = postgresql.ENUM(
    "verified",
    "pending_validation",
    "legacy_unknown",
    name="webhook_verification_status",
    create_type=False,
)
webhook_processing_status = postgresql.ENUM(
    "queued",
    "processing",
    "processed",
    "ignored",
    "retry",
    "dead_letter",
    name="webhook_processing_status",
    create_type=False,
)
provider_geo_level = postgresql.ENUM(
    "division", "district", "upazila", name="provider_geo_level", create_type=False
)
payment_method = postgresql.ENUM(
    "cod", "bkash", "nagad", "sslcommerz", name="payment_method", create_type=False
)
courier_provider = postgresql.ENUM(
    "pathao",
    "steadfast",
    "redx",
    "manual",
    "mock",
    name="courier_provider",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (
        refund_status,
        refund_mode,
        webhook_kind,
        webhook_verification_status,
        webhook_processing_status,
        provider_geo_level,
    ):
        enum.create(bind, checkfirst=True)
    op.execute("ALTER TYPE payment_record_status ADD VALUE IF NOT EXISTS 'processing'")
    op.execute("ALTER TYPE payment_record_status ADD VALUE IF NOT EXISTS 'expired'")
    op.execute("ALTER TYPE payment_record_status ADD VALUE IF NOT EXISTS 'unknown'")
    op.execute("ALTER TYPE shipment_status ADD VALUE IF NOT EXISTS 'unknown'")

    op.add_column("orders", sa.Column("payment_due_at", sa.DateTime(timezone=True)))

    for column in (
        sa.Column("attempt_no", sa.SmallInteger()),
        sa.Column("merchant_reference", sa.String(length=128)),
        sa.Column("provider_payment_id", sa.String(length=255)),
        sa.Column("amount_poisha", sa.BigInteger()),
        sa.Column("provider_status", sa.String(length=120)),
        sa.Column("failure_code", sa.String(length=120)),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column("next_action", postgresql.JSONB()),
        sa.Column("action_expires_at", sa.DateTime(timezone=True)),
        sa.Column("initiated_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True)),
        sa.Column("reconcile_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ):
        op.add_column("payments", column)

    op.create_table(
        "payment_refunds",
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", payment_method, nullable=False),
        sa.Column("refund_no", sa.SmallInteger(), nullable=False),
        sa.Column("merchant_reference", sa.String(length=128), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=255)),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("amount_poisha", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'BDT'"), nullable=False),
        sa.Column("status", refund_status, server_default=sa.text("'pending'"), nullable=False),
        sa.Column("mode", refund_mode, nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("manual_reference", sa.String(length=255)),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True)),
        sa.Column("provider_status", sa.String(length=120)),
        sa.Column("failure_code", sa.String(length=120)),
        sa.Column("failure_reason", sa.String(length=500)),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("initiated_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True)),
        sa.Column("reconcile_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "refund_no", name="uq_payment_refunds_payment_refund_no"),
        sa.UniqueConstraint("merchant_reference", name="uq_payment_refunds_merchant_reference"),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_refunds_idempotency_key"),
        sa.CheckConstraint("refund_no > 0", name=op.f("ck_payment_refunds_refund_no_positive")),
        sa.CheckConstraint(
            "amount_poisha > 0", name=op.f("ck_payment_refunds_amount_poisha_positive")
        ),
        sa.CheckConstraint("currency = 'BDT'", name=op.f("ck_payment_refunds_currency_bdt")),
        sa.CheckConstraint("revision > 0", name=op.f("ck_payment_refunds_revision_positive")),
        sa.CheckConstraint(
            "mode <> 'manual' OR manual_reference IS NOT NULL",
            name=op.f("ck_payment_refunds_manual_reference_required"),
        ),
    )
    op.create_index(
        "ix_payment_refunds_order_created", "payment_refunds", ["order_id", "created_at"]
    )
    op.create_index(
        "ix_payment_refunds_reconcile_due", "payment_refunds", ["next_reconcile_at", "id"]
    )
    op.create_index(
        "uq_payment_refunds_provider_refund_id",
        "payment_refunds",
        ["provider", "provider_refund_id"],
        unique=True,
        postgresql_where=sa.text("provider_refund_id IS NOT NULL"),
    )

    for column in (
        sa.Column("attempt_no", sa.SmallInteger()),
        sa.Column("merchant_reference", sa.String(length=128)),
        sa.Column("provider_status", sa.String(length=120)),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=120)),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True)),
        sa.Column("reconcile_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True)),
        sa.Column("picked_up_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("returned_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("shipments", column)

    for column in (
        sa.Column("kind", webhook_kind),
        sa.Column("event_type", sa.String(length=120)),
        sa.Column("raw_body_sha256", sa.CHAR(length=64)),
        sa.Column(
            "normalized_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("verification_status", webhook_verification_status),
        sa.Column("verification_method", sa.String(length=80)),
        sa.Column("processing_status", webhook_processing_status),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("refund_id", postgresql.UUID(as_uuid=True)),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider_occurred_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=120)),
        sa.Column("last_error", sa.String(length=500)),
    ):
        op.add_column("webhook_events", column)
    op.create_foreign_key(
        "fk_webhook_events_payment_id_payments",
        "webhook_events",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_webhook_events_refund_id_payment_refunds",
        "webhook_events",
        "payment_refunds",
        ["refund_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_webhook_events_shipment_id_shipments",
        "webhook_events",
        "shipments",
        ["shipment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "provider_location_mappings",
        sa.Column("courier", courier_provider, nullable=False),
        sa.Column("geo_level", provider_geo_level, nullable=False),
        sa.Column("division_id", postgresql.UUID(as_uuid=True)),
        sa.Column("district_id", postgresql.UUID(as_uuid=True)),
        sa.Column("upazila_id", postgresql.UUID(as_uuid=True)),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_parent_id", sa.String(length=255)),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "provider_payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_synchronized_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["division_id"], ["geo_divisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["district_id"], ["geo_districts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upazila_id"], ["geo_upazilas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "num_nonnulls(division_id, district_id, upazila_id) = 1",
            name=op.f("ck_provider_location_mappings_exactly_one_local_location"),
        ),
        sa.CheckConstraint(
            "(geo_level = 'division' AND division_id IS NOT NULL) OR (geo_level = 'district' AND district_id IS NOT NULL) OR (geo_level = 'upazila' AND upazila_id IS NOT NULL)",
            name=op.f("ck_provider_location_mappings_geo_level_matches_location"),
        ),
        sa.UniqueConstraint(
            "courier", "geo_level", "external_id", name="uq_provider_locations_external"
        ),
    )
    op.create_index(
        "ix_provider_locations_active",
        "provider_location_mappings",
        ["courier", "geo_level", "active"],
    )
    op.create_index(
        "uq_provider_locations_division",
        "provider_location_mappings",
        ["courier", "division_id"],
        unique=True,
        postgresql_where=sa.text("division_id IS NOT NULL"),
    )
    op.create_index(
        "uq_provider_locations_district",
        "provider_location_mappings",
        ["courier", "district_id"],
        unique=True,
        postgresql_where=sa.text("district_id IS NOT NULL"),
    )
    op.create_index(
        "uq_provider_locations_upazila",
        "provider_location_mappings",
        ["courier", "upazila_id"],
        unique=True,
        postgresql_where=sa.text("upazila_id IS NOT NULL"),
    )

    op.create_table(
        "reconciliation_conflicts",
        sa.Column("resource_kind", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_kind", "resource_id", "code", name="uq_reconcile_conflict"),
    )
    op.create_index(
        "ix_reconciliation_conflicts_open",
        "reconciliation_conflicts",
        ["resolved_at", "created_at"],
    )

    op.add_column("outbox_events", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("locked_by", sa.String(length=128)))


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM payments WHERE attempt_no > 1 OR status::text IN ('processing','expired','unknown'))
             OR EXISTS (SELECT 1 FROM payment_refunds WHERE provider_payload->>'legacy_payment_id' IS NULL)
             OR EXISTS (SELECT 1 FROM shipments WHERE attempt_no > 1 OR status::text = 'unknown')
             OR EXISTS (SELECT 1 FROM provider_location_mappings)
             OR EXISTS (SELECT 1 FROM webhook_events WHERE verification_status::text <> 'legacy_unknown') THEN
            RAISE EXCEPTION 'cannot downgrade 0010: Phase 6 provider history would be destroyed';
          END IF;
        END $$;
        """
    )
    for name in ("locked_by", "lease_expires_at", "locked_at"):
        op.drop_column("outbox_events", name)
    op.drop_index("ix_reconciliation_conflicts_open", table_name="reconciliation_conflicts")
    op.drop_table("reconciliation_conflicts")
    op.drop_index("ix_provider_locations_active", table_name="provider_location_mappings")
    op.drop_table("provider_location_mappings")
    for constraint in (
        "fk_webhook_events_shipment_id_shipments",
        "fk_webhook_events_refund_id_payment_refunds",
        "fk_webhook_events_payment_id_payments",
    ):
        op.drop_constraint(constraint, "webhook_events", type_="foreignkey")
    for name in (
        "last_error",
        "last_error_code",
        "next_attempt_at",
        "attempts",
        "provider_occurred_at",
        "shipment_id",
        "refund_id",
        "payment_id",
        "processing_status",
        "verification_method",
        "verification_status",
        "normalized_payload",
        "raw_body_sha256",
        "event_type",
        "kind",
    ):
        op.drop_column("webhook_events", name)
    for name in (
        "cancelled_at",
        "returned_at",
        "delivered_at",
        "picked_up_at",
        "booked_at",
        "reconcile_attempts",
        "next_reconcile_at",
        "last_reconciled_at",
        "last_event_at",
        "failure_code",
        "provider_payload",
        "provider_status",
        "merchant_reference",
        "attempt_no",
    ):
        op.drop_column("shipments", name)
    op.drop_index("uq_payment_refunds_provider_refund_id", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_reconcile_due", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_order_created", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    for name in (
        "revision",
        "provider_payload",
        "reconcile_attempts",
        "next_reconcile_at",
        "last_reconciled_at",
        "terminal_at",
        "expires_at",
        "initiated_at",
        "action_expires_at",
        "next_action",
        "failure_reason",
        "failure_code",
        "provider_status",
        "amount_poisha",
        "provider_payment_id",
        "merchant_reference",
        "attempt_no",
    ):
        op.drop_column("payments", name)
    op.drop_column("orders", "payment_due_at")
    for enum in (
        provider_geo_level,
        webhook_processing_status,
        webhook_verification_status,
        webhook_kind,
        refund_mode,
        refund_status,
    ):
        enum.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot safely remove enum labels in-place. New labels are harmlessly retained.
