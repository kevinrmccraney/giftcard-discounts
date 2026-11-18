# Gift Card Discounts - Project State

**Version:** 0.1.0  
**State:** Live public-catalog collection and AWS deployment source implemented; local Safari app built; deployment and actual Safari acceptance pending.  
**Maturity:** 4 (implementation-ready locally; production release gated on Safari acceptance + AWS deploy + provider permission).  
**Last reapproach:** 2026-11-17 — implemented `lookup` CLI; refreshed live 11-retailer collect + sanitized fixture; audited demo defaults and log hygiene.

## Implemented

Python standard-library importer, normalization, weighted metrics, SQLite development history, snapshot generation; Safari Web Extension source; local cache/session controller; domain matching; expiry; demo guard; notification and settings UI; suppression/snooze; local interactive preview; tests and GitHub CI.

The three planning files are `PRD.md`, `TASKS.md` and `PROJECT_STATE.md` in this directory. Original v0.1 source recovered from /Users/kmccraney/Downloads/giftcard-discounts-v0.1.zip. Active source: /Users/kmccraney/Documents/Codex/2026-10-24/do-i/outputs/giftcard-discounts. No cloud account was modified.

## Verification

- Python 3.14 (2026-11-17): **78 pytest cases passed** in `tests/test_gcx.py` + `tests/test_pipeline.py` after lookup + fixture refresh (AWS suite not re-run in this pass).
- Node: **26 core tests passed** on 2026-11-17; earlier session also had session/cache concurrency coverage.
- Chromium: **15 offline UI checks passed** historically; not re-run this session. These are Chromium preview tests, not installed Safari extension tests.
- Safari/Xcode: **Release app built and ad-hoc signature verified** historically; actual Safari runtime still deferred.
- AWS: runtime and infrastructure source implemented; offline tests existed; not provisioned or deployed.
- GCX: live collect+import succeeded again on 2026-11-17 for 11 retailers; `lookup dominos` returned 17.6% before fees + purchase link; fixture refreshed.

## Settled direction

Safari/macOS first; US gift cards only; GCX initially; daily configurable serverless collection; DynamoDB history; static S3/CloudFront snapshot; local per-session download and hostname lookup. One notification per retailer per browser session. No current/fresh inventory means no UI. Provider comparison and other providers remain future work.

## Important implementation defaults

48-hour observation expiry; provider averages are not called weighted without evidence; shown discounts are before fees. SQLite is only a local harness. Demo is opt-in and purchasing is disabled. Local import assumes a single writer. Three demo retailer mappings are examples, not full catalog coverage.

## Blockers and next work

**Done this session:** `lookup` CLI, live collect/import, fixture refresh, demo/logging checklist audit.

**Still needs you:** `gh auth refresh` → create/push public repo → enable Pages → run **Publish snapshot** → paste feed URL into extension; then Safari checklist. AWS deploy not required for personal use (`DEPLOY.md`). GCX terms and signed distribution remain later concerns.

Pages publish source is ready locally. Safari checks in `SAFARI-CHECKLIST.md`. AWS reference in `infra/README.md`.

## Run

```bash
python3 -m giftcard_tool preview
bash scripts/test.sh
bash scripts/package-safari.sh  # macOS + Xcode only
```

## Latest implementation review

Updated 2026-10-24T08:32:42+00:00. Source and quickstart: /Users/kmccraney/Documents/Codex/2026-10-24/do-i/outputs/giftcard-discounts/README.md. Outputs include a local app ZIP, reproducible source ZIP, and latest real snapshot. User requested the local codebase basics; deployment and actual Safari extension testing are deferred. Safari development setting is on after approved local authentication, app launched, extension remains disabled.

Popup behavior: raw advertised discount must be >1%; 0 and exactly 1 are hidden, 1.01 qualifies. Compact popup includes direct GCX retailer link and visible up-to/before-fees wording.
