# API Contract

The REST API is rooted at `/api/v1`. Outside production, FastAPI serves interactive OpenAPI documentation at `/docs`, ReDoc at `/redoc`, and the raw schema at `/api/v1/openapi.json`. Interactive documentation is disabled in production.

## Operational Endpoints

- `GET /health`: process liveness; no external dependency is required.
- `GET /ready`: checks PostgreSQL and Redis and returns `200` when required dependencies are ready, otherwise `503`.
- `GET /api/v1/health`: versioned health response for API clients.

Every response includes `X-Request-ID`; a valid inbound ID is retained, otherwise the API creates one. Errors use FastAPI's structured error shape in Phase 1 and will gain a shared domain envelope with feature routers.

## Client Generation

Run `pnpm api:generate`. The command boots no server: it imports the FastAPI app, writes a sorted `backend/openapi.json`, then runs `openapi-typescript` to produce `frontend/src/lib/api/schema.d.ts`.

Generated files are committed so Vercel and editor builds do not require Python. CI regenerates them and rejects drift.

## Catalog And Storefront

- `GET /api/v1/catalog/categories`: localized active category tree and product counts.
- `GET /api/v1/catalog/categories/{slug}`: category context, children, breadcrumb, and count.
- `GET /api/v1/catalog/products`: cursor feed with search, category/brand, integer-poisha price, rating, discount, stock, collection, and sort filters.
- `GET /api/v1/catalog/filters`: filter facets scoped by the current search/category context.
- `GET /api/v1/catalog/search/suggestions`: ranked product, category, and brand autocomplete.
- `GET /api/v1/catalog/products/{slug}`: localized gallery, variants, effective prices, stock, review preview, SEO, and related products.
- `GET /api/v1/catalog/products/{slug}/reviews`: approved cursor-paginated reviews.
- `GET /api/v1/catalog/delivery-estimate`: district-zone estimate for a concrete variant.
- `GET /api/v1/storefront/home`: ordered visible homepage sections with live catalog data.
- `GET /api/v1/storefront/shell`: announcement, navigation categories, footer/settings, and localized districts.

All money is integer poisha. Cursors are opaque and malformed values return `422`. Catalog detail, category, home, and shell responses use bounded Redis caching with a graceful development fallback.

## ISR Revalidation

The frontend exposes `POST /api/revalidate` for trusted admin events. Send `X-Revalidation-Secret` and a bounded JSON event containing `entity`, `event`, optional `slug`, and optional `locale`. The route uses constant-time secret comparison and an allowlisted entity-to-tag mapping; it is not a public webhook.

## Auth And Commerce

- `GET /api/v1/auth/session`, `POST /auth/refresh`, and `POST /auth/logout` manage guest/access/rotating-refresh cookies.
- `POST /api/v1/auth/otp/request`, `/auth/otp/verify`, and `/auth/email/login` provide phone-first and existing-account login.
- `GET /api/v1/cart` plus item, coupon, and shipping-estimate mutations operate on the current guest/user cart.
- `GET /api/v1/geo/divisions`, `/districts`, and `/upazilas` provide validated checkout hierarchy options.
- `POST /api/v1/checkout/quote` returns a short-lived authoritative quote; `POST /checkout/orders` requires CSRF and `Idempotency-Key` and accepts COD only in Phase 3.
- `GET /api/v1/orders/{number}` returns an authorized receipt; `POST /orders/track` returns a rate-limited redacted public status.

Unsafe cookie-authenticated requests require an exact allowed `Origin`, JSON content where a body exists, and `X-CSRF-Token`. Commerce responses use `Cache-Control: no-store`. Clients never send prices or totals; the API recomputes integer-poisha values under PostgreSQL row locks.

## Customer Account

All `/api/v1/account/*` operations require an active, unrevoked, non-guest customer access session and return `Cache-Control: no-store`.

- Dashboard/profile endpoints expose customer-safe counts and name-only profile updates.
- Address endpoints validate the Bangladesh hierarchy, enforce one default, cap saved addresses, and use `ETag`/`If-Match` plus idempotent creates.
- Order endpoints return only owned snapshots and customer-visible timeline notes.
- Wishlist endpoints provide cursor pages, batch membership, and idempotent toggles for active products.
- Review endpoints derive verified-purchase lineage from delivered owned order items and support pending moderation plus structured owned photo assets.
- Coupon wallet endpoints expose discoverable eligible offers and the customer’s redemption history; checkout remains authoritative.
- Support endpoints expose owned ticket threads, hide internal messages, and require idempotency for ticket/message creation.

Mutable revisioned resources return strong `ETag` values. Missing `If-Match` is `428`; a stale validator is `412`. Cross-owner and missing resources use the same response semantics.

## Admin API

`/api/v1/admin/*` uses a separate JWT audience, cookie names, refresh channel, CSRF token, rate limits, and optional encrypted TOTP/recovery flow. Customer credentials and sessions cannot access admin routes.

- Dashboard and revisioned catalog/category/brand/media/CSV endpoints manage stock through immutable inventory movements.
- Order endpoints return API-derived legal actions, support transaction-safe state changes, manual/mock shipment booking, notes, payment history, and snapshot invoice/packing PDFs.
- Customer, review moderation, coupon, flash sale, homepage/banner, page/blog, typed settings, media, and audit endpoints use ETags plus replay-safe idempotency.
- Public blog/static-page rendering consumes structured rich-document blocks; arbitrary HTML, scripts, and unsafe links are rejected.

Admin mutations append redacted audit records and durable revalidation/outbox rows in the same transaction. The ARQ worker performs external delivery and cleanup outside database locks.

## Payments And Couriers

- `GET /api/v1/checkout/payment-methods` returns effective COD/bKash/Nagad/SSLCOMMERZ capabilities and reason codes without credentials.
- Online order creation remains inventory-authoritative and returns `payment_required`; `POST /orders/{number}/payment-attempts` creates one replay-safe hosted payment attempt.
- Payment status/return routes expose normalized states only. Browser returns never mark money paid.
- Verified payment/courier webhook endpoints capture exact raw-body hashes, deduplicate by kind/provider/event ID, queue processing, and validate reference, amount, currency and resource identity before mutation.
- Admin provider capabilities, refunds, reconcile/cancel commands, shipment attempts and webhook dead-letter operations require ETags plus idempotency keys.

Payment attempts, refunds, shipments and order aggregates are separate state machines. `unknown` outcomes cannot be blindly retried; workers reconcile them by stable merchant reference. Customer responses never expose provider credentials, raw payloads or internal transaction identifiers.

## Engagement And Assistant

- Consent and communication-preference endpoints use versioned policy evidence, strong ETags and deny optional analytics/marketing by default.
- Newsletter subscription is enumeration-safe double opt-in; confirmation/unsubscribe tokens are single-use POST credentials and remain outside URL query strings.
- Analytics intake accepts allowlisted IDs/intents only and resolves authoritative commerce values server-side. Purchase events are created atomically with orders and reuse one event UUID for browser Meta and CAPI deduplication.
- Assistant sessions require explicit AI disclosure, scoped ownership, idempotent client message IDs, bounded rates and encrypted redacted retention. Product/policy/order responses use server-side allowlisted tools and structured citations.
- Admin engagement APIs expose masked delivery/subscription/session data, provider capabilities and safe retry/cancel operations; credentials and raw recipients are never returned.

Notification, CAPI, cart-reminder and assistant-cleanup jobs use leased `SKIP LOCKED` workers with terminal dead-letter/suppression states. Order verification requires number plus phone and returns only redacted customer-safe status.
