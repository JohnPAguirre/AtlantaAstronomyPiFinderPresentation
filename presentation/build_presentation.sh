#!/usr/bin/env bash
# Builds john-digital-finder-scopes.md into an HTML slideshow.
#
# Usage:
#   bash presentation/build_presentation.sh            # build self-contained HTML
#   bash presentation/build_presentation.sh --watch    # live-preview in browser while editing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/john-digital-finder-scopes.md"
OUT="$SCRIPT_DIR/../john-digital-finder-scopes.html"
TMP="/tmp/marp_presentation_out.html"

if ! command -v marp &>/dev/null; then
    echo "Error: marp not found. Install it with: brew install marp-cli"
    exit 1
fi

if [[ "${1:-}" == "--watch" || "${1:-}" == "-w" ]]; then
    echo "Starting live preview..."
    marp --watch --preview "$SRC"
    exit 0
fi

if command -v monolith &>/dev/null; then
    echo "Building self-contained HTML (marp + monolith)..."
    marp --allow-local-files "$SRC" -o "$TMP"
    monolith "$TMP" -b "file://$SCRIPT_DIR/" -o "$OUT"
    rm -f "$TMP"
else
    echo "Building HTML (monolith not found — images linked, not embedded)..."
    echo "  To embed images: brew install monolith  or  cargo install monolith"
    marp --allow-local-files "$SRC" -o "$OUT"
fi

echo "Done: $OUT"
