# Gift Card Discounts - Tasks

## Done: first executable slice

- [x] Research current public provider surface; document access and metric limitations.
- [x] Define retailer/domain/provider and normalized observation contracts.
- [x] Create clearly synthetic fixtures; do not represent them as captured GCX responses.
- [x] Implement complete-batch validation, discount calculation, optional metrics and explicit no-inventory records.
- [x] Implement idempotent local observation history and guarded atomic snapshot publication.
- [x] Implement local matcher, subdomain/alias handling, expiry and demo guards.
- [x] Implement cached refresh, HTTP conditional requests, offline fallback and session-wide deduplication.
- [x] Implement pill/details, dismissal, snooze, persistent suppression and restoration.
- [x] Package Safari Web Extension source and a Mac packaging script.
- [x] Build interactive local preview with no production services required.
- [x] Run Python and JavaScript unit tests, plus offline Chromium preview checks.
- [x] Add GitHub test CI and update the three planning files.

## Next: verify the two integration boundaries

- [ ] Obtain/confirm permitted GCX collection and redistribution access.
- [x] Verify the actual catalog/inventory response, paging, identifiers, URLs and rate limits.
  - status: Done for public HTML catalog surface (not a private inventory API).
  - completion: Live collect 2026-11-17 succeeded for 11 retailers; docs/GCX-SOURCE.md records paging/budget/fail-closed behavior. Per-card inventory JSON still unavailable publicly.
  - updated: 2026-11-17
- [x] Capture sanitized real fixtures; establish maximum/average/fee semantics without guessing.
  - status: Done for advertised maxima; averages/fees remain unknown/before_fees.
  - completion: fixtures/gcx-catalog-captured.html refreshed 2026-11-17; averages stay null; fee schedule documented but not invented into net cost.
  - updated: 2026-11-17
- [x] Implement GCX adapter and bounded collection/retries against those fixtures.
  - status: Done
  - acceptance: Bounded public-catalog parsing; no purchases or bypasses; drift/errors fail closed.
  - completion: giftcard_tool/gcx.py, __main__.py, fixtures/gcx-catalog-captured.html, docs/GCX-SOURCE.md; live advertised maxima collected; unknown inventory/averages remain null.
  - verification: 72 collector + pipeline tests passed; 11-retailer live collection and import succeeded.
  - blockers: None
  - updated: 2026-10-24T08:32:42+00:00
- [x] Expand reviewed retailer-to-domain mappings beyond the three demo examples.
  - status: Done
  - acceptance: Reviewed merchant mappings beyond original three.
  - completion: config/retailers-live.json covers 11 retailers; separate demo catalog preserved.
  - verification: Live batch imported all 11 retailers; merchant source links in docs/GCX-SOURCE.md.
  - blockers: None
  - updated: 2026-10-24T08:32:42+00:00
- [ ] Generate/build the app with Xcode and test actual Safari installation and website permission flow.
  - status: Needs Review
  - acceptance: Build app and complete actual Safari permission/runtime checks.
  - completion: scripts/package-safari.sh bundle ID corrected; scripts/build-safari.sh builds Release in temporary folder; portable ad-hoc app ZIP verified; SAFARI-CHECKLIST.md lists actual Safari checks.
  - verification: Release xcodebuild succeeded; extracted ZIP codesign --verify --deep --strict passed; bundled extension resources match source.
  - blockers: Actual Safari extension not enabled; Allow unsigned extensions is on after user approval and local authentication; containing app launched; extension itself remains disabled; no distribution signing identity. User must review development setting or supply signing identity.
  - updated: 2026-10-24T08:32:42+00:00
- [ ] Confirm one notification across tabs/aliases, worker suspension and actual Safari quit/reopen.
- [ ] Verify notification layout on retailer pages and manual refresh/offline/suppression restoration.

**Gate:** A permitted source is necessary for live offers. Xcode/Safari testing is necessary for a usable Safari release. Neither is completed by mocked/local tests.

## Then: AWS production runtime

- [x] Implement infrastructure as code for EventBridge, Lambda, DynamoDB, S3 and optional CloudFront.
  - status: Done
  - acceptance: Deployable infrastructure source and locally tested runtime.
  - completion: infra/template.json and giftcard_tool/aws_runtime.py implement scheduled bounded collection, history/current keys and conditional snapshot publication; infra/README.md documents deployment.
  - verification: 11 offline AWS tests passed; real 11-retailer batch exercised fake cloud stores.
  - blockers: AWS deployment explicitly deferred by user; no cloud resources created.
  - updated: 2026-10-24T08:32:42+00:00
- [x] Adapt history persistence to DynamoDB; use provider/retailer/time keys and idempotent writes.
  - status: Done
  - acceptance: History writes are idempotent and current records directly addressable.
  - completion: giftcard_tool/aws_runtime.py implements immutable observations and CURRENT keys.
  - verification: 11 offline AWS tests passed; live saved batch produced 11 observations and 11 CURRENT keys.
  - blockers: None
  - updated: 2026-10-24T08:32:42+00:00
