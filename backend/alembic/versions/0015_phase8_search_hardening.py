"""Add the SKU trigram index used by public catalog search.

Revision ID: 0015_phase8_hardening
Revises: 0014_phase7_release_hardening
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_phase8_hardening"
down_revision: str | Sequence[str] | None = "0014_phase7_release_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_product_variants_sku_trgm",
        "product_variants",
        ["sku"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"sku": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_product_variants_sku_trgm", table_name="product_variants")
