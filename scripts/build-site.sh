#!/usr/bin/env bash
# Build the GitHub Pages site directory: landing page + validated live snapshot.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SITE="$ROOT/site"
LIVE="$ROOT/build/live-pages"
mkdir -p "$SITE" "$LIVE"

python3 -m giftcard_tool collect \
  --catalog config/retailers-live.json \
  --output "$LIVE/input.json"

python3 -m giftcard_tool import \
  "$LIVE/input.json" \
  --catalog config/retailers-live.json \
  --output "$SITE/snapshot.json" \
  --database "$LIVE/history.sqlite3"

cp "$ROOT/site-src/index.html" "$SITE/index.html"

python3 - <<PY
import json
from pathlib import Path
snap = json.loads(Path("$SITE/snapshot.json").read_text())
assert snap.get("demo") is False, snap.get("demo")
offers = sum(1 for r in snap["retailers"].values() if r.get("offers"))
print(f"site ready: {offers} retailers with offers @ {snap.get('generated_at')}")
PY
