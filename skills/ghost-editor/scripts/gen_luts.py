#!/usr/bin/env python3
"""Generate film-stock .cube LUTs with Spectral Film LUT (JanLohse/spectral_film_lut, MIT).

Runs the tool's own `create_lut()` headlessly (no GUI, no Qt window), with the GUI's default
settings except for the per-look overrides in LOOKS below. Input is assumed to be Rec.709 video
(iPhone / prep.sh output), output is Rec.709 gamma 2.4.

For every look it writes, into library/luts/ (gitignored media, ~25 MB; library/luts/looks.json is in git):
  <look>.cube                 full pipeline (negative -> print -> projection), 33^3
  split/<look>.neg.cube       negative stage, ADX "Density 4" encoded      (for grain)
  split/<look>.grain.cube     grain intensity per channel from the stock's RMS curves
  split/<look>.print.cube     print / projection stage (input: the .neg output)
  looks.json                  what each look is, with the exact parameters (paths relative to the folder)

    bash $S/scripts/setup_looks.sh                                   # venv + all LUTs (what you normally run)
    ~/.venvs/ghost-looks/bin/python $S/scripts/gen_luts.py --only cinestill800t --size 65
    ~/.venvs/ghost-looks/bin/python $S/scripts/gen_luts.py --list-stocks
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # the package imports PyQt6 widgets

HERE = Path(__file__).resolve().parent

# GUI defaults of Spectral Film LUT 0.18.12 (read from a headless MainWindow, 2026-10-10),
# except input_colorspace (GUI default is ARRI Wide Gamut 4; our footage is Rec.709).
GUI_DEFAULTS = dict(
    input_colorspace="ITU-R BT.709", output_gamut="Rec. 709", gamma_func="Gamma 2.4",
    projector_kelvin=6500, exp_comp=0.0, white_clip=False, white_balance=0, exp_kelvin=6500,
    red_light=0.0, green_light=0.0, blue_light=0.0, shadow_comp=0.0, color_masking=1.0,
    tint=0.0, sat_adjust=1.0, push_pull=0.0, inversion_gamma=3.0, idealized_curve=False,
    apd_intermediate=True, upsampling_method="SFL upsampling",
)
ADX_SCALING = 2.0  # GUI "Density 4": safe headroom for every negative (Density 2 can clip)

# Looks for a dusk / night talking head, tuned on reel-c009 (tight.mp4 16.5 s, wide.mp4 6.0 s).
# shadow_comp < 0 keeps night blacks deep (positive values lift them).
LOOKS = {
    "portra400": dict(
        title="Kodak Portra 400 (scan)",
        what="Warm, soft, pink-leaning skin; the modern scanned-negative Portra look.",
        negative="Kodak Portra 400", print="Inversion (ACES like)",
        params=dict(shadow_comp=-0.5), film_look=dict(grain=1.0)),
    "vision3_500t": dict(
        title="Kodak Vision3 500T 5219 + 2383 print",
        what="The night cinema look: tungsten negative printed on Vision 2383, rich warm skin, dense blacks.",
        negative="Kodak Vision3 500T 5219", print="Kodak Vision 2383",
        params=dict(shadow_comp=-0.5), film_look=dict(grain=1.0, halation=0.2)),
    "eterna500": dict(
        title="Fuji Eterna 500 + Eterna-CP 3513DI",
        what="Muted, low-saturation Fuji motion-picture look with soft contrast.",
        negative="Fuji Eterna 500", print="Fuji Eterna-CP Type 3513DI",
        params=dict(shadow_comp=-0.5), film_look=dict(grain=1.0)),
    "ektachrome100d": dict(
        title="Kodak Ektachrome 100D (slide)",
        what="Reversal film: crisp, contrasty, cool shadows against warm skin.",
        negative="Kodak Ektachrome 100D", print=None,
        params=dict(shadow_comp=-0.3, exp_comp=0.3), film_look=dict(grain=1.0)),
    "trix400": dict(
        title="Kodak Tri-X 400 pushed (Dev 11) on Polymax grade 3",
        what="Black and white, pushed Tri-X: hard contrast, deep blacks, strong grain.",
        negative="Kodak Trix-X 400 Dev 11", print="Kodak Polymax Fine-Art Paper Grade 3",
        params=dict(shadow_comp=-1.0), film_look=dict(grain=1.0)),
    "cinestill800t": dict(
        title="Cinestill-like 800T (5219 pushed, cool WB) + halation",
        what="Cinestill-style night stock: Vision3 500T rated at 800 (2/3 stop push) with a cooler white balance.",
        negative="Kodak Vision3 500T 5219", print="Kodak Vision 2383",
        params=dict(shadow_comp=-0.5, push_pull=0.67, exp_kelvin=4300),
        film_look=dict(halation=0.55, grain=1.6)),
}


def patch_upstream():
    """0.18.12 bug: 'Inversion (Optimized)' calls input_transform() whose default
    upsampling_method 'barycentric_nnls_all' no longer exists -> ValueError. Point the default at
    the GUI's 'SFL upsampling'. Harmless for every other path."""
    from spectral_film_lut.film_spectral import FilmSpectral
    d = tuple("SFL upsampling" if x == "barycentric_nnls_all" else x
              for x in FilmSpectral.input_transform.__defaults__)
    FilmSpectral.input_transform.__defaults__ = d


