#!/bin/bash
# Build an ad-hoc signed local app; distribution signing remains an Xcode task.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="$ROOT/build/safari/Gift Card Discounts/Gift Card Discounts.xcodeproj"
if [ ! -d "$PROJECT" ]; then
  bash "$ROOT/scripts/package-safari.sh"
fi
# File-provider folders may add FinderInfo metadata that codesign rejects.
# Keep compiler output outside Documents and package it without extended attributes.
DERIVED="$(mktemp -d /private/tmp/giftcard-safari.XXXXXX)"
trap 'rm -rf "$DERIVED"' EXIT
xcodebuild -quiet -project "$PROJECT" -scheme "Gift Card Discounts" \
  -destination 'platform=macOS' -configuration Release -derivedDataPath "$DERIVED" \
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM= build
APP="$DERIVED/Build/Products/Release/Gift Card Discounts.app"
codesign --verify --deep --strict "$APP"
mkdir -p "$ROOT/build"
ditto -c -k --norsrc --noextattr --keepParent "$APP" "$ROOT/build/Gift Card Discounts.zip"
printf '%s\n' "Local Safari app: $ROOT/build/Gift Card Discounts.zip"
printf '%s\n' 'Unzip and open the app. Enable it in Safari Settings > Extensions.'
printf '%s\n' 'Ad-hoc signing requires Safari developer settings to allow unsigned extensions.'
