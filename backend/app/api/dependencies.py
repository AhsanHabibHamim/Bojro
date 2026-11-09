"""HTTP dependency factories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import AdminTOTPService
from app.db.session import get_session
from app.repositories.account import AccountRepository
from app.repositories.admin import AdminRepository
from app.repositories.admin_auth import AdminAuthRepository
from app.repositories.auth import AuthRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.checkout import CheckoutRepository
from app.repositories.commerce import CommerceRepository
from app.repositories.geo import GeoRepository
from app.repositories.health import HealthRepository
from app.repositories.providers import ProviderRepository
from app.repositories.storefront import StorefrontRepository
from app.services.account import AccountService
from app.services.admin_auth import AdminAuthService
from app.services.admin_catalog import AdminCatalogService
from app.services.admin_catalog_csv import AdminCatalogCSVService
from app.services.admin_content import AdminContentService
from app.services.admin_customers_reviews import AdminCustomerReviewService
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_engagement import AdminEngagementService
from app.services.admin_marketing import AdminMarketingService
from app.services.admin_media import AdminMediaService
from app.services.admin_orders import AdminOrderService
from app.services.analytics import AnalyticsService
from app.services.assistant import AssistantService
from app.services.auth import AuthService
from app.services.cache import HotCache
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.checkout import CheckoutService
from app.services.content import ContentService
from app.services.e2e_phase6 import Phase6E2EResetService
from app.services.e2e_phase7 import Phase7E2EResetService
from app.services.engagement import EngagementService
from app.services.geo import GeoService
from app.services.health import HealthService
from app.services.order_pdf import OrderPDFService
from app.services.payments import PaymentService
from app.services.storefront import StorefrontService
from app.services.webhooks import WebhookService


def get_health_service(request: Request) -> HealthService:
    settings = request.app.state.settings
    repository = HealthRepository(
        request.app.state.engine,
        request.app.state.redis,
        redis_configured=settings.redis_url is not None,
        redis_required=settings.is_production_like,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    capabilities = [
        gateway.capabilities
        for gateway in (
            *request.app.state.payment_providers.values(),
            *request.app.state.courier_providers.values(),
        )
    ]
    capabilities.extend(
        provider.capabilities
        for provider in (
            *request.app.state.notification_providers.values(),
            request.app.state.meta_capi_provider,
            request.app.state.assistant_provider,
        )
    )
    return HealthService(
        repository,
        settings,
        request.app.state.storage_provider,
        capabilities,
        observability_available=request.app.state.observability.available,
    )


def get_catalog_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogService:
    cache: HotCache = request.app.state.hot_cache
    return CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)


def get_analytics_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalyticsService:
    return AnalyticsService(
        session,
        request.app.state.engagement_crypto,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_assistant_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssistantService:
    return AssistantService(
        session,
        request.app.state.assistant_provider,
        request.app.state.engagement_crypto,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_storefront_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StorefrontService:
    cache: HotCache = request.app.state.hot_cache
    catalog = CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)
    return StorefrontService(
        StorefrontRepository(session),
        catalog,
        cache,
        request.app.state.storage_provider,
        request.app.state.settings,
    )


def get_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthService:
    return AuthService(
        AuthRepository(session),
        request.app.state.token_service,
        request.app.state.otp_service,
        request.app.state.rate_limiter,
        request.app.state.settings,
        request.app.state.engagement_crypto,
    )


def get_engagement_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EngagementService:
    return EngagementService(
        session,
        request.app.state.engagement_crypto,
        request.app.state.engagement_tokens,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_geo_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GeoService:
    return GeoService(GeoRepository(session))


def get_cart_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CartService:
    return CartService(CommerceRepository(session))


def get_checkout_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CheckoutService:
    payment_service = PaymentService(
        ProviderRepository(session),
        request.app.state.payment_providers,
        request.app.state.settings,
    )
    return CheckoutService(
        CheckoutRepository(session),
        CommerceRepository(session),
        request.app.state.token_service,
        request.app.state.rate_limiter,
        request.app.state.settings,
        payment_service,
        request.app.state.engagement_crypto,
    )


def get_payment_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentService:
    return PaymentService(
        ProviderRepository(session),
        request.app.state.payment_providers,
        request.app.state.settings,
    )


def get_phase6_e2e_reset_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Phase6E2EResetService:
    return Phase6E2EResetService(session)


def get_phase7_e2e_reset_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Phase7E2EResetService:
    return Phase7E2EResetService(
        session,
        request.app.state.engagement_crypto,
        request.app.state.engagement_tokens,
        request.app.state.settings,
        request.app.state.hot_cache,
        True,
        request.app.state.rate_limiter,
    )


def get_webhook_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WebhookService:
    repository = ProviderRepository(session)
    payment_service = PaymentService(
        repository,
        request.app.state.payment_providers,
        request.app.state.settings,
    )
    return WebhookService(
        repository,
        request.app.state.payment_providers,
        request.app.state.courier_providers,
        payment_service,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_account_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountService:
    cache: HotCache = request.app.state.hot_cache
    catalog = CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)
    return AccountService(
        AccountRepository(session),
        catalog,
        request.app.state.storage_provider,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_admin_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminAuthService:
    return AdminAuthService(
        AdminAuthRepository(session),
        request.app.state.token_service,
        AdminTOTPService(request.app.state.settings),
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_admin_catalog_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminCatalogService:
    return AdminCatalogService(AdminRepository(session), request.app.state.storage_provider)


def get_admin_catalog_csv_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminCatalogCSVService:
    return AdminCatalogCSVService(AdminRepository(session))


def get_admin_media_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminMediaService:
    settings = request.app.state.settings
    return AdminMediaService(
        AdminRepository(session),
        request.app.state.storage_provider,
        settings.app_env,
        settings.media_upload_signature_seconds,
        settings.media_upload_cleanup_hours,
    )


def get_admin_dashboard_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminDashboardService:
    return AdminDashboardService(session)


def get_admin_engagement_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminEngagementService:
    return AdminEngagementService(
        AdminRepository(session),
        request.app.state.engagement_crypto,
        request.app.state.settings,
    )


def get_admin_order_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminOrderService:
    settings = request.app.state.settings
    return AdminOrderService(
        AdminRepository(session),
        request.app.state.courier_gateways,
        not settings.is_production_like and settings.courier_provider == "mock",
        request.app.state.courier_providers,
        settings,
        request.app.state.payment_providers,
        request.app.state.engagement_crypto,
    )


def get_admin_customer_review_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminCustomerReviewService:
    return AdminCustomerReviewService(AdminRepository(session), request.app.state.storage_provider)


def get_order_pdf_service(request: Request) -> OrderPDFService:
    return OrderPDFService(request.app.state.settings.pdf_font_path)


def get_admin_marketing_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminMarketingService:
    return AdminMarketingService(AdminRepository(session), request.app.state.storage_provider)


def get_admin_content_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminContentService:
    return AdminContentService(AdminRepository(session), request.app.state.storage_provider)


def get_content_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ContentService:
    return ContentService(session, request.app.state.storage_provider)
