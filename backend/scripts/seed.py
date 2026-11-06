"""Idempotently seed and upgrade Bojro's Phase 2 demonstration data."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import cast
from uuid import UUID

import structlog
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import FromClause

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.enums import (  # noqa: E402
    CouponType,
    HomepageSectionType,
    ProductStatus,
    ReviewStatus,
    UserRole,
)
from app.db.models import (  # noqa: E402
    Banner,
    Brand,
    Category,
    Coupon,
    FlashSale,
    FlashSaleItem,
    GeoDistrict,
    GeoDivision,
    GeoUpazila,
    HomepageSection,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    SiteSetting,
    StaticPage,
    User,
)
from app.db.session import create_engine, create_session_factory  # noqa: E402
from app.utils.uuid7 import uuid7  # noqa: E402

_LOGGER = structlog.get_logger(__name__)
_GEO_PATH = BACKEND_DIR / "app" / "seed_data" / "bangladesh_geo.json"
_PASSWORD_HASHER = PasswordHasher()
_DEMO_SEED_KEY = "_demo_seed_version"


class GeoMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coverage_as_of: str
    coverage_status: str
    expected_counts: dict[str, int]


class DivisionSeed(BaseModel):
    code: str
    name_en: str
    name_bn: str


class DistrictSeed(BaseModel):
    code: str
    division_code: str
    name_en: str
    name_bn: str


class UpazilaSeed(BaseModel):
    code: str
    district_code: str
    name_en: str
    name_bn: str


class GeoDataset(BaseModel):
    metadata: GeoMetadata
    divisions: list[DivisionSeed]
    districts: list[DistrictSeed]
    upazilas: list[UpazilaSeed]


@dataclass(frozen=True, slots=True)
class ProductSeed:
    slug: str
    category: str
    brand: str
    name_bn: str
    name_en: str


CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("skincare", "ত্বকের যত্ন", "Skincare", "sparkle"),
    ("haircare", "চুলের যত্ন", "Haircare", "drop"),
    ("personal-care", "ব্যক্তিগত যত্ন", "Personal Care", "heart"),
    ("home-kitchen", "ঘর ও রান্নাঘর", "Home & Kitchen", "house"),
    ("fashion", "ফ্যাশন", "Fashion", "t-shirt"),
    ("electronics", "ইলেকট্রনিকস", "Electronics", "lightning"),
    ("baby-care", "শিশুর যত্ন", "Baby Care", "baby"),
    ("groceries", "মুদি ও খাবার", "Groceries", "basket"),
)

BRANDS: tuple[tuple[str, str], ...] = (
    ("bojro-essentials", "Bojro Essentials"),
    ("prakriti", "Prakriti"),
    ("dhaka-craft", "Dhaka Craft"),
    ("technova", "TechNova"),
    ("shishucare", "ShishuCare"),
)

PRODUCTS: tuple[ProductSeed, ...] = (
    ProductSeed(
        "gentle-neem-face-wash", "skincare", "prakriti", "কোমল নিম ফেস ওয়াশ", "Gentle Neem Face Wash"
    ),
    ProductSeed(
        "vitamin-c-glow-serum",
        "skincare",
        "bojro-essentials",
        "ভিটামিন সি গ্লো সিরাম",
        "Vitamin C Glow Serum",
    ),
    ProductSeed(
        "aloe-hydrating-gel", "skincare", "prakriti", "অ্যালোভেরা হাইড্রেটিং জেল", "Aloe Hydrating Gel"
    ),
    ProductSeed(
        "daily-spf50-sunscreen",
        "skincare",
        "bojro-essentials",
        "ডেইলি এসপিএফ ৫০ সানস্ক্রিন",
        "Daily SPF 50 Sunscreen",
    ),
    ProductSeed(
        "rice-water-moisturizer",
        "skincare",
        "prakriti",
        "রাইস ওয়াটার ময়েশ্চারাইজার",
        "Rice Water Moisturizer",
    ),
    ProductSeed(
        "virgin-coconut-hair-oil",
        "haircare",
        "prakriti",
        "ভার্জিন নারিকেল হেয়ার অয়েল",
        "Virgin Coconut Hair Oil",
    ),
    ProductSeed(
        "onion-strength-shampoo",
        "haircare",
        "bojro-essentials",
        "অনিয়ন স্ট্রেংথ শ্যাম্পু",
        "Onion Strength Shampoo",
    ),
    ProductSeed(
        "keratin-repair-conditioner",
        "haircare",
        "bojro-essentials",
        "কেরাটিন রিপেয়ার কন্ডিশনার",
        "Keratin Repair Conditioner",
    ),
    ProductSeed("herbal-hair-mask", "haircare", "prakriti", "হারবাল হেয়ার মাস্ক", "Herbal Hair Mask"),
    ProductSeed(
        "anti-dandruff-tonic",
        "haircare",
        "prakriti",
        "অ্যান্টি ড্যানড্রাফ টনিক",
        "Anti-Dandruff Scalp Tonic",
    ),
    ProductSeed(
        "rose-body-wash", "personal-care", "bojro-essentials", "রোজ বডি ওয়াশ", "Rose Body Wash"
    ),
    ProductSeed(
        "charcoal-cleansing-bar",
        "personal-care",
        "prakriti",
        "চারকোল ক্লিনজিং বার",
        "Charcoal Cleansing Bar",
    ),
    ProductSeed(
        "lemon-hand-wash", "personal-care", "bojro-essentials", "লেমন হ্যান্ড ওয়াশ", "Lemon Hand Wash"
    ),
    ProductSeed(
        "shea-butter-lip-balm",
        "personal-care",
        "prakriti",
        "শিয়া বাটার লিপ বাম",
        "Shea Butter Lip Balm",
    ),
    ProductSeed(
        "fresh-deo-roll-on",
        "personal-care",
        "bojro-essentials",
        "ফ্রেশ ডিও রোল-অন",
        "Fresh Deo Roll-On",
    ),
    ProductSeed(
        "steel-thermal-bottle",
        "home-kitchen",
        "bojro-essentials",
        "স্টিল থার্মাল বোতল",
        "Steel Thermal Bottle",
    ),
    ProductSeed(
        "twelve-jar-spice-organizer",
        "home-kitchen",
        "dhaka-craft",
        "১২ জার মসলা অর্গানাইজার",
        "12-Jar Spice Organizer",
    ),
    ProductSeed(
        "microfiber-towel-set",
        "home-kitchen",
        "bojro-essentials",
        "মাইক্রোফাইবার তোয়ালে সেট",
        "Microfiber Towel Set",
    ),
    ProductSeed(
        "rechargeable-emergency-light",
        "home-kitchen",
        "technova",
        "রিচার্জেবল ইমার্জেন্সি লাইট",
        "Rechargeable Emergency Light",
    ),
    ProductSeed(
        "bamboo-cutting-board",
        "home-kitchen",
        "dhaka-craft",
        "বাঁশের কাটিং বোর্ড",
        "Bamboo Cutting Board",
    ),
    ProductSeed(
        "jamdani-cotton-scarf", "fashion", "dhaka-craft", "জামদানি কটন স্কার্ফ", "Jamdani Cotton Scarf"
    ),
    ProductSeed(
        "classic-cotton-panjabi",
        "fashion",
        "dhaka-craft",
        "ক্লাসিক কটন পাঞ্জাবি",
        "Classic Cotton Panjabi",
    ),
    ProductSeed(
        "soft-muslin-saree", "fashion", "dhaka-craft", "সফট মসলিন শাড়ি", "Soft Muslin Saree"
    ),
    ProductSeed(
        "handcrafted-leather-wallet",
        "fashion",
        "dhaka-craft",
        "হাতে তৈরি লেদার ওয়ালেট",
        "Handcrafted Leather Wallet",
    ),
    ProductSeed(
        "everyday-canvas-tote",
        "fashion",
        "bojro-essentials",
        "এভরিডে ক্যানভাস টোট",
        "Everyday Canvas Tote",
    ),
    ProductSeed(
        "compact-tws-earbuds",
        "electronics",
        "technova",
        "কমপ্যাক্ট টিডব্লিউএস ইয়ারবাড",
        "Compact TWS Earbuds",
    ),
    ProductSeed(
        "10000mah-fast-power-bank",
        "electronics",
        "technova",
        "১০০০০ এমএএইচ ফাস্ট পাওয়ার ব্যাংক",
        "10000mAh Fast Power Bank",
    ),
    ProductSeed(
        "touch-led-desk-lamp",
        "electronics",
        "technova",
        "টাচ এলইডি ডেস্ক ল্যাম্প",
        "Touch LED Desk Lamp",
    ),
    ProductSeed(
        "dual-port-smart-charger",
        "electronics",
        "technova",
        "ডুয়াল পোর্ট স্মার্ট চার্জার",
        "Dual-Port Smart Charger",
    ),
    ProductSeed(
        "mini-bluetooth-speaker",
        "electronics",
        "technova",
        "মিনি ব্লুটুথ স্পিকার",
        "Mini Bluetooth Speaker",
    ),
    ProductSeed(
        "gentle-baby-lotion", "baby-care", "shishucare", "জেন্টল বেবি লোশন", "Gentle Baby Lotion"
    ),
    ProductSeed(
        "head-to-toe-baby-wash",
        "baby-care",
        "shishucare",
        "হেড টু টো বেবি ওয়াশ",
        "Head-to-Toe Baby Wash",
    ),
    ProductSeed("soft-dry-diapers", "baby-care", "shishucare", "সফট ড্রাই ডায়াপার", "Soft Dry Diapers"),
    ProductSeed(
        "anti-colic-feeding-bottle",
        "baby-care",
        "shishucare",
        "অ্যান্টি-কলিক ফিডিং বোতল",
        "Anti-Colic Feeding Bottle",
    ),
    ProductSeed(
        "hooded-cotton-baby-towel",
        "baby-care",
        "shishucare",
        "হুডেড কটন বেবি তোয়ালে",
        "Hooded Cotton Baby Towel",
    ),
    ProductSeed(
        "cold-pressed-mustard-oil",
        "groceries",
        "prakriti",
        "ঘানি ভাঙা সরিষার তেল",
        "Cold-Pressed Mustard Oil",
    ),
    ProductSeed("pure-cow-ghee", "groceries", "prakriti", "খাঁটি গরুর ঘি", "Pure Cow Ghee"),
    ProductSeed(
        "sundarban-forest-honey", "groceries", "prakriti", "সুন্দরবনের মধু", "Sundarban Forest Honey"
    ),
    ProductSeed(
        "premium-sreemangal-tea",
        "groceries",
        "prakriti",
        "প্রিমিয়াম শ্রীমঙ্গল চা",
        "Premium Sreemangal Tea",
    ),
    ProductSeed(
        "essential-bengali-spice-box",
        "groceries",
        "bojro-essentials",
        "বাঙালি এসেনশিয়াল মসলা বক্স",
        "Essential Bengali Spice Box",
    ),
)

REVIEW_BODIES: tuple[tuple[str, str], ...] = (
    ("প্যাকেজিং সুন্দর ছিল এবং পণ্যটি সময়মতো পেয়েছি।", "Beautiful packaging and delivered on time."),
    ("দামের তুলনায় মান খুব ভালো, আবার কিনব।", "Excellent value for money; I will buy again."),
    (
        "ব্যবহার করে ভালো ফল পেয়েছি, একদম আসল পণ্য।",
        "Good results after use and the product feels authentic.",
    ),
    (
        "ডেলিভারি দ্রুত ছিল, পরিবারের সবাই পছন্দ করেছে।",
        "Delivery was quick and the whole family liked it.",
    ),
    ("বর্ণনার সঙ্গে পণ্যটি পুরোপুরি মিলে গেছে।", "The product matched its description perfectly."),
)

HOMEPAGE_SECTIONS: tuple[tuple[HomepageSectionType, str, str], ...] = (
    (
        HomepageSectionType.HERO,
        "আপনার প্রতিদিনের পছন্দ, এখন আরও সহজ",
        "Everyday favourites, delivered simply",
    ),
    (
        HomepageSectionType.MARQUEE,
        "১০০% অথেনটিক · ক্যাশ অন ডেলিভারি · ফাস্ট ডেলিভারি",
        "100% authentic · Cash on delivery · Fast delivery",
    ),
    (
        HomepageSectionType.PROMO_CHIPS,
        "নতুন পণ্য · সেরা দাম · নিশ্চিন্ত কেনাকাটা",
        "Latest drops · Lowest prices · Shop confidently",
    ),
    (HomepageSectionType.FLASH_SALE, "ঝটপট ফ্ল্যাশ সেল", "Lightning Flash Sale"),
    (HomepageSectionType.BEST_SELLER_CATEGORIES, "আমাদের সেরা ক্যাটাগরি", "Meet Our Best Sellers"),
    (HomepageSectionType.BEST_SELLING, "সবচেয়ে বেশি বিক্রি", "Best Selling"),
    (
        HomepageSectionType.FEATURE_BANDS,
        "প্রয়োজনের সবকিছু এক ঠিকানায়",
        "Everything you need in one place",
    ),
    (HomepageSectionType.FEATURED_CATEGORY_BAND, "এই সপ্তাহের পছন্দ", "This Week's Picks"),
    (HomepageSectionType.COMPARISON, "বজ্র কেন আলাদা", "Why Bojro Stands Apart"),
    (HomepageSectionType.SOCIAL_PROOF, "বজ্র পরিবারের সঙ্গে যোগ দিন", "Join the Bojro Family"),
    (
        HomepageSectionType.SHIPPING_OFFER,
        "৳১৫০০+ অর্ডারে ফ্রি ডেলিভারি",
        "Free Delivery on Orders over ৳1500",
    ),
    (
        HomepageSectionType.BRAND_STORY,
        "বাংলাদেশের জন্য বিশ্বাসের কেনাকাটা",
        "Trusted Shopping, Built for Bangladesh",
    ),
    (HomepageSectionType.REVIEWS, "ক্রেতারা যা বলছেন", "What Customers Say"),
    (HomepageSectionType.DEALS, "যে ডিলগুলো মিস করা যাবে না", "Deals You Can't Miss"),
    (HomepageSectionType.FOOTER, "বজ্রের সঙ্গে থাকুন", "Stay Connected with Bojro"),
)


def homepage_content_v2() -> dict[HomepageSectionType, tuple[dict[str, object], dict[str, object]]]:
    """Return fresh rich content; callers may safely merge it without shared mutation."""

    content: dict[HomepageSectionType, tuple[dict[str, object], dict[str, object]]] = {
        section_type: (
            {"title": title_bn, "eyebrow": "বজ্র", "cta": "এখনই দেখুন"},
            {"title": title_en, "eyebrow": "Bojro", "cta": "Explore now"},
        )
        for section_type, title_bn, title_en in HOMEPAGE_SECTIONS
    }
    content[HomepageSectionType.HERO][0].update(
        {
            "description": "দেশজুড়ে আসল পণ্য, স্বচ্ছ দাম ও নির্ভরযোগ্য ডেলিভারি।",
            "primary_target": "catalog:all",
            "benefits": [
                {"label": "আসল পণ্যের নিশ্চয়তা", "icon": "shield-check"},
                {"label": "ক্যাশ অন ডেলিভারি", "icon": "wallet"},
                {"label": "সহজ রিটার্ন", "icon": "rotate-left"},
            ],
        }
    )
    content[HomepageSectionType.HERO][1].update(
        {
            "description": "Authentic products, clear prices, and dependable delivery nationwide.",
            "primary_target": "catalog:all",
            "benefits": [
                {"label": "Authenticity guaranteed", "icon": "shield-check"},
                {"label": "Cash on delivery", "icon": "wallet"},
                {"label": "Easy returns", "icon": "rotate-left"},
            ],
        }
    )
    content[HomepageSectionType.MARQUEE][0].update(
        {
            "items": [
                "১০০% অথেনটিক পণ্য",
                "সারা দেশে ডেলিভারি",
                "নিরাপদ ক্যাশ অন ডেলিভারি",
                "সহজ রিটার্ন সহায়তা",
            ],
            "speed_seconds": 28,
        }
    )
    content[HomepageSectionType.MARQUEE][1].update(
        {
            "items": [
                "100% authentic products",
                "Nationwide delivery",
                "Secure cash on delivery",
                "Simple return support",
            ],
            "speed_seconds": 28,
        }
    )
    content[HomepageSectionType.PROMO_CHIPS][0].update(
        {
            "chips": [
                {"label": "নতুন এসেছে", "target": "collection:newest"},
                {"label": "সেরা বিক্রি", "target": "collection:best_selling"},
                {"label": "আজকের ডিল", "target": "collection:deals"},
                {"label": "৳১৫০০+ ফ্রি ডেলিভারি", "target": "offer:free_shipping"},
            ]
        }
    )
    content[HomepageSectionType.PROMO_CHIPS][1].update(
        {
            "chips": [
                {"label": "New arrivals", "target": "collection:newest"},
                {"label": "Best sellers", "target": "collection:best_selling"},
                {"label": "Today's deals", "target": "collection:deals"},
                {"label": "Free delivery over ৳1500", "target": "offer:free_shipping"},
            ]
        }
    )
    content[HomepageSectionType.FLASH_SALE][0].update(
        {
            "subtitle": "সময় শেষ হওয়ার আগেই পছন্দের পণ্যটি নিন।",
            "countdown": {"enabled": True, "source": "sale_end"},
            "view_all_target": "collection:deals",
        }
    )
    content[HomepageSectionType.FLASH_SALE][1].update(
        {
            "subtitle": "Pick your favourites before the clock runs out.",
            "countdown": {"enabled": True, "source": "sale_end"},
            "view_all_target": "collection:deals",
        }
    )
    content[HomepageSectionType.BEST_SELLER_CATEGORIES][0].update(
        {"subtitle": "ক্রেতাদের সবচেয়ে পছন্দের বিভাগ", "max_items": 4}
    )
    content[HomepageSectionType.BEST_SELLER_CATEGORIES][1].update(
        {"subtitle": "The categories customers return to", "max_items": 4}
    )
    content[HomepageSectionType.BEST_SELLING][0].update(
        {"subtitle": "সারা দেশে জনপ্রিয় পণ্য", "view_all_target": "collection:best_selling"}
    )
    content[HomepageSectionType.BEST_SELLING][1].update(
        {
            "subtitle": "Popular products across Bangladesh",
            "view_all_target": "collection:best_selling",
        }
    )
    content[HomepageSectionType.FEATURE_BANDS][0].update(
        {
            "bands": [
                {
                    "title": "ঘরের প্রতিদিনের প্রয়োজন",
                    "description": "রান্নাঘর ও ঘর গোছানোর বাছাই করা পণ্য।",
                    "target": "category:home-kitchen",
                    "image": "/seed/feature-home.svg",
                },
                {
                    "title": "নিজের যত্ন, নিজের মতো",
                    "description": "স্কিনকেয়ার ও পার্সোনাল কেয়ারের বিশ্বস্ত পছন্দ।",
                    "target": "category:skincare",
                    "image": "/seed/feature-care.svg",
                },
            ]
        }
    )
    content[HomepageSectionType.FEATURE_BANDS][1].update(
        {
            "bands": [
                {
                    "title": "Everyday home essentials",
                    "description": "Selected kitchen and home-organisation products.",
                    "target": "category:home-kitchen",
                    "image": "/seed/feature-home.svg",
                },
                {
                    "title": "Personal care, your way",
                    "description": "Dependable skincare and personal-care picks.",
                    "target": "category:skincare",
                    "image": "/seed/feature-care.svg",
                },
            ]
        }
    )
    content[HomepageSectionType.FEATURED_CATEGORY_BAND][0].update(
        {
            "category": "groceries",
            "headline": "বাংলার স্বাদ, বিশ্বস্ত উৎস থেকে",
            "description": "তেল, ঘি, মধু ও চায়ের বাছাই করা সংগ্রহ।",
            "target": "category:groceries",
            "image": "/seed/feature-groceries.svg",
            "categories": [
                {
                    "slug": "groceries",
                    "title": "বিশ্বস্ত গ্রোসারি",
                    "description": "তেল, ঘি, মধু ও চায়ের বাছাই করা সংগ্রহ।",
                    "target": "category:groceries",
                    "image": "/seed/feature-groceries.svg",
                },
                {
                    "slug": "fashion",
                    "title": "প্রতিদিনের ফ্যাশন",
                    "description": "আরামদায়ক ও ব্যবহারিক পোশাকের পছন্দ।",
                    "target": "category:fashion",
                    "image": "/seed/feature-fashion.svg",
                },
                {
                    "slug": "electronics",
                    "title": "স্মার্ট ইলেকট্রনিকস",
                    "description": "দৈনন্দিন কাজ সহজ করা নির্ভরযোগ্য ডিভাইস।",
                    "target": "category:electronics",
                    "image": "/seed/feature-electronics.svg",
                },
            ],
        }
    )
    content[HomepageSectionType.FEATURED_CATEGORY_BAND][1].update(
        {
            "category": "groceries",
            "headline": "Flavours of Bangladesh, from trusted sources",
            "description": "A selected range of oils, ghee, honey, and tea.",
            "target": "category:groceries",
            "image": "/seed/feature-groceries.svg",
            "categories": [
                {
                    "slug": "groceries",
                    "title": "Trusted groceries",
                    "description": "A selected range of oils, ghee, honey, and tea.",
                    "target": "category:groceries",
                    "image": "/seed/feature-groceries.svg",
                },
                {
                    "slug": "fashion",
                    "title": "Everyday fashion",
                    "description": "Comfortable and practical clothing picks.",
                    "target": "category:fashion",
                    "image": "/seed/feature-fashion.svg",
                },
                {
                    "slug": "electronics",
                    "title": "Smart electronics",
                    "description": "Dependable devices that simplify everyday tasks.",
                    "target": "category:electronics",
                    "image": "/seed/feature-electronics.svg",
                },
            ],
        }
    )
    content[HomepageSectionType.COMPARISON][0].update(
        {
            "columns": ["বজ্র", "সাধারণ মার্কেটপ্লেস"],
            "rows": [
                {"label": "পণ্যের উৎস যাচাই", "bojro": True, "other": False},
                {"label": "দাম ও ডেলিভারি চার্জ আগে থেকেই স্পষ্ট", "bojro": True, "other": False},
                {"label": "বাংলায় সহায়তা", "bojro": True, "other": False},
                {"label": "সহজ রিটার্ন নির্দেশনা", "bojro": True, "other": False},
            ],
        }
    )
    content[HomepageSectionType.COMPARISON][1].update(
        {
            "columns": ["Bojro", "Typical marketplace"],
            "rows": [
                {"label": "Product sources checked", "bojro": True, "other": False},
                {"label": "Prices and delivery fees shown upfront", "bojro": True, "other": False},
                {"label": "Bangla support", "bojro": True, "other": False},
                {"label": "Clear return guidance", "bojro": True, "other": False},
            ],
        }
    )
    content[HomepageSectionType.SOCIAL_PROOF][0].update(
        {
            "subtitle": "বাংলাদেশের নানা প্রান্তের ক্রেতাদের দৈনন্দিন পছন্দ।",
            "stats": [
                {"value": "40+", "label": "বাছাই করা পণ্য"},
                {"value": "8", "label": "জনপ্রিয় বিভাগ"},
                {"value": "64", "label": "জেলায় ডেলিভারি কভারেজ"},
            ],
            "gallery": [
                "/seed/social-proof-1.svg",
                "/seed/social-proof-2.svg",
                "/seed/social-proof-3.svg",
            ],
        }
    )
    content[HomepageSectionType.SOCIAL_PROOF][1].update(
        {
            "subtitle": "Everyday picks for customers across Bangladesh.",
            "stats": [
                {"value": "40+", "label": "Selected products"},
                {"value": "8", "label": "Popular categories"},
                {"value": "64", "label": "Districts covered"},
            ],
            "gallery": [
                "/seed/social-proof-1.svg",
                "/seed/social-proof-2.svg",
                "/seed/social-proof-3.svg",
            ],
        }
    )
    content[HomepageSectionType.SHIPPING_OFFER][0].update(
        {
            "description": "এক অর্ডারে বেশি কিনুন, ডেলিভারি চার্জ বাঁচান।",
            "threshold_poisha": 150_000,
            "target": "offer:free_shipping",
            "code": "FREESHIP",
        }
    )
    content[HomepageSectionType.SHIPPING_OFFER][1].update(
        {
            "description": "Bundle everyday needs and save the delivery charge.",
            "threshold_poisha": 150_000,
            "target": "offer:free_shipping",
            "code": "FREESHIP",
        }
    )
    content[HomepageSectionType.BRAND_STORY][0].update(
        {
            "paragraphs": [
                (
                    "বজ্র তৈরি হয়েছে বাংলাদেশের মানুষের অনলাইন কেনাকাটাকে সহজ, স্বচ্ছ ও "
                    "নির্ভরযোগ্য করার লক্ষ্য নিয়ে। আমরা দৈনন্দিন প্রয়োজনের পণ্য বাছাই করি "
                    "উৎস, মূল্য ও ব্যবহারিক মান বিবেচনা করে।"
                ),
                (
                    "আমাদের লক্ষ্য শুধু পণ্য পৌঁছে দেওয়া নয়; বাংলায় স্পষ্ট তথ্য, পরিচিত "
                    "পেমেন্ট পদ্ধতি ও প্রয়োজনে মানুষের সহায়তা দিয়ে দীর্ঘমেয়াদি আস্থা গড়ে তোলা।"
                ),
            ],
            "image": "/seed/brand-story.svg",
            "target": "page:about",
        }
    )
    content[HomepageSectionType.BRAND_STORY][1].update(
        {
            "paragraphs": [
                (
                    "Bojro was built to make online shopping in Bangladesh simpler, clearer, "
                    "and more dependable. We select everyday products with their source, price, "
                    "and practical quality in mind."
                ),
                (
                    "Our goal is not only to deliver products, but to earn lasting trust through "
                    "clear Bangla information, familiar payment methods, and helpful human support "
                    "when it matters."
                ),
            ],
            "image": "/seed/brand-story.svg",
            "target": "page:about",
        }
    )
    content[HomepageSectionType.REVIEWS][0].update(
        {
            "subtitle": "অনুমোদিত ক্রেতা মতামত থেকে সাম্প্রতিক অভিজ্ঞতা।",
            "max_items": 8,
            "verified_badge_requires_order": True,
        }
    )
    content[HomepageSectionType.REVIEWS][1].update(
        {
            "subtitle": "Recent experiences from approved customer reviews.",
            "max_items": 8,
            "verified_badge_requires_order": True,
        }
    )
    content[HomepageSectionType.DEALS][0].update(
        {
            "subtitle": "কার্যকর ছাড় অনুযায়ী সাজানো বর্তমান অফার।",
            "page_size": 8,
            "sort": "discount_desc",
            "view_all_target": "collection:deals",
        }
    )
    content[HomepageSectionType.DEALS][1].update(
        {
            "subtitle": "Current offers ranked by effective savings.",
            "page_size": 8,
            "sort": "discount_desc",
            "view_all_target": "collection:deals",
        }
    )
    content[HomepageSectionType.FOOTER][0].update(
        {
            "description": "আসল পণ্য ও নির্ভরযোগ্য সেবায় বাংলাদেশের প্রতিদিনের অনলাইন দোকান।",
            "link_groups": [
                {
                    "title": "কেনাকাটা",
                    "links": [
                        {"label": "সব পণ্য", "target": "catalog:all"},
                        {"label": "সেরা বিক্রি", "target": "collection:best_selling"},
                        {"label": "ডিল", "target": "collection:deals"},
                    ],
                },
                {
                    "title": "সহায়তা",
                    "links": [
                        {"label": "সাহায্য", "target": "page:help"},
                        {"label": "রিটার্ন ও রিফান্ড", "target": "page:return-refund"},
                        {"label": "যোগাযোগ", "target": "page:contact"},
                    ],
                },
            ],
            "newsletter": {"enabled": True, "title": "অফার ও নতুন পণ্যের খবর নিন"},
        }
    )
    content[HomepageSectionType.FOOTER][1].update(
        {
            "description": (
                "Bangladesh's everyday online shop for authentic products and dependable service."
            ),
            "link_groups": [
                {
                    "title": "Shop",
                    "links": [
                        {"label": "All products", "target": "catalog:all"},
                        {"label": "Best sellers", "target": "collection:best_selling"},
                        {"label": "Deals", "target": "collection:deals"},
                    ],
                },
                {
                    "title": "Support",
                    "links": [
                        {"label": "Help", "target": "page:help"},
                        {"label": "Return & refund", "target": "page:return-refund"},
                        {"label": "Contact", "target": "page:contact"},
                    ],
                },
            ],
            "newsletter": {"enabled": True, "title": "Get offers and new-product updates"},
        }
    )
    return content


def merge_missing(
    existing: dict[str, object],
    defaults: dict[str, object],
) -> dict[str, object]:
    """Deep-merge missing keys while treating every existing operator value as authoritative."""

    merged = dict(existing)
    for key, default in defaults.items():
        if key not in merged:
            merged[key] = default
            continue
        current = merged[key]
        if isinstance(current, dict) and isinstance(default, dict):
            merged[key] = merge_missing(
                cast(dict[str, object], current),
                cast(dict[str, object], default),
            )
    return merged


@cache
def seed_id(entity: str, natural_key: str) -> UUID:
    """Return one UUIDv7 per seed entity for the lifetime of this process."""

    del entity, natural_key
    return uuid7()


def load_geo_dataset() -> GeoDataset:
    dataset = GeoDataset.model_validate_json(_GEO_PATH.read_text(encoding="utf-8"))
    expected = dataset.metadata.expected_counts
    actual = {
        "divisions": len(dataset.divisions),
        "districts": len(dataset.districts),
        "upazilas": len(dataset.upazilas),
    }
    if actual != expected:
        raise ValueError(f"geo dataset count mismatch: expected {expected}, received {actual}")

    division_codes = {row.code for row in dataset.divisions}
    district_codes = {row.code for row in dataset.districts}
    if len(division_codes) != len(dataset.divisions):
        raise ValueError("duplicate division code in geo dataset")
    if len(district_codes) != len(dataset.districts):
        raise ValueError("duplicate district code in geo dataset")
    if len({row.code for row in dataset.upazilas}) != len(dataset.upazilas):
        raise ValueError("duplicate upazila code in geo dataset")
    if orphaned := [
        row.code for row in dataset.districts if row.division_code not in division_codes
    ]:
        raise ValueError(f"districts reference unknown divisions: {orphaned}")
    if orphaned := [
        row.code for row in dataset.upazilas if row.district_code not in district_codes
    ]:
        raise ValueError(f"upazilas reference unknown districts: {orphaned}")
    return dataset


async def upsert_rows(
    session: AsyncSession,
    table: FromClause,
    rows: list[dict[str, object]],
    *,
    conflict_columns: tuple[str, ...],
    update_columns: tuple[str, ...],
    batch_size: int = 250,
) -> None:
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        statement = insert(table).values(batch)  # type: ignore[arg-type]
        updates: dict[str, object] = {name: statement.excluded[name] for name in update_columns}
        if "updated_at" in table.c:
            updates["updated_at"] = func.now()
        statement = statement.on_conflict_do_update(
            index_elements=[table.c[name] for name in conflict_columns],
            set_=updates,
        )
        await session.execute(statement)


async def seed_geo(session: AsyncSession, dataset: GeoDataset) -> None:
    division_rows = [
        {
            "id": seed_id("geo_division", row.code),
            "code": row.code,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
        }
        for row in dataset.divisions
    ]
    await upsert_rows(
        session,
        GeoDivision.__table__,
        division_rows,
        conflict_columns=("code",),
        update_columns=("name_bn", "name_en"),
    )

    district_rows = [
        {
            "id": seed_id("geo_district", row.code),
            "division_id": seed_id("geo_division", row.division_code),
            "code": row.code,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
        }
        for row in dataset.districts
    ]
    await upsert_rows(
        session,
        GeoDistrict.__table__,
        district_rows,
        conflict_columns=("code",),
        update_columns=("division_id", "name_bn", "name_en"),
    )

    upazila_rows = [
        {
            "id": seed_id("geo_upazila", row.code),
            "district_id": seed_id("geo_district", row.district_code),
            "code": row.code,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
        }
        for row in dataset.upazilas
    ]
    await upsert_rows(
        session,
        GeoUpazila.__table__,
        upazila_rows,
        conflict_columns=("code",),
        update_columns=("district_id", "name_bn", "name_en"),
    )


async def seed_catalog(session: AsyncSession) -> list[UUID]:
    category_rows: list[dict[str, object]] = [
        {
            "id": seed_id("category", slug),
            "parent_id": None,
            "slug": slug,
            "name_bn": name_bn,
            "name_en": name_en,
            "icon": icon,
            "image": "/seed/category-placeholder.svg",
            "sort": sort,
            "is_active": True,
        }
        for sort, (slug, name_bn, name_en, icon) in enumerate(CATEGORIES, start=1)
    ]
    await upsert_rows(
        session,
        Category.__table__,
        category_rows,
        conflict_columns=("slug",),
        update_columns=("name_bn", "name_en", "icon", "image", "sort", "is_active"),
    )

    brand_rows = [
        {"id": seed_id("brand", slug), "slug": slug, "name": name} for slug, name in BRANDS
    ]
    await upsert_rows(
        session,
        Brand.__table__,
        brand_rows,
        conflict_columns=("slug",),
        update_columns=("name",),
    )

    product_rows: list[dict[str, object]] = []
    variant_rows: list[dict[str, object]] = []
    image_rows: list[dict[str, object]] = []
    primary_variant_ids: list[UUID] = []
    for position, product in enumerate(PRODUCTS, start=1):
        product_id = seed_id("product", product.slug)
        rating = 5 if position % 3 else 4
        has_review = position <= 20
        product_rows.append(
            {
                "id": product_id,
                "slug": product.slug,
                "category_id": seed_id("category", product.category),
                "brand_id": seed_id("brand", product.brand),
                "name_bn": product.name_bn,
                "name_en": product.name_en,
                "desc_bn": f"{product.name_bn} দৈনন্দিন ব্যবহারের জন্য বাছাই করা মানসম্মত পণ্য।",
                "desc_en": (
                    f"{product.name_en} is a quality everyday essential selected for Bangladesh."
                ),
                "status": ProductStatus.ACTIVE,
                "is_featured": position <= 8,
                "rating_avg": rating if has_review else 0,
                "rating_count": 1 if has_review else 0,
                "sold_count": 240 - (position * 3),
                "seo_title_bn": f"{product.name_bn} কিনুন | বজ্র",
                "seo_title_en": f"Buy {product.name_en} | Bojro",
                "seo_description_bn": f"বজ্র থেকে আসল {product.name_bn} অর্ডার করুন।",
                "seo_description_en": f"Order authentic {product.name_en} from Bojro.",
            }
        )
        base_price = 19_900 + position * 3_700
        category_option = {
            "fashion": ("size", "M", "L"),
            "electronics": ("color", "Indigo", "Black"),
            "home-kitchen": ("pack", "Single", "Pair"),
        }.get(product.category, ("size", "Standard", "Family"))
        for variant_number, option_value in enumerate(category_option[1:], start=1):
            variant_id = seed_id("variant", f"{product.slug}:{variant_number}")
            if variant_number == 1:
                primary_variant_ids.append(variant_id)
            variant_rows.append(
                {
                    "id": variant_id,
                    "product_id": product_id,
                    "sku": f"BJ-{position:03d}-{variant_number:02d}",
                    "options": {category_option[0]: option_value},
                    "price": base_price + (variant_number - 1) * 15_000,
                    "compare_at_price": base_price + (variant_number - 1) * 15_000 + 12_000,
                    "currency": "BDT",
                    "stock_on_hand": 80 + position,
                    "stock_reserved": 0,
                    "weight_g": 200 + position * 10 + variant_number * 100,
                    "is_active": True,
                }
            )
        for image_number in range(1, 3):
            image_rows.append(
                {
                    "id": seed_id("product_image", f"{product.slug}:{image_number}"),
                    "product_id": product_id,
                    "variant_id": None,
                    "url": "/seed/product-placeholder.svg",
                    "alt": product.name_en,
                    "sort": image_number,
                }
            )

    await upsert_rows(
        session,
        Product.__table__,
        product_rows,
        conflict_columns=("slug",),
        update_columns=(
            "category_id",
            "brand_id",
            "name_bn",
            "name_en",
            "desc_bn",
            "desc_en",
            "status",
            "is_featured",
            "rating_avg",
            "rating_count",
            "sold_count",
            "seo_title_bn",
            "seo_title_en",
            "seo_description_bn",
            "seo_description_en",
        ),
    )
    await upsert_rows(
        session,
        ProductVariant.__table__,
        variant_rows,
        conflict_columns=("sku",),
        update_columns=(
            "product_id",
            "options",
            "price",
            "compare_at_price",
            "currency",
            "stock_on_hand",
            "stock_reserved",
            "weight_g",
            "is_active",
        ),
    )
    await upsert_rows(
        session,
        ProductImage.__table__,
        image_rows,
        conflict_columns=("id",),
        update_columns=("product_id", "variant_id", "url", "alt", "sort"),
    )
    return primary_variant_ids


async def seed_reviews(session: AsyncSession) -> None:
    customer_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    for position, product in enumerate(PRODUCTS[:20], start=1):
        phone = f"+88017{position:08d}"
        customer_id = seed_id("demo_customer", phone)
        customer_rows.append(
            {
                "id": customer_id,
                "role": UserRole.CUSTOMER,
                "name": f"ডেমো ক্রেতা {position}",
                "phone": phone,
                "email": None,
                "password_hash": None,
                "is_guest": False,
            }
        )
        body_bn, body_en = REVIEW_BODIES[(position - 1) % len(REVIEW_BODIES)]
        review_rows.append(
            {
                "id": seed_id("review", product.slug),
                "product_id": seed_id("product", product.slug),
                "user_id": customer_id,
                "rating": 5 if position % 3 else 4,
                "body": f"{body_bn} {body_en}",
                "photos": [],
                "status": ReviewStatus.APPROVED,
                "is_verified_purchase": False,
            }
        )
    await upsert_rows(
        session,
        User.__table__,
        customer_rows,
        conflict_columns=("phone",),
        update_columns=("role", "name", "is_guest"),
    )
    await upsert_rows(
        session,
        Review.__table__,
        review_rows,
        conflict_columns=("product_id", "user_id"),
        update_columns=("rating", "body", "photos", "status", "is_verified_purchase"),
    )


async def seed_promotions(
    session: AsyncSession,
    primary_variant_ids: list[UUID],
    seeded_at: datetime,
) -> None:
    coupon_starts_at = seeded_at - timedelta(days=1)
    coupon_ends_at = seeded_at + timedelta(days=3650)
    sale_starts_at = seeded_at - timedelta(minutes=15)
    sale_ends_at = seeded_at + timedelta(hours=24)
    coupon_rows: list[dict[str, object]] = [
        {
            "id": seed_id("coupon", "BOJRO10"),
            "code": "BOJRO10",
            "type": CouponType.PERCENT,
            "value": 10,
            "min_subtotal": 80_000,
            "max_discount": 30_000,
            "currency": "BDT",
            "usage_limit": 500,
            "usage_count": 0,
            "per_user_limit": 1,
            "starts_at": coupon_starts_at,
            "ends_at": coupon_ends_at,
            "is_active": True,
        },
        {
            "id": seed_id("coupon", "WELCOME150"),
            "code": "WELCOME150",
            "type": CouponType.FIXED,
            "value": 15_000,
            "min_subtotal": 100_000,
            "max_discount": 15_000,
            "currency": "BDT",
            "usage_limit": 1_000,
            "usage_count": 0,
            "per_user_limit": 1,
            "starts_at": coupon_starts_at,
            "ends_at": coupon_ends_at,
            "is_active": True,
        },
        {
            "id": seed_id("coupon", "FREESHIP"),
            "code": "FREESHIP",
            "type": CouponType.FREE_SHIPPING,
            "value": 0,
            "min_subtotal": 150_000,
            "max_discount": None,
            "currency": "BDT",
            "usage_limit": 300,
            "usage_count": 0,
            "per_user_limit": 2,
            "starts_at": coupon_starts_at,
            "ends_at": coupon_ends_at,
            "is_active": True,
        },
    ]
    await upsert_rows(
        session,
        Coupon.__table__,
        coupon_rows,
        conflict_columns=("code",),
        update_columns=(
            "type",
            "value",
            "min_subtotal",
            "max_discount",
            "currency",
            "usage_limit",
            "per_user_limit",
            "starts_at",
            "ends_at",
            "is_active",
        ),
    )

    sale_id = seed_id("flash_sale", "launch-sale")
    await upsert_rows(
        session,
        FlashSale.__table__,
        [
            {
                "id": sale_id,
                "name_bn": "বজ্র লঞ্চ ফ্ল্যাশ সেল",
                "name_en": "Bojro Launch Flash Sale",
                "starts_at": sale_starts_at,
                "ends_at": sale_ends_at,
                "is_active": True,
            }
        ],
        conflict_columns=("id",),
        update_columns=("name_bn", "name_en", "starts_at", "ends_at", "is_active"),
    )
    flash_rows = [
        {
            "id": seed_id("flash_sale_item", str(variant_id)),
            "flash_sale_id": sale_id,
            "variant_id": variant_id,
            "sale_price": 18_900 + position * 3_200,
            "currency": "BDT",
            "qty_limit": 100,
            "sold_qty": position * 2,
        }
        for position, variant_id in enumerate(primary_variant_ids[:8], start=1)
    ]
    await upsert_rows(
        session,
        FlashSaleItem.__table__,
        flash_rows,
        conflict_columns=("flash_sale_id", "variant_id"),
        update_columns=("sale_price", "currency", "qty_limit", "sold_qty"),
    )


async def seed_content(session: AsyncSession) -> None:
    banner_rows: list[dict[str, object]] = [
        {
            "id": seed_id("banner", "authentic-everyday"),
            "slug": "authentic-everyday",
            "placement": "home_hero",
            "title_bn": "আসল পণ্য, নিশ্চিন্ত প্রতিদিন",
            "title_en": "Authentic Essentials for Every Day",
            "subtitle_bn": "সারা বাংলাদেশে দ্রুত ডেলিভারি",
            "subtitle_en": "Fast delivery across Bangladesh",
            "image_bn": "/seed/banner-placeholder.svg",
            "image_en": "/seed/banner-placeholder.svg",
            "href": "catalog:all",
            "sort": 1,
            "is_visible": True,
            "starts_at": None,
            "ends_at": None,
        },
        {
            "id": seed_id("banner", "free-delivery"),
            "slug": "free-delivery",
            "placement": "home_promo",
            "title_bn": "৳১৫০০+ অর্ডারে ফ্রি ডেলিভারি",
            "title_en": "Free Delivery over ৳1500",
            "subtitle_bn": "আজই পছন্দের পণ্য অর্ডার করুন",
            "subtitle_en": "Order your favourites today",
            "image_bn": "/seed/banner-placeholder.svg",
            "image_en": "/seed/banner-placeholder.svg",
            "href": "offer:free_shipping",
            "sort": 2,
            "is_visible": True,
            "starts_at": None,
            "ends_at": None,
        },
        {
            "id": seed_id("banner", "cod-confidence"),
            "slug": "cod-confidence",
            "placement": "home_hero",
            "title_bn": "ক্যাশ অন ডেলিভারিতে সহজ কেনাকাটা",
            "title_en": "Shop Easily with Cash on Delivery",
            "subtitle_bn": "নিরাপদ, স্বচ্ছ ও নির্ভরযোগ্য",
            "subtitle_en": "Safe, clear, and dependable",
            "image_bn": "/seed/banner-placeholder.svg",
            "image_en": "/seed/banner-placeholder.svg",
            "href": "page:help",
            "sort": 3,
            "is_visible": True,
            "starts_at": None,
            "ends_at": None,
        },
    ]
    await upsert_rows(
        session,
        Banner.__table__,
        banner_rows,
        conflict_columns=("slug",),
        update_columns=(
            "placement",
            "title_bn",
            "title_en",
            "subtitle_bn",
            "subtitle_en",
            "image_bn",
            "image_en",
            "href",
            "sort",
            "is_visible",
            "starts_at",
            "ends_at",
        ),
    )

    section_content = homepage_content_v2()
    section_rows = [
        {
            "id": seed_id("homepage_section", section_type.value),
            "type": section_type,
            "order": order,
            "is_visible": True,
            "content_bn": section_content[section_type][0],
            "content_en": section_content[section_type][1],
        }
        for order, (section_type, _, _) in enumerate(HOMEPAGE_SECTIONS, start=1)
    ]
    await upsert_rows(
        session,
        HomepageSection.__table__,
        section_rows,
        conflict_columns=("type",),
        update_columns=("order", "is_visible", "content_bn", "content_en"),
    )

    page_rows: list[dict[str, object]] = [
        {
            "id": seed_id("static_page", slug),
            "slug": slug,
            "title_bn": title_bn,
            "title_en": title_en,
            "body_bn": body_bn,
            "body_en": body_en,
            "is_published": True,
        }
        for slug, title_bn, title_en, body_bn, body_en in (
            (
                "about",
                "আমাদের গল্প",
                "Our Story",
                "বাংলাদেশের মানুষের দৈনন্দিন কেনাকাটাকে সহজ ও বিশ্বাসযোগ্য করতে বজ্রের যাত্রা।",
                "Bojro makes everyday shopping in Bangladesh simple, dependable, and transparent.",
            ),
            (
                "help",
                "সহায়তা ও সাধারণ প্রশ্ন",
                "Help & FAQ",
                "অর্ডার, পেমেন্ট ও ডেলিভারি সম্পর্কে সহায়তার জন্য আমাদের সাপোর্ট টিম পাশে আছে।",
                "Our support team can help with orders, payments, delivery, and common questions.",
            ),
            (
                "contact",
                "যোগাযোগ",
                "Contact",
                "সোমবার থেকে শনিবার সকাল ৯টা থেকে রাত ৯টা পর্যন্ত আমাদের সঙ্গে যোগাযোগ করুন।",
                "Contact us Monday through Saturday, 9:00 AM to 9:00 PM Bangladesh time.",
            ),
            (
                "return-refund",
                "রিটার্ন ও রিফান্ড",
                "Return & Refund",
                "ডেলিভারির পর নির্ধারিত সময়ের মধ্যে যোগ্য পণ্য সহজে রিটার্ন করা যাবে।",
                "Eligible items may be returned within the stated period after delivery.",
            ),
            (
                "privacy",
                "গোপনীয়তা নীতি",
                "Privacy Policy",
                "আপনার তথ্য কেবল অর্ডার সম্পন্ন, সেবা উন্নয়ন ও আইনগত প্রয়োজনে ব্যবহৃত হয়।",
                "We use your data only to fulfil orders, improve service, "
                "and meet legal obligations.",
            ),
            (
                "terms",
                "ব্যবহারের শর্তাবলি",
                "Terms & Conditions",
                "বজ্র ব্যবহার ও অর্ডার করার ক্ষেত্রে প্রযোজ্য শর্তাবলি এখানে বর্ণিত।",
                "These terms govern use of Bojro and orders placed through the service.",
            ),
            (
                "warranty",
                "ওয়ারেন্টি নীতি",
                "Warranty Policy",
                "প্রযোজ্য পণ্যে ব্র্যান্ড বা প্রস্তুতকারকের ঘোষিত ওয়ারেন্টি কার্যকর হবে।",
                "Eligible products carry the warranty stated by the brand or manufacturer.",
            ),
        )
    ]
    await upsert_rows(
        session,
        StaticPage.__table__,
        page_rows,
        conflict_columns=("slug",),
        update_columns=("title_bn", "title_en", "body_bn", "body_en", "is_published"),
    )

    setting_rows: list[dict[str, object]] = [
        {
            "id": seed_id("site_setting", "shipping_rules"),
            "key": "shipping_rules",
            "value": {
                "inside_dhaka_poisha": 7000,
                "outside_dhaka_poisha": 12000,
                "free_shipping_threshold_poisha": 150000,
                "inside_dhaka_min_days": 1,
                "inside_dhaka_max_days": 2,
                "outside_dhaka_min_days": 3,
                "outside_dhaka_max_days": 5,
                "weight_tiers_g": [500, 1000, 2000],
            },
        },
        {
            "id": seed_id("site_setting", "contact"),
            "key": "contact",
            "value": {
                "email": "support@bojro.com.bd",
                "phone": "+8801700000000",
                "hours_bn": "সকাল ৯টা-রাত ৯টা",
                "hours_en": "9 AM-9 PM",
                "address_bn": "ঢাকা, বাংলাদেশ",
                "address_en": "Dhaka, Bangladesh",
            },
        },
        {
            "id": seed_id("site_setting", "payment_methods"),
            "key": "payment_methods",
            "value": {"cod": True, "bkash": False, "nagad": False, "sslcommerz": False},
        },
        {
            "id": seed_id("site_setting", "social_links"),
            "key": "social_links",
            "value": {"facebook": "", "instagram": "", "youtube": ""},
        },
        {
            "id": seed_id("site_setting", "announcement"),
            "key": "announcement",
            "value": {
                "enabled": True,
                "bn": "৳১৫০০+ অর্ডারে ফ্রি ডেলিভারি",
                "en": "Free delivery on orders over ৳1500",
            },
        },
        {
            "id": seed_id("site_setting", "storefront_toggles"),
            "key": "storefront_toggles",
            "value": {
                "show_announcement": True,
                "show_social_links": True,
                "show_payment_methods": True,
            },
        },
        {
            "id": seed_id("site_setting", "cod_risk"),
            "key": "cod_risk",
            "value": {"enabled": False, "minimum_completed_orders": 3, "maximum_return_rate": 0.4},
        },
    ]
    await upsert_rows(
        session,
        SiteSetting.__table__,
        setting_rows,
        conflict_columns=("key",),
        update_columns=("value",),
    )


async def upgrade_demo_seed_v1_to_v2(
    session: AsyncSession,
    marker: SiteSetting,
    upgraded_at: datetime,
) -> None:
    """One-time additive content upgrade that never replaces existing operator values."""

    defaults = homepage_content_v2()
    existing_sections = {
        section.section_type: section for section in await session.scalars(select(HomepageSection))
    }
    used_orders = {section.sort_order for section in existing_sections.values()}
    for order, (section_type, _, _) in enumerate(HOMEPAGE_SECTIONS, start=1):
        section = existing_sections.get(section_type)
        content_bn, content_en = defaults[section_type]
        if section is None:
            assigned_order = order
            if assigned_order in used_orders:
                assigned_order = next(value for value in range(1, 16) if value not in used_orders)
            used_orders.add(assigned_order)
            session.add(
                HomepageSection(
                    id=seed_id("homepage_section_v2", section_type.value),
                    section_type=section_type,
                    sort_order=assigned_order,
                    is_visible=True,
                    content_bn=content_bn,
                    content_en=content_en,
                )
            )
            continue
        section.content_bn = merge_missing(section.content_bn, content_bn)
        section.content_en = merge_missing(section.content_en, content_en)

    setting_defaults: dict[str, dict[str, object]] = {
        "shipping_rules": {
            "inside_dhaka_min_days": 1,
            "inside_dhaka_max_days": 2,
            "outside_dhaka_min_days": 3,
            "outside_dhaka_max_days": 5,
        },
        "contact": {
            "phone": "+8801700000000",
            "address_bn": "ঢাকা, বাংলাদেশ",
            "address_en": "Dhaka, Bangladesh",
        },
        "announcement": {"enabled": True},
        "storefront_toggles": {
            "show_announcement": True,
            "show_social_links": True,
            "show_payment_methods": True,
        },
    }
    existing_settings = {
        setting.key: setting
        for setting in await session.scalars(
            select(SiteSetting).where(SiteSetting.key.in_(setting_defaults))
        )
    }
    for key, value in setting_defaults.items():
        setting = existing_settings.get(key)
        if setting is None:
            session.add(SiteSetting(id=seed_id("site_setting_v2", key), key=key, value=value))
        else:
            setting.value = merge_missing(setting.value, value)

    marker.value = {**marker.value, "version": 2, "upgraded_at": upgraded_at.isoformat()}


async def seed_admin(session: AsyncSession, settings: Settings) -> bool:
    if settings.seed_admin_email is None or settings.seed_admin_password is None:
        return False

    email = str(settings.seed_admin_email).casefold()
    password = settings.seed_admin_password.get_secret_value()
    admin = await session.scalar(select(User).where(User.role == UserRole.ADMIN))
    if admin is not None and admin.email != email:
        raise ValueError("a different admin account already exists")
    if admin is None:
        account = await session.scalar(select(User).where(func.lower(User.email) == email))
        if account is not None and account.role != UserRole.ADMIN:
            raise ValueError("SEED_ADMIN_EMAIL belongs to a customer account")
        admin = account
    if admin is None:
        admin = User(
            id=uuid7(),
            role=UserRole.ADMIN,
            name="Bojro Admin",
            phone=None,
            email=email,
            password_hash=_PASSWORD_HASHER.hash(password),
            is_guest=False,
        )
        session.add(admin)
        return True

    admin.role = UserRole.ADMIN
    admin.is_guest = False
    if admin.password_hash is None:
        admin.password_hash = _PASSWORD_HASHER.hash(password)
    else:
        matches: bool = False
        try:
            _PASSWORD_HASHER.verify(admin.password_hash, password)
            matches = True
        except VerificationError:
            pass
        if not matches or _PASSWORD_HASHER.check_needs_rehash(admin.password_hash):
            admin.password_hash = _PASSWORD_HASHER.hash(password)
    return True


async def ensure_demo_target_is_empty(session: AsyncSession) -> None:
    """Refuse to merge demo records into an existing operational database."""

    checks = {
        "users": await session.scalar(select(func.count(User.id))),
        "geo_divisions": await session.scalar(select(func.count(GeoDivision.id))),
        "products": await session.scalar(select(func.count(Product.id))),
        "site_settings": await session.scalar(select(func.count(SiteSetting.id))),
    }
    populated = [name for name, count in checks.items() if (count or 0) > 0]
    if populated:
        raise RuntimeError(
            "demo seed requires an empty database; populated tables: " + ", ".join(populated)
        )


async def seed_database() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    dataset = load_geo_dataset()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            seeded_at = datetime.now(UTC)
            marker = await session.scalar(
                select(SiteSetting).where(SiteSetting.key == _DEMO_SEED_KEY)
            )
            demo_seeded = marker is None
            demo_upgraded = False
            if marker is None:
                await ensure_demo_target_is_empty(session)
                await seed_geo(session, dataset)
                primary_variant_ids = await seed_catalog(session)
                await seed_reviews(session)
                await seed_promotions(session, primary_variant_ids, seeded_at)
                await seed_content(session)
                marker = SiteSetting(
                    id=uuid7(),
                    key=_DEMO_SEED_KEY,
                    value={
                        "version": 2,
                        "geo_coverage_as_of": dataset.metadata.coverage_as_of,
                    },
                )
                session.add(marker)
            elif (marker_version := marker.value.get("version")) in {1, 2}:
                demo_upgraded = marker_version == 1
                await upgrade_demo_seed_v1_to_v2(session, marker, seeded_at)
            elif marker.value.get("version") != 2:
                raise RuntimeError("unsupported demo seed marker version")
            admin_configured = await seed_admin(session, settings)
        _LOGGER.info(
            "seed_complete",
            divisions=len(dataset.divisions),
            districts=len(dataset.districts),
            upazilas=len(dataset.upazilas),
            products=len(PRODUCTS),
            reviews=20,
            homepage_sections=len(HOMEPAGE_SECTIONS),
            admin_configured=admin_configured,
            geo_coverage_as_of=dataset.metadata.coverage_as_of,
            demo_seeded=demo_seeded,
            demo_upgraded=demo_upgraded,
        )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
