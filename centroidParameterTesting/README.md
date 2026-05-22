# centroidParameterTesting

Sweeps centroid-detection parameters across every `.fits` file in this directory and produces annotated PNG frames and a GIF for each target, making it easy to visually compare how each parameter combination affects star detection.

## What it does

For each `.fits` / draw-image pair in this directory, `review_centroids.py`:

1. Loads the FITS file as the source for centroid detection
2. Loads the matching visual image (same filename, `.png` or `.jpg`) as the drawing canvas
3. Runs a frame with tetra3 defaults as a baseline
4. Sweeps all combinations of `sigma`, `bg_sub_mode`, `sigma_mode`, `filtsize`, and `max_area`
5. Saves each combination as an annotated PNG into `<target>/<bg_mode>__<sigma_mode>/`
6. Assembles all frames into `<target>/<target>.gif`
7. Prints a summary table sorted by star count and by speed

## Adding a new target

Drop two files into this directory with matching stems:

| File | Purpose |
|------|---------|
| `TargetName.fits` | FITS image used for centroid detection |
| `TargetName.png` or `TargetName.jpg` | Visual image used as the drawing canvas |

Example:
```
centroidParameterTesting/
  M57.fits
  M57.png
```

The script auto-discovers all pairs on each run — no configuration needed.

If no matching draw file is found, the script automatically generates the canvas by applying an STF stretch to the FITS image itself.

## Running

Activate the virtual environment, then run from the **project root**:

```bash
source ~/venvs/cedar312/bin/activate
python centroidParameterTesting/review_centroids.py
```

## Compressing the output GIF

The raw GIFs can be large. Use `gifsicle` to compress — make a copy first:

```bash
cp centroidParameterTesting/<target>/<target>.gif centroidParameterTesting/<target>/<target>_shrunk.gif
gifsicle -O3 --lossy=80 --colors 128 --resize-width 960 --batch centroidParameterTesting/<target>/<target>_shrunk.gif
```

Adjust `--resize-width`, `--colors`, and `--lossy` to taste.

## Dependencies

### Python environment

Requires Python 3.12+. Install dependencies from this directory:

```bash
pip install -r requirements.txt
```

Installs `cedar-solve` (tetra3 API), `Pillow`, `numpy`, and `scipy`.

> **Note:** `image_utils.py` is sourced from `../scripts/` at runtime — the script adds that path automatically, no manual step needed.

### gifsicle — GIF compression

Used separately after the script runs to compress output GIFs.

**macOS (Homebrew):**
```bash
brew install gifsicle
```

**Fedora / RHEL (dnf):**
```bash
sudo dnf install gifsicle
```

**Ubuntu / Debian (apt):**
```bash
sudo apt install gifsicle
```
