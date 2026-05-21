"""
review_centroids.py
-------------------
For each .fits file in the script's directory, finds the matching draw canvas
(.png or .jpg with the same stem), sweeps centroid-detection parameters, saves
annotated images into a subdirectory named after the FITS file, then assembles
a gif from those images.
"""

import glob
import itertools
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import tetra3
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).parent

# ── Configuration ─────────────────────────────────────────────────────────────

CIRCLE_COLOR  = 'red'
CIRCLE_RADIUS = 12

GIF_FRAME_MS = 100    # ms per frame

# ── Sweep parameters ──────────────────────────────────────────────────────────

SIGMA_VALUES = [0.5, 0.8, 1.0, 1.5, 2.0, 3.0]
BG_SUB_MODES = ['local_mean', 'global_median', 'global_mean']
# 'local_median' — uses filtsize but takes a very long time
SIGMA_MODES  = ['global_root_square']
# 'local_median_abs' — uses filtsize but takes a very long time
# 'local_root_square' — uses filtsize but takes a very long time
FILT_SIZES   = [15, 25, 35]
MAX_AREAS    = [100, 200, 500]

# bg_sub_modes and sigma_modes that require filtsize
FILT_REQUIRES_BG  = {'local_median', 'local_mean'}
FILT_REQUIRES_SIG = {'local_median_abs', 'local_root_square'}


# ── Image loading ───────────────────────

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

def load_draw_canvas(path: Path) -> Image.Image:
    raw = Image.open(path)
    if raw.mode in ('I', 'I;16', 'I;16B', 'I;16L'):
        data = np.array(raw.convert('I'), dtype=np.int32)
        return Image.fromarray((data >> 8).clip(0, 255).astype('uint8')).convert('RGB')
    return raw.convert('RGB')


def annotate(canvas: Image.Image, centroids, lines: list, seq: int, total: int) -> Image.Image:
    img_rgb = canvas.copy()
    draw = ImageDraw.Draw(img_rgb)
    for c in centroids:
        y, x = c[0], c[1]
        draw.ellipse([x - CIRCLE_RADIUS, y - CIRCLE_RADIUS,
                      x + CIRCLE_RADIUS, y + CIRCLE_RADIUS],
                     outline=CIRCLE_COLOR, width=2)
    font = ImageFont.load_default(size=70)
    margin = 40
    line_gap = 12
    all_lines = lines + [f'{seq} - {total}']
    y = img_rgb.height - margin
    for line in reversed(all_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        lh = bbox[3] - bbox[1]
        y -= lh
        draw.text((margin, y), line, fill='yellow', font=font)
        y -= line_gap
    return img_rgb


def build_gif(output_dir: Path):
    paths = sorted(
        glob.glob(str(output_dir / '**' / '*.png'), recursive=True),
        key=os.path.basename,
    )
    if not paths:
        print("  No frames found for GIF.")
        return

    sample = Image.open(paths[0])
    print(f"  Building GIF: {len(paths)} frames at {sample.width}×{sample.height}")
    frames = []
    for i, p in enumerate(paths):
        img = Image.open(p).convert('RGB')
        frames.append(img.convert('P', palette=Image.ADAPTIVE, dither=Image.Dither.NONE))
        if (i + 1) % 50 == 0 or (i + 1) == len(paths):
            print(f"    loaded {i+1}/{len(paths)}")

    gif_path = output_dir / f'{output_dir.name}.gif'
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=GIF_FRAME_MS,
        loop=0,
        optimize=False,
    )
    size_mb = gif_path.stat().st_size / 1_000_000
    print(f"  Saved {gif_path}  ({size_mb:.1f} MB)")

    shrunk_path = gif_path.with_stem(f'{gif_path.stem}_shrunk')
    shutil.copy2(gif_path, shrunk_path)
    subprocess.run(['gifsicle', '-O3', '--colors', '256', '--resize-width', '1500', '--batch', str(shrunk_path)], check=True)
    shrunk_mb = shrunk_path.stat().st_size / 1_000_000
    print(f"  Shrunk {shrunk_path.name}  ({shrunk_mb:.1f} MB)\n")


# ── Main ──────────────────────────────────────────────────────────────────────

fits_files = sorted(SCRIPT_DIR.glob('*.fits'))
if not fits_files:
    print("No .fits files found in script directory.")
    raise SystemExit(1)

