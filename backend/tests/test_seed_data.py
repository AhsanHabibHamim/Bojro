from typing import Any, cast

import pytest
from scripts.seed import (
    CATEGORIES,
    HOMEPAGE_SECTIONS,
    PRODUCTS,
    ensure_demo_target_is_empty,
    homepage_content_v2,
    load_geo_dataset,
    merge_missing,
    seed_id,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.enums import HomepageSectionType


def test_geo_dataset_is_validated_and_bilingual() -> None:
    dataset = load_geo_dataset()

    assert dataset.metadata.coverage_status == "current_complete_snapshot"
    assert len(dataset.divisions) == 8
    assert len(dataset.districts) == 64
    assert len(dataset.upazilas) == 495
    assert all(row.name_bn and row.name_en for row in dataset.divisions)
    assert all(row.name_bn and row.name_en for row in dataset.districts)
    assert all(row.name_bn and row.name_en for row in dataset.upazilas)
    assert {row.name_en for row in dataset.divisions} >= {"Chattogram", "Barishal"}
    assert {row.name_en for row in dataset.districts} >= {"Cumilla", "Barishal"}
    assert {row.name_en for row in dataset.upazilas} >= {"Indurkani", "Shantiganj"}


def test_catalog_and_homepage_seed_contract() -> None:
    assert len(CATEGORIES) >= 8
    assert len(PRODUCTS) >= 40
    assert len({product.category for product in PRODUCTS}) >= 8
    assert all(product.name_bn and product.name_en for product in PRODUCTS)
    assert len(HOMEPAGE_SECTIONS) == 15
    assert {row[0] for row in HOMEPAGE_SECTIONS} == set(HomepageSectionType)


def test_seed_ids_are_stable_across_processes_by_natural_key() -> None:
    first = seed_id("product", "demo")
    assert first.version == 5
    assert seed_id("product", "demo") == first
    assert seed_id("product", "different") != first


def test_v2_homepage_content_covers_all_sections_with_rich_contracts() -> None:
    content = homepage_content_v2()

    assert set(content) == set(HomepageSectionType)
    assert all(content[item][0]["title"] for item in HomepageSectionType)
    assert all(content[item][1]["title"] for item in HomepageSectionType)
    assert len(content[HomepageSectionType.HERO][0]["benefits"]) == 3  # type: ignore[arg-type]
    assert len(content[HomepageSectionType.BRAND_STORY][1]["paragraphs"]) == 2  # type: ignore[arg-type]
    assert content[HomepageSectionType.REVIEWS][1]["verified_badge_requires_order"] is True
    assert content[HomepageSectionType.FLASH_SALE][1]["countdown"] == {
        "enabled": True,
        "source": "sale_end",
    }
    assert content[HomepageSectionType.SOCIAL_PROOF][1]["gallery"] == [
        "/seed/social-proof-1.svg",
        "/seed/social-proof-2.svg",
        "/seed/social-proof-3.svg",
    ]


def test_v1_to_v2_merge_never_overwrites_operator_content() -> None:
    existing: dict[str, object] = {
        "title": "Operator title",
        "countdown": {"enabled": False},
        "custom": "keep-me",
    }
    defaults: dict[str, object] = {
        "title": "Default title",
        "countdown": {"enabled": True, "source": "sale_end"},
        "cta": "Browse",
    }

    merged = merge_missing(existing, defaults)

    assert merged == {
        "title": "Operator title",
        "countdown": {"enabled": False, "source": "sale_end"},
        "custom": "keep-me",
        "cta": "Browse",
    }
    assert existing["countdown"] == {"enabled": False}


@pytest.mark.asyncio
async def test_initial_seed_emptiness_guard_checks_every_managed_table() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.tables: set[str] = set()

        async def scalar(self, statement: Any) -> int:
            self.tables.update(table.name for table in statement.get_final_froms())
            return 0

    session = RecordingSession()
    await ensure_demo_target_is_empty(cast(AsyncSession, session))
    assert session.tables == set(Base.metadata.tables)
