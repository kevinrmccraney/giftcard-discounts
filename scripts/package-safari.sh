#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(uname -s)" != "Darwin" ]; then
  printf '%s\n' 'Safari packaging requires macOS and Xcode.' >&2
  exit 1
fi
if xcrun --find safari-web-extension-packager >/dev/null 2>&1; then
  TOOL=safari-web-extension-packager
elif xcrun --find safari-web-extension-converter >/dev/null 2>&1; then
  TOOL=safari-web-extension-converter
else
  printf '%s\n' 'Select a full Xcode installation with xcode-select before packaging.' >&2
  exit 1
fi
xcrun "$TOOL" "$ROOT/extension" \
  --project-location "$ROOT/build/safari" \
  --app-name "Gift Card Discounts" \
  --bundle-identifier "local.homecooked.Gift-Card-Discounts" \
  --macos-only --swift --no-open --no-prompt
printf '%s\n' 'Xcode project generated in build/safari. Open it, select your signing team, and build/run.'