for fits_path in fits_files:
    stem = fits_path.stem

    draw_path = None
    for ext in ('.png', '.jpg', '.jpeg'):
        candidate = fits_path.with_suffix(ext)
        if candidate.exists():
            draw_path = candidate
            break

    if draw_path is None:
        print(f"[INFO] No draw file found for {fits_path.name} — using STF stretch of FITS as canvas")

    output_dir = SCRIPT_DIR / stem
    output_dir.mkdir(exist_ok=True)

    print(f"\n{'='*75}")
    print(f"Processing: {fits_path.name}")
    print(f"Draw canvas: {draw_path.name if draw_path else 'STF stretch (auto)'}")
    print(f"Output dir:  {output_dir}\n")

    img = open_image(str(fits_path))
    print(f"Image size: {img.size[0]}x{img.size[1]} px")

    if draw_path is not None:
        draw_base = load_draw_canvas(draw_path)
        print(f"Canvas: {draw_path.name}  {draw_base.size[0]}x{draw_base.size[1]} px\n")
    else:
        draw_base = open_image(str(fits_path), stretch='stf').convert('RGB')
        print(f"Canvas: STF stretch of {fits_path.name}  {draw_base.size[0]}x{draw_base.size[1]} px\n")

    # Sweep
    total_combos = 0
    for _sm, _bm in itertools.product(SIGMA_MODES, BG_SUB_MODES):
        filt_count = len(FILT_SIZES) if (_bm in FILT_REQUIRES_BG or _sm in FILT_REQUIRES_SIG) else 1
        total_combos += filt_count * len(MAX_AREAS) * len(SIGMA_VALUES)
    total_images = total_combos + 1  # +1 for defaults frame

    # Frame 0000: tetra3 defaults
    t0 = time.perf_counter()
    defaults_centroids = tetra3.get_centroids_from_image(img)
    defaults_ms = (time.perf_counter() - t0) * 1000
    defaults_count = len(defaults_centroids)
    print(f"defaults  →  {defaults_count} stars  {defaults_ms:.0f} ms")
    frame = annotate(draw_base, defaults_centroids,
                     ['defaults', f'stars={defaults_count}', f't={defaults_ms:.0f}ms'],
                     seq=0, total=total_images)
    frame.save(str(output_dir / '0000__defaults.png'))
    print()
    print(f"Total combinations: {total_combos}\n")
    print(f"{'bg_sub_mode':<16} {'sigma_mode':<22} {'filt':>4} {'max_a':>5} {'sig':>4} {'stars':>5} {'time':>9}")
    print("-" * 75)

    results = []
    seq = 0

    for sig_mode, bg_mode, max_area in itertools.product(SIGMA_MODES, BG_SUB_MODES, MAX_AREAS):
        use_filt = bg_mode in FILT_REQUIRES_BG or sig_mode in FILT_REQUIRES_SIG
        filt_values = FILT_SIZES if use_filt else [None]

        subdir = output_dir / f"{bg_mode}__{sig_mode}"
        subdir.mkdir(exist_ok=True)

        for filtsize, sigma in itertools.product(filt_values, SIGMA_VALUES):
            kwargs = dict(sigma=sigma, bg_sub_mode=bg_mode, sigma_mode=sig_mode, max_area=max_area)
            if filtsize is not None:
                kwargs['filtsize'] = filtsize

            t0 = time.perf_counter()
            centroids = tetra3.get_centroids_from_image(img, **kwargs)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            count = len(centroids)

            filt_display = str(filtsize) if filtsize is not None else 'NA'
            print(f"{bg_mode:<16} {sig_mode:<22} {filt_display:>4} {max_area:>5} {sigma:>4} {count:>5} {elapsed_ms:>7.0f}ms")

            results.append(dict(
                bg_mode=bg_mode, sig_mode=sig_mode, filtsize=filt_display,
                max_area=max_area, sigma=sigma, count=count, ms=elapsed_ms,
            ))

            seq += 1
            lines = [
                f'bg={bg_mode}',
                f'sig_mode={sig_mode}',
                f'filt={filt_display}',
                f'max_area={max_area}',
                f'sigma={sigma}',
                f'stars={count}',
                f't={elapsed_ms:.0f}ms',
            ]
            frame = annotate(draw_base, centroids, lines, seq=seq, total=total_images)

            fname = f"{seq:04d}__sigma_{str(sigma).replace('.','_')}__filt_{filt_display}__maxarea_{max_area}.png"
            frame.save(str(subdir / fname))

    # Summary
    print(f"\n{'='*75}")
    print(f"TOP 20 BY STAR COUNT  [{stem}]")
    print(f"{'='*75}")
    print(f"{'stars':>5}  {'time':>7}  {'sigma':>4}  {'bg_sub_mode':<16} {'sigma_mode':<22} {'filt':>4} {'max_a':>5}")
    print("-" * 75)
    for r in sorted(results, key=lambda x: x['count'], reverse=True)[:20]:
        print(f"{r['count']:>5}  {r['ms']:>6.0f}ms  {r['sigma']:>4}  {r['bg_mode']:<16} "
              f"{r['sig_mode']:<22} {r['filtsize']:>4} {r['max_area']:>5}")

    print(f"\n{'='*75}")
    print(f"TOP 20 BY SPEED  [{stem}]")
    print(f"{'='*75}")
    print(f"{'time':>7}  {'stars':>5}  {'sigma':>4}  {'bg_sub_mode':<16} {'sigma_mode':<22} {'filt':>4} {'max_a':>5}")
    print("-" * 75)
    for r in sorted(results, key=lambda x: x['ms'])[:20]:
        print(f"{r['ms']:>6.0f}ms  {r['count']:>5}  {r['sigma']:>4}  {r['bg_mode']:<16} "
              f"{r['sig_mode']:<22} {r['filtsize']:>4} {r['max_area']:>5}")
    print("=" * 75)

    build_gif(output_dir)
