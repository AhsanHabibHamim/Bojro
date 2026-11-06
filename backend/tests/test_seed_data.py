from scripts.seed import CATEGORIES, HOMEPAGE_SECTIONS, PRODUCTS, load_geo_dataset, seed_id

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


def test_seed_ids_are_stable_per_process_uuid7_values() -> None:
    first = seed_id("product", "demo")
    assert first.version == 7
    assert seed_id("product", "demo") == first
    assert seed_id("product", "different") != first
