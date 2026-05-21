#!/usr/bin/env bash
# Creates a Python 3.12 virtual environment and installs project dependencies.
set -euo pipefail

VENV_DIR="${1:-venv}"

if [ ! -d "$VENV_DIR" ]; then
    python3.12 -m venv "$VENV_DIR"
    echo "Created virtual environment: $VENV_DIR"
else
    echo "Virtual environment already exists: $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
# cedar-solve 0.5.1 declares Pillow<9 and numpy<2, but those constraints predate
# Python 3.12 and GCC 14. Install it without deps so modern versions can be used.
pip install --no-deps cedar-solve==0.5.1
pip install -r requirements.txt

# Patch tetra3-gen-db: argparser is missing --pattern-stars-per-fov that the code references
GENDB="$VENV_DIR/lib64/python3.12/site-packages/tetra3/cli/generate_database.py"
python3 - "$GENDB" <<'PYEOF'
import sys
path = sys.argv[1]
content = open(path).read()
if 'pattern_stars_per_fov=args.pattern_stars_per_fov' in content and \
   '--pattern-stars-per-fov' not in content:
    insert = ('    parser.add_argument("--pattern-stars-per-fov", type=int, default=None,\n'
              '                        help="Target number of stars used for generating patterns.")\n')
    content = content.replace('    args = parser.parse_args()', insert + '    args = parser.parse_args()')
    open(path, 'w').write(content)
    print("Patched tetra3-gen-db: added missing --pattern-stars-per-fov argument")
PYEOF

echo ""
echo "Setup complete. Activate with: source $VENV_DIR/bin/activate"
echo ""
echo "NOTE: The following tools must be installed manually:"
echo ""
echo "  gifsicle (GIF compression for review_centroids.py):"
echo "    macOS:          brew install gifsicle"
echo "    Fedora/RHEL:    sudo dnf install gifsicle"
echo "    Ubuntu/Debian:  sudo apt install gifsicle"
echo ""
echo "  marp-cli (presentation builder — required for build_presentation.sh):"
echo "    brew install marp-cli"
echo ""
echo "  monolith (optional — embeds images into a single self-contained HTML):"
echo "    macOS:  brew install monolith"
echo "    other:  cargo install monolith"
echo ""
echo "Example commands (run from project root):"
echo ""
echo "  # Plate-solve every .fits in annotate/, write 4 annotated JPEGs per target"
echo "  python annotate/annotate_solve.py"
echo ""
echo "  # Plate-solve every image in databaseTesting/, print solve summary table"
echo "  python databaseTesting/solvingEveryImage.py"
echo ""
echo "  # Centroid parameter sweep (sigma, bg_sub_mode, filtsize, etc.)"
echo "  python centroidParameterTesting/review_centroids.py"
echo ""
echo "  # Rebuild star databases (set BUILD_V* flags at top of script first)"
echo "  python databases/build_database.py"
echo ""
echo "  # Build the presentation into a self-contained HTML slideshow"
echo "  bash presentation/build_presentation.sh"
echo ""
echo "  # Live-preview the presentation in a browser while editing"
echo "  bash presentation/build_presentation.sh --watch"
