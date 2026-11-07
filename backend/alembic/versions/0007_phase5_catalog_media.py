"""add revisioned catalog aggregates, media, and catalog imports

Revision ID: 0007_phase5_catalog
Revises: 0006_phase5_admin
Create Date: 2026-11-07 04:50:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase5_catalog"
down_revision: str | None = "0006_phase5_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

media_purpose = postgresql.ENUM(
    "product",
    "category",
    "brand",
    "banner",
    "page",
    "blog",
    "logo",
    name="media_purpose",
    create_type=False,
)
media_state = postgresql.ENUM(
    "pending",
    "ready",
    "delete_pending",
    "deleted",
    name="media_state",
    create_type=False,
)
catalog_import_status = postgresql.ENUM(
    "validating",
    "valid",
    "invalid",
    "imported",
    "failed",
    name="catalog_import_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                WITH RECURSIVE ancestry AS (
                    SELECT id AS origin_id, id, parent_id, ARRAY[id] AS path, 1 AS depth, false AS cycle
                      FROM categories
                    UNION ALL
                    SELECT ancestry.origin_id, parent.id, parent.parent_id,
                           ancestry.path || parent.id, ancestry.depth + 1,
                           parent.id = ANY(ancestry.path)
                      FROM ancestry
                      JOIN categories AS parent ON parent.id = ancestry.parent_id
                     WHERE NOT ancestry.cycle AND ancestry.depth <= 100
                )
                SELECT 1 FROM ancestry WHERE cycle OR depth > 3
            ) THEN
                RAISE EXCEPTION 'cannot upgrade 0007: category hierarchy has a cycle or exceeds depth 3';
            END IF;
        END $$;
        """
    )
    bind = op.get_bind()
    media_purpose.create(bind, checkfirst=True)
    media_state.create(bind, checkfirst=True)
    catalog_import_status.create(bind, checkfirst=True)

    op.create_table(
        "media_assets",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", media_purpose, nullable=False),
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
        sa.Column("state", media_state, server_default=sa.text("'pending'"), nullable=False),
        sa.Column("signature_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("signature_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_after", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 10485760", name=op.f("ck_media_assets_byte_size_range")
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name=op.f("ck_media_assets_mime_type_allowed"),
        ),
        sa.CheckConstraint(
            "width IS NULL OR (width >= 64 AND width <= 8000)",
            name=op.f("ck_media_assets_width_range"),
        ),
        sa.CheckConstraint(
            "height IS NULL OR (height >= 64 AND height <= 8000)",
            name=op.f("ck_media_assets_height_range"),
        ),
        sa.CheckConstraint(
            "width IS NULL OR height IS NULL OR width::bigint * height::bigint <= 40000000",
            name=op.f("ck_media_assets_pixel_limit"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_media_assets_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("provider", "public_id", name="uq_media_assets_provider_public_id"),
        sa.UniqueConstraint("provider_asset_id", name=op.f("uq_media_assets_provider_asset_id")),
    )
    op.create_index(
        "ix_media_assets_owner_purpose_created",
        "media_assets",
        ["owner_id", "purpose", "created_at"],
    )
    op.create_index(
        "ix_media_assets_cleanup",
        "media_assets",
        ["state", "cleanup_after"],
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )

    op.create_table(
        "catalog_imports",
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", catalog_import_status, nullable=False),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "report", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_catalog_imports_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_imports")),
    )
    op.create_index(
        "ix_catalog_imports_actor_created", "catalog_imports", ["actor_id", "created_at"]
    )
    op.add_column(
        "inventory_movements", sa.Column("catalog_import_id", postgresql.UUID(as_uuid=True))
    )
    op.create_foreign_key(
        op.f("fk_inventory_movements_catalog_import_id_catalog_imports"),
        "inventory_movements",
        "catalog_imports",
        ["catalog_import_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for table in ("categories", "brands", "products", "product_variants", "product_images"):
        op.add_column(
            table, sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False)
        )
    op.add_column("categories", sa.Column("image_asset_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_categories_image_asset_id_media_assets"),
        "categories",
        "media_assets",
        ["image_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "brands",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("brands", sa.Column("logo_asset_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_brands_logo_asset_id_media_assets"),
        "brands",
        "media_assets",
        ["logo_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("product_images", sa.Column("alt_bn", sa.String(length=255)))
    op.add_column("product_images", sa.Column("alt_en", sa.String(length=255)))
    op.add_column("product_images", sa.Column("media_asset_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_product_images_media_asset_id_media_assets"),
        "product_images",
        "media_assets",
        ["media_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute("UPDATE product_images SET alt_bn = alt, alt_en = alt")
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (PARTITION BY product_id ORDER BY sort, created_at, id) - 1 AS position
              FROM product_images
        )
        UPDATE product_images AS image SET sort = ordered.position
          FROM ordered WHERE image.id = ordered.id
        """
    )
    op.create_unique_constraint(
        "uq_product_images_product_sort",
        "product_images",
        ["product_id", "sort"],
        deferrable=True,
        initially="DEFERRED",
    )

    # Legacy URLs are retained and dual-read. When an admin exists, represent those trusted local
    # seed assets structurally without guessing dimensions or provider metadata.
    op.execute(
        """
        INSERT INTO media_assets (
            id, owner_id, purpose, provider, folder, public_id, original_filename,
            mime_type, byte_size, state, signature_hash, signature_expires_at,
            completed_at, revision, created_at, updated_at
        )
        SELECT gen_random_uuid(), admin.id, 'product', 'local', 'legacy/products',
               'legacy/product-image/' || image.id::text, 'legacy-product.webp',
               'image/webp', 1, 'ready', repeat('0', 64), now() + interval '100 years',
               now(), 1, image.created_at, image.created_at
          FROM product_images AS image
          CROSS JOIN LATERAL (
              SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1
          ) AS admin
        ON CONFLICT (provider, public_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE product_images AS image
           SET media_asset_id = asset.id
          FROM media_assets AS asset
         WHERE asset.provider = 'local'
           AND asset.public_id = 'legacy/product-image/' || image.id::text
        """
    )
    op.execute(
        """
        INSERT INTO media_assets (
            id, owner_id, purpose, provider, folder, public_id, original_filename,
            mime_type, byte_size, state, signature_hash, signature_expires_at,
            completed_at, revision, created_at, updated_at
        )
        SELECT gen_random_uuid(), admin.id, 'category', 'local', 'legacy/categories',
               'legacy/category/' || category.id::text, 'legacy-category.webp',
               'image/webp', 1, 'ready', repeat('0', 64), now() + interval '100 years',
               now(), 1, category.created_at, category.updated_at
          FROM categories AS category
          CROSS JOIN LATERAL (
              SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1
          ) AS admin
         WHERE category.image IS NOT NULL
        ON CONFLICT (provider, public_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE categories AS category
           SET image_asset_id = asset.id
          FROM media_assets AS asset
         WHERE asset.provider = 'local'
           AND asset.public_id = 'legacy/category/' || category.id::text
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM catalog_imports)
               OR EXISTS (SELECT 1 FROM media_assets WHERE public_id NOT LIKE 'legacy/%')
               OR EXISTS (
                   SELECT 1 FROM brands
                    WHERE logo_asset_id IS NOT NULL OR is_active IS NOT TRUE
               )
               OR EXISTS (
                   SELECT 1 FROM product_images
                    WHERE alt_bn IS DISTINCT FROM alt OR alt_en IS DISTINCT FROM alt
               ) THEN
                RAISE EXCEPTION 'cannot downgrade 0007: Phase 5 catalog or media data would be destroyed';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("uq_product_images_product_sort", "product_images", type_="unique")
    op.drop_constraint(
        op.f("fk_product_images_media_asset_id_media_assets"), "product_images", type_="foreignkey"
    )
    for name in ("media_asset_id", "alt_en", "alt_bn"):
        op.drop_column("product_images", name)
    op.drop_constraint(op.f("fk_brands_logo_asset_id_media_assets"), "brands", type_="foreignkey")
    op.drop_column("brands", "logo_asset_id")
    op.drop_column("brands", "is_active")
    op.drop_constraint(
        op.f("fk_categories_image_asset_id_media_assets"), "categories", type_="foreignkey"
    )
    op.drop_column("categories", "image_asset_id")
    for table in ("product_images", "product_variants", "products", "brands", "categories"):
        op.drop_column(table, "revision")
    op.drop_constraint(
        op.f("fk_inventory_movements_catalog_import_id_catalog_imports"),
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_column("inventory_movements", "catalog_import_id")
    op.drop_index("ix_catalog_imports_actor_created", table_name="catalog_imports")
    op.drop_table("catalog_imports")
    op.drop_index(
        "ix_media_assets_cleanup",
        table_name="media_assets",
        postgresql_where=sa.text("state IN ('pending', 'delete_pending')"),
    )
    op.drop_index("ix_media_assets_owner_purpose_created", table_name="media_assets")
    op.drop_table("media_assets")
    catalog_import_status.drop(op.get_bind(), checkfirst=True)
    media_state.drop(op.get_bind(), checkfirst=True)
    media_purpose.drop(op.get_bind(), checkfirst=True)
