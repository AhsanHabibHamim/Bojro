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
