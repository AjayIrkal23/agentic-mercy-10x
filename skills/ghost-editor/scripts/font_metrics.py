#!/usr/bin/env python3
"""Advance-width tables for the bundled caption fonts, so caption-templates.mjs
can lay out lines (and fit font sizes) in Node without a browser.

    ~/.venvs/ghost-captions/bin/python $S/scripts/font_metrics.py \
        $S/templates/fonts  $S/scripts/lib/metrics.json      (venv: bash $S/scripts/setup_captions.sh)

For every family x weight it instantiates the variable font at that weight and
stores each character's advance in thousandths of an em. Kerning is ignored
(it is almost always negative), so measured widths err on the wide side.
"""
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FAMILIES = {
    "Inter": "inter",
    "Montserrat": "montserrat",
    "Unbounded": "unbounded",
    "Oswald": "oswald",
    "JetBrains Mono": "jetbrains-mono",
    "Geist": "geist",
}
WEIGHTS = [300, 400, 500, 600, 700, 800, 900]
CHARS = (
    [chr(c) for c in range(0x20, 0x7F)]
    + [chr(c) for c in range(0xA0, 0x100)]
    + [chr(c) for c in range(0x400, 0x460)]
    + list("«»–—…‘’“”„№•")
)


def advances(path: Path, wght: int):
    f = TTFont(str(path))
    if "fvar" in f:
        ax = next(a for a in f["fvar"].axes if a.axisTag == "wght")
        w = max(ax.minValue, min(ax.maxValue, wght))
        f = instancer.instantiateVariableFont(f, {"wght": w}, inplace=False)
    upm = f["head"].unitsPerEm
    cmap = f.getBestCmap()
    hmtx = f["hmtx"]
    out = {}
    for ch in CHARS:
        g = cmap.get(ord(ch))
        if g is not None:
            out[ch] = round(hmtx[g][0] * 1000 / upm)
    return out


def main():
    src = Path(sys.argv[1]).expanduser()
    dst = Path(sys.argv[2])
    res = {}
    for fam, stem in FAMILIES.items():
        files = sorted(src.glob(f"{stem}-*.woff2"))
        files = [p for p in files if "italic" not in p.name and not (stem == "geist" and "mono" in p.name)]
        if not files:
            continue
        res[fam] = {}
        for w in WEIGHTS:
            table = {}
            for p in files:
                for ch, a in advances(p, w).items():
                    table.setdefault(ch, a)
            res[fam][str(w)] = table
        print(fam, len(files), "files,", len(res[fam]["700"]), "chars")
    dst.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    print("->", dst, dst.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
