"""
annotate_solve.py
-----------------
For each .fits file in the script's directory (annotated/), plate-solves it
and produces 4 annotated images in a subfolder named after the FITS file stem:

  <stem>/1_original.jpg   — the raw image (grayscale → RGB)
  <stem>/2_centroids.jpg  — all detected centroids circled
  <stem>/3_quads.jpg      — centroids + every candidate quad pattern drawn
  <stem>/4_solution.jpg   — only the stars used in the final plate solve highlighted

Run from the project root:
    python annotated/annotate_solve.py
"""

import itertools
from pathlib import Path

import numpy as np
import tetra3
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).parent

# ── Configuration ─────────────────────────────────────────────────────────────

DATABASE               = '/var/home/john/softwareProjects/plateSolveTest/databases/astro_dbV8'
STRETCH                = 'stf'    # 'stf' (PixInsight auto), 'linear', 'asinh', 'log', 'sqrt', or None
ASINH_SOFTENING        = 0.1      # asinh only: smaller = more compression of bright stars

FOV_ESTIMATE           = 6.553
SIGMA                  = 2.0
FILTSIZE               = 15
MAX_AREA               = 1000
MAX_RETURNED           = 100
PATTERN_CHECKING_STARS = 6
MATCH_RADIUS           = 0.01

CIRCLE_RADIUS          = 12
JPEG_QUALITY           = 85

COLOR_CENTROIDS        = 'red'
COLOR_QUADS            = 'cyan'
COLOR_SOLUTION         = 'yellow'

# ── Image loading (inlined from scripts/image_utils.py) ───────────────────────

_STF_BLACK_POINT_SIGMA = -2.8
_STF_MAD_TO_SIGMA      = 1.4826
_STF_TARGET_BACKGROUND = 0.25


def _mtf(x, m):
    x = np.asarray(x, dtype=np.float64)
    denom = (2 * m - 1) * x - m
    with np.errstate(divide='ignore', invalid='ignore'):
        result = np.where(denom == 0, 0.0, (m - 1) * x / denom)
    return np.clip(result, 0.0, 1.0)


def _stf_stretch(data):
    norm = float(np.percentile(data, 99.99))
    if norm == 0:
        return np.zeros_like(data, dtype=np.uint8)
    normed = (data / norm).clip(0.0, 1.0).astype(np.float64)
    median = float(np.median(normed))
    mad    = float(np.median(np.abs(normed - median)))
    if median > 0.5:
        white_point = float(np.clip(
            median - mad * _STF_BLACK_POINT_SIGMA * _STF_MAD_TO_SIGMA, 0, 1))
        mid_point = _mtf(_STF_TARGET_BACKGROUND, white_point - median)
        stretched = _mtf(1.0 - normed, float(mid_point))
    else:
        black_point = float(np.clip(
            median + mad * _STF_BLACK_POINT_SIGMA * _STF_MAD_TO_SIGMA, 0, 1))
        shifted = np.clip(normed - black_point, 0.0, 1.0)
        mid_point = float(_mtf(median - black_point, _STF_TARGET_BACKGROUND))
        stretched = _mtf(shifted, mid_point)
    return (stretched * 255).clip(0, 255).astype(np.uint8)


def _apply_stretch(data, mode, lo_pct, hi_pct, asinh_softening):
    if mode == 'stf':
        return _stf_stretch(data)
    from astropy.visualization import AsinhStretch, LogStretch, SqrtStretch
    vmin = float(np.percentile(data, lo_pct))
    vmax = float(np.percentile(data, hi_pct))
    if vmax == vmin:
        return np.zeros_like(data, dtype=np.uint8)
    normed = ((data - vmin) / (vmax - vmin)).clip(0.0, 1.0)
    if mode == 'asinh':
        normed = AsinhStretch(a=asinh_softening)(normed)
    elif mode == 'log':
        normed = LogStretch()(normed)
    elif mode == 'sqrt':
        normed = SqrtStretch()(normed)
    return (normed * 255).clip(0, 255).astype(np.uint8)


def open_image(path, lo_pct=0.5, hi_pct=99.9, stretch='stf', asinh_softening=0.1):
    if str(path).lower().endswith(('.fits', '.fit')):
        import astropy.io.fits as fits
        with fits.open(path) as hdul:
            data = hdul[0].data.astype(np.float32)
        data = np.squeeze(data)
        if data.ndim == 3:
            data = data[0]
        if stretch is None:
            data = np.clip(data, 0, 255).astype(np.uint8)
        else:
            data = _apply_stretch(data, stretch, lo_pct, hi_pct, asinh_softening)
        return Image.fromarray(data, mode='L')
    else:
        raw = Image.open(path)
        if raw.mode in ('I', 'I;16', 'I;16B', 'I;16L'):
            data = np.array(raw.convert('I'), dtype=np.float32)
            if stretch is None:
                data = (data / 256).clip(0, 255).astype(np.uint8)
            else:
                data = _apply_stretch(data, stretch, lo_pct, hi_pct, asinh_softening)
            return Image.fromarray(data, mode='L')
        return raw.convert('L')

# ── Helpers ───────────────────────────────────────────────────────────────────

