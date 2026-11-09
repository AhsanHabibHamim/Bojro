FROM node:25-alpine AS dependencies
RUN corepack enable && corepack prepare pnpm@11.5.2 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile

FROM node:25-alpine AS builder
RUN corepack enable && corepack prepare pnpm@11.5.2 --activate
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=dependencies /app/frontend/node_modules ./frontend/node_modules
COPY . .
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT=
ARG NEXT_PUBLIC_E2E_STORAGE_MOCK=false
ARG NEXT_PUBLIC_E2E_PROVIDER_MOCK=false
ARG NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK=false
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT=$NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT
ENV NEXT_PUBLIC_E2E_STORAGE_MOCK=$NEXT_PUBLIC_E2E_STORAGE_MOCK
ENV NEXT_PUBLIC_E2E_PROVIDER_MOCK=$NEXT_PUBLIC_E2E_PROVIDER_MOCK
ENV NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK=$NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK
RUN pnpm --filter @bojro/frontend build

FROM node:25-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx
WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/static ./frontend/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/frontend/public ./frontend/public
USER nextjs
EXPOSE 3000
CMD ["node", "frontend/server.js"]
