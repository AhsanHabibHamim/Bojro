"""Health and readiness business service."""

from __future__ import annotations

import asyncio

from app import __version__
from app.core.config import Settings
from app.db.base import utc_now
from app.providers.types import ProviderCapabilities
from app.repositories.health import HealthRepository, StorageHealthProbe
from app.schemas.health import ComponentHealth, HealthResponse, ReadinessResponse


class HealthService:
    def __init__(
        self,
        repository: HealthRepository,
        settings: Settings,
        storage_provider: StorageHealthProbe,
        provider_capabilities: list[ProviderCapabilities] | None = None,
        *,
        observability_available: bool = True,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._service_name = settings.app_name
        self._storage_provider = storage_provider
        self._provider_capabilities = provider_capabilities or []
        self._observability_available = observability_available

    @property
    def settings(self) -> Settings:
        return self._settings

    def liveness(self) -> HealthResponse:
        return HealthResponse(
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
        )

    async def readiness(self) -> ReadinessResponse:
        database, redis, schema, storage, admin, worker, engagement_config = await asyncio.gather(
            self._repository.check_database(),
            self._repository.check_redis(),
            self._repository.check_schema_head(),
            self._repository.check_storage(self._storage_provider, required=True),
            self._repository.check_admin_policy(
                totp_required=self._settings.admin_totp_required,
                required=self._settings.is_production_like,
            ),
            self._repository.check_worker_heartbeat(
                key=self._settings.worker_heartbeat_key,
                max_age_seconds=self._settings.worker_heartbeat_max_age_seconds,
                required=(
                    self._settings.worker_heartbeat_required or self._settings.is_production_like
                ),
            ),
            self._repository.check_engagement_public_config(
                expected={
                    "analytics": {
                        "google_analytics_id": self._settings.google_analytics_id,
                        "meta_pixel_id": self._settings.meta_pixel_id,
                        "consent_policy_version": self._settings.consent_policy_version,
                    },
                    "assistant": {
                        "enabled": self._settings.assistant_public_enabled,
                    },
                    "whatsapp": {
                        "enabled": self._settings.whatsapp_enabled,
                        "phone": self._settings.whatsapp_phone,
                        "message_bn": self._settings.whatsapp_message_bn,
                        "message_en": self._settings.whatsapp_message_en,
                    },
                    "engagement": {
                        "newsletter_enabled": self._settings.newsletter_enabled,
                        "consent_policy_version": self._settings.consent_policy_version,
                    },
                },
                required=self._settings.is_production_like,
            ),
        )
        checks = {
            "database": database,
            "redis": redis,
            "schema": schema,
            "storage": storage,
            "admin": admin,
            "worker": worker,
            "engagement_config": engagement_config,
            "observability": self._observability_check(),
        }
        for capability in self._provider_capabilities:
            enabled = capability.mode.value != "disabled"
            required = enabled
            available = capability.available and capability.configured
            checks[f"provider:{capability.kind}:{capability.provider}"] = ComponentHealth(
                status="ok" if available or not enabled else "unavailable",
                required=required,
                detail=(
                    (
                        f"mode={capability.mode.value},"
                        f"configured={capability.configured},"
                        f"idempotency={capability.supports_idempotency},"
                        f"semantics={capability.delivery_semantics or 'n/a'}"
                    )
                    if available
                    else (
                        f"mode={capability.mode.value},"
                        f"reason={capability.unavailable_reason or 'not_configured'}"
                    )
                ),
            )
        if any(check.status != "ok" and check.required for check in checks.values()):
            status = "unavailable"
        elif any(check.status != "ok" for check in checks.values()):
            status = "degraded"
        else:
            status = "ready"
        return ReadinessResponse(
            status=status,
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
            checks=checks,
        )

    def _observability_check(self) -> ComponentHealth:
        enabled = self._settings.sentry_dsn is not None
        if not enabled:
            if self._settings.is_production_like:
                return ComponentHealth(
                    status="unavailable",
                    required=True,
                    detail="sentry_not_configured",
                )
            return ComponentHealth(status="ok", required=False, detail="disabled")
        return ComponentHealth(
            status="ok" if self._observability_available else "unavailable",
            required=True,
            detail="sentry" if self._observability_available else "sentry_sdk_unavailable",
        )
