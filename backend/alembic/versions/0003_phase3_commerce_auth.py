"""add phase 3 commerce and authentication schema

Revision ID: 0003_phase3
Revises: 0002_phase2
Create Date: 2026-11-06 15:30:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3"
down_revision: str | None = "0002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                collision text;
            BEGIN
                SELECT lower(email)
                  INTO collision
                  FROM users
                 WHERE email IS NOT NULL
                 GROUP BY lower(email)
                HAVING count(*) > 1
                 LIMIT 1;
                IF collision IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Phase 3 migration blocked: users.email values collide case-insensitively for "%"',
                        collision
                        USING HINT = 'Merge or rename the duplicate user emails, then rerun the migration.';
                END IF;
            END $$;
            """
        )
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                collision text;
            BEGIN
                SELECT upper(btrim(code))
                  INTO collision
                  FROM coupons
                 GROUP BY upper(btrim(code))
                HAVING count(*) > 1
                 LIMIT 1;
                IF collision IS NOT NULL THEN
                    RAISE EXCEPTION
                        'Phase 3 migration blocked: coupons.code values collide case-insensitively for "%"',
                        collision
                        USING HINT = 'Merge or rename the duplicate coupon codes, then rerun the migration.';
                END IF;
            END $$;
            """
        )
    )
    op.execute(sa.text("UPDATE coupons SET code = upper(btrim(code))"))
    op.create_check_constraint(
        op.f("ck_coupons_code_normalized"),
        "coupons",
        "code = upper(btrim(code)) AND code <> ''",
    )
    op.create_index(
        "uq_coupons_code_upper",
        "coupons",
        [sa.text("upper(code)")],
        unique=True,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("refresh_jti_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent_hash", sa.CHAR(length=64)),
        sa.Column("ip_prefix_hash", sa.CHAR(length=64)),
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
            "expires_at > created_at", name=op.f("ck_auth_sessions_expiry_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("refresh_jti_hash", name=op.f("uq_auth_sessions_refresh_jti_hash")),
    )
    op.create_index(
        "ix_auth_sessions_active_expiry",
        "auth_sessions",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_auth_sessions_family", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_user_expires", "auth_sessions", ["user_id", "expires_at"])

    op.drop_constraint("uq_carts_guest_token", "carts", type_="unique")
    op.add_column("carts", sa.Column("coupon_id", sa.UUID()))
    op.add_column("carts", sa.Column("shipping_district_id", sa.UUID()))
    op.add_column(
        "carts",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_carts_coupon_id_coupons"),
        "carts",
        "coupons",
        ["coupon_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_carts_shipping_district_id_geo_districts"),
        "carts",
        "geo_districts",
        ["shipping_district_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(op.f("ck_cart_items_quantity_positive"), "cart_items", type_="check")
    op.create_check_constraint(
        op.f("ck_cart_items_quantity_range"),
        "cart_items",
        "quantity >= 1 AND quantity <= 99",
    )

    op.drop_constraint("uq_orders_idempotency_key", "orders", type_="unique")
    op.alter_column("orders", "idempotency_key", existing_type=sa.String(128), nullable=True)
    op.add_column("orders", sa.Column("source_cart_id", sa.UUID()))
    op.create_foreign_key(
        op.f("fk_orders_source_cart_id_carts"),
        "orders",
        "carts",
        ["source_cart_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(op.f("uq_orders_source_cart_id"), "orders", ["source_cart_id"])

    op.add_column("order_items", sa.Column("flash_sale_item_id", sa.UUID()))
    op.create_foreign_key(
        op.f("fk_order_items_flash_sale_item_id_flash_sale_items"),
        "order_items",
        "flash_sale_items",
        ["flash_sale_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_order_items_flash_sale_item", "order_items", ["flash_sale_item_id"])

    op.create_table(
        "coupon_redemptions",
        sa.Column("coupon_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("code_snapshot", sa.String(length=64), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["coupon_id"],
            ["coupons.id"],
            name=op.f("fk_coupon_redemptions_coupon_id_coupons"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_coupon_redemptions_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_coupon_redemptions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coupon_redemptions")),
        sa.UniqueConstraint("order_id", name=op.f("uq_coupon_redemptions_order_id")),
    )
    op.create_index(
        "ix_coupon_redemptions_coupon_user_released",
        "coupon_redemptions",
        ["coupon_id", "user_id", "released_at"],
    )
    op.create_index(
        "ix_coupon_redemptions_user_created",
        "coupon_redemptions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("endpoint", sa.String(length=160), nullable=False),
        sa.Column("scope_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("order_id", sa.UUID()),
        sa.Column("response_status", sa.SmallInteger()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_idempotency_records_expiry_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_idempotency_records_order_id_orders"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
        sa.UniqueConstraint(
            "endpoint",
            "scope_hash",
            "idempotency_key",
            name=op.f("uq_idempotency_records_endpoint_scope_hash_idempotency_key"),
        ),
    )
    op.create_index("ix_idempotency_records_expiry", "idempotency_records", ["expires_at"])
    op.create_index("ix_idempotency_records_order", "idempotency_records", ["order_id"])

    op.create_table(
        "order_number_counters",
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "next_value >= 1 AND next_value <= 1000000",
            name=op.f("ck_order_number_counters_next_value_range"),
        ),
        sa.CheckConstraint(
            "year >= 2020 AND year <= 9999",
            name=op.f("ck_order_number_counters_year_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_number_counters")),
        sa.UniqueConstraint("year", name=op.f("uq_order_number_counters_year")),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO order_number_counters (id, year, next_value)
            SELECT gen_random_uuid(),
                   substring(number FROM 4 FOR 4)::smallint,
                   LEAST(max(right(number, 6)::integer) + 1, 1000000)
              FROM orders
             WHERE number ~ '^BJ-[0-9]{4}-[0-9]{6}$'
             GROUP BY substring(number FROM 4 FOR 4)::smallint
            ON CONFLICT (year) DO UPDATE
               SET next_value = GREATEST(
                   order_number_counters.next_value,
                   EXCLUDED.next_value
               )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("order_number_counters")
    op.drop_index("ix_idempotency_records_order", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_expiry", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_coupon_redemptions_user_created", table_name="coupon_redemptions")
    op.drop_index(
        "ix_coupon_redemptions_coupon_user_released",
        table_name="coupon_redemptions",
    )
    op.drop_table("coupon_redemptions")

    op.drop_index("uq_coupons_code_upper", table_name="coupons")
    op.drop_constraint(op.f("ck_coupons_code_normalized"), "coupons", type_="check")

    op.drop_index("ix_order_items_flash_sale_item", table_name="order_items")
    op.drop_constraint(
        op.f("fk_order_items_flash_sale_item_id_flash_sale_items"),
        "order_items",
        type_="foreignkey",
    )
    op.drop_column("order_items", "flash_sale_item_id")

    op.drop_constraint(op.f("uq_orders_source_cart_id"), "orders", type_="unique")
    op.drop_constraint(op.f("fk_orders_source_cart_id_carts"), "orders", type_="foreignkey")
    op.drop_column("orders", "source_cart_id")
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (PARTITION BY idempotency_key ORDER BY created_at, id) AS position
                FROM orders
            )
            UPDATE orders AS target
               SET idempotency_key = 'legacy-' || target.id::text
              FROM ranked
             WHERE target.id = ranked.id
               AND (target.idempotency_key IS NULL OR ranked.position > 1)
            """
        )
    )
    op.alter_column("orders", "idempotency_key", existing_type=sa.String(128), nullable=False)
    op.create_unique_constraint("uq_orders_idempotency_key", "orders", ["idempotency_key"])

    op.drop_constraint(op.f("ck_cart_items_quantity_range"), "cart_items", type_="check")
    op.create_check_constraint(
        op.f("ck_cart_items_quantity_positive"), "cart_items", "quantity > 0"
    )
    op.drop_constraint(
        op.f("fk_carts_shipping_district_id_geo_districts"),
        "carts",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("fk_carts_coupon_id_coupons"), "carts", type_="foreignkey")
    op.drop_column("carts", "version")
    op.drop_column("carts", "shipping_district_id")
    op.drop_column("carts", "coupon_id")
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (PARTITION BY guest_token ORDER BY created_at DESC, id) AS position
                FROM carts
                WHERE guest_token IS NOT NULL
            )
            UPDATE carts AS target
               SET guest_token = gen_random_uuid()
              FROM ranked
             WHERE target.id = ranked.id AND ranked.position > 1
            """
        )
    )
    op.create_unique_constraint("uq_carts_guest_token", "carts", ["guest_token"])

    op.drop_index("ix_auth_sessions_user_expires", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_family", table_name="auth_sessions")
    op.drop_index(
        "ix_auth_sessions_active_expiry",
        table_name="auth_sessions",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_table("auth_sessions")

    op.drop_index(
        "uq_users_email_lower",
        table_name="users",
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "is_active")
