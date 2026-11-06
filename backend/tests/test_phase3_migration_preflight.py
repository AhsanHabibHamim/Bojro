from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings

pytestmark = pytest.mark.integration
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _messages(error: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(messages)


def _migrate(database_url: str, revision: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    configuration = Config(str(_BACKEND_DIR / "alembic.ini"))
    command.upgrade(configuration, revision)


def _downgrade(database_url: str, revision: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    configuration = Config(str(_BACKEND_DIR / "alembic.ini"))
    command.downgrade(configuration, revision)


async def _admin_statement(database_url: str, statement: str) -> None:
    admin_url = (
        make_url(database_url).set(database="postgres").render_as_string(hide_password=False)
    )
    engine = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@contextmanager
def _temporary_database(settings: Settings) -> Iterator[str]:
    name = f"bojro_migration_{uuid4().hex[:16]}"
    url = make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    original = os.environ.get("DATABASE_URL")
    asyncio.run(_admin_statement(settings.database_url, f'CREATE DATABASE "{name}"'))
    try:
        yield url
    finally:
        admin_url = (
            make_url(settings.database_url)
            .set(database="postgres")
            .render_as_string(hide_password=False)
        )

        async def drop() -> None:
            engine = create_async_engine(
                admin_url,
                isolation_level="AUTOCOMMIT",
                hide_parameters=True,
            )
            try:
                async with engine.connect() as connection:
                    await connection.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = :name AND pid <> pg_backend_pid()"
                        ),
                        {"name": name},
                    )
                    await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            finally:
                await engine.dispose()

        asyncio.run(drop())
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original
        get_settings.cache_clear()


async def _execute(database_url: str, statement: str) -> None:
    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _scalar(database_url: str, statement: str) -> object:
    engine = create_async_engine(database_url, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement))
    finally:
        await engine.dispose()


def test_migration_preflights_casefold_email_and_coupon_collisions(
    integration_settings: Settings,
) -> None:
    with _temporary_database(integration_settings) as database_url:
        _migrate(database_url, "0002_phase2")
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO users (id, role, name, email, is_guest)
                VALUES
                    ('{uuid4()}', 'customer', 'First', 'Case@Test.Example', false),
                    ('{uuid4()}', 'customer', 'Second', 'case@test.example', false)
                """,
            )
        )
        with pytest.raises(DBAPIError) as email_failure:
            _migrate(database_url, "head")
        email_message = _messages(email_failure.value)
        assert "users.email values collide case-insensitively" in email_message
        assert "Merge or rename the duplicate user emails" in email_message

        asyncio.run(
            _execute(
                database_url,
                "DELETE FROM users WHERE email = 'case@test.example'",
            )
        )
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO coupons (
                    id, code, type, value, min_subtotal, currency,
                    usage_count, per_user_limit, is_active
                )
                VALUES
                    ('{uuid4()}', 'save10', 'fixed', 100, 0, 'BDT', 0, 1, true),
                    ('{uuid4()}', 'SAVE10', 'fixed', 100, 0, 'BDT', 0, 1, true)
                """,
            )
        )
        with pytest.raises(DBAPIError) as coupon_failure:
            _migrate(database_url, "head")
        coupon_message = _messages(coupon_failure.value)
        assert "coupons.code values collide case-insensitively" in coupon_message
        assert "Merge or rename the duplicate coupon codes" in coupon_message

        asyncio.run(_execute(database_url, "DELETE FROM coupons WHERE code = 'SAVE10'"))
        _migrate(database_url, "head")
        assert (
            asyncio.run(
                _scalar(database_url, "SELECT code FROM coupons WHERE upper(code) = 'SAVE10'")
            )
            == "SAVE10"
        )
        index_definition = asyncio.run(
            _scalar(
                database_url,
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_coupons_code_upper'",
            )
        )
        assert index_definition is not None
        assert "upper" in str(index_definition).lower()