def add_label(draw, canvas, text, color='white', size=75):
    font = ImageFont.load_default(size=size)
    bbox = draw.textbbox((0, 0), text, font=font)
    margin = 10
    x = canvas.width  - (bbox[2] - bbox[0]) - margin
    y = canvas.height - (bbox[3] - bbox[1]) - margin
    draw.text((x, y), text, fill=color, font=font)


def draw_centroids(draw, centroids, radius, color, width=2):
    for c in centroids:
        cy, cx = c[0], c[1]
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=color, width=width,
        )

# ── Main ──────────────────────────────────────────────────────────────────────

fits_files = sorted(SCRIPT_DIR.glob('*.fits'))
if not fits_files:
    print("No .fits files found in annotated/ directory.")
    raise SystemExit(1)

print(f"Loading database: {DATABASE}")
t3 = tetra3.Tetra3(DATABASE)

for fits_path in fits_files:
    stem = fits_path.stem
    output_dir = SCRIPT_DIR / stem
    output_dir.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Processing: {fits_path.name}")
    print(f"Output dir: {output_dir}")

    img_raw     = open_image(str(fits_path), stretch='linear')
    img_display = open_image(str(fits_path), stretch=STRETCH, asinh_softening=ASINH_SOFTENING)
    img_rgb     = img_display.convert('RGB')
    print(f"Image size: {img_raw.size[0]}x{img_raw.size[1]} px")

    # ── Image 1: original ─────────────────────────────────────────────────────

    out1 = output_dir / '1_original.jpg'
    img_rgb.save(str(out1), quality=JPEG_QUALITY)
    print(f"Saved {out1}")

    # ── Detect centroids ──────────────────────────────────────────────────────

    centroids = tetra3.get_centroids_from_image(
        img_raw,
        sigma        = SIGMA,
        filtsize     = FILTSIZE,
        max_area     = MAX_AREA,
        max_returned = MAX_RETURNED,
    )
    print(f"{len(centroids)} centroids detected")

    # ── Image 2: centroids ────────────────────────────────────────────────────

    canvas = img_rgb.copy()
    draw   = ImageDraw.Draw(canvas)
    draw_centroids(draw, centroids, CIRCLE_RADIUS, COLOR_CENTROIDS)
    add_label(draw, canvas,
              f"{len(centroids)} centroids  sigma={SIGMA}  filtsize={FILTSIZE}  max_area={MAX_AREA}")
    out2 = output_dir / '2_centroids.jpg'
    canvas.save(str(out2), quality=JPEG_QUALITY)
    print(f"Saved {out2}")

    # ── Image 3: quads ────────────────────────────────────────────────────────

    canvas      = img_rgb.copy()
    draw        = ImageDraw.Draw(canvas)
    search_stars = centroids[:PATTERN_CHECKING_STARS]
    quad_count  = 0
    for quad in itertools.combinations(search_stars, 4):
        pts = [(c[1], c[0]) for c in quad]
        for i, j in itertools.combinations(range(4), 2):
            draw.line([pts[i], pts[j]], fill=COLOR_QUADS, width=1)
        quad_count += 1
    draw_centroids(draw, centroids, CIRCLE_RADIUS, COLOR_CENTROIDS)
    draw_centroids(draw, search_stars, CIRCLE_RADIUS + 6, COLOR_QUADS, width=2)
    add_label(draw, canvas,
              f"{len(centroids)} centroids  top {PATTERN_CHECKING_STARS} → {quad_count} quads")
    out3 = output_dir / '3_quads.jpg'
    canvas.save(str(out3), quality=JPEG_QUALITY)
    print(f"Saved {out3}  ({quad_count} quads from top {PATTERN_CHECKING_STARS} stars)")

    # ── Solve ─────────────────────────────────────────────────────────────────

    print("Solving...")
    solution = t3.solve_from_centroids(
        centroids,
        size                   = img_raw.size,
        fov_estimate           = FOV_ESTIMATE,
        pattern_checking_stars = PATTERN_CHECKING_STARS,
        match_radius           = MATCH_RADIUS,
        return_matches         = True,
    )
    print(f"Solution: {solution}")

    # ── Image 4: solution stars ───────────────────────────────────────────────

    canvas  = img_rgb.copy()
    draw    = ImageDraw.Draw(canvas)
    matched = solution.get('matched_centroids')
    if matched:
        draw_centroids(draw, centroids, CIRCLE_RADIUS, 'gray', width=1)
        for c in matched:
            cy, cx = c[0], c[1]
            r = CIRCLE_RADIUS * 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         outline=COLOR_SOLUTION, width=3)
        ra  = solution.get('RA',  float('nan'))
        dec = solution.get('Dec', float('nan'))
        fov = solution.get('FOV', float('nan'))
        label = (f"RA={ra:.4f}°  Dec={dec:.4f}°  FOV={fov:.4f}°  "
                 f"{len(matched)} matched stars")
    else:
        draw_centroids(draw, centroids, CIRCLE_RADIUS, COLOR_CENTROIDS)
        label = "No solution found"
    add_label(draw, canvas, label, color=COLOR_SOLUTION if matched else 'red')
    out4 = output_dir / '4_solution.jpg'
    canvas.save(str(out4), quality=JPEG_QUALITY)
    print(f"Saved {out4}")

print(f"\nDone.")
