"""Complete Phase 1 PostgreSQL ORM model contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.db.enums import (
    CartStatus,
    CouponType,
    CourierProvider,
    HomepageSectionType,
    MessageAuthor,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    ProductStatus,
    ReviewStatus,
    ShipmentStatus,
    TicketPriority,
    TicketStatus,
    UserRole,
)


def db_enum[EnumT: Enum](enum_class: type[EnumT], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda members: [str(member.value) for member in members],
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("phone IS NOT NULL OR email IS NOT NULL", name="contact_required"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "phone IS NULL OR phone ~ '^\\+8801[3-9][0-9]{8}$'",
            name="phone_bd_e164",
        ),
        Index("ix_users_role_created_at", "role", "created_at"),
        Index(
            "uq_users_email_lower",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_users_single_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'admin'"),
        ),
    )

    role: Mapped[UserRole] = mapped_column(
        db_enum(UserRole, "user_role"), default=UserRole.CUSTOMER, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(14), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str | None] = mapped_column(String(512))
    is_guest: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )

    addresses: Mapped[list[Address]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    carts: Mapped[list[Cart]] = relationship(back_populates="user")
    orders: Mapped[list[Order]] = relationship(back_populates="user")
    reviews: Mapped[list[Review]] = relationship(
        back_populates="user", foreign_keys="Review.user_id"
    )
    auth_sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),
        Index("ix_auth_sessions_family", "family_id"),
        Index(
            "ix_auth_sessions_active_expiry",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_jti_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    family_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent_hash: Mapped[str | None] = mapped_column(CHAR(64))
    ip_prefix_hash: Mapped[str | None] = mapped_column(CHAR(64))

    user: Mapped[User] = relationship(back_populates="auth_sessions")


class GeoDivision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "geo_divisions"

    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name_bn: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)

    districts: Mapped[list[GeoDistrict]] = relationship(
        back_populates="division", cascade="all, delete-orphan"
    )


class GeoDistrict(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "geo_districts"
    __table_args__ = (
        UniqueConstraint("division_id", "name_en"),
        UniqueConstraint("id", "division_id", name="uq_geo_districts_id_division"),
        Index("ix_geo_districts_division_name", "division_id", "name_en"),
    )

    division_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_divisions.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    name_bn: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)

    division: Mapped[GeoDivision] = relationship(back_populates="districts")
    upazilas: Mapped[list[GeoUpazila]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )


class GeoUpazila(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "geo_upazilas"
    __table_args__ = (
        UniqueConstraint("district_id", "name_en"),
        UniqueConstraint("id", "district_id", name="uq_geo_upazilas_id_district"),
        Index("ix_geo_upazilas_district_name", "district_id", "name_en"),
    )

    district_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_districts.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name_bn: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)

    district: Mapped[GeoDistrict] = relationship(back_populates="upazilas")


class Address(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        CheckConstraint("phone ~ '^\\+8801[3-9][0-9]{8}$'", name="phone_bd_e164"),
        CheckConstraint("revision > 0", name="revision_positive"),
        ForeignKeyConstraint(
            ["district_id", "division_id"],
            ["geo_districts.id", "geo_districts.division_id"],
            name="fk_addresses_district_division",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["upazila_id", "district_id"],
            ["geo_upazilas.id", "geo_upazilas.district_id"],
            name="fk_addresses_upazila_district",
            ondelete="RESTRICT",
        ),
        Index("ix_addresses_user", "user_id"),
        Index(
            "ix_addresses_user_default_created_id",
            "user_id",
            "is_default",
            "created_at",
            "id",
        ),
        Index(
            "uq_addresses_default_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    recipient: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(14), nullable=False)
    division_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_divisions.id", ondelete="RESTRICT"), nullable=False
    )
    district_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_districts.id", ondelete="RESTRICT"), nullable=False
    )
    upazila_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_upazilas.id", ondelete="RESTRICT"), nullable=False
    )
    address_line: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="addresses")
    division: Mapped[GeoDivision] = relationship()
    district: Mapped[GeoDistrict] = relationship(foreign_keys=[district_id])
    upazila: Mapped[GeoUpazila] = relationship(foreign_keys=[upazila_id])


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("sort >= 0", name="sort_nonnegative"),
        Index("ix_categories_parent_sort", "parent_id", "sort"),
        Index("ix_categories_active_sort", "is_active", "sort"),
        Index(
            "ix_categories_name_bn_trgm",
            "name_bn",
            postgresql_using="gin",
            postgresql_ops={"name_bn": "gin_trgm_ops"},
        ),
        Index(
            "ix_categories_name_en_trgm",
            "name_en",
            postgresql_using="gin",
            postgresql_ops={"name_en": "gin_trgm_ops"},
        ),
        Index(
            "ix_categories_slug_trgm",
            "slug",
            postgresql_using="gin",
            postgresql_ops={"slug": "gin_trgm_ops"},
        ),
    )

    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    name_bn: Mapped[str] = mapped_column(String(180), nullable=False)
    name_en: Mapped[str] = mapped_column(String(180), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(120))
    image: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        "sort", Integer, default=0, server_default=text("0"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    parent: Mapped[Category | None] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list[Category]] = relationship(back_populates="parent")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        Index(
            "ix_brands_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_brands_slug_trgm",
            "slug",
            postgresql_using="gin",
            postgresql_ops={"slug": "gin_trgm_ops"},
        ),
    )

    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)

    products: Mapped[list[Product]] = relationship(back_populates="brand")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("rating_avg >= 0 AND rating_avg <= 5", name="rating_range"),
        CheckConstraint("rating_count >= 0", name="rating_count_nonnegative"),
        CheckConstraint("sold_count >= 0", name="sold_count_nonnegative"),
        Index("ix_products_category_status", "category_id", "status"),
        Index("ix_products_brand_status", "brand_id", "status"),
        Index("ix_products_featured_status", "is_featured", "status"),
        Index("ix_products_status_created_at", "status", "created_at"),
        Index("ix_products_status_rating_avg", "status", "rating_avg"),
        Index("ix_products_status_sold_count", "status", "sold_count"),
        Index("ix_products_status_created_id", "status", "created_at", "id"),
        Index("ix_products_status_rating_id", "status", "rating_avg", "id"),
        Index("ix_products_status_sold_id", "status", "sold_count", "id"),
        Index(
            "ix_products_name_bn_trgm",
            "name_bn",
            postgresql_using="gin",
            postgresql_ops={"name_bn": "gin_trgm_ops"},
        ),
        Index(
            "ix_products_name_en_trgm",
            "name_en",
            postgresql_using="gin",
            postgresql_ops={"name_en": "gin_trgm_ops"},
        ),
        Index(
            "ix_products_slug_trgm",
            "slug",
            postgresql_using="gin",
            postgresql_ops={"slug": "gin_trgm_ops"},
        ),
    )

    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL")
    )
    name_bn: Mapped[str] = mapped_column(String(240), nullable=False)
    name_en: Mapped[str] = mapped_column(String(240), nullable=False)
    desc_bn: Mapped[str] = mapped_column(Text, nullable=False)
    desc_en: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        db_enum(ProductStatus, "product_status"),
        default=ProductStatus.DRAFT,
        nullable=False,
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.00"), server_default=text("0"), nullable=False
    )
    rating_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    sold_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    seo_title_bn: Mapped[str | None] = mapped_column(String(255))
    seo_title_en: Mapped[str | None] = mapped_column(String(255))
    seo_description_bn: Mapped[str | None] = mapped_column(String(320))
    seo_description_en: Mapped[str | None] = mapped_column(String(320))

    category: Mapped[Category] = relationship(back_populates="products")
    brand: Mapped[Brand | None] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(back_populates="product")


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= price",
            name="compare_at_not_below_price",
        ),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        CheckConstraint("stock_on_hand >= 0", name="stock_on_hand_nonnegative"),
        CheckConstraint("stock_reserved >= 0", name="stock_reserved_nonnegative"),
        CheckConstraint("stock_reserved <= stock_on_hand", name="reserved_within_stock"),
        CheckConstraint("weight_g > 0", name="weight_positive"),
        UniqueConstraint("id", "product_id", name="uq_product_variants_id_product"),
        Index("ix_product_variants_product_active", "product_id", "is_active"),
        Index("ix_product_variants_active_stock", "is_active", "stock_on_hand"),
        Index("ix_product_variants_active_price", "is_active", "price"),
        Index(
            "ix_product_variants_product_active_price_id",
            "product_id",
            "is_active",
            "price",
            "id",
        ),
        Index(
            "ix_product_variants_product_active_stock",
            "product_id",
            "is_active",
            "stock_on_hand",
            "stock_reserved",
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    options: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compare_at_price: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )
    stock_on_hand: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    stock_reserved: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="variants")
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="variant", foreign_keys="ProductImage.variant_id"
    )
    flash_sale_items: Mapped[list[FlashSaleItem]] = relationship(
        back_populates="variant", cascade="all, delete-orphan"
    )


class ProductImage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint("sort >= 0", name="sort_nonnegative"),
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            name="fk_product_images_variant_product",
            ondelete="CASCADE",
        ),
        Index("ix_product_images_product_sort", "product_id", "sort"),
        Index("ix_product_images_variant_sort", "variant_id", "sort"),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    alt: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        "sort", Integer, default=0, server_default=text("0"), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="images")
    variant: Mapped[ProductVariant | None] = relationship(
        back_populates="images", foreign_keys=[variant_id]
    )


class Cart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "carts"
    __table_args__ = (
        CheckConstraint("num_nonnulls(user_id, guest_token) = 1", name="exactly_one_owner"),
        Index(
            "uq_carts_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active' AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_carts_active_guest",
            "guest_token",
            unique=True,
            postgresql_where=text("status = 'active' AND guest_token IS NOT NULL"),
        ),
        Index("ix_carts_status_expires_at", "status", "expires_at"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    guest_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[CartStatus] = mapped_column(
        db_enum(CartStatus, "cart_status"), default=CartStatus.ACTIVE, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coupon_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("coupons.id", ondelete="SET NULL")
    )
    shipping_district_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("geo_districts.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )

    user: Mapped[User | None] = relationship(back_populates="carts")
    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )
    coupon: Mapped[Coupon | None] = relationship()
    shipping_district: Mapped[GeoDistrict | None] = relationship()


class CartItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id"),
        CheckConstraint("quantity >= 1 AND quantity <= 99", name="quantity_range"),
        Index("ix_cart_items_cart_created_at", "cart_id", "created_at"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship()


class Coupon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("value >= 0", name="value_nonnegative"),
        CheckConstraint(
            "type <> 'percent' OR (value >= 1 AND value <= 100)",
            name="percent_value_range",
        ),
        CheckConstraint("min_subtotal >= 0", name="min_subtotal_nonnegative"),
        CheckConstraint(
            "max_discount IS NULL OR max_discount >= 0", name="max_discount_nonnegative"
        ),
        CheckConstraint("usage_limit IS NULL OR usage_limit > 0", name="usage_limit_positive"),
        CheckConstraint("usage_count >= 0", name="usage_count_nonnegative"),
        CheckConstraint("per_user_limit > 0", name="per_user_limit_positive"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", name="dates"
        ),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        CheckConstraint(
            "code = upper(btrim(code)) AND code <> ''",
            name="code_normalized",
        ),
        Index("uq_coupons_code_upper", func.upper(text("code")), unique=True),
        Index("ix_coupons_active_dates", "is_active", "starts_at", "ends_at"),
        Index(
            "ix_coupons_discoverable_active_dates_id",
            "is_discoverable",
            "is_active",
            "starts_at",
            "ends_at",
            "id",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type: Mapped[CouponType] = mapped_column(db_enum(CouponType, "coupon_type"), nullable=False)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_subtotal: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    max_discount: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    usage_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    per_user_limit: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    is_discoverable: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    @validates("code")
    def normalize_code(self, _key: str, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("coupon code cannot be blank")
        return normalized


class FlashSale(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flash_sales"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="dates"),
        Index("ix_flash_sales_active_dates", "is_active", "starts_at", "ends_at"),
    )

    name_bn: Mapped[str] = mapped_column(String(180), nullable=False)
    name_en: Mapped[str] = mapped_column(String(180), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    items: Mapped[list[FlashSaleItem]] = relationship(
        back_populates="flash_sale", cascade="all, delete-orphan"
    )


class FlashSaleItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "flash_sale_items"
    __table_args__ = (
        UniqueConstraint("flash_sale_id", "variant_id"),
        CheckConstraint("sale_price >= 0", name="sale_price_nonnegative"),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        CheckConstraint("qty_limit > 0", name="qty_limit_positive"),
        CheckConstraint("sold_qty >= 0 AND sold_qty <= qty_limit", name="sold_qty_range"),
        Index("ix_flash_sale_items_sale_sold", "flash_sale_id", "sold_qty"),
    )

    flash_sale_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("flash_sales.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )
    qty_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    sold_qty: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    flash_sale: Mapped[FlashSale] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship(back_populates="flash_sale_items")


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("discount_total >= 0", name="discount_total_nonnegative"),
        CheckConstraint("discount_total <= subtotal", name="discount_within_subtotal"),
        CheckConstraint("shipping_total >= 0", name="shipping_total_nonnegative"),
        CheckConstraint("grand_total >= 0", name="grand_total_nonnegative"),
        CheckConstraint(
            "grand_total = subtotal - discount_total + shipping_total", name="total_consistent"
        ),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        CheckConstraint(
            "number ~ '^BJ-[0-9]{4}-[0-9]{6}$'",
            name="number_format",
        ),
        Index("ix_orders_user_placed_at", "user_id", "placed_at"),
        Index("ix_orders_user_placed_id", "user_id", "placed_at", "id"),
        Index("ix_orders_user_status_placed_id", "user_id", "status", "placed_at", "id"),
        Index("ix_orders_status_placed_at", "status", "placed_at"),
        Index("ix_orders_payment_status_placed_at", "payment_status", "placed_at"),
        Index("ix_orders_phone_lookup", text("(address_snapshot ->> 'phone')")),
    )

    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_cart_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("carts.id", ondelete="RESTRICT"), unique=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        db_enum(OrderStatus, "order_status"), default=OrderStatus.PENDING, nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        db_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        db_enum(PaymentMethod, "payment_method"), nullable=False
    )
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_total: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    shipping_total: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    grand_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )
    coupon_code: Mapped[str | None] = mapped_column(String(64))
    address_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(back_populates="order")
    shipments: Mapped[list[Shipment]] = relationship(back_populates="order")
    source_cart: Mapped[Cart | None] = relationship()


class OrderItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("line_total = price * qty", name="line_total_consistent"),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        Index("ix_order_items_order", "order_id"),
        Index("ix_order_items_product", "product_id"),
        Index("ix_order_items_order_product", "order_id", "product_id"),
        Index("ix_order_items_flash_sale_item", "flash_sale_item_id"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    variant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL")
    )
    flash_sale_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("flash_sale_items.id", ondelete="SET NULL")
    )
    name_bn: Mapped[str] = mapped_column(String(240), nullable=False)
    name_en: Mapped[str] = mapped_column(String(240), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    options: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    unit_price: Mapped[int] = mapped_column("price", BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column("qty", Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    variant: Mapped[ProductVariant | None] = relationship()
    flash_sale_item: Mapped[FlashSaleItem | None] = relationship()


class CouponRedemption(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        Index("ix_coupon_redemptions_coupon_user_released", "coupon_id", "user_id", "released_at"),
        Index("ix_coupon_redemptions_user_created", "user_id", "created_at"),
        Index("ix_coupon_redemptions_user_created_id", "user_id", "created_at", "id"),
    )

    coupon_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("coupons.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    code_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    coupon: Mapped[Coupon] = relationship()
    user: Mapped[User] = relationship()
    order: Mapped[Order] = relationship()


class IdempotencyRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("endpoint", "scope_hash", "idempotency_key"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "(resource_kind IS NULL) = (resource_id IS NULL)",
            name="resource_pair_complete",
        ),
        Index("ix_idempotency_records_expiry", "expires_at"),
        Index("ix_idempotency_records_order", "order_id"),
        Index("ix_idempotency_records_resource", "resource_kind", "resource_id"),
    )

    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL")
    )
    resource_kind: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped[Order | None] = relationship()


class OrderNumberCounter(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_number_counters"
    __table_args__ = (
        CheckConstraint("year >= 2020 AND year <= 9999", name="year_range"),
        CheckConstraint("next_value >= 1 AND next_value <= 1000000", name="next_value_range"),
    )

    year: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    next_value: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class OrderStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_status_history"
    __table_args__ = (
        Index("ix_order_status_history_order_at", "order_id", "at"),
        Index("ix_order_status_history_order_at_id", "order_id", "at", "id"),
        Index("ix_order_status_history_order_to", "order_id", "to"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[OrderStatus | None] = mapped_column(
        "from", db_enum(OrderStatus, "order_status")
    )
    to_status: Mapped[OrderStatus] = mapped_column(
        "to", db_enum(OrderStatus, "order_status"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        "actor", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    customer_note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="status_history")
    actor: Mapped[User | None] = relationship()


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint("currency = 'BDT'", name="currency_bdt"),
        UniqueConstraint("provider", "provider_txn_id"),
        Index("ix_payments_order_created_at", "order_id", "created_at"),
        Index("ix_payments_status_created_at", "status", "created_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[PaymentMethod] = mapped_column(
        db_enum(PaymentMethod, "payment_method"), nullable=False
    )
    provider_txn_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="BDT", server_default=text("'BDT'"), nullable=False
    )
    status: Mapped[PaymentRecordStatus] = mapped_column(
        db_enum(PaymentRecordStatus, "payment_record_status"),
        default=PaymentRecordStatus.PENDING,
        nullable=False,
    )
    raw_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    order: Mapped[Order] = relationship(back_populates="payments")


class Shipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("courier", "consignment_id"),
        Index("ix_shipments_order_created_at", "order_id", "created_at"),
        Index("ix_shipments_tracking_code", "tracking_code"),
        Index("ix_shipments_status_updated_at", "status", "updated_at"),
    )

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    courier: Mapped[CourierProvider] = mapped_column(
        db_enum(CourierProvider, "courier_provider"), nullable=False
    )
    consignment_id: Mapped[str | None] = mapped_column(String(255))
    tracking_code: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ShipmentStatus] = mapped_column(
        db_enum(ShipmentStatus, "shipment_status"),
        default=ShipmentStatus.PENDING,
        nullable=False,
    )
    raw: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="shipments")


class Review(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "user_id"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_range"),
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint(
            "NOT is_verified_purchase OR purchase_order_item_id IS NOT NULL",
            name="verified_purchase_has_lineage",
        ),
        Index("ix_reviews_product_status_created", "product_id", "status", "created_at"),
        Index("ix_reviews_user_created_at", "user_id", "created_at"),
        Index("ix_reviews_user_updated_id", "user_id", "updated_at", "id"),
        Index(
            "ix_reviews_approved_product_created_id",
            "product_id",
            "created_at",
            "id",
            postgresql_where=text("status = 'approved'"),
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    photos: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]"), nullable=False
    )
    status: Mapped[ReviewStatus] = mapped_column(
        db_enum(ReviewStatus, "review_status"),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    purchase_order_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT")
    )
    author_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderated_by_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    moderation_note: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(String(500))

    product: Mapped[Product] = relationship(back_populates="reviews")
    user: Mapped[User] = relationship(back_populates="reviews", foreign_keys=[user_id])
    purchase_order_item: Mapped[OrderItem | None] = relationship()
    moderator: Mapped[User | None] = relationship(foreign_keys=[moderated_by_id])
    photo_assets: Mapped[list[ReviewPhoto]] = relationship(
        back_populates="review", cascade="save-update, merge"
    )


class ReviewPhoto(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_photos"
    __table_args__ = (
        CheckConstraint("byte_size > 0 AND byte_size <= 5242880", name="byte_size_range"),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="mime_type_allowed",
        ),
        CheckConstraint(
            "state IN ('pending', 'ready', 'attached', 'delete_pending', 'deleted')",
            name="state_allowed",
        ),
        CheckConstraint(
            "sort_order IS NULL OR (sort_order >= 0 AND sort_order < 5)",
            name="sort_order_range",
        ),
        CheckConstraint("width IS NULL OR width > 0", name="width_positive"),
        CheckConstraint("height IS NULL OR height > 0", name="height_positive"),
        UniqueConstraint("provider", "public_id", name="uq_review_photos_provider_public_id"),
        Index(
            "uq_review_photos_provider_asset_id",
            "provider",
            "provider_asset_id",
            unique=True,
            postgresql_where=text("provider_asset_id IS NOT NULL"),
        ),
        Index(
            "uq_review_photos_review_sort",
            "review_id",
            "sort_order",
            unique=True,
            postgresql_where=text("review_id IS NOT NULL"),
        ),
        Index("ix_review_photos_user_state_created_id", "user_id", "state", "created_at", "id"),
        Index(
            "ix_review_photos_cleanup",
            "state",
            "cleanup_after",
            postgresql_where=text("state IN ('pending', 'ready', 'delete_pending')"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    review_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    folder: Mapped[str] = mapped_column(String(255), nullable=False)
    public_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_asset_id: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(16))
    alt_text: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int | None] = mapped_column(SmallInteger)
    state: Mapped[str] = mapped_column(
        String(24), default="pending", server_default=text("'pending'"), nullable=False
    )
    signature_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    signature_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    user: Mapped[User] = relationship()
    review: Mapped[Review | None] = relationship(back_populates="photo_assets")


class WishlistItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        Index("ix_wishlist_items_user_created_at", "user_id", "created_at"),
        Index("ix_wishlist_items_user_created_id", "user_id", "created_at", "id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    user: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()


class RecentlyViewed(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "recently_viewed"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        Index("ix_recently_viewed_user_viewed_at", "user_id", "viewed_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship()
    product: Mapped[Product] = relationship()


class SupportTicket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint("revision > 0", name="revision_positive"),
        CheckConstraint("number ~ '^BJ-SUP-[0-9]{4}-[0-9]{6}$'", name="number_format"),
        Index("ix_support_tickets_user_created_at", "user_id", "created_at"),
        Index(
            "ix_support_tickets_user_public_last_message_id",
            "user_id",
            "public_last_message_at",
            "id",
        ),
        Index(
            "ix_support_tickets_user_status_public_last_message_id",
            "user_id",
            "status",
            "public_last_message_at",
            "id",
        ),
        Index("ix_support_tickets_status_priority", "status", "priority"),
    )

    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    order_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        db_enum(TicketStatus, "ticket_status"), default=TicketStatus.OPEN, nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        db_enum(TicketPriority, "ticket_priority"),
        default=TicketPriority.NORMAL,
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    public_last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    customer_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    order: Mapped[Order | None] = relationship()
    messages: Mapped[list[SupportMessage]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )


class SupportMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        Index("ix_support_messages_ticket_created_at", "ticket_id", "created_at"),
        Index("ix_support_messages_ticket_created_id", "ticket_id", "created_at", "id"),
    )

    ticket_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_type: Mapped[MessageAuthor] = mapped_column(
        db_enum(MessageAuthor, "message_author"), nullable=False
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]"), nullable=False
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship()


class SupportTicketNumberCounter(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "support_ticket_number_counters"
    __table_args__ = (
        CheckConstraint("year >= 2020 AND year <= 9999", name="year_range"),
        CheckConstraint("next_value >= 1 AND next_value <= 1000000", name="next_value_range"),
    )

    year: Mapped[int] = mapped_column(SmallInteger, unique=True, nullable=False)
    next_value: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class Banner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "banners"
    __table_args__ = (
        CheckConstraint("sort >= 0", name="sort_nonnegative"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", name="dates"
        ),
        Index("ix_banners_placement_visible_sort", "placement", "is_visible", "sort"),
        Index("ix_banners_visible_dates", "is_visible", "starts_at", "ends_at"),
    )

    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    placement: Mapped[str] = mapped_column(String(80), nullable=False)
    title_bn: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle_bn: Mapped[str | None] = mapped_column(String(320))
    subtitle_en: Mapped[str | None] = mapped_column(String(320))
    image_bn: Mapped[str] = mapped_column(Text, nullable=False)
    image_en: Mapped[str] = mapped_column(Text, nullable=False)
    href: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        "sort", Integer, default=0, server_default=text("0"), nullable=False
    )
    is_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HomepageSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "homepage_sections"
    __table_args__ = (
        CheckConstraint('"order" >= 1 AND "order" <= 15', name="order_range"),
        Index("ix_homepage_sections_visible_order", "is_visible", "order"),
    )

    section_type: Mapped[HomepageSectionType] = mapped_column(
        "type", db_enum(HomepageSectionType, "homepage_section_type"), unique=True, nullable=False
    )
    sort_order: Mapped[int] = mapped_column("order", SmallInteger, unique=True, nullable=False)
    is_visible: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    content_bn: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    content_en: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )


class StaticPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "static_pages"
    __table_args__ = (Index("ix_static_pages_published_updated", "is_published", "updated_at"),)

    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    title_bn: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    body_bn: Mapped[str] = mapped_column(Text, nullable=False)
    body_en: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class SiteSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_at", "actor", "at"),
        Index("ix_audit_logs_entity_entity_id_at", "entity", "entity_id", "at"),
        Index("ix_audit_logs_action_at", "action", "at"),
    )

    actor_id: Mapped[UUID | None] = mapped_column(
        "actor", PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    entity: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    diff: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(INET)
    request_id: Mapped[str | None] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    actor: Mapped[User | None] = relationship()


class WebhookEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_provider_processed", "provider", "processed_at"),
        Index(
            "ix_webhook_events_unprocessed",
            "created_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )

    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
