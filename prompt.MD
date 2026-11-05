# ROLE
You are a Principal Full-Stack Engineer and Solution Architect with 15+ years
building high-traffic e-commerce platforms, plus a senior product designer's eye
for polish. You write production-grade, typed, tested, documented code. You
think before you build, you verify what you build, and you never leave the
project in a broken state.

# MISSION
Build "Bojro" (বজ্র, "Bojro"): a complete, Bangla-first, mobile-first,
single-brand e-commerce platform for Bangladesh (domain: bojro.com.bd).
UX reference: Cartup (cartup.com) — big search, flash sales, category grids,
sticky mobile cart bar, COD-first checkout. Bojro is NOT a marketplace: no
vendors, no seller dashboards, ONE admin. Visual feel: premium, alive,
animated (Lottie + motion), consistent with the brand system below.
No files are attached; everything needed is in this document.

# WORKING PROTOCOL (follow strictly)
1. Work in the PHASES listed in section 12. Do ONE phase at a time, then stop
   and wait for me to say "next".
2. Before coding a phase: print a short plan (files to create, decisions,
   risks). Then build.
3. After coding a phase: run install, lint, typecheck, tests and the dev
   servers. Fix everything. Do not report "done" while anything fails.
4. Then print: what was built, how to run it, how to verify it (exact commands
   and URLs), known limitations, and the acceptance checklist ticked off.
5. Do not ask me questions unless truly blocked. For ambiguity, choose the
   sensible default and log it in /docs/DECISIONS.md (date, decision, reason).
6. Never hardcode secrets. Never invent API credentials. Never fake an
   integration: if credentials are missing, implement against the official
   sandbox spec behind an interface and a mock, and mark clearly in docs.
7. Small, logical commits with conventional messages (feat:, fix:, chore:).
8. Keep the repo always runnable from a fresh clone with the README steps.

# 1. BRAND SYSTEM
Logo: Bangla "বজ্র" in heavy rounded-geometric deep-indigo lettering, with a
purple lightning bolt (white inner highlight) striking through a soft purple
heart-like arc above. Until I supply the real file, generate placeholders
/public/logo.svg and /public/icon.svg (bold "বজ্র" in Noto Serif Bengali
ExtraBold + SVG bolt). Build a <Logo/> component so swapping to /public/logo.png
needs no code change. Generate favicon, apple-touch-icon and PWA icons.

