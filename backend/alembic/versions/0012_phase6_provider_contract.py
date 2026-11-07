"""contract the Phase 6 provider schema after verified backfill

Revision ID: 0012_phase6_contract
Revises: 0011_phase6_backfill
Create Date: 2026-11-07 17:40:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_phase6_contract"
down_revision: str | None = "0011_phase6_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM payments WHERE attempt_no IS NULL OR merchant_reference IS NULL OR amount_poisha IS NULL) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: payment backfill incomplete';
          END IF;
          IF EXISTS (SELECT 1 FROM shipments WHERE attempt_no IS NULL OR merchant_reference IS NULL) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: shipment backfill incomplete';
          END IF;
          IF EXISTS (SELECT 1 FROM webhook_events WHERE kind IS NULL OR event_type IS NULL OR raw_body_sha256 IS NULL OR verification_status IS NULL OR processing_status IS NULL) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: webhook backfill incomplete';
          END IF;
          IF EXISTS (SELECT 1 FROM payments WHERE status::text IN ('pending','initiated','processing','authorized','unknown') GROUP BY order_id HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: multiple active payment attempts';
          END IF;
          IF EXISTS (SELECT 1 FROM payments WHERE status::text = 'succeeded' GROUP BY order_id HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: multiple succeeded payment attempts';
          END IF;
          IF EXISTS (SELECT 1 FROM shipments WHERE status::text IN ('pending','ready','unknown','booked','picked_up','in_transit') GROUP BY order_id HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Phase 6 contract preflight: multiple active shipment attempts';
          END IF;
        END $$;
        """
    )
    op.alter_column("payments", "attempt_no", nullable=False, server_default=sa.text("1"))
    op.alter_column("payments", "merchant_reference", nullable=False)
    op.alter_column("payments", "amount_poisha", nullable=False)
    op.create_check_constraint(
        op.f("ck_payments_attempt_no_positive"), "payments", "attempt_no > 0"
    )
    op.create_check_constraint(
        op.f("ck_payments_amount_poisha_positive"), "payments", "amount_poisha > 0"
    )
    op.create_check_constraint(op.f("ck_payments_revision_positive"), "payments", "revision > 0")
    op.create_unique_constraint(
        "uq_payments_order_attempt_no", "payments", ["order_id", "attempt_no"]
    )
    op.create_unique_constraint(
        "uq_payments_merchant_reference", "payments", ["merchant_reference"]
    )
    op.drop_constraint("uq_payments_provider_provider_txn_id", "payments", type_="unique")
    op.create_index(
        "uq_payments_provider_payment_id",
        "payments",
        ["provider", "provider_payment_id"],
        unique=True,
        postgresql_where=sa.text("provider_payment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_provider_txn_id",
        "payments",
        ["provider", "provider_txn_id"],
        unique=True,
        postgresql_where=sa.text("provider_txn_id IS NOT NULL"),
    )
    op.create_index(
        "uq_payments_one_active_per_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending','initiated','processing','authorized','unknown')"
        ),
    )
    op.create_index(
        "uq_payments_one_succeeded_per_order",
        "payments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )
    op.create_index("ix_payments_reconcile_due", "payments", ["next_reconcile_at", "id"])
    op.drop_constraint(op.f("ck_payments_amount_nonnegative"), "payments", type_="check")
    op.drop_column("payments", "amount")
    op.drop_column("payments", "raw_payload")

    op.alter_column("shipments", "attempt_no", nullable=False, server_default=sa.text("1"))
    op.alter_column("shipments", "merchant_reference", nullable=False)
    op.create_check_constraint(
        op.f("ck_shipments_attempt_no_positive"), "shipments", "attempt_no > 0"
    )
    op.create_check_constraint(op.f("ck_shipments_revision_positive"), "shipments", "revision > 0")
    op.create_unique_constraint(
        "uq_shipments_order_attempt_no", "shipments", ["order_id", "attempt_no"]
    )
    op.create_unique_constraint(
        "uq_shipments_merchant_reference", "shipments", ["merchant_reference"]
    )
    op.drop_constraint("uq_shipments_courier_consignment_id", "shipments", type_="unique")
    op.drop_index("ix_shipments_tracking_code", table_name="shipments")
    op.create_index(
        "uq_shipments_courier_consignment_id",
        "shipments",
        ["courier", "consignment_id"],
        unique=True,
        postgresql_where=sa.text("consignment_id IS NOT NULL"),
    )
    op.create_index(
        "uq_shipments_courier_tracking_code",
        "shipments",
        ["courier", "tracking_code"],
        unique=True,
        postgresql_where=sa.text("tracking_code IS NOT NULL"),
    )
    op.create_index(
        "uq_shipments_one_active_per_order",
        "shipments",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text(
            "courier <> 'mock' AND "
            "status IN ('pending','ready','unknown','booked','picked_up','in_transit')"
        ),
    )
    op.drop_index("ix_shipments_reconcile", table_name="shipments")
    op.create_index("ix_shipments_reconcile", "shipments", ["next_reconcile_at", "id"])
    op.drop_column("shipments", "raw")

    for name in (
        "kind",
        "event_type",
        "raw_body_sha256",
        "verification_status",
        "verification_method",
        "processing_status",
    ):
        op.alter_column(
            "webhook_events",
            name,
            nullable=False,
            server_default=(sa.text("'queued'") if name == "processing_status" else False),
        )
    op.drop_constraint("uq_webhook_events_event_id", "webhook_events", type_="unique")
    op.create_unique_constraint(
        "uq_webhook_events_identity", "webhook_events", ["kind", "provider", "event_id"]
    )
    op.drop_index("ix_webhook_events_provider_processed", table_name="webhook_events")
    op.drop_index("ix_webhook_events_unprocessed", table_name="webhook_events")
    op.create_index(
        "ix_webhook_events_provider_processed",
        "webhook_events",
        ["kind", "provider", "processed_at"],
    )
    op.create_index(
        "ix_webhook_events_processing_due",
        "webhook_events",
        ["processing_status", "next_attempt_at", "created_at"],
        postgresql_where=sa.text("processing_status IN ('queued','retry','processing')"),
    )
    op.create_index(
        "ix_orders_unpaid_payment_due",
        "orders",
        ["payment_due_at", "id"],
        postgresql_where=sa.text(
            "payment_due_at IS NOT NULL AND payment_status NOT IN ('paid','refunded')"
        ),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM payments WHERE attempt_no > 1 OR status::text IN ('processing','expired','unknown'))
             OR EXISTS (SELECT 1 FROM payment_refunds WHERE provider_payload->>'legacy_payment_id' IS NULL)
             OR EXISTS (SELECT 1 FROM shipments WHERE attempt_no > 1 OR status::text = 'unknown')
             OR EXISTS (SELECT 1 FROM provider_location_mappings)
             OR EXISTS (SELECT 1 FROM webhook_events WHERE verification_status::text <> 'legacy_unknown') THEN
            RAISE EXCEPTION 'cannot downgrade 0012: Phase 6 attempts, refunds, mappings, or verified webhooks would be lost';
          END IF;
        END $$;
        """
    )
    op.drop_index("ix_orders_unpaid_payment_due", table_name="orders")
    op.drop_index("ix_webhook_events_processing_due", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider_processed", table_name="webhook_events")
    op.create_index(
        "ix_webhook_events_provider_processed", "webhook_events", ["provider", "processed_at"]
    )
    op.create_index(
        "ix_webhook_events_unprocessed",
        "webhook_events",
        ["created_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.drop_constraint("uq_webhook_events_identity", "webhook_events", type_="unique")
    op.create_unique_constraint("uq_webhook_events_event_id", "webhook_events", ["event_id"])
    for name in (
        "processing_status",
        "verification_method",
        "verification_status",
        "raw_body_sha256",
        "event_type",
        "kind",
    ):
        op.alter_column(
            "webhook_events",
            name,
            nullable=True,
            server_default=(None if name == "processing_status" else False),
        )

    op.add_column(
        "shipments",
        sa.Column("raw", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.execute("UPDATE shipments SET raw = provider_payload")
    op.drop_index("ix_shipments_reconcile", table_name="shipments")
    op.create_index("ix_shipments_reconcile", "shipments", ["status", "updated_at"])
    op.drop_index("uq_shipments_one_active_per_order", table_name="shipments")
    op.drop_index("uq_shipments_courier_tracking_code", table_name="shipments")
    op.drop_index("uq_shipments_courier_consignment_id", table_name="shipments")
    op.create_index("ix_shipments_tracking_code", "shipments", ["tracking_code"])
    op.create_unique_constraint(
        "uq_shipments_courier_consignment_id", "shipments", ["courier", "consignment_id"]
    )
    op.drop_constraint("uq_shipments_merchant_reference", "shipments", type_="unique")
    op.drop_constraint("uq_shipments_order_attempt_no", "shipments", type_="unique")
    op.drop_constraint(op.f("ck_shipments_revision_positive"), "shipments", type_="check")
    op.drop_constraint(op.f("ck_shipments_attempt_no_positive"), "shipments", type_="check")
    op.alter_column("shipments", "merchant_reference", nullable=True)
    op.alter_column("shipments", "attempt_no", nullable=True, server_default=None)

    op.add_column(
        "payments",
        sa.Column(
            "raw_payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column("payments", sa.Column("amount", sa.BigInteger()))
    op.execute("UPDATE payments SET amount = amount_poisha, raw_payload = provider_payload")
    op.alter_column("payments", "amount", nullable=False)
    op.create_check_constraint(op.f("ck_payments_amount_nonnegative"), "payments", "amount >= 0")
    op.drop_index("ix_payments_reconcile_due", table_name="payments")
    op.drop_index("uq_payments_one_succeeded_per_order", table_name="payments")
    op.drop_index("uq_payments_one_active_per_order", table_name="payments")
    op.drop_index("uq_payments_provider_txn_id", table_name="payments")
    op.drop_index("uq_payments_provider_payment_id", table_name="payments")
    op.create_unique_constraint(
        "uq_payments_provider_provider_txn_id", "payments", ["provider", "provider_txn_id"]
    )
    op.drop_constraint("uq_payments_merchant_reference", "payments", type_="unique")
    op.drop_constraint("uq_payments_order_attempt_no", "payments", type_="unique")
    op.drop_constraint(op.f("ck_payments_revision_positive"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_amount_poisha_positive"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_attempt_no_positive"), "payments", type_="check")
    op.alter_column("payments", "amount_poisha", nullable=True)
    op.alter_column("payments", "merchant_reference", nullable=True)
    op.alter_column("payments", "attempt_no", nullable=True, server_default=None)
