#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m giftcard_tool preview