Palette (tokens in Tailwind theme + CSS variables):
- Deep Indigo #2A1565 (headings, footer, announcement bar)
- Brand Purple #5B2FC9 (buttons, links, prices, active)
- Electric Violet #7C4DFF (bolt accents, hover, focus ring)
- Soft Lavender #EDE7FF (chips, marquee, section bands)
- Background #F7F5FC, Surface #FFFFFF
- Text #1B1033 / secondary #5E5675
- Sale Amber #FFB400 (only non-logo color: discount badges, flash timer, low stock)
- Success #16A34A, Error #DC2626
- Signature gradient: linear-gradient(135deg, #2A1565, #5B2FC9, #7C4DFF)
Style: rounded 12–16px cards, soft purple-tinted shadows, generous whitespace,
lightning-bolt motifs used sparingly (underlines, loaders, dividers, 404).

# 2. TYPOGRAPHY (FINAL)
Via next/font/google, display: swap, subsets latin + bengali, exposed as CSS
variables switched by active language:
- EN headings: "Chonburi" 400 (retro chunky display serif), Title Case,
  fallback "Rozha One", serif
- BN headings: "Noto Serif Bengali" 700–800
- EN body/UI: "Nunito Sans" 400/600/700
- BN body/UI: "Hind Siliguri" 400/500/600
Variables: --font-display, --font-display-bn, --font-body, --font-body-bn.
Text styles:
- Section headings: centered, clamp(28px → 44px), Deep Indigo, small bolt/purple
  underline accent
- Body: 16–17px, line-height 1.7 (Bangla 1.8), #5E5675, max 60ch
- Hero: 2-line display heading, left-aligned, short paragraph, 3–4 ✔ benefit
  lines with animated icons, one gradient pill CTA, eyebrow with animated ★★★★★
  and a count-up "১০,০০০+ সন্তুষ্ট কাস্টমার"
- Product title: 14–15px/600, 2-line clamp, centered; price bold Brand Purple,
  old price struck grey, discount as Amber pill
- Buttons: pill; outlined "Add to Cart" fills purple on hover with tiny bolt
  animation; primary CTA uses signature gradient
- Prices "৳" with Bangla numerals in BN mode (৳১,২৫০); one formatter util only

# 3. ARCHITECTURE (decisions are LOCKED; do not deviate)
Monorepo (pnpm workspaces):
/frontend  Next.js (App Router, TypeScript strict, Tailwind) -> Vercel
/backend   FastAPI (Python 3.12, async SQLAlchemy 2, Alembic, Pydantic v2) -> Railway
/docs      ARCHITECTURE.md, DECISIONS.md, API.md, DEPLOYMENT.md, LOTTIE_TODO.md
/infra     docker-compose.yml (postgres, redis, backend, frontend), .env.example files

Principles:
- REST API under /api/v1, OpenAPI is the source of truth. Generate a typed TS
  client from the OpenAPI schema into /frontend/src/lib/api (no hand-written
  fetch calls scattered around).
- Backend layers: routers -> services (business logic) -> repositories (DB).
  No business logic in routers. Dependency injection for providers.
- Rendering: Server Components + ISR for catalog (revalidate by tag when admin
  edits), client components only where interactivity is needed. Cart/checkout/
  account are dynamic.
- Caching: Redis for rate limiting, OTP storage, cart-session cache and hot
  catalog queries. Graceful fallback if Redis is absent in dev.
- Background work (emails, SMS, courier sync, webhooks retries): ARQ (Redis)
  workers; keep jobs idempotent.
- Auth: short-lived JWT access token + rotating refresh token, both in httpOnly,
  Secure, SameSite=Lax cookies (CSRF token for state-changing requests).
  Argon2 password hashing. Phone-number OTP login (primary for BD) + email
  login. Guest checkout creates a lightweight guest customer record.
- Money: store ALL amounts as integer poisha (BIGINT) with currency "BDT".
  Never floats. One Money util on both sides.
- Phone numbers: normalize to E.164 (+8801XXXXXXXXX); validate BD operators.
- IDs: UUIDv7 or ULID for public IDs; human order numbers like BJ-2026-000123.
- Timestamps: timestamptz UTC in DB, display in Asia/Dhaka.
- i18n: translatable fields stored as name_bn / name_en (and description_*)
  columns on catalog tables; UI strings in message catalogs (next-intl).

# 4. DATA MODEL (create with Alembic migrations, add proper indexes/constraints)
users(id, role[customer|admin], name, phone UNIQUE, email UNIQUE NULL,
 password_hash NULL, is_guest, created_at)
addresses(user_id, label, recipient, phone, division, district, upazila,
 address_line, is_default)
geo_divisions/districts/upazilas (seed full Bangladesh hierarchy, bn + en names)
categories(id, parent_id, slug, name_bn, name_en, icon, image, sort, is_active)
brands(id, slug, name)
products(id, slug, category_id, brand_id, name_bn, name_en, desc_bn, desc_en,
 status, is_featured, rating_avg, rating_count, sold_count, seo_*)
product_variants(id, product_id, sku UNIQUE, options JSONB, price, compare_at_price,
 stock_on_hand, stock_reserved, weight_g, is_active)
product_images(product_id, variant_id NULL, url, alt, sort)
carts / cart_items (server-side cart for logged-in + guest via cookie id)
coupons(code, type[percent|fixed|free_shipping], value, min_subtotal, max_discount,
 usage_limit, per_user_limit, starts_at, ends_at, is_active)
flash_sales + flash_sale_items(sale_price, qty_limit, sold_qty)
orders(id, number, user_id, status, payment_status, payment_method, subtotal,
 discount_total, shipping_total, grand_total, coupon_code, address_snapshot JSONB,
 notes, placed_at) ; order_items(snapshot of name, sku, price, qty)
order_status_history(order_id, from, to, actor, note, at)
payments(order_id, provider, provider_txn_id, amount, status, raw_payload JSONB,
 idempotency_key UNIQUE)
shipments(order_id, courier, consignment_id, tracking_code, status, raw JSONB)
reviews(product_id, user_id, rating, body, photos, status[pending|approved|rejected],
 is_verified_purchase)
wishlist_items, recently_viewed (client + optional server), support_tickets/messages
banners, homepage_sections(type, order, is_visible, content_bn JSONB, content_en JSONB)
static_pages(slug, title_bn/en, body_bn/en), site_settings(key, value JSONB)
audit_logs(actor, action, entity, entity_id, diff, at), webhook_events(provider,
 event_id UNIQUE, payload, processed_at)

# 5. CORE BUSINESS RULES
- Order state machine (enforce in one service, reject illegal transitions):
  pending -> confirmed -> processing -> shipped -> delivered -> completed;
  cancel allowed before shipped; returned/refunded after delivered.
  Every transition writes order_status_history + audit log.
- Inventory: on order placement run a transaction with SELECT ... FOR UPDATE on
  variants, move qty to stock_reserved; on shipped decrement stock_on_hand; on
  cancel release. Never oversell. Flash-sale quantity limits enforced the same way.
- Price integrity: server recalculates all totals; never trust client prices.
  Coupon validation (limits, dates, min subtotal) happens server-side.
- Idempotency: order creation and payment initiation accept an Idempotency-Key
  header; webhooks deduplicated through webhook_events.event_id.
- Shipping: zone rules (inside Dhaka / outside Dhaka), weight tiers, free-shipping
  threshold, all editable in site_settings.
- COD risk: phone-based return-rate check; for risky numbers require advance
  payment (toggle in settings).
- Reviews only from verified buyers can show a "Verified" badge; moderation queue.

# 6. INTEGRATIONS (each behind an interface + sandbox + mock implementation)
PaymentProvider: COD, bKash (tokenized checkout), Nagad, SSLCommerz (cards/MFS,
IPN validation with server-side verification call). CourierProvider: Pathao,
Steadfast, RedX (create consignment, store tracking, status webhook/polling).
NotificationProvider: email (SMTP/Resend) + SMS (pluggable BD gateway) with
templates in Bangla + English for: order placed, confirmed, shipped, delivered,
OTP. Analytics: Facebook Pixel + Conversions API (server-side, deduplicated
with event_id), GA4: ViewContent, AddToCart, InitiateCheckout, Purchase.
Storage: Cloudinary (signed uploads from admin).
Chat: floating WhatsApp button (number from settings) + separate floating
live-chat assistant button. The assistant answers store questions
(delivery, returns, order status by order number + phone, products) in
Bangla/English via an LLM API (key in env), with a friendly agent name/persona.
It must NEVER claim to be human if a customer sincerely asks, and should hand
off to WhatsApp for complex issues. Rate-limit it and keep it grounded on
store data/policies only.

# 7. STOREFRONT SPEC
Header: thin Deep Indigo announcement bar ("ফ্রি ডেলিভারি ৳১৫০০+ অর্ডারে ⚡"),
sticky header (logo, large search with autocomplete + recent searches, nav:
Home, Shop All ▾ mega menu, Our Story, Blog, Contact; account; cart with live
count; language toggle). Mobile: bottom tab bar (Home, Categories, Cart, Account).
Homepage sections in this order, ALL admin-editable (text, images, order,
visibility, bn/en):
1 Hero (lavender textured bg, text left, product art right, banner slider)
2 Infinite marquee ticker (Lavender): "১০০% অথেনটিক ⚡ · ক্যাশ অন ডেলিভারি 🚚 ·
  ফাস্ট ডেলিভারি ⚡ · ইজি রিটার্ন ↩" (pause on hover)
3 Promo chips (Latest Drops, Lowest Price, 100% Authentic)
4 Flash Sale (countdown + horizontal scroller)
5 "Meet Our Best Sellers" — 4 large category cards
6 "Best Selling" grid (2x4; 2 columns on mobile)
7 Alternating image/text feature bands with CTA
8 3 featured category cards on solid Brand Purple band
9 "Why Bojro vs Others" ✔/✖ comparison around a center image
10 Social proof "Join the Bojro family" photo strip
11 Free-shipping/offer banner
12 Brand story (logo, heading, 2 paragraphs, "Read Full Story")
13 Reviews carousel (autoplay, animated 5★, avatar, verified badge)
14 "Deals You Can't Miss" infinite-scroll grid
15 Footer (logo, contact, Shop links, Quick links, subscribe, socials, payment
   logos bKash/Nagad/Visa/Mastercard/COD/SSL, copyright)
Other pages: category (filters: price, brand, rating, discount, stock; sort;
grid/list; URL-synced filters), product (zoom gallery, variants, price/old
price/discount %, stock indicator, delivery estimate by district, reviews, Q&A,
related, sticky mobile add-to-cart), search, cart (drawer + page, coupon, shipping
calc), checkout (guest OK; Division>District>Upazila selects; phone 01XXXXXXXXX
validation; payment method; review), order success, order tracking (number +
phone), customer dashboard (profile, addresses, orders with status timeline,
wishlist, reviews, coupons, tickets), static pages (About, Help/FAQ, Contact,
Return & Refund, Privacy, Terms, Warranty), blog, custom 404/500.

# 8. MOTION, LOTTIE & ICONS (HIGH PRIORITY — site must feel alive and premium)
Libs: framer-motion, lottie-react (or @lottiefiles/dotlottie-react),
@phosphor-icons/react (duotone) + lucide-react, react-countup,
embla-carousel-react (autoplay).
Lottie rules: store in /public/lottie, lazy-load via dynamic import, play only
in viewport, <= 300KB total per page, recolor to brand palette. Build a single
<LottieIcon name=... fallback=... /> wrapper. You cannot download assets: author
simple Lottie JSON yourself where feasible (bolt pulse, checkmark, heart burst,
cart bounce, loader, confetti); otherwise render a CSS/SVG fallback animation and
list each missing slot in /docs/LOTTIE_TODO.md with a LottieFiles search keyword.
Use for: hero bolt/sparkle particles; trust badges (COD, fast delivery,
authentic, easy return, secure payment); add-to-cart success; wishlist heart
burst; flash-sale fire/bolt; empty states (cart/search/orders/wishlist); route
loader; order-success confetti; tracking truck; 404; animated review stars.
Icons: every heading, feature card, benefit item and footer link gets a fitting
duotone icon, consistent 24–32px, brand colors.
Motion: headings fade-up on scroll; staggered hero words; count-up numbers;
shimmer on Sale/Flash labels; product card lift + image zoom; quick-add and
wishlist icons slide in on hover; category tilt; stagger children 80–120ms.
Respect prefers-reduced-motion; zero layout shift.

# 9. ADMIN PANEL (single admin; no roles beyond admin; optional TOTP 2FA)
Dashboard (sales, revenue chart, orders by status, low stock, top products);
products (CRUD, variants, bulk CSV import/export, Cloudinary upload, drag-sort
images); categories, brands; orders (filters, status transitions via the state
machine, invoice + packing-slip PDF, "Send to courier" one-click, notes);
customers; review moderation; coupons; flash sales; homepage manager;
static pages + blog editor; site settings (logo, contacts, WhatsApp number,
shipping rules, payment toggles, social links, pixel IDs, announcement text).
Fast tables (server-side pagination/search), keyboard-friendly, mobile usable.

# 10. SECURITY, PERFORMANCE, QUALITY
- Security: input validation everywhere, parameterized queries, rate limiting
  (login, OTP, checkout, chat), secure headers/CSP, CORS allowlist, file-upload
  validation, no PII in logs, webhook signature verification, admin routes
  protected server-side, audit log for admin actions, OWASP top-10 review in
  /docs/SECURITY.md.
- Performance: Lighthouse mobile >= 90, LCP < 2.5s on 4G, next/image + WebP,
  font subsetting, route-level code splitting, DB indexes for every filter/sort,
  no N+1 queries (verify), HTTP caching + ISR tags.
- SEO: SSR/ISR, dynamic meta + OpenGraph, JSON-LD (Product, BreadcrumbList,
  Organization), sitemap.xml, robots.txt, Bangla-safe slugs, canonical URLs.
- Accessibility: WCAG AA contrast, focus states, keyboard nav, aria labels,
  alt text.
- Observability: structured JSON logs, request IDs, Sentry hooks (env-gated),
  /health and /ready endpoints.
- Testing: pytest (services, state machine, inventory concurrency, coupons,
  payment webhooks), Vitest for utils/components, Playwright E2E for the golden
  path (browse -> add to cart -> checkout COD -> order tracking) and admin
  order processing. CI via GitHub Actions: lint, typecheck, test, build.
- Code quality: ruff + mypy (backend), eslint + prettier + tsc strict
  (frontend), pre-commit hooks, no dead code, no TODO left without an entry in
  /docs.

# 11. CONTENT
All copy realistic Bangla and English; no lorem ipsum. Seed >= 40 demo products
across >= 8 categories with variants, images (use generated SVG/gradient product
placeholders or public-domain URLs; keep a single seed script), 20 reviews,
3 coupons, 1 flash sale, full BD geo data, sample banners, homepage sections,
and one admin account created from env vars (never a default password in code).

# 12. PHASES AND ACCEPTANCE CRITERIA
Phase 1 — Foundation: monorepo, docker-compose, env templates, Tailwind theme
 (palette + fonts), i18n (bn default), <Logo/>, placeholder assets, layout
 (announcement bar, header, footer, mobile tab bar), marquee, <LottieIcon/>
 wrapper with fallbacks, DB schema + migrations, seed script, OpenAPI -> TS client
 pipeline, CI workflow, health endpoints.
 Accept: `docker compose up` (or documented dev commands) runs everything;
 seeded DB; layout renders in bn/en on mobile + desktop; lint/type/test pass.
Phase 2 — Catalog: categories, product list/filters/search (autocomplete),
 product page, home page sections 1–15 reading real data, ISR + tag revalidation.
 Accept: all homepage sections render from API; filters URL-synced; Lighthouse
 mobile >= 90 on home and product page.
Phase 3 — Cart & Checkout: server cart (guest + user), coupons, shipping calc,
 guest checkout, OTP/email auth, COD order placement with inventory reservation,
 order success + tracking.
 Accept: concurrent-order test proves no overselling; totals always recomputed
 server-side; E2E golden path passes.
Phase 4 — Customer Area: dashboard, addresses, order history timeline,
 wishlist, reviews with photos, coupons, support tickets.
Phase 5 — Admin Panel: all modules in section 9 with audit logging.
 Accept: admin can run the full order lifecycle without touching the DB.
Phase 6 — Payments & Couriers: bKash, Nagad, SSLCommerz, Pathao, Steadfast,
 RedX behind interfaces; webhooks with verification + dedupe; sandbox docs.
 Accept: each provider has a mock + contract tests; webhook replay is idempotent.
Phase 7 — Engagement: chat assistant + WhatsApp, email/SMS notifications,
 Pixel + CAPI + GA4 with event dedupe, newsletter, abandoned-cart reminder job.
Phase 8 — Hardening & Launch: SEO pass, performance pass, security review,
 a11y audit, E2E suite, README, DEPLOYMENT.md (Vercel + Railway + Cloudinary +
 domain/DNS + env vars checklist), backup/restore notes, launch checklist.

# START
Begin with Phase 1 only. First print your plan, then build, verify, and report
using the protocol in the WORKING PROTOCOL section.