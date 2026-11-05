# API Contract

The REST API is rooted at `/api/v1`. FastAPI serves interactive OpenAPI documentation at `/docs`, ReDoc at `/redoc`, and the raw schema at `/openapi.json`.

## Operational Endpoints

- `GET /health`: process liveness; no external dependency is required.
- `GET /ready`: checks PostgreSQL and Redis and returns `200` when required dependencies are ready, otherwise `503`.
- `GET /api/v1/health`: versioned health response for API clients.

Every response includes `X-Request-ID`; a valid inbound ID is retained, otherwise the API creates one. Errors use FastAPI's structured error shape in Phase 1 and will gain a shared domain envelope with feature routers.

## Client Generation

Run `pnpm api:generate`. The command boots no server: it imports the FastAPI app, writes a sorted `backend/openapi.json`, then runs `openapi-typescript` to produce `frontend/src/lib/api/schema.d.ts`.

Generated files are committed so Vercel and editor builds do not require Python. CI regenerates them and rejects drift.