- [x] Add an independently addressable current state without scanning unbounded history.
  - status: Done
  - acceptance: History writes are idempotent and current records directly addressable.
  - completion: giftcard_tool/aws_runtime.py implements immutable observations and CURRENT keys.
  - verification: 11 offline AWS tests passed; live saved batch produced 11 observations and 11 CURRENT keys.
  - blockers: None
  - updated: 2026-10-24T08:32:42+00:00
- [x] Implement distributed publication safeguards, retries, failure alarms and source freshness monitoring.
  - status: Done (source only; not deployed)
  - completion: S3 conditional writes, Lambda retry/DLQ, CollectorErrors/StaleSource/DeadLetters alarms in infra/template.json; aws_runtime.py publication races covered by offline tests.
  - blockers: Live alarm verification needs a deployed stack.
  - updated: 2026-11-17
- [x] Add configurable cadence, bounded concurrency and provider-specific request budgets.
  - status: Done (source only; not deployed)
  - completion: Schedule/EnableSchedule/MaxPages/RequestBudget parameters; sequential collection with request budget and pacing in collector + Lambda env.
  - blockers: None for code; cadence change after deploy is a CloudFormation parameter override.
  - updated: 2026-11-17
- [x] Add least-privilege IAM, GitHub deployment identity, budget alerts and bounded log retention.
  - status: Done (source only; not deployed)
  - completion: CollectorRole, optional GitHubDeployRole OIDC params, Budgets resource, 14-day log/failure retention, 30-day noncurrent snapshot versions.
  - blockers: GitHub OIDC/provider ARNs and OpsEmail required at deploy time.
  - updated: 2026-11-17
- [ ] Deploy a test stack and verify collection -> history -> snapshot -> Safari cache end to end.
  - status: Superseded for personal use by GitHub Pages (see below); AWS path still available in infra/.
  - blockers: AWS credentials not required if using Pages.
  - updated: 2026-11-17
- [x] Add GitHub Pages personal publish path (Actions collect → snapshot.json).
  - status: Source ready; remote repo/Pages enablement needs user (gh auth refresh + push).
  - completion: `.github/workflows/pages.yml`, `scripts/build-site.sh`, `site-src/index.html`, `DEPLOY.md`.
  - updated: 2026-11-17
- [ ] Create public GitHub repo, enable Pages (Actions), run first publish, paste feed URL into extension.

## Release checklist

- [x] Live no-inventory and partial-failure behavior validated against the provider.
  - status: Done for collector fail-closed paths; live 11-retailer collect succeeded 2026-11-17.
  - note: Explicit live all-no-inventory day not observed; missing brand / markup drift / HTTP 401/403/429 covered by tests and docs.
  - updated: 2026-11-17
- [x] Fees and average labels accurately describe the real source.
  - status: Done without inventing fee math.
  - completion: UI/snapshot use before_fees; averages null with catalog_advertised; GCX Cash excluded.
  - updated: 2026-11-17
- [x] All demo defaults remain off and test data cannot appear as live offers.
  - status: Done (code audit 2026-11-17).
  - completion: extension/controller.js defaults demoMode false; live mode rejects snapshot.demo; AWS runtime rejects synthetic input.
  - updated: 2026-11-17
- [x] No browsing URLs, credentials, gift-card codes or personal contents enter logs.
  - status: Done (code audit 2026-11-17).
  - completion: aws_runtime logs only stack + retailer offer counts; collector/CLI emit structured paths/counts, not page HTML or hosts browsed.
  - updated: 2026-11-17
- [ ] Real Safari accessibility, dark-mode, permissions, session and stale-cache tests pass.
- [ ] Stable signed local build is ready before copying to Applications/Home-Cooked.

## Requested popup threshold — 2026-10-24

- [x] Show a dismissible retailer popup only for advertised GCX discounts strictly greater than 1%, with a direct purchase-page link.
  - status: Done
  - acceptance: 0% and 1% produce no popup; 1.01% qualifies; visible up-to/before-fees label and direct GCX retailer link; suppression and stale rules preserved.
  - completion: extension/core.js threshold; extension/ui.js compact visible provider link; tests/core.test.js boundary cases; scripts/browser-smoke.py verifies direct href/new tab/referrer protections.
  - verification: 41 JavaScript tests passed; 15 offline Chromium UI checks passed; updated Release Safari app built successfully. Actual installed Safari runtime deferred by user.
  - blockers: Live HTTPS feed requires future deployment; user requested local basics only.
  - updated: 2026-10-24T08:36:52+00:00
- [x] Background GCX scrape for max % off + purchase link for a given gift card.
  - status: Done for local tooling.
  - completion: `python3 -m giftcard_tool lookup <retailer>` returns max_discount_pct + offer_url; full collect/import and Safari matcher remain. Live HTTPS feed still undeployed.
  - verification: Unit tests for resolve/lookup; live lookup dominos returned 17.6% + GCX link on 2026-11-17.
  - updated: 2026-11-17
