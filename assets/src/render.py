#!/usr/bin/env python3
"""render.py — re-render the README plates: assets/src/<name>.html -> assets/<name>.webp.

    python3 assets/src/render.py            # every plate
    python3 assets/src/render.py hooks mcp  # just these

Headless Chromium screenshots each page at 2x (fonts load from Google Fonts, so it needs
the network), then ImageMagick (or ffmpeg) downsamples to 1600 px wide WebP.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEIGHTS = {"hero": 660, "install": 830, "router": 800, "invoke": 850,
           "hooks": 990, "mercy": 930, "deck": 810, "mcp": 960}


def chrome() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge"):
        if path := shutil.which(name):
            return path
    cache = os.path.expanduser("~/.cache/ms-playwright") if os.name != "nt" else \
        os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
    hits = sorted(glob.glob(os.path.join(cache, "chromium_headless_shell-*", "*", "chrome-headless-shell*")))
    if hits:
        return hits[-1]
    sys.exit("render.py: no Chromium found (install chromium or run `npx playwright install chromium-headless-shell`)")


def to_webp(png: str, out: Path) -> None:
    if magick := shutil.which("magick"):
        cmd = [magick, png, "-filter", "Lanczos", "-resize", "1600x", "-quality", "90",
               "-define", "webp:method=6", str(out)]
    elif ffmpeg := shutil.which("ffmpeg"):
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", png, "-vf", "scale=1600:-1:flags=lanczos",
               "-c:v", "libwebp", "-quality", "90", str(out)]
    else:
        sys.exit("render.py: needs ImageMagick (magick) or ffmpeg")
    subprocess.run(cmd, check=True)


def render(name: str, browser: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, f"{name}.png")
        subprocess.run([browser, "--headless", "--no-sandbox", "--hide-scrollbars",
                        "--force-device-scale-factor=2", "--virtual-time-budget=8000",
                        f"--window-size=1600,{HEIGHTS[name]}", f"--screenshot={png}",
                        (HERE / f"{name}.html").as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out = HERE.parent / f"{name}.webp"
        to_webp(png, out)
        print(f"{out.name}  {out.stat().st_size // 1024} KB")


def main(argv: list[str]) -> int:
    names = argv or list(HEIGHTS)
    unknown = [n for n in names if n not in HEIGHTS]
    if unknown:
        sys.exit(f"render.py: unknown plate(s) {unknown}; known: {', '.join(HEIGHTS)}")
    browser = chrome()
    for name in names:
        render(name, browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