def test_phase4_migration_sanitizes_unverifiable_legacy_reviews_and_round_trips(
    integration_settings: Settings,
) -> None:
    with _temporary_database(integration_settings) as database_url:
        _migrate(database_url, "0003_phase3")
        user_id = uuid4()
        category_id = uuid4()
        product_id = uuid4()
        review_id = uuid4()
        statements = [
            f"""
                INSERT INTO users (id, role, name, phone, is_guest, is_active)
                VALUES ('{user_id}', 'customer', 'Legacy Reviewer', '+8801712345678', false, true)
            """,
            f"""
                INSERT INTO categories (id, slug, name_bn, name_en)
                VALUES ('{category_id}', 'legacy-category', 'লিগ্যাসি', 'Legacy')
            """,
            f"""
                INSERT INTO products (
                    id, slug, category_id, name_bn, name_en, desc_bn, desc_en,
                    status, is_featured, rating_avg, rating_count, sold_count
                ) VALUES (
                    '{product_id}', 'legacy-product', '{category_id}',
                    'লিগ্যাসি পণ্য', 'Legacy Product', 'বিবরণ', 'Description',
                    'active', false, 5, 1, 1
                )
            """,
            f"""
                INSERT INTO reviews (
                    id, product_id, user_id, rating, body, photos, status,
                    is_verified_purchase
                ) VALUES (
                    '{review_id}', '{product_id}', '{user_id}', 5, 'Legacy body',
                    ARRAY['javascript:alert(1)', 'https://untrusted.example/photo.jpg']::text[],
                    'approved', true
                )
            """,
        ]
        for statement in statements:
            asyncio.run(_execute(database_url, statement))

        _migrate(database_url, "head")
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT is_verified_purchase FROM reviews WHERE id = '{review_id}'",
                )
            )
            is False
        )
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT purchase_order_item_id FROM reviews WHERE id = '{review_id}'",
                )
            )
            is None
        )
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT author_name_snapshot FROM reviews WHERE id = '{review_id}'",
                )
            )
            == "Legacy Reviewer"
        )
        assert asyncio.run(_scalar(database_url, "SELECT count(*) FROM review_photos")) == 0
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT photos[1] FROM reviews WHERE id = '{review_id}'",
                )
            )
            == "javascript:alert(1)"
        )

        _downgrade(database_url, "0003_phase3")
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT photos[2] FROM reviews WHERE id = '{review_id}'",
                )
            )
            == "https://untrusted.example/photo.jpg"
        )
        _migrate(database_url, "head")
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'ix_reviews_user_updated_id'",
                )
            )
            == 1
        )


