# Accessibility And Performance Evidence

This is the Phase 8 evidence protocol. Automated scores are release gates, not a WCAG conformance claim. Production launch requires both automated artifacts and dated manual review in Bangla and English.

## Automated CI Gate

The `Quality / compose-smoke` job runs against a fresh local production build and uploads artifacts on success or failure.

| Check                          | Scope                                                  | Gate                                                                                                                           |
| ------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Lighthouse mobile              | BN/EN home and representative product, three runs each | Median performance >=0.90, median accessibility >=0.95, median LCP <=2,500 ms                                                  |
| Playwright accessibility smoke | BN/EN home and representative product                  | Correct language, landmark/heading basics, accessible names, form labels, alt text, unique IDs, no obvious horizontal overflow |
| Full Playwright suite          | Customer/admin/mobile/provider/engagement flows        | No unexpected skip/failure; HTML report retained                                                                               |
| Unit/type/lint/build           | Frontend and generated contract                        | All pass                                                                                                                       |

Lighthouse uses its standard mobile simulated throttling profile; do not lower CPU slowdown or disable network throttling to pass. The median is the middle of three independent runs for each route and metric. CI stores raw reports plus `lighthouse-summary.json`.

The repository accessibility smoke is intentionally dependency-light and axe-like, not the complete axe ruleset. Run current axe-core or an equivalent approved scanner against staging and attach its full result before launch.

## Required Route Matrix

At minimum test these in `bn` and `en`, mobile and desktop where interactive:

- Home, category/list/search, and representative in-stock/out-of-stock/discounted product.
- Cart drawer/page, coupon/shipping estimate, checkout validation, ambiguous result, and success.
- OTP/email login, account dashboard/profile/address/orders/wishlist/reviews/support.
- Order tracking and payment-return states.
- Newsletter consent/unsubscribe, analytics consent, assistant disclosure/chat/order verification, WhatsApp handoff.
- Admin login/TOTP, dashboard, product/inventory/media, order/payment/refund/shipment, customer/review, content/settings/audit, provider/webhook/engagement views.
- Loading, empty, validation, 403/404/409/412/429, offline/provider unavailable, and global error states.

## Manual WCAG AA Review

Record pass/fail/not-applicable plus evidence for each item:

- Keyboard-only navigation, logical tab order, visible focus, skip link, no traps, Escape/close, and focus restoration.
- Dialog/drawer/menu semantics, inert background, accessible name/description, and announced dynamic state.
- Form labels, instructions, required/error association, field-level server errors, autocomplete/input purpose, and no color-only status.
- Heading hierarchy, landmarks, page titles, language changes, link purpose, button names, table headers, and list semantics.
- Image alt decisions, product/review evidence descriptions, decorative image treatment, icons, charts, and animation alternatives.
- Text/non-text contrast, focus indicator contrast, hover/active/disabled states, forced colors, and dark/system contrast where supported.
- 200% text zoom and 400% browser zoom/reflow at 320 CSS px with no two-dimensional scrolling except essential tables/media.
- Touch targets and spacing on representative low-width Android viewport.
- Reduced motion, paused/reduced Lottie/Framer effects, no flashing, and no motion-only information.
- Screen-reader checks with at least NVDA + Firefox/Chrome on desktop and TalkBack + Chrome on Android.
- Bangla pronunciation/order, Unicode numerals/currency, mixed-language accessible names, font fallback, line height, wrapping, and truncation.
- Session expiry, logout, cart updates, quote expiry, payment status, upload progress, notifications, and errors announced without repeated/noisy live regions.
- CAPTCHA/provider-hosted pages and external payment/courier journeys have an accessible fallback/support path.

Any blocker preventing purchase, authentication, support, account control, or admin safety by keyboard/screen reader is no-go regardless of Lighthouse score.

## Performance Review

Automated local CI is a regression gate. Before launch, repeat the three-run median on the deployed staging custom domains and once on production before general traffic.

Record:

- Lighthouse version, Chromium version, runner region, commit SHA, environment, route, locale, cache state, and raw reports.
- Median performance/accessibility/LCP, plus individual run values.
- Core Web Vitals or field data when available: LCP, INP, and CLS at p75 by route class and locale.
- JavaScript, CSS, image, font, and total transfer size; largest requests and third-party origin count.
- Server/route cache status, API response time, image format/dimensions, font subset/load behavior, and hydration errors.
- Provider/analytics behavior before and after consent.

Launch thresholds:

| Metric                        | Gate                                                                         |
| ----------------------------- | ---------------------------------------------------------------------------- |
| Lighthouse mobile performance | Median >=90 on every required public route                                   |
| Lighthouse mobile LCP         | Median <2.5 seconds                                                          |
| Lighthouse accessibility      | Median >=95; no known critical/serious scanner finding                       |
| CLS                           | <=0.1 at p75 or lab equivalent                                               |
| INP                           | <=200 ms at p75 when field data exists; otherwise interaction trace reviewed |
| Route errors                  | No hydration/console error or failed required resource                       |

A single route/locale below threshold fails the gate. Do not average Bangla and English or home and product together.

## Evidence Record

| Field                                         | Value |
| --------------------------------------------- | ----- |
| Review ID and date                            |       |
| Commit SHA and deployment IDs                 |       |
| Reviewer(s), including native Bangla reviewer |       |
| Browser/AT/device matrix                      |       |
| CI Quality run URL                            |       |
| Lighthouse artifact URL and summary           |       |
| Playwright artifact URL                       |       |
| Axe/equivalent staging report URL             |       |
| Manual checklist artifact                     |       |
| Screen-reader notes/recording                 |       |
| 200%/400% reflow evidence                     |       |
| Contrast evidence                             |       |
| Known issues, severity, owner, due date       |       |
| Result (`PASS` or `FAIL`)                     |       |
| Expiry/retest date, maximum 90 days           |       |

Artifacts must not contain credentials, browser storage, customer/admin PII, raw provider payloads, or production session recordings.

## Local Phase 8 Evidence (Not Launch Approval)

- Date/environment: 2026-11-08, local Docker Compose production images, Lighthouse 12.8.2/Chromium headless.
- Browser acceptance: 49/49 Playwright scenarios passed, including axe WCAG A/AA checks, BN/EN, mobile/admin, offline/CSP/SEO, all commerce, provider and engagement flows.
- Accessibility: Lighthouse 99–100 on measured home/product routes; zero known critical/serious axe violations; CLS was zero in recorded runs.
- Standard Lighthouse mobile performance: local runs remained approximately 65–69 with LCP around 3.2–3.7 seconds and TBT around 1.1–1.3 seconds, below the release gate despite removing the 741 KB Lottie runtime from the critical bundle.
- Result: **FAIL / launch blocked** for performance. Owner: frontend performance. Required action: profile the deployed staging custom domain, reduce hydration/main-thread work and obtain three-run median >=90 with LCP <2.5 seconds before launch approval.
- This record does not replace native-Bangla, screen-reader, 400% reflow or deployed-staging evidence.
