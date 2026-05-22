# Atlanta Astronomy PiFinder Presentation

Creating a presentation for the Atlanta Astronomy Club on pi finder like devices and how they work

## Setup

```bash
bash setup.sh
source venv/bin/activate
```

> **gifsicle** (used to compress GIF output from `review_centroids.py`) must be installed separately:
> - macOS: `brew install gifsicle`
> - Fedora/RHEL: `sudo dnf install gifsicle`
> - Ubuntu/Debian: `sudo apt install gifsicle`

---

## Building the Presentation

The presentation source is `presentation/john-digital-finder-scopes.md` (Marp Markdown). Run the build script from the project root:

```bash
bash presentation/build_presentation.sh           # build john-digital-finder-scopes.html
bash presentation/build_presentation.sh --watch   # live-preview in browser while editing
```

The script uses [marp-cli](https://github.com/marp-team/marp-cli) (`brew install marp-cli`) and, if [monolith](https://github.com/Y2Z/monolith) is available, produces a fully self-contained HTML file with all images embedded. Without monolith the HTML is still usable but images are linked rather than embedded.

To install monolith:
- macOS: `brew install monolith`
- Fedora/RHEL: `cargo install monolith` (requires Rust)
- Ubuntu/Debian: `cargo install monolith` or check your distro packages

---

## Scripts

All scripts are run from the **project root**.

---

### `annotate/annotate_solve.py`

Plate-solves every `.fits` file in the `annotate/` directory and writes four annotated JPEG images into a subfolder named after each target, showing progressively more detail about how the solver arrived at a solution.

**Output per target (`annotate/<stem>/`):**

| File | Contents |
|------|----------|
| `1_original.jpg` | Raw image converted to grayscale RGB |
| `2_centroids.jpg` | All detected star centroids circled |
| `3_quads.jpg` | Centroids plus every candidate quad pattern drawn |
| `4_solution.jpg` | Only the stars used in the final plate solve highlighted |

**Key configuration** (top of script):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE` | `databases/astro_dbV8` | Path to `.npz` star database (no extension) |
| `STRETCH` | `'stf'` | Image stretch mode: `'stf'`, `'linear'`, `'asinh'`, `'log'`, `'sqrt'`, or `None` |
| `FOV_ESTIMATE` | `6.553` | Estimated field of view in degrees |
| `SIGMA` | `2.0` | Centroid detection threshold |
| `PATTERN_CHECKING_STARS` | `6` | Stars used to form quad patterns; more = slower but more robust |

```bash
python annotate/annotate_solve.py
```

---

### `databaseTesting/solvingEveryImage.py`

Attempts to plate-solve every `.fits`, `.jpg`, and `.png` image in the `databaseTesting/` directory using a single database. Useful for evaluating how well a given database performs across a range of test images.

After all images are attempted it prints:
- A summary table of solve results (success/failure, FOV, solve time)
- The observed FOV range across all solved images
- A recommended `tetra3-gen-db` command to build a database tuned to that FOV range

**Key configuration** (top of script):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE` | `databases/astro_dbV9` | Path to `.npz` star database to evaluate |
| `SIGMA` | `2.0` | Centroid detection threshold |
| `PATTERN_CHECKING_STARS` | `8` | Uses library default for the best chance of solving |

```bash
python databaseTesting/solvingEveryImage.py
```

---

### `centroidParameterTesting/review_centroids.py`

For every `.fits` file in `centroidParameterTesting/`, sweeps all combinations of centroid-detection parameters and saves one annotated PNG per combination, then assembles a GIF so the effect of each parameter can be compared visually.

**What is swept:**

| Parameter | Values tried |
|-----------|-------------|
| `sigma` | 0.5, 0.8, 1.0, 1.5, 2.0, 3.0 |
| `bg_sub_mode` | `local_mean`, `global_median`, `global_mean` |
| `sigma_mode` | `global_root_square` |
| `filtsize` | 15, 25, 35 |
| `max_area` | 100, 200, 500 |

**Output per target (`centroidParameterTesting/<stem>/`):**

- One annotated PNG per parameter combination, organised into `<bg_mode>__<sigma_mode>/` subfolders
- `<stem>.gif` â€” all frames assembled into a single animated GIF
- `<stem>_shrunk.gif` â€” gifsicle-compressed copy (created by the script if `gifsicle` is on `$PATH`)

**Adding a new target:** drop a `.fits` and a matching `.png` or `.jpg` with the same stem into `centroidParameterTesting/`. The script auto-discovers all pairs â€” no configuration needed. If no draw file is found the script generates the canvas from the FITS image itself using an STF stretch.

**Compressing the output GIF manually:**

```bash
gifsicle -O3 --lossy=80 --colors 128 --resize-width 960 \
  --batch centroidParameterTesting/<stem>/<stem>_shrunk.gif
```

```bash
python centroidParameterTesting/review_centroids.py
```

---

### `databases/build_database.py`

Builds one or more tetra3/cedar-solve star databases using the `tetra3-gen-db` CLI and the Hipparcos / Tycho catalogues in `databases/catalogues/`.

Set the `BUILD_V*` flags at the top of the script to choose which databases to build, then run:

```bash
python databases/build_database.py
```

Each build can take several minutes and produce hundreds of MB on disk.

**Database versions:**

| Version | FOV range | Magnitude | Size | Solve rate | Notes |
|---------|-----------|-----------|------|------------|-------|
| V6 | 1.0Â°â€“2.0Â° multiscale | auto | â€” | â€” | First db to solve 1.553Â° rig FOV |
| V7 | 2.0Â°â€“4.0Â° multiscale | auto | â€” | â€” | For 2.724Â° rig; wrong range for 1.553Â° |
| V8 | 1.5Â°â€“4.0Â° multiscale | auto | 926 MB | 6/6 | Original production database |
| V9 | 1.55Â° single-scale | mag 11 | 518 MB | 6/6 | **Recommended** â€” same rate as V8 at 44% the size |
| V10 | 10Â° single-scale | Hipparcos | â€” | â€” | Wide-field / finder-scope FOV |

> Magnitude limit is the dominant factor: mag 8 â†’ 3/6 solves, mag 9â€“10 â†’ 5/6, mag 11 â†’ 6/6. Single-scale beats multiscale at the same magnitude.
