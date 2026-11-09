"""Operational bootstrap for the sole admin and non-demo system defaults."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import PasswordService
from app.db.enums import AuthSessionKind, HomepageSectionType, UserRole
from app.db.models import AuditLog, AuthSession, HomepageSection, SiteSetting, User

SCHEMA_HEAD = "0015_phase8_hardening"


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    admin_created: bool
    password_rotated: bool
    sessions_revoked: int
    settings_created: int
    homepage_sections_created: int


_SYSTEM_SETTINGS: dict[str, tuple[dict[str, object], int]] = {
    "branding": (
        {
            "store_name_bn": "বজ্র",
            "store_name_en": "Bojro",
            "logo_asset_id": None,
            "favicon_asset_id": None,
        },
        1,
    ),
    "payment_methods": (
        {"cod": True, "bkash": False, "nagad": False, "sslcommerz": False},
        1,
    ),
    "social_links": ({"facebook": "", "instagram": "", "youtube": ""}, 1),
    "analytics": (
        {
            "google_analytics_id": None,
            "meta_pixel_id": None,
            "consent_policy_version": "2026-11-07-v1",
        },
        2,
    ),
    "whatsapp": (
        {
            "enabled": False,
            "phone": "+8801700000000",
            "message_bn": "বজ্র সাপোর্টে স্বাগতম",
            "message_en": "Welcome to Bojro support",
        },
        1,
    ),
    "assistant": (
        {
            "enabled": False,
            "name_bn": "বজ্র সহকারী",
            "name_en": "Bojro Assistant",
            "disclosure_version": "2026-11-07-v1",
            "disclosure_bn": "এটি একটি এআই সহকারী। গুরুত্বপূর্ণ তথ্য যাচাই করুন।",
            "disclosure_en": "This is an AI assistant. Verify important information.",
        },
        1,
    ),
    "engagement_providers": (
        {
            "email": "disabled",
            "sms": "disabled",
            "meta_capi": "disabled",
            "assistant": "disabled",
        },
        1,
    ),
    "engagement": (
        {
            "newsletter_enabled": True,
            "consent_policy_version": "2026-11-07-v1",
        },
        1,
    ),
    "announcement": ({"enabled": False, "bn": "", "en": ""}, 1),
    "cod_risk": (
        {
            "version": 3,
            "enabled": False,
            "minimum_completed_orders": 0,
            "maximum_return_rate": 1.0,
            "advance_payment_required": False,
            "return_statuses": ["returned", "refunded"],
        },
        3,
    ),
    "storefront_toggles": (
        {
            "show_announcement": False,
            "show_social_links": False,
            "show_payment_methods": True,
        },
        1,
    ),
    "shipping_rules": (
        {
            "version": 3,
            "free_shipping_threshold_poisha": None,
            "zones": {
                "inside_dhaka": {
                    "district_codes": ["26"],
                    "tiers": [{"max_weight_g": 1000, "charge_poisha": 6000}],
                    "additional_kg_poisha": 2000,
                    "minimum_days": 1,
                    "maximum_days": 3,
                },
                "outside_dhaka": {
                    "district_codes": [],
                    "tiers": [{"max_weight_g": 1000, "charge_poisha": 12000}],
                    "additional_kg_poisha": 3000,
                    "minimum_days": 2,
                    "maximum_days": 7,
                },
            },
        },
        3,
    ),
}


async def bootstrap_operational_defaults(
    session: AsyncSession, settings: Settings
) -> BootstrapResult:
    if settings.bootstrap_admin_email is None or settings.bootstrap_admin_password is None:
        raise RuntimeError("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required")
    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != SCHEMA_HEAD:
        raise RuntimeError(f"database schema must be at {SCHEMA_HEAD}, found {revision!r}")

    email = str(settings.bootstrap_admin_email).casefold()
    password = settings.bootstrap_admin_password.get_secret_value()
    admin = await session.scalar(select(User).where(User.role == UserRole.ADMIN).with_for_update())
    if admin is not None and admin.email != email:
        raise RuntimeError("a different admin account already exists")
    if admin is None:
        account = await session.scalar(
            select(User).where(func.lower(User.email) == email).with_for_update()
        )
        if account is not None:
            raise RuntimeError("BOOTSTRAP_ADMIN_EMAIL belongs to a customer account")
        admin = User(
            role=UserRole.ADMIN,
            name="Bojro Admin",
            email=email,
            password_hash=PasswordService.hash(password),
            is_guest=False,
        )
        session.add(admin)
        await session.flush()
        session.add(
            AuditLog(
                action="admin.created_by_bootstrap",
                entity="admin_auth",
                entity_id=admin.id,
                event_kind="security",
                actor_snapshot={"kind": "system", "source": "bootstrap"},
                diff={"account": {"created": True}},
                status_code=201,
            )
        )
        admin_created = True
    else:
        admin_created = False

    rotated = False
    revoked = 0
    if not admin_created and settings.bootstrap_admin_force_password_rotation:
        now = datetime.now(UTC)
        admin.password_hash = PasswordService.hash(password)
        admin.password_changed_at = now
        admin.revision += 1
        result = await session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == admin.id,
                AuthSession.kind == AuthSessionKind.ADMIN,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .returning(AuthSession.id)
        )
        revoked = len(result.scalars().all())
        session.add(
            AuditLog(
                action="admin.password_rotated_by_bootstrap",
                entity="admin_auth",
                entity_id=admin.id,
                event_kind="security",
                actor_snapshot={"kind": "system", "source": "bootstrap"},
                diff={"password": {"changed": True}, "sessions_revoked": revoked},
                status_code=200,
            )
        )
        rotated = True

    setting_rows = {
        row.key: row for row in await session.scalars(select(SiteSetting).with_for_update())
    }
    runtime_values: dict[str, dict[str, object]] = {
        "analytics": {
            "google_analytics_id": settings.google_analytics_id,
            "meta_pixel_id": settings.meta_pixel_id,
            "consent_policy_version": settings.consent_policy_version,
        },
        "assistant": {"enabled": settings.assistant_public_enabled},
        "whatsapp": {
            "enabled": settings.whatsapp_enabled,
            "phone": settings.whatsapp_phone,
            "message_bn": settings.whatsapp_message_bn,
            "message_en": settings.whatsapp_message_en,
        },
        "engagement_providers": {
            "email": settings.email_provider,
            "sms": settings.sms_provider,
            "meta_capi": settings.meta_capi_mode,
            "assistant": settings.assistant_provider,
        },
        "engagement": {
            "newsletter_enabled": settings.newsletter_enabled,
            "consent_policy_version": settings.consent_policy_version,
        },
    }
    settings_created = 0
    for key, (value, schema_version) in _SYSTEM_SETTINGS.items():
        authoritative_value = {**value, **runtime_values.get(key, {})}
        row = setting_rows.get(key)
        if row is None:
            session.add(
                SiteSetting(
                    key=key,
                    value=authoritative_value,
                    schema_version=schema_version,
                )
            )
            settings_created += 1
        elif key in runtime_values:
            row.value = {**row.value, **runtime_values[key]}
            row.schema_version = schema_version

    existing_sections = set(await session.scalars(select(HomepageSection.section_type)))
    sections_created = 0
    for order, section_type in enumerate(HomepageSectionType, 1):
        if section_type not in existing_sections:
            session.add(
                HomepageSection(
                    section_type=section_type,
                    sort_order=order,
                    is_visible=False,
                    content_bn={},
                    content_en={},
                    schema_version=1,
                )
            )
            sections_created += 1

    return BootstrapResult(
        admin_created=admin_created,
        password_rotated=rotated,
        sessions_revoked=revoked,
        settings_created=settings_created,
        homepage_sections_created=sections_created,
    )
