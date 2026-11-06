"""harden phase 4 correctness and downgrade safety

Revision ID: 0005_phase4_p1
Revises: 0004_phase4
Create Date: 2026-11-07 00:30:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase4_p1"
down_revision: str | None = "0004_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUPPORT_NUMBER = r"^BJ-SUP-[0-9]{4}-[0-9]{6}$"


def upgrade() -> None:
    # Every non-empty address book must have exactly one deterministic default.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT address.id,
                       row_number() OVER (
                           PARTITION BY address.user_id
                           ORDER BY address.created_at DESC, address.id DESC
                       ) AS position
                  FROM addresses AS address
                 WHERE NOT EXISTS (
                     SELECT 1
                       FROM addresses AS current_default
                      WHERE current_default.user_id = address.user_id
                        AND current_default.is_default
                 )
            )
            UPDATE addresses AS address
               SET is_default = true
              FROM ranked
             WHERE address.id = ranked.id
               AND ranked.position = 1
            """
        )
    )

    op.drop_index(
        "ix_review_photos_cleanup",
        table_name="review_photos",
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )
    op.create_index(
        "ix_review_photos_cleanup",
        "review_photos",
        ["state", "cleanup_after"],
        postgresql_where=sa.text("state IN ('pending', 'ready', 'delete_pending')"),
    )

    # Preserve valid human numbers, then allocate deterministic suffixes to all legacy rows.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    WITH valid_max AS (
                        SELECT substring(number FROM 8 FOR 4)::integer AS year,
                               max(right(number, 6)::integer) AS maximum
                          FROM support_tickets
                         WHERE number ~ '{_SUPPORT_NUMBER}'
                         GROUP BY substring(number FROM 8 FOR 4)::integer
                    ),
                    invalid_counts AS (
                        SELECT greatest(
                                   2020,
                                   extract(year FROM created_at AT TIME ZONE 'Asia/Dhaka')::integer
                               ) AS year,
                               count(*) AS total
                          FROM support_tickets
                         WHERE number !~ '{_SUPPORT_NUMBER}'
                         GROUP BY 1
                    )
                    SELECT 1
                      FROM invalid_counts
                      LEFT JOIN valid_max USING (year)
                     WHERE coalesce(valid_max.maximum, 0) + invalid_counts.total > 999999
                ) THEN
                    RAISE EXCEPTION 'legacy support ticket sequence exceeds six digits';
                END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH valid_max AS (
                SELECT substring(number FROM 8 FOR 4)::integer AS year,
                       max(right(number, 6)::integer) AS maximum
                  FROM support_tickets
                 WHERE number ~ '{_SUPPORT_NUMBER}'
                 GROUP BY substring(number FROM 8 FOR 4)::integer
            ),
            invalid AS (
                SELECT ticket.id,
                       greatest(
                           2020,
                           extract(year FROM ticket.created_at AT TIME ZONE 'Asia/Dhaka')::integer
                       ) AS year,
                       row_number() OVER (
                           PARTITION BY greatest(
                               2020,
                               extract(year FROM ticket.created_at AT TIME ZONE 'Asia/Dhaka')::integer
                           )
                           ORDER BY ticket.created_at, ticket.id
                       ) AS position
                  FROM support_tickets AS ticket
                 WHERE ticket.number !~ '{_SUPPORT_NUMBER}'
            )
            UPDATE support_tickets AS ticket
               SET number = format(
                   'BJ-SUP-%s-%s',
                   invalid.year,
                   lpad(
                       (coalesce(valid_max.maximum, 0) + invalid.position)::text,
                       6,
                       '0'
                   )
               )
              FROM invalid
              LEFT JOIN valid_max USING (year)
             WHERE ticket.id = invalid.id
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_support_tickets_number_format"),
        "support_tickets",
        f"number ~ '{_SUPPORT_NUMBER}'",
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO support_ticket_number_counters (id, year, next_value)
            SELECT gen_random_uuid(),
                   substring(number FROM 8 FOR 4)::smallint,
                   LEAST(max(right(number, 6)::integer) + 1, 1000000)
              FROM support_tickets
             WHERE number ~ '{_SUPPORT_NUMBER}'
               AND substring(number FROM 8 FOR 4)::integer >= 2020
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
        "support_tickets", sa.Column("public_last_message_at", sa.DateTime(timezone=True))
    )
    op.execute(
        sa.text(
            """
            UPDATE support_tickets AS ticket
               SET public_last_message_at = coalesce(
                   (
                       SELECT max(message.created_at)
                         FROM support_messages AS message
                        WHERE message.ticket_id = ticket.id
                          AND NOT message.is_internal
                   ),
                   ticket.created_at
               )
            """
        )
    )
    op.alter_column(
        "support_tickets",
        "public_last_message_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    op.drop_index("ix_support_tickets_user_status_last_message_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_user_last_message_id", table_name="support_tickets")
    op.create_index(
        "ix_support_tickets_user_public_last_message_id",
        "support_tickets",
        ["user_id", "public_last_message_at", "id"],
    )
    op.create_index(
        "ix_support_tickets_user_status_public_last_message_id",
        "support_tickets",
        ["user_id", "status", "public_last_message_at", "id"],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM support_messages WHERE is_internal) THEN
                    RAISE EXCEPTION
                        'cannot downgrade 0005: internal support messages would lose isolation';
                END IF;
                IF EXISTS (SELECT 1 FROM review_photos) THEN
                    RAISE EXCEPTION
                        'cannot downgrade 0005: structured review photos require provider cleanup';
                END IF;
            END $$;
            """
        )
    )

    op.drop_index(
        "ix_support_tickets_user_status_public_last_message_id",
        table_name="support_tickets",
    )
    op.drop_index("ix_support_tickets_user_public_last_message_id", table_name="support_tickets")
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
    op.drop_column("support_tickets", "public_last_message_at")
    op.drop_constraint(op.f("ck_support_tickets_number_format"), "support_tickets", type_="check")

    op.drop_index(
        "ix_review_photos_cleanup",
        table_name="review_photos",
        postgresql_where=sa.text("state IN ('pending', 'ready', 'delete_pending')"),
    )
    op.create_index(
        "ix_review_photos_cleanup",
        "review_photos",
        ["state", "cleanup_after"],
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )
