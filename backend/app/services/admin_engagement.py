"""Masked, audited admin engagement operations; consent grants are intentionally absent."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.engagement_crypto import EngagementCrypto
from app.core.errors import DomainError
from app.db.models import (
    AssistantMessage,
    AssistantSession,
    AuditLog,
    CommunicationPreference,
    ConsentEvent,
    NewsletterSubscription,
    NotificationAttempt,
    NotificationDelivery,
)
from app.repositories.admin import AdminRepository
from app.schemas.admin_engagement import (
    AdminCustomerCommunicationPreference,
    AdminEngagementMutationResponse,
    AdminEngagementProvider,
    AdminEngagementProviderList,
    AdminNewsletterItem,
    AdminNewsletterList,
    AdminNotificationAttempt,
    AdminNotificationDeliveryDetail,
    AdminNotificationDeliveryItem,
    AdminNotificationDeliveryList,
    AdminTemplateCatalog,
    AdminTemplateCatalogItem,
    AdminTemplatePreviewRequest,
    AdminTemplatePreviewResponse,
    AdminTestSendRequest,
    AdminTestSendResponse,
)
from app.schemas.assistant import (
    AdminAssistantMetricResponse,
    AdminAssistantSessionItem,
    AdminAssistantSessionList,
)
from app.schemas.engagement import CommunicationPreferenceResponse
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.services.notification_templates import render_template, template_catalog
from app.services.notifications import queue_notification
from app.utils.account_http import enforce_if_match, strong_etag


class AdminEngagementService(AdminServiceBase):
    def __init__(
        self,
        repository: AdminRepository,
        crypto: EngagementCrypto,
        settings: Settings,
    ) -> None:
        super().__init__(repository)
        self._session: AsyncSession = repository.session
        self._crypto = crypto
        self._settings = settings

    async def deliveries(
        self,
        *,
        status: str | None,
        channel: str | None,
        limit: int,
    ) -> AdminNotificationDeliveryList:
        filters = []
        if status:
            filters.append(NotificationDelivery.status == status)
        if channel:
            filters.append(NotificationDelivery.channel == channel)
        rows = list(
            await self._session.scalars(
                select(NotificationDelivery)
                .where(*filters)
                .order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
                .limit(limit)
            )
        )
        return AdminNotificationDeliveryList(items=[self._delivery(row) for row in rows])

    async def delivery(self, delivery_id: UUID) -> AdminNotificationDeliveryDetail:
        row = await self._session.get(NotificationDelivery, delivery_id)
        if row is None:
            raise DomainError("DELIVERY_NOT_FOUND", "Delivery not found.", status_code=404)
        attempts = list(
            await self._session.scalars(
                select(NotificationAttempt)
                .where(NotificationAttempt.delivery_id == row.id)
                .order_by(NotificationAttempt.attempt_no)
            )
        )
        return AdminNotificationDeliveryDetail(
            **self._delivery(row).model_dump(),
            attempts_history=[
                AdminNotificationAttempt(
                    attempt_no=item.attempt_no,
                    provider=item.provider,
                    outcome=item.outcome,
                    response_class=item.response_class,
                    response_code=item.response_code,
                    latency_ms=item.latency_ms,
                    provider_message_id=item.provider_message_id,
                    error=item.error,
                    created_at=item.created_at,
                )
                for item in attempts
            ],
        )

    async def retry_delivery(
        self,
        delivery_id: UUID,
        *,
        acknowledge_possible_duplicate: bool,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.engagement.deliveries.retry:{delivery_id}",
                context,
                idempotency_key,
                {"acknowledge_possible_duplicate": acknowledge_possible_duplicate},
            )
            if replay is not None:
                return replay
            row = await self._session.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id)
                .with_for_update()
            )
            if row is None:
                raise DomainError("DELIVERY_NOT_FOUND", "Delivery not found.", status_code=404)
            enforce_if_match(if_match, strong_etag("notification-delivery", row.id, row.revision))
            if row.status == "unknown" and not acknowledge_possible_duplicate:
                raise DomainError(
                    "POSSIBLE_DUPLICATE_ACK_REQUIRED",
                    "Acknowledge the possible duplicate before retrying this delivery.",
                    status_code=409,
                )
            if row.status not in {"dead_letter", "rejected", "unknown", "expired"}:
                raise DomainError(
                    "DELIVERY_RETRY_INVALID",
                    "This delivery is not eligible for retry.",
                    status_code=409,
                )
            if row.recipient_ciphertext is None or row.context_ciphertext is None:
                raise DomainError(
                    "DELIVERY_CONTENT_ERASED",
                    "Erased delivery content cannot be retried.",
                    status_code=409,
                )
            before = {"status": row.status, "revision": row.revision}
            row.status = "retry"
            row.next_attempt_at = now
            row.terminal_at = None
            row.last_error = None
            row.max_attempts = max(row.max_attempts, row.attempts + 1)
            row.revision += 1
            body = AdminEngagementMutationResponse(
                id=row.id, status=row.status, revision=row.revision
            ).model_dump(mode="json")
            self._audit(
                context,
                "engagement.delivery.retry",
                "notification_delivery",
                row.id,
                before,
                body,
                200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="notification_delivery",
                resource_id=row.id,
                now=now,
                etag=strong_etag("notification-delivery", row.id, row.revision),
            )

    async def cancel_delivery(
        self,
        delivery_id: UUID,
        *,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.engagement.deliveries.cancel:{delivery_id}",
                context,
                idempotency_key,
                {},
            )
            if replay is not None:
                return replay
            row = await self._session.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id)
                .with_for_update()
            )
            if row is None:
                raise DomainError("DELIVERY_NOT_FOUND", "Delivery not found.", status_code=404)
            enforce_if_match(if_match, strong_etag("notification-delivery", row.id, row.revision))
            if row.status == "processing":
                raise DomainError(
                    "DELIVERY_IN_FLIGHT",
                    "An in-flight delivery cannot be cancelled.",
                    status_code=409,
                )
            if row.status not in {"queued", "retry"}:
                raise DomainError(
                    "DELIVERY_CANCEL_INVALID",
                    "This delivery can no longer be cancelled.",
                    status_code=409,
                )
            before = {"status": row.status, "revision": row.revision}
            row.status = "cancelled"
            row.terminal_at = now
            row.lease_owner = None
            row.leased_at = None
            row.lease_expires_at = None
            row.revision += 1
            if row.template_key == "auth.otp":
                self._erase_delivery(row)
            body = AdminEngagementMutationResponse(
                id=row.id, status=row.status, revision=row.revision
            ).model_dump(mode="json")
            self._audit(
                context,
                "engagement.delivery.cancel",
                "notification_delivery",
                row.id,
                before,
                body,
                200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="notification_delivery",
                resource_id=row.id,
                now=now,
                etag=strong_etag("notification-delivery", row.id, row.revision),
            )

    def templates(self) -> AdminTemplateCatalog:
        return AdminTemplateCatalog(
            items=[AdminTemplateCatalogItem.model_validate(item) for item in template_catalog()]
        )

    def preview(self, payload: AdminTemplatePreviewRequest) -> AdminTemplatePreviewResponse:
        rendered = render_template(
            payload.template_key,
            payload.version,
            payload.locale,
            payload.channel,
            self._sample_context(payload.template_key, payload.locale),
        )
        return AdminTemplatePreviewResponse(
            subject=rendered.subject, text=rendered.text, html=rendered.html
        )

    def providers(self) -> AdminEngagementProviderList:
        values = (
            (
                "email",
                self._settings.email_provider,
                self._settings.email_provider in {"mock", "resend"},
                "at_least_once"
                if self._settings.email_provider == "smtp"
                else "exactly_once_effect",
                "https://resend.com/docs/api-reference/emails/send-email"
                if self._settings.email_provider == "resend"
                else None,
                "official-https-v1" if self._settings.email_provider == "resend" else None,
            ),
            (
                "sms",
                self._settings.sms_provider,
                self._settings.sms_provider == "mock" or self._settings.sms_supports_idempotency,
                "exactly_once_effect",
                self._settings.sms_documentation_url,
                self._settings.sms_documentation_version,
            ),
            (
                "meta_capi",
                self._settings.meta_capi_mode,
                self._settings.meta_capi_mode in {"mock", "live"},
                "exactly_once_effect",
                "https://developers.facebook.com/docs/marketing-api/conversions-api",
                "graph-v21.0",
            ),
            (
                "assistant",
                self._settings.assistant_provider,
                False,
                None,
                None,
                None,
            ),
        )
        return AdminEngagementProviderList(
            items=[
                AdminEngagementProvider(
                    channel=channel,
                    provider=provider,
                    enabled=provider != "disabled",
                    production_safe=(
                        provider not in {"mock", "disabled"}
                        and (channel == "assistant" or supports_idempotency)
                    ),
                    supports_idempotency=supports_idempotency,
                    delivery_semantics=semantics,
                    documentation_url=documentation_url,
                    documentation_version=documentation_version,
                )
                for (
                    channel,
                    provider,
                    supports_idempotency,
                    semantics,
                    documentation_url,
                    documentation_version,
                ) in values
            ]
        )

    async def test_send(
        self,
        payload: AdminTestSendRequest,
        *,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        recipient = self._settings.engagement_test_recipient_aliases.get(payload.recipient_alias)
        if recipient is None:
            raise DomainError(
                "TEST_RECIPIENT_NOT_ALLOWED",
                "The recipient alias is not allowlisted.",
                status_code=422,
            )
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.engagement.test-send",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            delivery_id = await queue_notification(
                self._session,
                self._crypto,
                self._settings,
                dedupe_key=f"admin-test:{context.actor_id}:{idempotency_key}",
                category="transactional",
                channel=payload.channel,
                template_key=payload.template_key,
                locale=payload.locale,
                recipient=recipient,
                context=self._sample_context(payload.template_key, payload.locale),
                priority=60,
                max_attempts=3,
                now=now,
            )
            body = AdminTestSendResponse(
                delivery_id=delivery_id,
                recipient_alias=payload.recipient_alias,
            ).model_dump(mode="json")
            self._audit(
                context,
                "engagement.test_send",
                "notification_delivery",
                delivery_id,
                None,
                {"recipient_alias": payload.recipient_alias},
                202,
            )
            return self._complete(
                record,
                body=body,
                status_code=202,
                resource_kind="notification_delivery",
                resource_id=delivery_id,
                now=now,
            )

    async def newsletter(self, *, status: str | None, limit: int) -> AdminNewsletterList:
        filters = [NewsletterSubscription.status == status] if status else []
        rows = list(
            await self._session.scalars(
                select(NewsletterSubscription)
                .where(*filters)
                .order_by(
                    NewsletterSubscription.created_at.desc(),
                    NewsletterSubscription.id.desc(),
                )
                .limit(limit)
            )
        )
        return AdminNewsletterList(items=[self._newsletter(row) for row in rows])

    async def change_newsletter_status(
        self,
        subscription_id: UUID,
        target: str,
        *,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        if target not in {"suppressed", "unsubscribed"}:
            raise ValueError("admin cannot grant newsletter consent")
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.engagement.newsletter.{target}:{subscription_id}",
                context,
                idempotency_key,
                {},
            )
            if replay is not None:
                return replay
            row = await self._session.scalar(
                select(NewsletterSubscription)
                .where(NewsletterSubscription.id == subscription_id)
                .with_for_update()
            )
            if row is None:
                raise DomainError(
                    "NEWSLETTER_SUBSCRIPTION_NOT_FOUND",
                    "Subscription not found.",
                    status_code=404,
                )
            enforce_if_match(if_match, strong_etag("newsletter-subscription", row.id, row.revision))
            before = {"status": row.status, "revision": row.revision}
            row.status = target
            row.suppressed_at = now if target == "suppressed" else row.suppressed_at
            row.unsubscribed_at = now if target == "unsubscribed" else row.unsubscribed_at
            row.confirmation_token_hash = None
            row.confirmation_expires_at = None
            row.email_key_id = None
            row.email_nonce = None
            row.email_ciphertext = None
            row.revision += 1
            self._session.add(
                ConsentEvent(
                    subject_kind="newsletter",
                    subject_hash=row.email_hash,
                    user_id=row.user_id,
                    purpose="newsletter",
                    action="withdraw",
                    policy_version=row.policy_version,
                    source=f"admin_{target}",
                    locale=row.locale,
                    ip_hash=self._crypto.lookup_hash("consent-ip", context.ip_address),
                    user_agent_hash=self._crypto.lookup_hash(
                        "consent-user-agent", context.user_agent
                    ),
                    created_at=now,
                )
            )
            body = AdminEngagementMutationResponse(
                id=row.id, status=row.status, revision=row.revision
            ).model_dump(mode="json")
            self._audit(
                context,
                f"engagement.newsletter.{target}",
                "newsletter_subscription",
                row.id,
                before,
                body,
                200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="newsletter_subscription",
                resource_id=row.id,
                now=now,
                etag=strong_etag("newsletter-subscription", row.id, row.revision),
            )

    async def customer_preferences(self, user_id: UUID) -> AdminCustomerCommunicationPreference:
        row = await self._session.get(CommunicationPreference, user_id)
        if row is None:
            preferences = CommunicationPreferenceResponse(
                locale="bn",
                order_email=True,
                order_sms=True,
                abandoned_cart_email=False,
                abandoned_cart_sms=False,
                revision=0,
            )
        else:
            preferences = CommunicationPreferenceResponse(
                locale="en" if row.locale == "en" else "bn",
                order_email=row.order_email,
                order_sms=row.order_sms,
                abandoned_cart_email=row.abandoned_cart_email,
                abandoned_cart_sms=row.abandoned_cart_sms,
                revision=row.revision,
            )
        return AdminCustomerCommunicationPreference(user_id=user_id, preferences=preferences)

    async def assistant_metrics(self, context: AdminCommandContext) -> AdminAssistantMetricResponse:
        now = datetime.now(UTC)
        active = await self._session.scalar(
            select(func.count(AssistantSession.id)).where(
                AssistantSession.status == "active", AssistantSession.expires_at > now
            )
        )
        total = await self._session.scalar(select(func.count(AssistantSession.id)))
        messages = await self._session.scalar(select(func.count(AssistantMessage.id)))
        handoffs = await self._session.scalar(
            select(func.coalesce(func.sum(AssistantSession.handoff_count), 0))
        )
        self._audit(
            context,
            "engagement.assistant.metrics_view",
            "assistant_metrics",
            None,
            None,
            {"accessed": True},
            200,
            event_kind="access",
        )
        await self._session.commit()
        return AdminAssistantMetricResponse(
            active_sessions=int(active or 0),
            total_sessions=int(total or 0),
            messages=int(messages or 0),
            handoffs=int(handoffs or 0),
        )

    async def assistant_sessions(
        self, context: AdminCommandContext, *, limit: int
    ) -> AdminAssistantSessionList:
        rows = list(
            await self._session.scalars(
                select(AssistantSession)
                .order_by(AssistantSession.created_at.desc(), AssistantSession.id.desc())
                .limit(limit)
            )
        )
        self._audit(
            context,
            "engagement.assistant.sessions_view",
            "assistant_session",
            None,
            None,
            {"count": len(rows)},
            200,
            event_kind="access",
        )
        await self._session.commit()
        return AdminAssistantSessionList(items=[self._assistant_session_item(row) for row in rows])

    async def assistant_session(
        self, context: AdminCommandContext, session_id: UUID
    ) -> AdminAssistantSessionItem:
        row = await self._session.get(AssistantSession, session_id)
        if row is None:
            raise DomainError(
                "ASSISTANT_SESSION_NOT_FOUND",
                "Assistant session not found.",
                status_code=404,
            )
        self._audit(
            context,
            "engagement.assistant.session_view",
            "assistant_session",
            row.id,
            None,
            {"accessed": True},
            200,
            event_kind="access",
        )
        await self._session.commit()
        return self._assistant_session_item(row)

    def _audit(
        self,
        context: AdminCommandContext,
        action: str,
        entity: str,
        entity_id: UUID | None,
        before: object,
        after: object,
        status_code: int,
        *,
        event_kind: str = "mutation",
    ) -> None:
        self._session.add(
            AuditLog(
                actor_id=context.actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                diff={"before": before, "after": after},
                ip_address=None,
                request_id=context.request_id,
                event_kind=event_kind,
                actor_snapshot={"id": str(context.actor_id), "role": "admin"},
                method=context.method,
                path=context.path,
                status_code=status_code,
                user_agent_hash=self._crypto.lookup_hash(
                    "admin-audit-user-agent", context.user_agent
                ),
            )
        )

    @staticmethod
    def _delivery(row: NotificationDelivery) -> AdminNotificationDeliveryItem:
        return AdminNotificationDeliveryItem(
            id=row.id,
            category=row.category,
            channel=row.channel,
            provider=row.provider,
            template=f"{row.template_key}.v{row.template_version}",
            locale="en" if row.locale == "en" else "bn",
            recipient_masked=row.recipient_masked,
            status=row.status,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            next_attempt_at=row.next_attempt_at,
            expires_at=row.expires_at,
            provider_message_id=row.provider_message_id,
            last_error=row.last_error,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _newsletter(row: NewsletterSubscription) -> AdminNewsletterItem:
        return AdminNewsletterItem(
            id=row.id,
            masked_email=row.masked_email,
            locale="en" if row.locale == "en" else "bn",
            status=row.status,
            source=row.source,
            revision=row.revision,
            consented_at=row.consented_at,
            confirmed_at=row.confirmed_at,
            unsubscribed_at=row.unsubscribed_at,
            suppressed_at=row.suppressed_at,
        )

    @staticmethod
    def _erase_delivery(row: NotificationDelivery) -> None:
        row.recipient_key_id = None
        row.recipient_nonce = None
        row.recipient_ciphertext = None
        row.context_key_id = None
        row.context_nonce = None
        row.context_ciphertext = None

    @staticmethod
    def _assistant_session_item(row: AssistantSession) -> AdminAssistantSessionItem:
        return AdminAssistantSessionItem(
            id=row.id,
            owner_kind="user" if row.owner_kind == "user" else "guest",
            locale="en" if row.locale == "en" else "bn",
            status=row.status,
            message_count=row.message_count,
            handoff_count=row.handoff_count,
            created_at=row.created_at,
            delete_after=row.delete_after,
        )

    def _sample_context(self, template_key: str, locale: str) -> dict[str, object]:
        storefront = self._settings.public_storefront_base_url
        if template_key.startswith("order."):
            return {"order_number": "BJ-2026-000001", "grand_total_poisha": 125000}
        if template_key == "cart.abandoned":
            return {"cart_url": f"{storefront}/{locale}/cart"}
        if template_key == "newsletter.confirm":
            return {"confirm_url": f"{storefront}/{locale}/newsletter/confirm"}
        if template_key == "newsletter.welcome":
            return {"unsubscribe_url": f"{storefront}/{locale}/newsletter/unsubscribe"}
        if template_key == "auth.otp":
            return {"code": "[sample]"}
        return {}
