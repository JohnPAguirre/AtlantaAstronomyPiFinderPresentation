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
TMP_BUILD="/tmp/pifinder_pres_build"
TMP_HTML="$TMP_BUILD/presentation.html"

if ! command -v marp &>/dev/null; then
    echo "Error: marp not found. Install it with: brew install marp-cli"
    exit 1
fi

if [[ "${1:-}" == "--watch" || "${1:-}" == "-w" ]]; then
    echo "Starting live preview..."
    marp --watch --preview "$SRC"
    exit 0
fi

compress_images() {
    echo "Compressing images into $TMP_BUILD ..."

    # Copy markdown with .gif references rewritten to .webp
    sed 's/\.gif)/.webp)/g' "$SRC" > "$TMP_BUILD/$(basename "$SRC")"

    [ -d "$SCRIPT_DIR/themes" ] && cp -r "$SCRIPT_DIR/themes" "$TMP_BUILD/"

    # Use mapfile to avoid subshell issues with pipe+while
    mapfile -t image_files < <(find "$SCRIPT_DIR" -type f \( \
        -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \
        -o -iname "*.gif" -o -iname "*.webp" \
    \))

    for src_file in "${image_files[@]}"; do
        rel="${src_file#"$SCRIPT_DIR/"}"
        ext="${src_file##*.}"
        ext="${ext,,}"

        if [[ "$ext" == "gif" ]]; then
            dst_file="$TMP_BUILD/${rel%.*}.webp"
        else
            dst_file="$TMP_BUILD/$rel"
        fi

        mkdir -p "$(dirname "$dst_file")"
        [[ -f "$dst_file" ]] && continue

        case "$ext" in
            gif)
                echo "  gif→webp: $rel"
                if ! ffmpeg -y -i "$src_file" \
                        -vf "scale=800:-1:flags=lanczos" \
                        -loop 0 -q:v 75 "$dst_file" 2>/dev/null; then
                    cp "$src_file" "${dst_file%.*}.gif"
                fi
                ;;
            jpg|jpeg)
                if ! ffmpeg -y -i "$src_file" \
                        -vf "scale='if(gt(iw,1920),1920,iw)':-2" \
                        -q:v 5 -update 1 "$dst_file" 2>/dev/null; then
                    cp "$src_file" "$dst_file"
                fi
                ;;
            png)
                if ! ffmpeg -y -i "$src_file" \
                        -vf "scale='if(gt(iw,1920),1920,iw)':-2" \
                        -update 1 "$dst_file" 2>/dev/null; then
                    cp "$src_file" "$dst_file"
                fi
                ;;
            webp)
                if ! ffmpeg -y -i "$src_file" \
                        -vf "scale='if(gt(iw,1920),1920,iw)':-2" \
                        -q:v 80 -update 1 "$dst_file" 2>/dev/null; then
                    cp "$src_file" "$dst_file"
                fi
                ;;
            *)
                cp "$src_file" "$dst_file"
                ;;
        esac
    done
}

mkdir -p "$TMP_BUILD"

compress_images

COMPRESSED_SRC="$TMP_BUILD/$(basename "$SRC")"

if command -v monolith &>/dev/null; then
    echo "Building self-contained HTML (marp + monolith)..."
    marp --allow-local-files "$COMPRESSED_SRC" -o "$TMP_HTML"
    monolith "$TMP_HTML" -b "file://$TMP_BUILD/" -o "$OUT"
else
    echo "Building HTML (monolith not found — images linked, not embedded)..."
    echo "  To embed images: brew install monolith  or  cargo install monolith"
    marp --allow-local-files "$COMPRESSED_SRC" -o "$OUT"
fi

echo "Done: $OUT"
