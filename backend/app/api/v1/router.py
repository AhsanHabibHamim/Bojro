"""Version 1 route registry."""

from fastapi import APIRouter

from app.api.v1.account import router as account_router
from app.api.v1.admin_auth import router as admin_auth_router
from app.api.v1.admin_catalog import router as admin_catalog_router
from app.api.v1.admin_commerce import router as admin_commerce_router
from app.api.v1.admin_content import router as admin_content_router
from app.api.v1.admin_marketing import router as admin_marketing_router
from app.api.v1.admin_media import router as admin_media_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cart import router as cart_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.checkout import router as checkout_router
from app.api.v1.content import router as content_router
from app.api.v1.geo import router as geo_router
from app.api.v1.health import router as health_router
from app.api.v1.orders import router as orders_router
from app.api.v1.storefront import router as storefront_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(admin_auth_router)
router.include_router(admin_catalog_router)
router.include_router(admin_commerce_router)
router.include_router(admin_media_router)
router.include_router(admin_marketing_router)
router.include_router(admin_content_router)
router.include_router(account_router)
router.include_router(geo_router)
router.include_router(content_router)
router.include_router(cart_router)
router.include_router(checkout_router)
router.include_router(orders_router)
router.include_router(catalog_router)
router.include_router(storefront_router)
