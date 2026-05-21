"""
build_database.py
-----------------
Builds all tetra3/cedar-solve star databases for this project.

Uses the `tetra3-gen-db` CLI (not the Python API) — see research/database_size_comparison.md:
the CLI uses denser lattice-based pattern generation and consistently outperforms
equivalent Python API builds at the same magnitude limit.

Run from the project root with the cedar312 venv active:
    source ~/venvs/cedar312/bin/activate
    python databases/build_database.py

Set the BUILD_* flags below to control which databases are built.
Each build takes several minutes and may use hundreds of MB of disk.
"""

import os
import subprocess
import sys

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS       = os.path.join(ROOT, 'databases', 'catalogues')
DBS        = os.path.join(ROOT, 'databases')
TYC_MAIN   = os.path.join(CATS, 'tyc_main.dat')
TYCHO2     = os.path.join(CATS, 'tycho2.dat')
HIP_MAIN   = os.path.join(CATS, 'hip_main.dat')

# ── Toggle which databases to build ───────────────────────────────────────────

BUILD_V6   = False  # 1.0°–2.0° multiscale, auto mag  — first working database
BUILD_V7   = False  # 2.0°–4.0° multiscale, auto mag  — covers wider-FOV rig config
BUILD_V8   = True  # 1.5°–4.0° multiscale, auto mag  — 926 MB, 6/6; original reference
BUILD_V9   = False   # 1.55° single-scale,   mag 11     — 518 MB, 6/6; RECOMMENDED
BUILD_V10  = False  # 10° single-scale, Hipparcos      — wide-field / finder-scope FOV

# ── Database definitions ───────────────────────────────────────────────────────
#
# Source: research/setup.md, research/database_size_comparison.md, research/solving_notes.md
#
# Results summary (6 test images: Crab Nebula, M43, Christmas 2022, Cygnus, LBN 131):
#   V6: covers 1.0–2.0°  — first db to solve the 1.553° rig FOV
#   V7: covers 2.0–4.0°  — wrong range for 1.553° rig (silently fails); for 2.724° rig
#   V8: covers 1.5–4.0°  — 926 MB, 6/6 solves; original production db
#   V9: 1.55° single, mag 11 — 518 MB, 6/6 solves; same rate as V8 at 44% size — RECOMMENDED
#       Magnitude is the dominant factor: mag 8 → 3/6, mag 9–10 → 5/6, mag 11 → 6/6
#       Single-scale beats multiscale at the same magnitude

DATABASES = [
    {
        'name':    'V6',
        'build':   BUILD_V6,
        'save_as': os.path.join(DBS, 'astro_dbV6'),
        'catalog': TYC_MAIN,
        'args':    ['--max-fov', '2', '--min-fov', '1'],
        'notes':   '1.0–2.0° multiscale, auto magnitude; first db to solve 1.553° rig FOV',
    },
    {
        'name':    'V7',
        'build':   BUILD_V7,
        'save_as': os.path.join(DBS, 'astro_dbV7'),
        'catalog': TYCHO2,
        'args':    ['--max-fov', '4', '--min-fov', '2'],
        'notes':   '2.0–4.0° multiscale, Tycho2 catalog; covers 2.724° rig FOV, NOT 1.553°',
    },
    {
        'name':    'V8',
        'build':   BUILD_V8,
        'save_as': os.path.join(DBS, 'astro_dbV8'),
        'catalog': TYC_MAIN,
        'args':    ['--max-fov', '4', '--min-fov', '1.5'],
        'notes':   '1.5–4.0° multiscale, auto magnitude (~11); 926 MB, 6/6 solves; original reference',
    },
    {
        'name':    'V9',
        'build':   BUILD_V9,
        'save_as': os.path.join(DBS, 'astro_dbV9'),
        'catalog': TYC_MAIN,
        'args':    ['--max-fov', '1.55', '--star-max-magnitude', '11'],
        'notes':   '1.55° single-scale, mag 11; 518 MB, 6/6 solves; same rate as V8 at 44% size — RECOMMENDED',
    },
    {
        'name':    'V10',
        'build':   BUILD_V10,
        'save_as': os.path.join(DBS, 'astro_dbV10'),
        'catalog': HIP_MAIN,
        'args':    ['--max-fov', '10'],
        'notes':   '10° single-scale, Hipparcos catalog; wide-field / finder-scope FOV',
    },
]

# ── Build ─────────────────────────────────────────────────────────────────────

to_build = [db for db in DATABASES if db['build']]

if not to_build:
    print("No databases selected. Set BUILD_V* = True at the top of this script.")
    sys.exit(0)

print(f"Building {len(to_build)} database(s):\n")
for db in to_build:
    print(f"  {db['name']}: {db['notes']}")
print()

for db in to_build:
    cmd = ['tetra3-gen-db'] + db['args'] + [db['catalog'], db['save_as']]
    print(f"{'─' * 60}")
    print(f"Building {db['name']}: {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"\nERROR: {db['name']} build failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"\nSaved: {db['save_as']}.npz\n")

print("Done.")