def load():
    from spectral_film_lut.film_loader import load_filmstocks
    patch_upstream()
    return load_filmstocks(lambda *a: None)


def make(stocks, name, look, out_dir, size, split=True):
    from spectral_film_lut.utils import create_lut
    neg = stocks[look["negative"]]
    pname = look["print"]
    inversion = bool(pname) and pname.startswith("Inversion")
    pfilm = None if (not pname or inversion) else stocks[pname]
    kw = dict(GUI_DEFAULTS)
    kw.update(look.get("params", {}))
    common = dict(inversion=inversion, custom_inversion=inversion and "ACES" not in pname,
                  reference_negative=stocks["Kodak Vision3 250D 5207"], adx_scaling=ADX_SCALING)
    files = {}
    t = time.time()
    files["full"] = create_lut(neg, pfilm, name=str(out_dir / name), lut_size=size, cube=True,
                               mode="full", **common, **kw)
    if split:
        sd = out_dir / "split"
        sd.mkdir(exist_ok=True)
        for mode, suffix in (("negative", "neg"), ("print", "print"), ("grain", "grain")):
            try:
                files[suffix] = create_lut(neg, pfilm, name=str(sd / f"{name}.{suffix}"),
                                           lut_size=size, cube=True, mode=mode, **common, **kw)
            except Exception as e:  # e.g. a stock without RMS data has no grain stage
                print(f"  {name}: no {mode} LUT ({type(e).__name__}: {e})")
    for f in files.values():  # the tool titles a LUT with its absolute output path; keep only the name
        p = Path(f)
        txt = p.read_text()
        if txt.startswith("TITLE "):
            p.write_text(f'TITLE "{p.stem}"' + txt[txt.index("\n"):])
    print(f"  {name}: {', '.join(Path(f).name for f in files.values())} ({time.time() - t:.1f}s)")
    return {k: str(Path(v).relative_to(out_dir)) for k, v in files.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="look names (default: all)")
    ap.add_argument("--size", type=int, default=33, help="LUT size (GUI default 33)")
    ap.add_argument("--out", default=str(HERE.parent / "library" / "luts"))
    ap.add_argument("--no-split", action="store_true", help="only the full LUT")
    ap.add_argument("--list-stocks", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    stocks = load()
    print(f"loaded {len(stocks)} stocks in {time.time() - t0:.1f}s")
    if a.list_stocks:
        for k, s in stocks.items():
            if s is not None:
                print(f"{k:42s} {s.stage:7s} {s.film_type:9s} rms={getattr(s, 'rms', None)}")
        return
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta_path = out / "looks.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    import spectral_film_lut
    for name in (a.only or LOOKS):
        if name not in LOOKS:
            sys.exit(f"unknown look {name}; have {', '.join(LOOKS)}")
        look = LOOKS[name]
        files = make(stocks, name, look, out, a.size, split=not a.no_split)
        neg = stocks[look["negative"]]
        files = {**meta.get(name, {}).get("files", {}), **files}  # --no-split keeps old split LUTs
        meta[name] = dict(title=look["title"], what=look["what"], negative=look["negative"],
                          print=look["print"], params={**GUI_DEFAULTS, **look.get("params", {})},
                          adx_scaling=ADX_SCALING, size=a.size, rms=getattr(neg, "rms", None),
                          bw=neg.density_measure == "bw", film_look=look.get("film_look", {}),
                          files=files, generator=f"spectral_film_lut {spectral_film_lut.__version__}")
    meta_path.write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"wrote {meta_path}")


if __name__ == "__main__":
    main()
