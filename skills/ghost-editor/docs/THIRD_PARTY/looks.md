# Third-party code and data: transitions and film looks

Everything here is MIT, except two gl-transitions ports inside the vendored xfade-easing file that are BSD-2 and BSD-3 (notices in `scripts/vendor/xfade-easing/NOTICE-gl-transitions.txt`). Nothing GPL/AGPL, nothing non-commercial, no model weights.

| What | Repo | Licence | Version | What we took |
|---|---|---|---|---|
| xfade-easing | https://github.com/scriptituk/xfade-easing | MIT, Copyright (c) 2025 Raymond Luckhurst | v3.6.6 (commit 206e099) | `scripts/vendor/xfade-easing/eased-transitions-yuv420p-script.txt` and `xfade-easings-script.txt`, copied verbatim with its `LICENSE`. `scripts/transitions.py` reads them at run time: the standard easing expressions (Robert Penner's equations as adapted by Pohoreski and Luckhurst) and every expression-capable transition. No code from `xfade-easing.sh` or the C patch. |
| gl-transitions (through xfade-easing's ports) | https://github.com/gl-transitions/gl-transitions | per shader; the four in the curated set are MIT (crosswarp by Eke Peter, directionalwarp by pschroen, DirectionalScaled by Thibaut Foussard, static_wipe by Ben Lucas); others reachable via `-t gl_*` are MIT, one BSD-2 and one BSD-3 | 1.71.0 | Through xfade-easing's ports in `eased-transitions-yuv420p-script.txt` (64 `GL_*` ports, shipped as upstream ships them); the BSD notices of GL_INVERTEDPAGECURL and GL_STEREOVIEWER are in `NOTICE-gl-transitions.txt`. |
| Spectral Film LUT | https://github.com/JanLohse/spectral_film_lut | MIT, Copyright (c) 2026 Jan Lohse | 0.18.12 (PyPI) | Installed in the optional venv `~/.venvs/ghost-looks` by `scripts/setup_looks.sh`, not vendored. `scripts/gen_luts.py` calls its `create_lut()` and `load_filmstocks()` to generate `library/luts/*.cube` (data, not in git) from the film datasheets digitised in the package; `scripts/film_look.py` calls its `generate_grain()` for the grain plate when the package is importable (else numpy noise). The negative -> grain -> print chain in ffmpeg follows the tool's README node tree in our own code. |

Own code (no third-party source): `transitions.py` (CSS `cubic-bezier()`/`ease*` expressions with a bisection solver, the
easing cache, the `zoomblur`, `whip` and `softwipe` transitions, the native-xfade timestamp-warp easing, the parallel chunk
renderer, timing, assembly, audio and the reel.json integration), `film_look.py` (halation, grain plumbing, split screen),
`gen_luts.py` (look presets, headless driver).

Python packages pulled in by `spectral_film_lut` in that venv: numpy, scipy, numba, colour-science (BSD-3), opencv-python
(Apache-2.0), PyQt6 (GPL-3 / commercial: imported by the package, run locally only, never shipped or linked into anything
distributed), matplotlib, imageio, networkx.

Upstream bug found in 0.18.12: with print stock "Inversion (Optimized)", `FilmSpectral.cid_to_xyz` calls `input_transform()`
with the default `upsampling_method="barycentric_nnls_all"`, which no longer exists; `gen_luts.py` patches the default to
`"SFL upsampling"` at run time.
