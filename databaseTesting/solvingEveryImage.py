"""
solvingEveryImage.py
--------------------
Attempts to plate-solve every FITS/JPG/PNG image in this directory using a
single tetra3 database. Useful for evaluating how well a given database
performs across a range of test images — drop images alongside this script,
set DATABASE to the .npz to test, then run:

    python databaseTesting/solvingEveryImage.py

At the end it prints a summary table and the FOV range of all solved images,
which you can use to pick the right parameters when building a new database.
"""

import os
import time
from collections import Counter

import numpy as np
from PIL import Image
import tetra3

# ── Configuration ─────────────────────────────────────────────────────────────

HERE     = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(HERE)
DATABASE = os.path.join(ROOT, 'databases', 'astro_dbV9')

IMAGE_EXTENSIONS       = ('.fits', '.fit', '.jpg', '.jpeg', '.png')
SIGMA                  = 2.0
FILTSIZE               = 15
MAX_AREA               = 1000
MAX_RETURNED           = 100
PATTERN_CHECKING_STARS = 8    # use library default for best chance of solving
MATCH_RADIUS           = 0.01

# Padding added each side of the observed FOV range for the database recommendation
FOV_MARGIN_DEG = 0.5

# ── Image loading ───────────────────────

_STF_BLACK_POINT_SIGMA = -2.8
_STF_MAD_TO_SIGMA      = 1.4826   # MAD → standard deviation for Gaussian
_STF_TARGET_BACKGROUND = 0.25


def _mtf(x, m):
    """PixInsight Midtone Transfer Function.

    Maps [0, 1] → [0, 1] so that x = m → 0.5 (midtone lands at mid-grey).
    Formula: MTF(x, m) = (m - 1)·x / ((2m - 1)·x - m)
    """
    x = np.asarray(x, dtype=np.float64)
    denom = (2 * m - 1) * x - m
    with np.errstate(divide='ignore', invalid='ignore'):
        result = np.where(denom == 0, 0.0, (m - 1) * x / denom)
    return np.clip(result, 0.0, 1.0)


def _stf_stretch(data):
    """Apply PixInsight-style auto STF stretch to float32 data."""
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
    """Normalise float32 pixel data to [0, 255] using the chosen stretch."""
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
    """Open any image as an 8-bit grayscale PIL Image.

    Handles FITS and 16-bit formats correctly; 8-bit formats pass straight
    through PIL. stretch: 'stf', 'linear', 'asinh', 'log', 'sqrt', or None.
    """
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
            # 16-bit PNG/TIFF — PIL's convert('L') takes the wrong 8 bits
            data = np.array(raw.convert('I'), dtype=np.float32)
            if stretch is None:
                data = (data / 256).clip(0, 255).astype(np.uint8)
            else:
                data = _apply_stretch(data, stretch, lo_pct, hi_pct, asinh_softening)
            return Image.fromarray(data, mode='L')

        return raw.convert('L')

# ── Load database ─────────────────────────────────────────────────────────────

print(f"Loading database: {DATABASE}")
t3 = tetra3.Tetra3(DATABASE)

# ── Find all image files ──────────────────────────────────────────────────────

image_files = sorted(
    os.path.join(HERE, f) for f in os.listdir(HERE)
    if f.lower().endswith(IMAGE_EXTENSIONS)
)

print(f"\nFound {len(image_files)} image(s) in {HERE}\n")
print(f"{'#':<5} {'Result':<8} {'FOV°':>6} {'RA°':>8} {'Dec°':>8} "
      f"{'Stars':>5} {'T_centoid_and_solve':>8}  File")
print("-" * 100)

# ── Solve each file ───────────────────────────────────────────────────────────

results = []

