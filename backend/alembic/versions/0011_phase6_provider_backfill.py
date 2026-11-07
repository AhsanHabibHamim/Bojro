"""backfill and transform Phase 5 provider records for Phase 6

Revision ID: 0011_phase6_backfill
Revises: 0010_phase6_expand
Create Date: 2026-11-07 17:30:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "0011_phase6_backfill"
down_revision: str | None = "0010_phase6_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM payments
             WHERE amount::numeric <> trunc(amount::numeric)
          ) THEN
            RAISE EXCEPTION 'Phase 6 payment preflight: amount contains fractional poisha';
          END IF;
          IF EXISTS (
            SELECT 1 FROM payments WHERE provider_txn_id IS NOT NULL
             GROUP BY provider, provider_txn_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'Phase 6 payment preflight: duplicate provider transaction identifiers';
          END IF;
          IF EXISTS (
            SELECT 1 FROM shipments WHERE consignment_id IS NOT NULL
             GROUP BY courier, consignment_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'Phase 6 shipment preflight: duplicate provider consignment identifiers';
          END IF;
          IF EXISTS (
            SELECT 1 FROM shipments WHERE tracking_code IS NOT NULL
             GROUP BY courier, tracking_code HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'Phase 6 shipment preflight: duplicate provider tracking identifiers';
          END IF;
          IF EXISTS (
            SELECT 1 FROM payments legacy
             WHERE legacy.status::text = 'refunded'
               AND (SELECT count(*) FROM payments capture
                     WHERE capture.order_id = legacy.order_id
                       AND capture.status::text = 'succeeded') <> 1
          ) THEN
            RAISE EXCEPTION 'Phase 6 refund preflight: legacy refund has no unambiguous capture';
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        WITH numbered AS (
          SELECT id, row_number() OVER (PARTITION BY order_id ORDER BY created_at, id)::smallint AS n
            FROM payments
        )
        UPDATE payments p
           SET attempt_no = numbered.n,
               merchant_reference = 'BP' || substr(replace(p.id::text, '-', ''), 1, 28),
               amount_poisha = p.amount,
               provider_payload = coalesce(p.raw_payload, '{}'::jsonb),
               initiated_at = CASE WHEN p.status::text <> 'pending' THEN p.created_at ELSE NULL END,
               terminal_at = CASE WHEN p.status::text IN ('succeeded','failed','cancelled','refunded') THEN p.updated_at ELSE NULL END
          FROM numbered WHERE p.id = numbered.id
        """
    )
    op.execute(
        """
        WITH legacy AS (
          SELECT legacy.*, capture.id AS capture_id,
                 row_number() OVER (PARTITION BY capture.id ORDER BY legacy.created_at, legacy.id)::smallint AS refund_no
            FROM payments legacy
            JOIN payments capture ON capture.order_id = legacy.order_id
                                 AND capture.status::text = 'succeeded'
           WHERE legacy.status::text = 'refunded'
        )
        INSERT INTO payment_refunds (
          id, payment_id, order_id, provider, refund_no, merchant_reference,
          provider_refund_id, idempotency_key, amount_poisha, currency, status,
          mode, reason, manual_reference, provider_status, provider_payload,
          initiated_at, completed_at, revision, created_at, updated_at
        )
        SELECT gen_random_uuid(), capture_id, order_id, provider, refund_no,
               'BR' || substr(replace(id::text, '-', ''), 1, 28), provider_txn_id,
               idempotency_key, amount, currency, 'succeeded'::refund_status,
               'manual'::refund_mode, 'Legacy Phase 5 confirmed refund',
               coalesce(provider_txn_id, 'legacy-' || id::text), 'legacy_refunded',
               jsonb_build_object('legacy_payment_id', id::text, 'legacy_raw_payload', raw_payload),
               created_at, updated_at, 1, created_at, updated_at
          FROM legacy
        """
    )
    op.execute("DELETE FROM payments WHERE status::text = 'refunded'")
    op.execute(
        """
        WITH numbered AS (
          SELECT id, row_number() OVER (PARTITION BY order_id ORDER BY created_at, id)::smallint AS n
            FROM shipments
        )
        UPDATE shipments s
           SET attempt_no = numbered.n,
               merchant_reference = 'BS' || substr(replace(s.id::text, '-', ''), 1, 28),
               provider_payload = coalesce(s.raw, '{}'::jsonb),
               provider_status = s.status::text,
               booked_at = CASE WHEN s.status::text IN ('booked','picked_up','in_transit','delivered','returned') THEN s.created_at ELSE NULL END,
               picked_up_at = CASE WHEN s.status::text IN ('picked_up','in_transit','delivered','returned') THEN s.updated_at ELSE NULL END,
               delivered_at = CASE WHEN s.status::text IN ('delivered','returned') THEN s.updated_at ELSE NULL END,
               returned_at = CASE WHEN s.status::text = 'returned' THEN s.updated_at ELSE NULL END,
               cancelled_at = CASE WHEN s.status::text = 'cancelled' THEN s.updated_at ELSE NULL END
          FROM numbered WHERE s.id = numbered.id
        """
    )
    op.execute(
        """
        UPDATE webhook_events
           SET kind = CASE
                 WHEN lower(provider) IN ('cod','bkash','nagad','sslcommerz') THEN 'payment'::webhook_kind
                 ELSE 'courier'::webhook_kind END,
               event_type = 'legacy.unknown',
               raw_body_sha256 = encode(digest(payload::text, 'sha256'), 'hex'),
               verification_status = 'legacy_unknown'::webhook_verification_status,
               verification_method = 'legacy_unverified',
               processing_status = CASE WHEN processed_at IS NULL THEN 'ignored'::webhook_processing_status ELSE 'processed'::webhook_processing_status END,
               next_attempt_at = created_at
        """
    )
    op.execute(
        """
        UPDATE orders
           SET payment_due_at = placed_at + interval '30 minutes'
         WHERE payment_method::text <> 'cod'
           AND payment_status::text NOT IN ('paid','refunded')
           AND payment_due_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO payments (
          id, order_id, provider, provider_txn_id, amount, currency, status,
          raw_payload, idempotency_key, created_at, updated_at
        )
        SELECT (provider_payload->>'legacy_payment_id')::uuid, order_id, provider,
               provider_refund_id, amount_poisha, currency,
               'refunded'::payment_record_status,
               coalesce(provider_payload->'legacy_raw_payload', '{}'::jsonb),
               idempotency_key, created_at, updated_at
          FROM payment_refunds
         WHERE provider_payload->>'legacy_payment_id' IS NOT NULL
        """
    )
    op.execute(
        "DELETE FROM payment_refunds WHERE provider_payload->>'legacy_payment_id' IS NOT NULL"
    )
    op.execute(
        """
        UPDATE payments SET attempt_no = NULL, merchant_reference = NULL,
          amount_poisha = NULL, provider_payload = '{}'::jsonb, initiated_at = NULL,
          terminal_at = NULL
        """
    )
    op.execute(
        """
        UPDATE shipments SET attempt_no = NULL, merchant_reference = NULL,
          provider_status = NULL, provider_payload = '{}'::jsonb, booked_at = NULL,
          picked_up_at = NULL, delivered_at = NULL, returned_at = NULL, cancelled_at = NULL
        """
    )
    op.execute(
        """
        UPDATE webhook_events SET kind = NULL, event_type = NULL, raw_body_sha256 = NULL,
          verification_status = NULL, verification_method = NULL, processing_status = NULL
        """
    )
    op.execute("UPDATE orders SET payment_due_at = NULL")
