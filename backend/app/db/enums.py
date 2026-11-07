"""Database-backed domain enumerations."""

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class AuthSessionKind(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CartStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"
    ABANDONED = "abandoned"


class CouponType(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"
    FREE_SHIPPING = "free_shipping"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(StrEnum):
    COD = "cod"
    BKASH = "bkash"
    NAGAD = "nagad"
    SSLCOMMERZ = "sslcommerz"


class PaymentRecordStatus(StrEnum):
    PENDING = "pending"
    INITIATED = "initiated"
    PROCESSING = "processing"
    AUTHORIZED = "authorized"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"
    # Kept only so databases upgraded from Phase 5 can deserialize legacy rows.
    REFUNDED = "refunded"


class RefundStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class RefundMode(StrEnum):
    PROVIDER = "provider"
    MANUAL = "manual"


class ProviderMode(StrEnum):
    DISABLED = "disabled"
    MOCK = "mock"
    SANDBOX = "sandbox"
    LIVE = "live"


class CourierProvider(StrEnum):
    PATHAO = "pathao"
    STEADFAST = "steadfast"
    REDX = "redx"
    MANUAL = "manual"
    MOCK = "mock"


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    UNKNOWN = "unknown"
    BOOKED = "booked"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageAuthor(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class HomepageSectionType(StrEnum):
    HERO = "hero"
    MARQUEE = "marquee"
    PROMO_CHIPS = "promo_chips"
    FLASH_SALE = "flash_sale"
    BEST_SELLER_CATEGORIES = "best_seller_categories"
    BEST_SELLING = "best_selling"
    FEATURE_BANDS = "feature_bands"
    FEATURED_CATEGORY_BAND = "featured_category_band"
    COMPARISON = "comparison"
    SOCIAL_PROOF = "social_proof"
    SHIPPING_OFFER = "shipping_offer"
    BRAND_STORY = "brand_story"
    REVIEWS = "reviews"
    DEALS = "deals"
    FOOTER = "footer"


class MediaPurpose(StrEnum):
    PRODUCT = "product"
    CATEGORY = "category"
    BRAND = "brand"
    BANNER = "banner"
    PAGE = "page"
    BLOG = "blog"
    LOGO = "logo"


class MediaState(StrEnum):
    PENDING = "pending"
    READY = "ready"
    DELETE_PENDING = "delete_pending"
    DELETED = "deleted"


class CatalogImportStatus(StrEnum):
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    IMPORTED = "imported"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookKind(StrEnum):
    PAYMENT = "payment"
    COURIER = "courier"


class WebhookVerificationStatus(StrEnum):
    VERIFIED = "verified"
    PENDING_VALIDATION = "pending_validation"
    LEGACY_UNKNOWN = "legacy_unknown"


class WebhookProcessingStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    IGNORED = "ignored"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


class ProviderGeoLevel(StrEnum):
    DIVISION = "division"
    DISTRICT = "district"
    UPAZILA = "upazila"