for i, path in enumerate(image_files, 1):
    short = os.path.basename(path)

    try:
        img = open_image(path, stretch='linear')
    except Exception as e:
        print(f"{i:<5} {'ERR_OPEN':<8} {'':>6} {'':>8} {'':>8} {'':>5} {'':>8}  {short}  [{e}]")
        results.append({'path': path, 'status': 'error_open'})
        continue

    t0 = time.perf_counter()
    
    try:
        centroids = tetra3.get_centroids_from_image(
            img,
            sigma        = SIGMA,
            filtsize     = FILTSIZE,
            max_area     = MAX_AREA,
            max_returned = MAX_RETURNED,
        )
    except Exception as e:
        print(f"{i:<5} {'ERR_CENT':<8} {'':>6} {'':>8} {'':>8} {'':>5} {'':>8}  {short}  [{e}]")
        results.append({'path': path, 'status': 'error_centroid'})
        continue

    
    try:
        solution = t3.solve_from_centroids(
            centroids,
            size                   = img.size,
            pattern_checking_stars = PATTERN_CHECKING_STARS,
            match_radius           = MATCH_RADIUS,
        )
    except Exception:
        solution = {}
    elapsed = (time.perf_counter() - t0) * 1000

    if solution.get('RA') is not None:
        fov     = solution.get('FOV', float('nan'))
        ra      = solution.get('RA',  float('nan'))
        dec     = solution.get('Dec', float('nan'))
        matches = solution.get('Matches', '?')
        print(f"{i:<5} {'SOLVED':<8} {fov:>6.3f} {ra:>8.3f} {dec:>8.3f} "
              f"{str(matches):>5} {elapsed:>7.0f}ms  {short}")
        results.append({'path': path, 'status': 'solved', 'FOV': fov,
                        'RA': ra, 'Dec': dec, 'Matches': matches, 'ms': elapsed})
    else:
        print(f"{i:<5} {'NO_SOLVE':<8} {'':>6} {'':>8} {'':>8} "
              f"{len(centroids):>5} {elapsed:>7.0f}ms  {short}")
        results.append({'path': path, 'status': 'no_solve',
                        'centroids': len(centroids), 'ms': elapsed})

# ── Summary ───────────────────────────────────────────────────────────────────

solved   = [r for r in results if r['status'] == 'solved']
unsolved = [r for r in results if r['status'] == 'no_solve']
errors   = [r for r in results if r['status'].startswith('error')]

print("\n" + "=" * 100)
print(f"SUMMARY:  {len(solved)} solved  |  {len(unsolved)} no solution  |  {len(errors)} errors  "
      f"|  {len(results)} total")

if solved:
    fovs    = [r['FOV'] for r in solved]
    min_fov = min(fovs)
    max_fov = max(fovs)
    avg_fov = sum(fovs) / len(fovs)

    print(f"\nFOV range:  min={min_fov:.3f}°  max={max_fov:.3f}°  avg={avg_fov:.3f}°")

    fov_groups = Counter(round(f, 1) for f in fovs)
    print(f"FOV clusters (rounded to 0.1°): {dict(sorted(fov_groups.items()))}")

    rec_min = max(0.1, round(min_fov - FOV_MARGIN_DEG, 2))
    rec_max = round(max_fov + FOV_MARGIN_DEG, 2)

    print(f"\n{'=' * 100}")
    print("RECOMMENDED DATABASE BUILD (see databases/build_database.py)")
    print(f"{'=' * 100}")
    print(f"  tetra3-gen-db --max-fov {rec_max} --min-fov {rec_min} "
          f"databases/catalogues/tyc_main.dat databases/astro_dbVX")
    print(f"  FOV margin applied: ±{FOV_MARGIN_DEG}° around observed range "
          f"({min_fov:.3f}°–{max_fov:.3f}°)")
    print(f"  Tighten min_fov/max_fov further if all images share a single FOV cluster.")

if unsolved:
    print(f"\nFiles with no solution ({len(unsolved)}):")
    for r in unsolved:
        print(f"  {os.path.basename(r['path'])}  ({r['centroids']} centroids detected)")