def test_phase4_migration_rewrites_support_numbers_and_backfills_one_default(
    integration_settings: Settings,
) -> None:
    with _temporary_database(integration_settings) as database_url:
        _migrate(database_url, "0003_phase3")
        user_id = uuid4()
        division_id = uuid4()
        district_id = uuid4()
        upazila_id = uuid4()
        older_address = uuid4()
        newer_address = uuid4()
        statements = [
            f"""
            INSERT INTO users (id, role, name, phone, is_guest, is_active)
            VALUES ('{user_id}', 'customer', 'Legacy Customer', '+8801712345678', false, true)
            """,
            f"""
            INSERT INTO geo_divisions (id, code, name_bn, name_en)
            VALUES ('{division_id}', '6', 'ঢাকা', 'Dhaka')
            """,
            f"""
            INSERT INTO geo_districts (id, division_id, code, name_bn, name_en)
            VALUES ('{district_id}', '{division_id}', '47', 'ঢাকা', 'Dhaka')
            """,
            f"""
            INSERT INTO geo_upazilas (id, district_id, code, name_bn, name_en)
            VALUES ('{upazila_id}', '{district_id}', 'legacy', 'ঢাকা', 'Dhaka')
            """,
            f"""
            INSERT INTO addresses (
                id, user_id, label, recipient, phone, division_id, district_id,
                upazila_id, address_line, is_default, created_at
            ) VALUES
                ('{older_address}', '{user_id}', 'Old', 'Legacy Customer', '+8801712345678',
                 '{division_id}', '{district_id}', '{upazila_id}', 'Old address line', false,
                 '2026-01-01T00:00:00Z'),
                ('{newer_address}', '{user_id}', 'New', 'Legacy Customer', '+8801712345678',
                 '{division_id}', '{district_id}', '{upazila_id}', 'New address line', false,
                 '2026-02-01T00:00:00Z')
            """,
            f"""
            INSERT INTO support_tickets (
                id, number, user_id, subject, status, priority, created_at
            ) VALUES
                ('{uuid4()}', 'BJ-SUP-2026-000010', '{user_id}', 'Valid ticket', 'open',
                 'normal', '2026-01-01T00:00:00Z'),
                ('{uuid4()}', 'legacy-alpha', '{user_id}', 'First legacy', 'open',
                 'normal', '2026-02-01T00:00:00Z'),
                ('{uuid4()}', 'legacy-beta', '{user_id}', 'Second legacy', 'open',
                 'normal', '2026-03-01T00:00:00Z')
            """,
        ]
        for statement in statements:
            asyncio.run(_execute(database_url, statement))

        _migrate(database_url, "head")
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    f"SELECT id FROM addresses WHERE user_id = '{user_id}' AND is_default",
                )
            )
            == newer_address
        )
        rewritten = asyncio.run(
            _scalar(
                database_url,
                "SELECT string_agg(number, ',' ORDER BY number) FROM support_tickets",
            )
        )
        assert rewritten == ("BJ-SUP-2026-000010,BJ-SUP-2026-000011,BJ-SUP-2026-000012")
        with pytest.raises(Exception, match="number_format"):
            asyncio.run(
                _execute(
                    database_url,
                    f"""
                    INSERT INTO support_tickets (
                        id, number, user_id, subject, status, priority
                    ) VALUES (
                        '{uuid4()}', 'legacy-invalid', '{user_id}', 'Invalid', 'open', 'normal'
                    )
                    """,
                )
            )
        assert (
            asyncio.run(
                _scalar(
                    database_url,
                    "SELECT confdeltype FROM pg_constraint "
                    "WHERE conname = 'fk_reviews_purchase_order_item_id_order_items'",
                )
            )
            == b"r"
        )
        _downgrade(database_url, "0003_phase3")


def test_phase4_downgrade_refuses_internal_messages_and_structured_photos(
    integration_settings: Settings,
) -> None:
    with _temporary_database(integration_settings) as database_url:
        _migrate(database_url, "head")
        user_id = uuid4()
        ticket_id = uuid4()
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO users (id, role, name, phone, is_guest, is_active)
                VALUES ('{user_id}', 'customer', 'Private Customer', '+8801712345678', false, true)
                """,
            )
        )
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO support_tickets (
                    id, number, user_id, subject, status, priority
                ) VALUES (
                    '{ticket_id}', 'BJ-SUP-2026-000001', '{user_id}', 'Private', 'open', 'normal'
                )
                """,
            )
        )
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO support_messages (
                    id, ticket_id, author_type, author_id, body, attachments, is_internal
                ) VALUES (
                    '{uuid4()}', '{ticket_id}', 'admin', NULL, 'Internal note',
                    ARRAY[]::text[], true
                )
                """,
            )
        )
        with pytest.raises(Exception, match="internal support messages"):
            _downgrade(database_url, "0003_phase3")

        asyncio.run(_execute(database_url, "DELETE FROM support_messages WHERE is_internal"))
        asyncio.run(
            _execute(
                database_url,
                f"""
                INSERT INTO review_photos (
                    id, user_id, provider, folder, public_id, original_filename,
                    mime_type, byte_size, state, signature_hash, signature_expires_at,
                    cleanup_after
                ) VALUES (
                    '{uuid4()}', '{user_id}', 'mock', 'review-uploads/private',
                    'review-uploads/private/asset', 'private.png', 'image/png', 100,
                    'pending', '{"0" * 64}', now() + interval '5 minutes', now()
                )
                """,
            )
        )
        with pytest.raises(Exception, match="structured review photos require provider cleanup"):
            _downgrade(database_url, "0003_phase3")

        asyncio.run(_execute(database_url, "DELETE FROM review_photos"))
        _downgrade(database_url, "0003_phase3")
