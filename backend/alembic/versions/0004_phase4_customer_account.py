"""add phase 4 authenticated customer account schema

Revision ID: 0004_phase4
Revises: 0003_phase3
Create Date: 2026-11-07 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4"
down_revision: str | None = "0003_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.execute(sa.text("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"))
    op.alter_column(
        "users",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    op.add_column(
        "users",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(op.f("ck_users_revision_positive"), "users", "revision > 0")

    op.add_column(
        "addresses",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(op.f("ck_addresses_revision_positive"), "addresses", "revision > 0")
    op.create_index(
        "ix_addresses_user_default_created_id",
        "addresses",
        ["user_id", "is_default", "created_at", "id"],
    )

    op.create_index("ix_orders_user_placed_id", "orders", ["user_id", "placed_at", "id"])
    op.create_index(
        "ix_orders_user_status_placed_id",
        "orders",
        ["user_id", "status", "placed_at", "id"],
    )
    op.create_index("ix_order_items_order_product", "order_items", ["order_id", "product_id"])
    op.add_column("order_status_history", sa.Column("customer_note", sa.Text()))
    op.create_index(
        "ix_order_status_history_order_at_id",
        "order_status_history",
        ["order_id", "at", "id"],
    )
    op.create_index("ix_order_status_history_order_to", "order_status_history", ["order_id", "to"])

    op.add_column(
        "reviews",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("reviews", sa.Column("purchase_order_item_id", sa.UUID()))
    op.add_column("reviews", sa.Column("author_name_snapshot", sa.String(length=160)))
    op.add_column("reviews", sa.Column("moderated_at", sa.DateTime(timezone=True)))
    op.add_column("reviews", sa.Column("moderated_by_id", sa.UUID()))
    op.add_column("reviews", sa.Column("moderation_note", sa.Text()))
    op.add_column("reviews", sa.Column("rejection_reason", sa.String(length=500)))
    op.create_check_constraint(op.f("ck_reviews_revision_positive"), "reviews", "revision > 0")
    op.create_foreign_key(
        op.f("fk_reviews_purchase_order_item_id_order_items"),
        "reviews",
        "order_items",
        ["purchase_order_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_reviews_moderated_by_id_users"),
        "reviews",
        "users",
        ["moderated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            """
            UPDATE reviews AS review
               SET author_name_snapshot = "user".name
              FROM users AS "user"
             WHERE "user".id = review.user_id
               AND review.author_name_snapshot IS NULL
            """
        )
    )
    op.alter_column(
        "reviews",
        "author_name_snapshot",
        existing_type=sa.String(length=160),
        nullable=False,
    )

    # A legacy boolean is not evidence. Re-establish it only from an owned order item
    # with an immutable delivered/completed history event.
    op.execute(
        sa.text("UPDATE reviews SET is_verified_purchase = false, purchase_order_item_id = NULL")
    )
    op.execute(
        sa.text(
            """
            WITH eligible AS (
                SELECT review.id AS review_id,
                       item.id AS order_item_id,
                       row_number() OVER (
                           PARTITION BY review.id
                           ORDER BY delivered.delivered_at DESC, item.created_at DESC, item.id DESC
                       ) AS position
                  FROM reviews AS review
                  JOIN orders AS customer_order
                    ON customer_order.user_id = review.user_id
                  JOIN order_items AS item
                    ON item.order_id = customer_order.id
                   AND item.product_id = review.product_id
                  JOIN LATERAL (
                      SELECT max(history.at) AS delivered_at
                        FROM order_status_history AS history
                       WHERE history.order_id = customer_order.id
                         AND history."to" IN ('delivered', 'completed')
                  ) AS delivered ON delivered.delivered_at IS NOT NULL
            )
            UPDATE reviews AS review
               SET purchase_order_item_id = eligible.order_item_id,
                   is_verified_purchase = true
              FROM eligible
             WHERE review.id = eligible.review_id
               AND eligible.position = 1
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_reviews_verified_purchase_has_lineage"),
        "reviews",
        "NOT is_verified_purchase OR purchase_order_item_id IS NOT NULL",
    )
    op.create_index("ix_reviews_user_updated_id", "reviews", ["user_id", "updated_at", "id"])

    op.create_table(
        "review_photos",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("review_id", sa.UUID()),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("public_id", sa.String(length=255), nullable=False),
        sa.Column("provider_asset_id", sa.String(length=255)),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("format", sa.String(length=16)),
        sa.Column("alt_text", sa.String(length=255)),
        sa.Column("sort_order", sa.SmallInteger()),
        sa.Column(
            "state", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("signature_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("signature_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("attached_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_after", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 5242880",
            name=op.f("ck_review_photos_byte_size_range"),
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name=op.f("ck_review_photos_mime_type_allowed"),
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'ready', 'attached', 'delete_pending', 'deleted')",
            name=op.f("ck_review_photos_state_allowed"),
        ),
        sa.CheckConstraint(
            "sort_order IS NULL OR (sort_order >= 0 AND sort_order < 5)",
            name=op.f("ck_review_photos_sort_order_range"),
        ),
        sa.CheckConstraint(
            "width IS NULL OR width > 0",
            name=op.f("ck_review_photos_width_positive"),
        ),
        sa.CheckConstraint(
            "height IS NULL OR height > 0",
            name=op.f("ck_review_photos_height_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["reviews.id"],
            name=op.f("fk_review_photos_review_id_reviews"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_review_photos_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_photos")),
        sa.UniqueConstraint("provider", "public_id", name="uq_review_photos_provider_public_id"),
    )
    op.create_index(
        "uq_review_photos_provider_asset_id",
        "review_photos",
        ["provider", "provider_asset_id"],
        unique=True,
        postgresql_where=sa.text("provider_asset_id IS NOT NULL"),
    )
    op.create_index(
        "uq_review_photos_review_sort",
        "review_photos",
        ["review_id", "sort_order"],
        unique=True,
        postgresql_where=sa.text("review_id IS NOT NULL"),
    )
    op.create_index(
        "ix_review_photos_user_state_created_id",
        "review_photos",
        ["user_id", "state", "created_at", "id"],
    )
    op.create_index(
        "ix_review_photos_cleanup",
        "review_photos",
        ["state", "cleanup_after"],
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )

    op.add_column(
        "coupons",
        sa.Column("is_discoverable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "ix_coupons_discoverable_active_dates_id",
        "coupons",
        ["is_discoverable", "is_active", "starts_at", "ends_at", "id"],
    )
    op.create_index(
        "ix_coupon_redemptions_user_created_id",
        "coupon_redemptions",
        ["user_id", "created_at", "id"],
    )

    op.create_table(
        "support_ticket_number_counters",
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "year >= 2020 AND year <= 9999",
            name=op.f("ck_support_ticket_number_counters_year_range"),
        ),
        sa.CheckConstraint(
            "next_value >= 1 AND next_value <= 1000000",
            name=op.f("ck_support_ticket_number_counters_next_value_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_ticket_number_counters")),
        sa.UniqueConstraint("year", name=op.f("uq_support_ticket_number_counters_year")),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO support_ticket_number_counters (id, year, next_value)
            SELECT gen_random_uuid(),
                   substring(number FROM 8 FOR 4)::smallint,
                   LEAST(max(right(number, 6)::integer) + 1, 1000000)
              FROM support_tickets
             WHERE number ~ '^BJ-SUP-[0-9]{4}-[0-9]{6}$'
             GROUP BY substring(number FROM 8 FOR 4)::smallint
            ON CONFLICT (year) DO UPDATE
               SET next_value = GREATEST(
                   support_ticket_number_counters.next_value,
                   EXCLUDED.next_value
               )
            """
        )
    )
    op.add_column(
        "support_tickets",
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column("support_tickets", sa.Column("last_message_at", sa.DateTime(timezone=True)))
    op.add_column("support_tickets", sa.Column("customer_last_read_at", sa.DateTime(timezone=True)))
    op.add_column("support_tickets", sa.Column("admin_last_read_at", sa.DateTime(timezone=True)))
    op.execute(
        sa.text(
            """
            UPDATE support_tickets AS ticket
               SET last_message_at = coalesce(
                   (
                       SELECT max(message.created_at)
                         FROM support_messages AS message
                        WHERE message.ticket_id = ticket.id
                   ),
                   ticket.created_at
                )
            """
        )
    )
    op.alter_column(
        "support_tickets",
        "last_message_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_support_tickets_revision_positive"), "support_tickets", "revision > 0"
    )
    op.create_index(
        "ix_support_tickets_user_last_message_id",
        "support_tickets",
        ["user_id", "last_message_at", "id"],
    )
    op.create_index(
        "ix_support_tickets_user_status_last_message_id",
        "support_tickets",
        ["user_id", "status", "last_message_at", "id"],
    )
    op.add_column(
        "support_messages",
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "ix_support_messages_ticket_created_id",
        "support_messages",
        ["ticket_id", "created_at", "id"],
    )

    op.add_column("idempotency_records", sa.Column("resource_kind", sa.String(length=40)))
    op.add_column("idempotency_records", sa.Column("resource_id", sa.UUID()))
    op.execute(
        sa.text(
            """
            UPDATE idempotency_records
               SET resource_kind = 'order', resource_id = order_id
             WHERE order_id IS NOT NULL
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        "(resource_kind IS NULL) = (resource_id IS NULL)",
    )
    op.create_index(
        "ix_idempotency_records_resource",
        "idempotency_records",
        ["resource_kind", "resource_id"],
    )

    op.create_index(
        "ix_wishlist_items_user_created_id",
        "wishlist_items",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM support_messages WHERE is_internal) THEN
                    RAISE EXCEPTION
                        'cannot downgrade 0004: internal support messages would become public';
                END IF;
                IF EXISTS (SELECT 1 FROM review_photos) THEN
                    RAISE EXCEPTION
                        'cannot downgrade 0004: structured review photos require provider cleanup';
                END IF;
            END $$;
            """
        )
    )
    op.drop_index("ix_wishlist_items_user_created_id", table_name="wishlist_items")

    op.drop_index("ix_idempotency_records_resource", table_name="idempotency_records")
    op.drop_constraint(
        op.f("ck_idempotency_records_resource_pair_complete"),
        "idempotency_records",
        type_="check",
    )
    op.drop_column("idempotency_records", "resource_id")
    op.drop_column("idempotency_records", "resource_kind")

    op.drop_index("ix_support_messages_ticket_created_id", table_name="support_messages")
    op.drop_column("support_messages", "is_internal")
    op.drop_index("ix_support_tickets_user_status_last_message_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_last_message_id", table_name="support_tickets")
    op.drop_constraint(
        op.f("ck_support_tickets_revision_positive"), "support_tickets", type_="check"
    )
    op.drop_column("support_tickets", "admin_last_read_at")
    op.drop_column("support_tickets", "customer_last_read_at")
    op.drop_column("support_tickets", "last_message_at")
    op.drop_column("support_tickets", "revision")
    op.drop_table("support_ticket_number_counters")

    op.drop_index("ix_coupon_redemptions_user_created_id", table_name="coupon_redemptions")
    op.drop_index("ix_coupons_discoverable_active_dates_id", table_name="coupons")
    op.drop_column("coupons", "is_discoverable")

    op.drop_index(
        "ix_review_photos_cleanup",
        table_name="review_photos",
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )
    op.drop_index("ix_review_photos_user_state_created_id", table_name="review_photos")
    op.drop_index(
        "uq_review_photos_review_sort",
        table_name="review_photos",
        postgresql_where=sa.text("review_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_review_photos_provider_asset_id",
        table_name="review_photos",
        postgresql_where=sa.text("provider_asset_id IS NOT NULL"),
    )
    op.drop_table("review_photos")

    op.drop_index("ix_reviews_user_updated_id", table_name="reviews")
    op.drop_constraint(op.f("ck_reviews_verified_purchase_has_lineage"), "reviews", type_="check")
    op.drop_constraint(op.f("fk_reviews_moderated_by_id_users"), "reviews", type_="foreignkey")
    op.drop_constraint(
        op.f("fk_reviews_purchase_order_item_id_order_items"),
        "reviews",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("ck_reviews_revision_positive"), "reviews", type_="check")
    op.drop_column("reviews", "rejection_reason")
    op.drop_column("reviews", "moderation_note")
    op.drop_column("reviews", "moderated_by_id")
    op.drop_column("reviews", "moderated_at")
    op.drop_column("reviews", "author_name_snapshot")
    op.drop_column("reviews", "purchase_order_item_id")
    op.drop_column("reviews", "revision")

    op.drop_index("ix_order_status_history_order_to", table_name="order_status_history")
    op.drop_index("ix_order_status_history_order_at_id", table_name="order_status_history")
    op.drop_column("order_status_history", "customer_note")
    op.drop_index("ix_order_items_order_product", table_name="order_items")
    op.drop_index("ix_orders_user_status_placed_id", table_name="orders")
    op.drop_index("ix_orders_user_placed_id", table_name="orders")

    op.drop_index("ix_addresses_user_default_created_id", table_name="addresses")
    op.drop_constraint(op.f("ck_addresses_revision_positive"), "addresses", type_="check")
    op.drop_column("addresses", "revision")

    op.drop_constraint(op.f("ck_users_revision_positive"), "users", type_="check")
    op.drop_column("users", "revision")
    op.drop_column("users", "updated_at")
