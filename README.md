# Gift Card Discounts

**Local GCX collection, Safari extension source, and a personal GitHub Pages snapshot feed. AWS templates remain optional and unused for the personal path.**

Bundled demo offers remain synthetic and opt-in. The collector reads public GCX catalog HTML for advertised maximum discounts (before fees; not checkout quotes). For single-user hosting, prefer **GitHub Pages** — see [`DEPLOY.md`](DEPLOY.md). AWS IaC in `infra/` is reference-only unless you choose it later.

## Local basics

From this source directory, the preview and collector need only Python 3.11+; AWS packages and accounts are unnecessary. To set up tests:

```bash
cd /Users/kmccraney/Documents/Codex/2026-10-24/do-i/outputs/giftcard-discounts
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
bash scripts/test.sh
```

Node is required for JavaScript tests. AWS deployment is deferred by the user; its inspectable code and instructions are in `infra/`.

## Try the preview without Xcode or AWS

Requires Python 3.11+; no third-party runtime packages.

```bash
cd giftcard-discounts
python3 -m giftcard_tool preview
```

Open `http://127.0.0.1:8765/` in your browser. Stop the server with Control-C. `Open Demo.command` runs the same command on macOS. Use `--port 8766` if the default port is busy.

Try `dominos.com`, then `order.dominos.com`: only the first visit shows a pill. Select **New simulated session** to reset session history. `lowes.com` demonstrates no inventory; `notdominos.com` must never match. Expand the pill to dismiss, snooze for 24 hours, or hide a retailer permanently. The preview uses the extension's actual matcher and notification UI, but simulates the Safari session lifecycle.

## What is implemented

- Provider-neutral JSON import, strict validation, balance-weighted averages, optional provider-reported averages, and explicit no-inventory states.
- Idempotent, append-only SQLite history for local development; atomic snapshot-file replacement and rollback protection.
- Local hostname matching; only discounts strictly above 1% show a compact dismissible popup with the up-to percentage before fees and a direct GCX retailer purchase-page link. Per-observation expiry, session-wide deduplication, persistent suppression and snooze remain active.
- Snapshot caching, conditional HTTP requests, last-good-cache fallback, and a once-per-session refresh attempt.
- Safari Web Extension source, settings popup, icons, and a macOS Xcode-packaging script.
- Unit tests, a local preview, an optional Chromium UI smoke test, and GitHub test CI.

SQLite is the **local test harness**, not a replacement for the agreed DynamoDB production design. Live collection and AWS infrastructure/runtime source are implemented; deployment and actual Safari extension testing remain unfinished.

## Collect public advertised discounts

```bash
python3 -m giftcard_tool collect --catalog config/retailers-live.json --output build/live/input.json
python3 -m giftcard_tool import build/live/input.json \
  --catalog config/retailers-live.json \
  --output build/live/snapshot.json --database build/live/history.sqlite3

# Single reviewed retailer: advertised max % (before fees) + purchase-page link.
python3 -m giftcard_tool lookup dominos
```

The collector scans all catalog pages within its request/page limits, validates every product, and logs and skips malformed products. The collected batch retains all valid products in `gcx_catalog`; the Pages build also publishes them as `catalog.json`. Extension offers use reviewed retailer/domain mappings. Missing or rewards-only retailers are omitted, never reported as zero inventory; partial mapped coverage is marked `complete: false`. Network/access failures or no valid configured discounts still prevent a new snapshot. The extension requires an HTTPS snapshot URL; it does not read this local file directly.

## Run the data pipeline

```bash
# Generate fresh SYNTHETIC observations and snapshot.
python3 -m giftcard_tool demo

# Import OUR documented interchange format, not arbitrary GCX JSON.
python3 -m giftcard_tool import path/to/provider-batch.json \
  --catalog config/retailers.json \
  --output build/import/snapshot.json \
  --database build/import/history.sqlite3 \
  --max-age-hours 48
```

The demo writes `build/demo/snapshot.json` and a private local history database. The preview serves only explicitly copied public assets, not the history database or the project directory.

`fixtures/demo-batch.json` documents the input shape. Complete batches include every configured retailer exactly once, with either `available` or `no_inventory`. Explicitly partial batches (`complete: false`) may contain a nonempty subset; unknown retailers, duplicates, invalid percentages, and unapproved offer URLs are rejected. Missing retailers produce no observations. A **verified complete** batch containing zero inventory for every retailer may correctly publish an empty snapshot.

A batch can contain complete listings (`balance`, `price`, optional `quantity`) or explicit summary metrics. Listing averages are weighted by available face value including quantity. A provider-supplied average is labeled `provider_reported`, not claimed to use a verified weighting method. Unknown average/count/value fields remain `null`.

An import never updates an observation's timestamp to make it look fresh. Default expiry is 48 hours from the observation, configurable up to seven days. Expired offers are omitted. Import uses one writer at a time; the future distributed publisher needs cloud concurrency controls.

## Package for Safari on your Mac

Requires full Xcode. The script detects Apple's current packager name and the older converter name; it does not force overwrite an existing project.

```bash
bash scripts/package-safari.sh
```

A prebuilt local app is provided beside this source folder as **Gift Card Discounts.zip**. For a reproducible local build, run `bash scripts/build-safari.sh`; it verifies ad-hoc signing and creates `build/Gift Card Discounts.zip`. Unzip and open the containing app, then enable it in Safari Settings > Extensions. This is a local development build, not a Developer ID signed or notarized distribution. A distribution build needs an Apple signing identity in Xcode.

In the extension popup, enable **synthetic demo data**, then visit a configured retailer over HTTPS. Demo data is fetched from the extension bundle, not from GCX. Quit and reopen Safari to test a real browser-session reset. The app was built in Release configuration and its signature verified. The user approved and locally authenticated enabling Safari’s **Allow unsigned extensions** setting; it is now on. The containing app launched successfully. The extension itself has not been enabled and no retailer website permissions have been granted. Further Safari setup was deferred when the user requested the codebase basics only. **Extension execution, website permissions, cross-tab/session reset, offline behavior, accessibility and dark mode have not been verified in actual Safari.** See `SAFARI-CHECKLIST.md`.

Website permissions are broad (`https://*/*`) because automatic matching must work on retailer sites and the eventual snapshot host. The content script reads no form fields or page text. It requests an offer using extension messaging; the background derives the hostname from the browser-supplied sender URL. No browsing hostname is sent to the snapshot server. Narrowing optional permissions is a later hardening task.

## Tests

Python tests use pytest; JavaScript tests use Node's built-in test runner. Node is a development dependency only.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install 'pytest>=8,<10'
bash scripts/test.sh
```

Optional UI smoke test, with the preview server running:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
python3 scripts/browser-smoke.py
```

`--offline` instead loads the same generated UI assets using in-memory fetch/storage doubles. That is how the Chromium UI was checked in the build environment, whose browser networking blocks localhost. These checks are not Safari integration tests.

## Repository

```text
Plans/                 PRD.md, TASKS.md, PROJECT_STATE.md
config/                Reviewed retailer/domain mappings
fixtures/              Explicitly synthetic interchange input
giftcard_tool/        Python validation, history, snapshot CLI
extension/             Safari Web Extension source
preview/               Standalone interactive UI harness
scripts/               Tests, browser smoke test, Mac packager
tests/                pytest + Node tests
.github/workflows/     Test CI; no production deployment
```

The three planning files are the durable handoff: requirements, task status, and concise project state. Remaining release gates are an AWS deployment with live end-to-end verification, provider access/redistribution confirmation, broader reviewed mappings, and actual Safari acceptance.
