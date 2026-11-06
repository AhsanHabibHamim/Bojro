"""add phase 2 catalog search and deterministic sort indexes

Revision ID: 0002_phase2
Revises: 0001_initial
Create Date: 2026-11-06 10:37:39
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    op.create_index(
        "ix_categories_name_bn_trgm",
        "categories",
        ["name_bn"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_bn": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_categories_name_en_trgm",
        "categories",
        ["name_en"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_en": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_categories_slug_trgm",
        "categories",
        ["slug"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"slug": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_brands_name_trgm",
        "brands",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_brands_slug_trgm",
        "brands",
        ["slug"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"slug": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_name_bn_trgm",
        "products",
        ["name_bn"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_bn": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_name_en_trgm",
        "products",
        ["name_en"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_en": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_slug_trgm",
        "products",
        ["slug"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"slug": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_status_created_id",
        "products",
        ["status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_products_status_rating_id",
        "products",
        ["status", "rating_avg", "id"],
        unique=False,
    )
    op.create_index(
        "ix_products_status_sold_id",
        "products",
        ["status", "sold_count", "id"],
        unique=False,
    )
    op.create_index(
        "ix_product_variants_product_active_price_id",
        "product_variants",
        ["product_id", "is_active", "price", "id"],
        unique=False,
    )
    op.create_index(
        "ix_product_variants_product_active_stock",
        "product_variants",
        ["product_id", "is_active", "stock_on_hand", "stock_reserved"],
        unique=False,
    )
    op.create_index(
        "ix_reviews_approved_product_created_id",
        "reviews",
        ["product_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reviews_approved_product_created_id",
        table_name="reviews",
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.drop_index(
        "ix_product_variants_product_active_stock",
        table_name="product_variants",
    )
    op.drop_index(
        "ix_product_variants_product_active_price_id",
        table_name="product_variants",
    )
    op.drop_index("ix_products_status_sold_id", table_name="products")
    op.drop_index("ix_products_status_rating_id", table_name="products")
    op.drop_index("ix_products_status_created_id", table_name="products")
    op.drop_index("ix_products_slug_trgm", table_name="products")
    op.drop_index("ix_products_name_en_trgm", table_name="products")
    op.drop_index("ix_products_name_bn_trgm", table_name="products")
    op.drop_index("ix_brands_slug_trgm", table_name="brands")
    op.drop_index("ix_brands_name_trgm", table_name="brands")
    op.drop_index("ix_categories_slug_trgm", table_name="categories")
    op.drop_index("ix_categories_name_en_trgm", table_name="categories")
    op.drop_index("ix_categories_name_bn_trgm", table_name="categories")
