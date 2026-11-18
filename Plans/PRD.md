# Gift Card Discounts - PRD

**Target:** Safari / macOS, US discounted gift cards, GCX first.  
**Current build:** Public GCX catalog collector, AWS runtime/infrastructure source, and built local Safari app; cloud deployment and actual Safari acceptance pending.

## 1. Product and browser behavior

Recognize a retailer's hostname locally and show an unobtrusive, dismissible pill only when its best advertised GCX discount is strictly greater than 1%. Show the up-to percentage before fees and a visible direct GCX retailer purchase-page link; never complete purchases. Show at most once per retailer per Safari session, including across aliases, subdomains, tabs, and background-worker restarts. Session dismissal, 24-hour snooze, persistent retailer suppression, and restoration are available. Missing inventory or expired data produces no notification.

The pill expands into provider, maximum, optional average/count, observation time, and an explicit offer link in a new tab. Use keyboard-accessible controls, dark mode, isolated styles, and no unsolicited focus changes. Do not imply that last-observed inventory is reserved or guaranteed available now. Synthetic offers must be opt-in, clearly labeled, and non-purchasable.

Download the same compact snapshot on first extension use in each Safari session; perform no per-navigation server queries. Retain the last valid cache. A failed refresh does not cause repeated requests during navigation. Offer expiry is evaluated from `observed_at`, never from a cache refresh or HTTP 304.

## 2. Provider discovery findings and release gate

2026-10-24 implementation: ordinary unauthenticated public HTML collection now works for 11 reviewed retailers. It records `catalog_advertised` maximum discounts, excludes GCX Cash, and leaves counts/averages unknown. These are possible cost-profile savings before fees, not per-card inventory or a checkout quote. The user authorized public scraping for estimates; no purchases, authentication or access-control bypasses are involved. Source evidence and fee limitations are in the implementation’s `docs/GCX-SOURCE.md`. Provider permission/redistribution remains a production concern.

The current public GCX catalog distinguishes advertised discounts from GCX Cash. GCX's terms restrict collection/republication without permission and describe buyer fees. Treat displayed percentages as **before fees**, exclude rewards, and obtain a permitted source before production collection. No live inventory JSON endpoint or retailer-average formula has been verified in this prototype.

Sources checked during this implementation:

- [GCX catalog](https://gcx.app/buy-gift-cards)
- [GCX terms, sections 4(i) and 6](https://gcx.app/terms)
- [Apple Safari compatibility, including session storage](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility)
- [Apple extension packaging](https://developer.apple.com/documentation/safariservices/packaging-a-web-extension-for-safari)

The earlier plan's assumption that the GCX frontend API was readily usable is unverified. `fixtures/demo-batch.json` is our synthetic interchange format, not a captured provider response. No login, CAPTCHA, or access-control circumvention is part of this project.

## 3. Architecture

Production target remains:

```text
EventBridge -> Python collector Lambda -> DynamoDB observations
                                      -> validated snapshot -> S3 / CloudFront
                                                            -> Safari local cache
```

GitHub hosts source and CI. No RDS, dynamic read API, user account system, or browsing analytics is needed. Cadence starts daily and remains provider-configurable. Decide bounded fan-out/retry orchestration after measuring the authorized source's request limits and collection duration.

Prototype substitutes a local JSON importer, SQLite history, and atomic file publication so normalization and client behavior can be developed independently of provider access. This does not represent a completed scraper or deployed AWS backend.

## 4. Contracts

| Entity | Fields / rules |
| --- | --- |
| Retailer | Stable `id`, display `name`; manually reviewed domain mappings initially |
| Domain | Canonical hostname, `retailer_id`, `include_subdomains`, `enabled`; most-specific label match wins; disabled mappings block fallback |
| Provider | Stable ID, display name, approved offer-link hosts |
| Observation | Provider + retailer + run + observation timestamp, availability, maximum/average, average method, optional count/value, currency, offer URL, demo flag |
| Snapshot | `schema_version`, `demo`, generation/source timestamps, freshness limit, domain map, retailer map, provider map; offers retain individual observation/expiry timestamps |

Percentages use percentage points: `12` means 12%, not 0.12. Maximum means the best available listing at observation. With complete listings, average is weighted by remaining face value and quantity. If a provider supplies an average, retain it with `average_method: provider_reported` until its semantics are verified. Unknown values are `null`, never fabricated or zero-filled. Money aggregates use integer USD cents.

The source batch declares completeness and explicitly reports every configured retailer as available or no-inventory. Unknown/error is not no-inventory. The V0 importer handles one provider per batch; the snapshot contract permits multiple provider offers, but multi-provider collection/merging is future work.

## 5. Publishing, freshness, and privacy

Validate the complete candidate before writing history or replacing the published snapshot. Preserve history on retries without rewriting prior observations; reject conflicting IDs and older replacement snapshots. A complete, verified all-no-inventory result may publish empty data; a failed/partial result may not. Local publication uses temporary-file replacement; distributed cloud concurrency protection remains a deployment requirement.

Prototype expiry defaults to **48 hours**, configurable; this is an engineering default rather than an agreed live-feed SLA. Keep expiry in V1, not a later feature. Long-running sessions may need manual refresh after expiry. Retain original observation timestamps during retries and rebuilding.

Browser activity and suppression settings remain local. Fetch snapshots without credentials/referrer; allow only approved HTTPS provider links. Render all remote strings as text. Demo and production caches/publication paths must not be mixed. No AWS credentials or provider sessions belong in extension files. Add least-privilege IAM, deployment budgets, operational alarms, and bounded log retention before cloud release.

## 6. Scope and acceptance

V1 includes verified GCX collection, historical observations, daily serverless publication, cached Safari matching, unobtrusive notification, suppression, and failure handling. A release must pass the local tests plus real Safari permission/session/offline tests and AWS end-to-end tests against the permitted source.

Out of scope: purchases, checkout integration, coupons, cashback, credit-card offers, international inventory, accounts, prediction, history charts, and additional browsers. Fold/Gift Card Granny and provider comparisons are future work; adding them must not require changing retailer identity or the core snapshot contract.
