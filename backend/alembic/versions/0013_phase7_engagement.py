"""add encrypted Phase 7 engagement domains

Revision ID: 0013_phase7_engagement
Revises: 0012_phase6_contract
Create Date: 2026-11-07 18:10:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_phase7_engagement"
down_revision: str | None = "0012_phase6_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _id() -> sa.Column:
    return sa.Column("id", UUID, nullable=False)


def _created() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _updated() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.execute("ALTER TYPE outbox_status ADD VALUE IF NOT EXISTS 'dead_letter'")

    op.create_table(
        "consent_events",
        _id(),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("subject_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column("ip_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.CHAR(length=64), nullable=True),
        _created(),
        sa.CheckConstraint(
            "subject_kind IN ('guest','user','newsletter')",
            name=op.f("ck_consent_events_subject_kind_allowed"),
        ),
        sa.CheckConstraint(
            "purpose IN ('analytics','advertising','newsletter','abandoned_cart_email','abandoned_cart_sms')",
            name=op.f("ck_consent_events_purpose_allowed"),
        ),
        sa.CheckConstraint(
            "action IN ('grant','withdraw')", name=op.f("ck_consent_events_action_allowed")
        ),
        sa.CheckConstraint("locale IN ('bn','en')", name=op.f("ck_consent_events_locale_allowed")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_consent_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_events")),
    )
    op.create_index(
        "ix_consent_events_subject_purpose_created",
        "consent_events",
        ["subject_hash", "purpose", "created_at"],
    )
    op.create_index("ix_consent_events_created", "consent_events", ["created_at"])
    op.execute(
        """
        CREATE FUNCTION phase7_refuse_consent_event_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'consent_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER consent_events_append_only
        BEFORE UPDATE OR DELETE ON consent_events
        FOR EACH ROW EXECUTE FUNCTION phase7_refuse_consent_event_mutation();
        """
    )

    op.create_table(
        "notification_deliveries",
        _id(),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("channel", sa.String(length=12), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("template_version", sa.SmallInteger(), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("order_id", UUID, nullable=True),
        sa.Column("cart_id", UUID, nullable=True),
        sa.Column("recipient_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("recipient_masked", sa.String(length=340), nullable=False),
        sa.Column("recipient_key_id", sa.String(length=64), nullable=True),
        sa.Column("recipient_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("recipient_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("context_key_id", sa.String(length=64), nullable=True),
        sa.Column("context_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("context_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("consent_event_id", UUID, nullable=True),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("50"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "category IN ('security','transactional','marketing')",
            name=op.f("ck_notification_deliveries_category_allowed"),
        ),
        sa.CheckConstraint(
            "channel IN ('email','sms')", name=op.f("ck_notification_deliveries_channel_allowed")
        ),
        sa.CheckConstraint(
            "locale IN ('bn','en')", name=op.f("ck_notification_deliveries_locale_allowed")
        ),
        sa.CheckConstraint(
            "status IN ('queued','processing','retry','accepted','rejected','unknown','dead_letter','cancelled','expired','suppressed')",
            name=op.f("ck_notification_deliveries_status_allowed"),
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 100",
            name=op.f("ck_notification_deliveries_priority_range"),
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts",
            name=op.f("ck_notification_deliveries_attempts_range"),
        ),
        sa.CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 20",
            name=op.f("ck_notification_deliveries_max_attempts_range"),
        ),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_notification_deliveries_revision_positive")
        ),
        sa.CheckConstraint(
            "num_nonnulls(recipient_key_id, recipient_nonce, recipient_ciphertext) IN (0,3)",
            name=op.f("ck_notification_deliveries_recipient_envelope_complete"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(context_key_id, context_nonce, context_ciphertext) IN (0,3)",
            name=op.f("ck_notification_deliveries_context_envelope_complete"),
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > created_at",
            name=op.f("ck_notification_deliveries_expiry_after_creation"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["consent_event_id"], ["consent_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_deliveries_dedupe_key"),
    )
    op.create_index(
        "ix_notification_deliveries_claim",
        "notification_deliveries",
        ["status", "next_attempt_at", "priority", "created_at"],
        postgresql_where=sa.text("status IN ('queued','retry','processing')"),
    )
    op.create_index(
        "ix_notification_deliveries_user_created",
        "notification_deliveries",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notification_deliveries_order_created",
        "notification_deliveries",
        ["order_id", "created_at"],
    )
    op.create_index(
        "ix_notification_deliveries_recipient_hash", "notification_deliveries", ["recipient_hash"]
    )
    op.create_index(
        "ix_notification_deliveries_terminal", "notification_deliveries", ["terminal_at"]
    )

    op.create_table(
        "notification_attempts",
        _id(),
        sa.Column("delivery_id", UUID, nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("response_class", sa.String(length=80), nullable=True),
        sa.Column("response_code", sa.String(length=80), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        _created(),
        sa.CheckConstraint(
            "attempt_no > 0", name=op.f("ck_notification_attempts_attempt_no_positive")
        ),
        sa.CheckConstraint(
            "outcome IN ('accepted','retryable','rejected','unknown')",
            name=op.f("ck_notification_attempts_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "latency_ms >= 0", name=op.f("ck_notification_attempts_latency_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["delivery_id"], ["notification_deliveries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_attempts")),
        sa.UniqueConstraint(
            "delivery_id", "attempt_no", name="uq_notification_attempts_delivery_attempt"
        ),
    )
    op.create_index(
        "ix_notification_attempts_delivery_created",
        "notification_attempts",
        ["delivery_id", "created_at"],
    )
    op.create_index("ix_notification_attempts_created", "notification_attempts", ["created_at"])

    op.create_table(
        "communication_preferences",
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("locale", sa.String(length=2), server_default=sa.text("'bn'"), nullable=False),
        sa.Column("order_email", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("order_sms", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "abandoned_cart_email", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "abandoned_cart_sms", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "locale IN ('bn','en')", name=op.f("ck_communication_preferences_locale_allowed")
        ),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_communication_preferences_revision_positive")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_communication_preferences")),
    )

    op.create_table(
        "newsletter_subscriptions",
        _id(),
        sa.Column("email_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("email_key_id", sa.String(length=64), nullable=True),
        sa.Column("email_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("email_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("masked_email", sa.String(length=340), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("confirmation_token_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column(
            "consented_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "locale IN ('bn','en')", name=op.f("ck_newsletter_subscriptions_locale_allowed")
        ),
        sa.CheckConstraint(
            "status IN ('pending','subscribed','unsubscribed','suppressed')",
            name=op.f("ck_newsletter_subscriptions_status_allowed"),
        ),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_newsletter_subscriptions_revision_positive")
        ),
        sa.CheckConstraint(
            "num_nonnulls(email_key_id, email_nonce, email_ciphertext) IN (0,3)",
            name=op.f("ck_newsletter_subscriptions_email_envelope_complete"),
        ),
        sa.CheckConstraint(
            "confirmation_expires_at IS NULL OR confirmation_token_hash IS NOT NULL",
            name=op.f("ck_newsletter_subscriptions_confirmation_expiry_requires_token"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_newsletter_subscriptions")),
        sa.UniqueConstraint("email_hash", name="uq_newsletter_subscriptions_email_hash"),
    )
    op.create_index(
        "ix_newsletter_subscriptions_status", "newsletter_subscriptions", ["status", "updated_at"]
    )
    op.create_index(
        "ix_newsletter_subscriptions_token_expiry",
        "newsletter_subscriptions",
        ["confirmation_expires_at"],
    )
    op.create_index("ix_newsletter_subscriptions_user", "newsletter_subscriptions", ["user_id"])

    op.create_table(
        "cart_reminder_state",
        _id(),
        sa.Column("cart_id", UUID, nullable=False),
        sa.Column("channel", sa.String(length=12), nullable=False),
        sa.Column("cart_version_queued", sa.Integer(), nullable=True),
        sa.Column("cart_version_sent", sa.Integer(), nullable=True),
        sa.Column("reminder_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivery_id", UUID, nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppression_reason", sa.String(length=120), nullable=True),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "channel IN ('email','sms')", name=op.f("ck_cart_reminder_state_channel_allowed")
        ),
        sa.CheckConstraint(
            "reminder_count >= 0", name=op.f("ck_cart_reminder_state_reminder_count_nonnegative")
        ),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["last_delivery_id"], ["notification_deliveries.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cart_reminder_state")),
        sa.UniqueConstraint("cart_id", "channel", name="uq_cart_reminder_state_cart_channel"),
    )
    op.create_index(
        "ix_cart_reminder_state_eligibility", "cart_reminder_state", ["next_eligible_at", "cart_id"]
    )
    op.create_index("ix_cart_reminder_state_delivery", "cart_reminder_state", ["last_delivery_id"])

    op.create_table(
        "analytics_events",
        sa.Column("event_id", UUID, nullable=False),
        sa.Column("event_name", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("order_id", UUID, nullable=True),
        sa.Column("product_id", UUID, nullable=True),
        sa.Column("variant_id", UUID, nullable=True),
        sa.Column("commerce_data", JSONB, nullable=False),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("advertising_consent_event_id", UUID, nullable=True),
        sa.Column("email_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("phone_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("context_key_id", sa.String(length=64), nullable=True),
        sa.Column("context_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("context_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("context_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "capi_status",
            sa.String(length=24),
            server_default=sa.text("'not_applicable'"),
            nullable=False,
        ),
        sa.Column("capi_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("capi_max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column(
            "capi_next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("capi_leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capi_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capi_lease_owner", sa.String(length=128), nullable=True),
        sa.Column("provider_event_id", sa.String(length=255), nullable=True),
        sa.Column("capi_last_error", sa.String(length=500), nullable=True),
        sa.Column("capi_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "event_name IN ('view_item','add_to_cart','begin_checkout','purchase')",
            name=op.f("ck_analytics_events_event_name_allowed"),
        ),
        sa.CheckConstraint(
            "source IN ('browser','server')", name=op.f("ck_analytics_events_source_allowed")
        ),
        sa.CheckConstraint(
            "capi_status IN ('not_applicable','queued','processing','retry','accepted','dead_letter','suppressed')",
            name=op.f("ck_analytics_events_capi_status_allowed"),
        ),
        sa.CheckConstraint(
            "capi_attempts >= 0 AND capi_attempts <= capi_max_attempts",
            name=op.f("ck_analytics_events_capi_attempts_range"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_analytics_events_revision_positive")),
        sa.CheckConstraint(
            "num_nonnulls(context_key_id, context_nonce, context_ciphertext) IN (0,3)",
            name=op.f("ck_analytics_events_context_envelope_complete"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["advertising_consent_event_id"], ["consent_events.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_analytics_events")),
    )
    op.create_index(
        "uq_analytics_events_purchase_order",
        "analytics_events",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("event_name = 'purchase'"),
    )
    op.create_index(
        "ix_analytics_events_capi_claim",
        "analytics_events",
        ["capi_status", "capi_next_attempt_at", "created_at"],
        postgresql_where=sa.text("capi_status IN ('queued','retry','processing')"),
    )
    op.create_index(
        "ix_analytics_events_context_expiry", "analytics_events", ["context_expires_at"]
    )

    op.create_table(
        "assistant_sessions",
        _id(),
        sa.Column("owner_kind", sa.String(length=12), nullable=False),
        sa.Column("owner_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column("disclosure_version", sa.String(length=64), nullable=False),
        sa.Column("message_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("handoff_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=False),
        _created(),
        _updated(),
        sa.CheckConstraint(
            "owner_kind IN ('guest','user')", name=op.f("ck_assistant_sessions_owner_kind_allowed")
        ),
        sa.CheckConstraint(
            "locale IN ('bn','en')", name=op.f("ck_assistant_sessions_locale_allowed")
        ),
        sa.CheckConstraint(
            "status IN ('active','deleted','expired')",
            name=op.f("ck_assistant_sessions_status_allowed"),
        ),
        sa.CheckConstraint(
            "message_count >= 0", name=op.f("ck_assistant_sessions_message_count_nonnegative")
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name=op.f("ck_assistant_sessions_token_counts_nonnegative"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_assistant_sessions_expiry_after_creation")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_sessions")),
    )
    op.create_index(
        "ix_assistant_sessions_owner_created", "assistant_sessions", ["owner_hash", "created_at"]
    )
    op.create_index("ix_assistant_sessions_cleanup", "assistant_sessions", ["delete_after"])

    op.create_table(
        "assistant_messages",
        _id(),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("client_message_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("body_key_id", sa.String(length=64), nullable=False),
        sa.Column("body_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("body_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("citations", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("actions", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        _created(),
        sa.CheckConstraint(
            "role IN ('user','assistant')", name=op.f("ck_assistant_messages_role_allowed")
        ),
        sa.CheckConstraint(
            "num_nonnulls(body_key_id, body_nonce, body_ciphertext) = 3",
            name=op.f("ck_assistant_messages_body_envelope_complete"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["assistant_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_messages")),
        sa.UniqueConstraint(
            "session_id", "client_message_id", name="uq_assistant_messages_session_client"
        ),
    )
    op.create_index(
        "ix_assistant_messages_session_created", "assistant_messages", ["session_id", "created_at"]
    )

    op.create_table(
        "assistant_order_grants",
        _id(),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("phone_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created(),
        sa.CheckConstraint(
            "expires_at > verified_at",
            name=op.f("ck_assistant_order_grants_expiry_after_verification"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["assistant_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_order_grants")),
        sa.UniqueConstraint(
            "session_id", "order_id", name="uq_assistant_order_grants_session_order"
        ),
    )
    op.create_index("ix_assistant_order_grants_expiry", "assistant_order_grants", ["expires_at"])


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM notification_deliveries)
             OR EXISTS (SELECT 1 FROM notification_attempts)
             OR EXISTS (SELECT 1 FROM communication_preferences)
             OR EXISTS (SELECT 1 FROM consent_events)
             OR EXISTS (SELECT 1 FROM newsletter_subscriptions)
             OR EXISTS (SELECT 1 FROM cart_reminder_state)
             OR EXISTS (SELECT 1 FROM analytics_events)
             OR EXISTS (SELECT 1 FROM assistant_sessions)
             OR EXISTS (SELECT 1 FROM assistant_messages)
             OR EXISTS (SELECT 1 FROM assistant_order_grants)
             OR EXISTS (SELECT 1 FROM outbox_events WHERE status::text = 'dead_letter') THEN
            RAISE EXCEPTION 'cannot downgrade 0013: Phase 7 engagement data would be lost';
          END IF;
        END $$;
        """
    )
    op.drop_index("ix_assistant_order_grants_expiry", table_name="assistant_order_grants")
    op.drop_table("assistant_order_grants")
    op.drop_index("ix_assistant_messages_session_created", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_sessions_cleanup", table_name="assistant_sessions")
    op.drop_index("ix_assistant_sessions_owner_created", table_name="assistant_sessions")
    op.drop_table("assistant_sessions")
    op.drop_index("ix_analytics_events_context_expiry", table_name="analytics_events")
    op.drop_index("ix_analytics_events_capi_claim", table_name="analytics_events")
    op.drop_index("uq_analytics_events_purchase_order", table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index("ix_cart_reminder_state_delivery", table_name="cart_reminder_state")
    op.drop_index("ix_cart_reminder_state_eligibility", table_name="cart_reminder_state")
    op.drop_table("cart_reminder_state")
    op.drop_index("ix_newsletter_subscriptions_user", table_name="newsletter_subscriptions")
    op.drop_index("ix_newsletter_subscriptions_token_expiry", table_name="newsletter_subscriptions")
    op.drop_index("ix_newsletter_subscriptions_status", table_name="newsletter_subscriptions")
    op.drop_table("newsletter_subscriptions")
    op.drop_table("communication_preferences")
    op.drop_index("ix_notification_attempts_created", table_name="notification_attempts")
    op.drop_index("ix_notification_attempts_delivery_created", table_name="notification_attempts")
    op.drop_table("notification_attempts")
    op.drop_index("ix_notification_deliveries_terminal", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_recipient_hash", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_order_created", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_user_created", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_claim", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.execute("DROP TRIGGER consent_events_append_only ON consent_events")
    op.execute("DROP FUNCTION phase7_refuse_consent_event_mutation()")
    op.drop_index("ix_consent_events_created", table_name="consent_events")
    op.drop_index("ix_consent_events_subject_purpose_created", table_name="consent_events")
    op.drop_table("consent_events")
    op.execute("ALTER TYPE outbox_status RENAME TO outbox_status_phase7")
    op.execute("CREATE TYPE outbox_status AS ENUM ('pending','processing','delivered','failed')")
    op.execute("ALTER TABLE outbox_events ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE outbox_events ALTER COLUMN status TYPE outbox_status "
        "USING status::text::outbox_status"
    )
    op.execute("ALTER TABLE outbox_events ALTER COLUMN status SET DEFAULT 'pending'::outbox_status")
    op.execute("DROP TYPE outbox_status_phase7")
