#!/bin/bash
# Двойной клик — полная установка NEON.DOC на Mac.
cd "$(dirname "$0")" || exit 1
D="$(pwd)/NEON.DOC"; [ -d "$D" ] || D="$(pwd)"
xattr -dr com.apple.quarantine "$D" 2>/dev/null
exec bash "$D/install_mac.command"
