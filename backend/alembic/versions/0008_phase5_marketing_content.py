"""add revisioned marketing, typed content, blog, and settings

Revision ID: 0008_phase5_content
Revises: 0007_phase5_catalog
Create Date: 2026-11-07 04:55:00
"""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase5_content"
down_revision: str | None = "0007_phase5_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_homepage_sections_order", "homepage_sections", type_="unique")
    op.create_unique_constraint(
        "uq_homepage_sections_order",
        "homepage_sections",
        ["order"],
        deferrable=True,
        initially="DEFERRED",
    )
    for table in (
        "coupons",
        "flash_sales",
        "banners",
        "homepage_sections",
        "static_pages",
        "site_settings",
    ):
        op.add_column(
            table, sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False)
        )

    op.add_column("banners", sa.Column("image_bn_asset_id", postgresql.UUID(as_uuid=True)))
    op.add_column("banners", sa.Column("image_en_asset_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_banners_image_bn_asset_id_media_assets"),
        "banners",
        "media_assets",
        ["image_bn_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_banners_image_en_asset_id_media_assets"),
        "banners",
        "media_assets",
        ["image_en_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "homepage_sections",
        sa.Column("schema_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
    )

    op.add_column(
        "static_pages",
        sa.Column(
            "document_bn", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        "static_pages",
        sa.Column(
            "document_en", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        "static_pages",
        sa.Column(
            "document_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
    )
    op.add_column("static_pages", sa.Column("published_at", sa.DateTime(timezone=True)))
    op.add_column(
        "static_pages",
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("static_pages", sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_static_pages_cover_asset_id_media_assets"),
        "static_pages",
        "media_assets",
        ["cover_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE static_pages
           SET document_bn = jsonb_build_object(
                   'type', 'doc', 'version', 1,
                   'content', jsonb_build_array(jsonb_build_object(
                       'type', 'paragraph', 'content', jsonb_build_array(
                           jsonb_build_object('type', 'text', 'text', body_bn)
                       )
                   ))
               ),
               document_en = jsonb_build_object(
                   'type', 'doc', 'version', 1,
                   'content', jsonb_build_array(jsonb_build_object(
                       'type', 'paragraph', 'content', jsonb_build_array(
                           jsonb_build_object('type', 'text', 'text', body_en)
                       )
                   ))
               ),
               published_at = CASE WHEN is_published THEN updated_at ELSE NULL END,
               is_system = true
        """
    )

    op.add_column(
        "site_settings",
        sa.Column("schema_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
    )
    op.execute(
        "UPDATE site_settings SET schema_version = CASE "
        "WHEN key = 'shipping_rules' THEN 3 ELSE 1 END"
    )

    op.create_table(
        "blog_posts",
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title_bn", sa.String(length=255), nullable=False),
        sa.Column("title_en", sa.String(length=255), nullable=False),
        sa.Column("excerpt_bn", sa.String(length=500)),
        sa.Column("excerpt_en", sa.String(length=500)),
        sa.Column("document_bn", postgresql.JSONB(), nullable=False),
        sa.Column("document_en", postgresql.JSONB(), nullable=False),
        sa.Column(
            "document_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("cover_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_published", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["cover_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_blog_posts_cover_asset_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_posts")),
        sa.UniqueConstraint("slug", name=op.f("uq_blog_posts_slug")),
    )
    op.create_index(
        "ix_blog_posts_published_at",
        "blog_posts",
        ["is_published", "published_at", "id"],
    )
    op.create_index("ix_blog_posts_tags", "blog_posts", ["tags"], postgresql_using="gin")
    op.create_index(
        "ix_flash_sale_items_variant_sale", "flash_sale_items", ["variant_id", "flash_sale_id"]
    )
    op.create_index(
        "ix_flash_sales_schedule", "flash_sales", ["is_active", "starts_at", "ends_at", "id"]
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM blog_posts)
               OR EXISTS (
                   SELECT 1 FROM static_pages
                    WHERE cover_asset_id IS NOT NULL
                       OR revision > 1
                       OR is_system IS NOT TRUE
                       OR document_bn <> jsonb_build_object(
                           'type', 'doc', 'version', 1,
                           'content', jsonb_build_array(jsonb_build_object(
                               'type', 'paragraph', 'content', jsonb_build_array(
                                   jsonb_build_object('type', 'text', 'text', body_bn)
                               )
                           ))
                       )
                       OR document_en <> jsonb_build_object(
                           'type', 'doc', 'version', 1,
                           'content', jsonb_build_array(jsonb_build_object(
                               'type', 'paragraph', 'content', jsonb_build_array(
                                   jsonb_build_object('type', 'text', 'text', body_en)
                               )
                           ))
                       )
               )
               OR EXISTS (
                   SELECT 1 FROM banners
                    WHERE image_bn_asset_id IS NOT NULL OR image_en_asset_id IS NOT NULL
                       OR revision > 1
               )
               OR EXISTS (SELECT 1 FROM homepage_sections WHERE revision > 1 OR schema_version <> 1)
               OR EXISTS (SELECT 1 FROM coupons WHERE revision > 1)
               OR EXISTS (SELECT 1 FROM flash_sales WHERE revision > 1)
               OR EXISTS (
                   SELECT 1 FROM site_settings
                    WHERE revision > 1
                       OR schema_version <> CASE WHEN key = 'shipping_rules' THEN 3 ELSE 1 END
               ) THEN
                RAISE EXCEPTION 'cannot downgrade 0008: Phase 5 content or media references would be destroyed';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("uq_homepage_sections_order", "homepage_sections", type_="unique")
    op.create_unique_constraint("uq_homepage_sections_order", "homepage_sections", ["order"])
    op.drop_index("ix_flash_sales_schedule", table_name="flash_sales")
    op.drop_index("ix_flash_sale_items_variant_sale", table_name="flash_sale_items")
    op.drop_index("ix_blog_posts_tags", table_name="blog_posts")
    op.drop_index("ix_blog_posts_published_at", table_name="blog_posts")
    op.drop_table("blog_posts")
    op.drop_column("site_settings", "schema_version")
    op.drop_constraint(
        op.f("fk_static_pages_cover_asset_id_media_assets"), "static_pages", type_="foreignkey"
    )
    for name in (
        "cover_asset_id",
        "is_system",
        "published_at",
        "document_version",
        "document_en",
        "document_bn",
    ):
        op.drop_column("static_pages", name)
    op.drop_column("homepage_sections", "schema_version")
    op.drop_constraint(
        op.f("fk_banners_image_en_asset_id_media_assets"), "banners", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_banners_image_bn_asset_id_media_assets"), "banners", type_="foreignkey"
    )
    op.drop_column("banners", "image_en_asset_id")
    op.drop_column("banners", "image_bn_asset_id")
    for table in (
        "site_settings",
        "static_pages",
        "homepage_sections",
        "banners",
        "flash_sales",
        "coupons",
    ):
        op.drop_column(table, "revision")
