# Cutout effects (`scripts/cutout_fx.py`)

One BiRefNet pass over a window of the speaker gives a soft alpha; every effect reuses it. In a reel they come in three
ways (all in references/reel-json.md):

- a `cutout` beat: one moment where the world around the speaker changes (2-3 s, at most 2 per reel)
- `look.cutout`: selective colour, spotlight or portrait blur over the whole reel, baked into the plate like `look.film`
- `cover`: the Reels cover (1080x1920) and a YouTube thumbnail (1280x720), shown on the approval sheet

```
window of the source --(BiRefNet, once)--> raw alpha at model size --(matte.py: median3 + deadband EMA, guided upsample)-->
alpha.mkv (FFV1 grey, source size, same frames) + meta.json      <- cached by source size/mtime + window + model
      |
      +-- Clip: frames + alpha in memmaps, decontaminated edge colour (blur-fusion) on demand, bottom-edge hole fill
      +-- bg-swap | bg-blur | selective | spotlight | sticker | neon | clones | pop | sandwich  -> H.264 (+ the window's audio)
      +-- thumb (1080x1920 + 1280x720 covers) | webm (VP9 + alpha for HyperFrames)
```

The refinement (guided filter, blur-fusion decontamination, temporal filter) is imported from `matte.py`, not copied.
It runs in the optional matte venv (`bash $S/scripts/setup_matte.sh`: torch, transformers, opencv, Pillow, BiRefNet-portrait
and BiRefNet_lite weights). Weights live in `~/.cache/ghost-matte/hf` (`CUTOUT_FX_CACHE` overrides; other models download
on first use), alphas in `~/.cache/ghost-matte/alpha/<clip>-<model>-<size>-<hash>/` (~3 MB per 5 s window).

## In a reel: how build.mjs places a `cutout` beat

- The window is `at`..`to` (original seconds, inside ONE take; the build stops otherwise), snapped to the output frame
  grid. Its first frame is exactly the source frame the take shows there (HyperFrames samples a `<video>` at
  floor(media time x fps)), and it holds exactly the beat's frame count: the head does not jump at either edge and the
  picture cannot drift against the voice. The clip is silent; the voice keeps coming from the take.
- `cutout_fx.py` renders `assets/fx/cutout-<n>.mp4` + `.json` (a signature of the source, options and code: an unchanged
  beat costs nothing on the next build; any change re-renders that window). `build/cutouts.json` lists the windows;
  `qa.py` re-counts every clip.
- The clip plays inside the camera wrappers like a transition window, so snaps, pushes, the hook punch and the CSS look
  apply to it; captions and cards stay on top. A `behind` word overlapping a cutout would show the original footage over
  the effect (the build warns).
- Every effect starts on the window's first frame (ramps in from the untouched frame) and eases back into the take over
  the last `release` seconds (default 0.3; 0 = hard end). The sticker freezes the frame on screen when the beat lands (or
  the one at `freeze`; the window plays live until then) and its `hold` is fitted to drop back 0.15 s before the window
  ends. Look at the frozen frame: a blink makes a bad sticker (it happened on the first test reel).
- Default model `lite@1024` (`model` per beat, or top-level `cutout: {model}`); ~1 min per 2.5 s beat on an M3 Air.

## The effects

| effect | what it does | how | options (reel.json camelCase = CLI kebab-case) |
|---|---|---|---|
| `bg-swap` | new background behind the speaker; still or video; a second background from a cut on | decontaminated edge colour (blur-fusion), Lab mean of the speaker pulled toward the scene (EMA over frames), light wrap = blurred background bleeding over the rim, slight defocus + slow push on stills, soft top-down reveal | `bg` (image, video, `#hex` or `#hex1,#hex2`), `bg2`, `switch` (source s), `wrap` 0.55, `match` 0.5, `defocus` 2, `push` 1.06, `wipe` 0.5 |
| `bg-blur` | portrait mode: the background racks out of focus | clean plate first (speaker removed by normalised-convolution fill, so no halo), disc lens blur in linear light with highlight bloom, radius ramps 0 -> `radius` | `radius` 26, `ramp` 0.9, `bokeh` 1, `dim` 0 |
| `selective` | speaker in colour, world in B&W / noir / muted teal-orange film | grade the plate, speaker on top with +18 % saturation | `look` bw\|noir\|film, `ramp` 0.6 |
| `spotlight` | background dims, warm pool of light behind the head, the body falls off into shadow | head position from the alpha (top row + band centre, EMA), radial pool + vignette + key-light falloff on the speaker | `dim` 0.18, `color` #ffb46b, `ramp` 0.6 |
| `sticker` | freeze frame -> die-cut sticker (white outline, shadow) pops, wiggles, drops back | distance-transform stroke on a padded alpha (closes where the body leaves the frame), back-out ease, decaying 2.6 Hz wiggle, shadow grows with the lift, frozen clean plate behind (no ghost) | `freeze` (original s, default `at`), `hold` (auto-fitted), `stroke` 22, `stickerScale` 0.84, `bg` plate\|dim\|#hex |
| `neon` | a neon tube traces the silhouette from the top of the head down both sides, an echo line follows, colours breathe | contour of the dilated alpha, smoothed along the curve, frame-border points dropped, arc-length reveal from the top point both ways, three-blur glow + white core | `colors` "#38f6ff,#ff3df2", `trace` 1.3, `dim` 0.32 |
| `clones` | three time-offset copies side by side, middle in front | each copy is a bust (crop) of the same matted clip at its own offset, mirrored on the left, smaller/higher at the sides for depth, bottoms fade into the floor, contact shadow; intro: the frame shrinks into the middle bust over a clean plate | `offsets` "0,0.4,0.8" (the window reads that much more source), `bust`, `midScale` 0.72, `sideScale` 0.54, `backdrop`, `light` |
| `pop` | video shrinks into a phone / card frame, the top edge slides down, the head breaks out over the bezel | anti-aliased rounded-rect SDF frame, the cut-out drawn on top (identical inside the screen, new above it), head shadow on the bezel | `frame` phone\|card, `bg` (spec or `blur`), `plate` 0.78, `bottom` 150, `brk` 0.62 |
| `sandwich` | words behind the head, in front of the body, and one that passes through the head | behind words between plate and cut-out, front words over everything, the through word split at the head centre | CLI only (`--behind/--front/--through TEXT@t0[-t1]`); in a reel use `behind` beats with `front` / `through` (crisp HTML type) |
| `thumb` | 9:16 Reels cover + 16:9 YouTube thumbnail | sharpest still frame (Laplacian variance in the head box minus motion), outline only on real silhouette edges, frame-cut edges faded, gradient + rays, auto-fit headline with an accent box | `headline` "A\|B\|*C*", `at`, `colors`, `accent`, `stroke`, `coverScale` |

Text uses the skill's Montserrat Black (woff2 subsets by script, so Cyrillic and Latin mix). Words on screen are words
the speaker says.

Where each one carries: on a dark background (night, a black wall) bg-blur, selective and spotlight only change the few
lit things behind the speaker; they are strong on daylight footage with a visible background. bg-swap, neon, sticker,
clones and pop carry anywhere.

## CLI

```bash
PY=~/.venvs/ghost-matte/bin/python; FX=$S/scripts/cutout_fx.py
W="assets/talk.mp4 --ss 15.6 --t 5.4"       # every video effect works on a window: source seconds, like reel.json

$PY $FX alpha     $W                          # matte once (cached), print the cache folder
$PY $FX bg-swap   $W --bg walk.png --bg2 rays.mp4 --switch 18.57 -o fx.mp4
$PY $FX bg-blur   $W --radius 30 -o fx.mp4
$PY $FX selective $W --look bw|noir|film -o fx.mp4
$PY $FX spotlight $W --dim 0.18 -o fx.mp4
$PY $FX sticker   $W --freeze 16.5 --hold 3.0 -o fx.mp4
$PY $FX neon      $W --colors "#38f6ff,#ff3df2" -o fx.mp4
$PY $FX clones    $W --offsets 0,0.4,0.8 -o fx.mp4
$PY $FX pop       $W --frame phone|card --bg "#ff7a18,#7a0b2e" -o fx.mp4
$PY $FX sandwich  $W --behind "WORD@16.32-17.40" --front "WORD@17.44-19.40" --through "WORD@20.04" -o fx.mp4
$PY $FX thumb     $W --headline "LINE|LINE|*ACCENT*" -o build/cover     # cover-9x16.jpg + cover-16x9.jpg
$PY $FX webm      $W -o talk-matte.webm                                 # VP9 + alpha cut-out for HyperFrames

$PY $FX still IMG --model dis|cod|general|hr-matting@2048|... --result checker|white|color|highlight|product -o out/name
$PY $FX bench $SRC --ss 15.6 --frames 30 --configs lite@512,lite@768,lite@1024,portrait@1024 --batches 1,4 -o bench.json
$PY $FX compare $W --configs portrait@1024,lite@1024,lite@768,lite@512 --bench bench.json --crops 60 -o grid.mp4
```

Common flags (every video effect): `--model NAME[@SIZE]` (default `lite@1024`, env `CUTOUT_FX_MODEL`), `--batch N`
(frames per model call; 4 helps lite at <= 768), `--scale 0.5` (work at half size for a quick preview), `--at` (source
second the effect starts; default 0.4 s into the window), `--release S` (ease back into the source over the last S
seconds), `--size 540x960`, `--audio FILE` / `--no-audio` (default: the source's own audio for the same window), `--crf`.
Outputs keep the window's frame count and fps (clones: minus the largest offset), H.264 yuv420p bt709, +faststart, and a
sidecar `OUT.json`: a second call with the same source, options and code returns at once (`cached:`).

Exact windows: ffmpeg's input seek returns the frame AT `--ss` only when `--ss` is that frame's time to 6 decimals
(3 decimals land a frame late on a third of the grid), and `--t` = n/fps can lose the last frame; build.mjs passes the
exact frame time and `--t` half a frame short, which `tests/test_cutout_fx.py` checks at every phase of the grid.

## The BiRefNet family (all MIT, huggingface.co/ZhengPeng7)

| `--model` | repo | input | size | use it for |
|---|---|---|---|---|
| `portrait` | BiRefNet-portrait | 1024 | 885 MB | people, soft hair edge (matte.py's default for `behind` words) |
| `general` | BiRefNet | 1024 | 444 MB | anything: products, objects, people |
| `lite` | BiRefNet_lite (swin-T) | 1024 (any) | 176 MB | speed: the video effects |
| `dis` | BiRefNet-DIS5K | 1024 | 885 MB | ultra-fine structures: spokes, wires, leaves, lace |
| `cod` | BiRefNet-COD | 1024 | 885 MB | camouflaged objects |
| `hr-matting` | BiRefNet_HR-matting | 2048 | 444 MB | soft alpha at high resolution: hair, fur (@2048 needs > 16 GB; @1536 is close) |
| `dynamic` | BiRefNet_dynamic | any (256-2304) | 444 MB | native aspect (576x1024 for 9:16), odd sizes |
| `lite-matting` | BiRefNet_lite-matting | 1024 | 89 MB | fast soft alpha |
| `hrsod`, `hr`, `matting`, `lite-2k`, `dynamic-matting` | | | | salient objects, general @2048, matting, 2560x1440 lite |

`bria` (RMBG-2.0, BiRefNet trained on private data) is non-commercial and is not offered.

## Speed (M3 MacBook Air 16 GB, MPS fp16, 1080x1920 talking head)

Model only, 30 frames, quiet Mac:

| config | s/frame | fps | batch 4 | peak GPU mem | vs portrait@1024 |
|---|---|---|---|---|---|
| lite @512 | 0.164 | **6.10** | 7.04 fps | 1.3 GB (3.4 at b4) | 13.5x |
| lite @768 | 0.319 | **3.14** | 3.51 fps | 3.4 GB | 6.9x |
| **lite @1024** (default) | 0.528 | **1.90** | 1.24 fps (slower: 10 GB) | 5.8 GB | 4.2x |
| portrait @768 | 1.108 | 0.90 | 0.92 fps | 3.3 GB | 2.0x |
| dynamic @576x1024 | 1.244 | 0.80 | 0.83 fps | 3.4 GB | 1.8x |
| portrait @1024 | 2.208 | 0.45 | (not run: memory) | 4.7 GB | 1x |

M4 Mac mini (24 GB): lite @512 7.7 fps (9.1 at b4), @768 4.0, @1024 2.2 (2.5 at b4), portrait @1024 0.71. Numbers move
+-30 % with load; lite is CPU-dispatch-bound on MPS, so batch 4 holds up on a busy Mac.

Whole pipeline: a 2.6 s `cutout` beat (78 frames) at lite@1024 takes ~1 min the first time (alpha ~55 s at 0.56 s/frame,
effect + encode 5-40 s depending on the effect) and nothing on the next build. A 5.4 s window: lite@1024 112 s,
lite@768 83 s, lite@512 39 s, portrait@1024 397 s. Effects add 5-65 s per 5.4 s window on the CPU (sticker 5, sandwich 13,
spotlight 17, clones 21, neon 26, selective 31, bg-blur 39, bg-swap 45, pop 48). `look.cutout` over a 65 s source at
lite@512 batch 4: 12 min end to end (alpha 396 s at 0.15 s/frame, selective effect + encode 294 s; Mac under load).

Quality (the same window through the same refinement): lite @1024 vs portrait @1024 IoU 0.9989, edge-band difference
6.0/255, edge flicker 1.83 vs 1.52. At reel size the configs are indistinguishable; at 100 % crops portrait keeps the
softest beard hairs, lite @1024 is close, lite @768 / @512 round the beard edge off. So: lite@1024 for cutout beats,
lite@512 batch 4 for reel-wide looks, portrait for `behind` words next to the beard in a close-up, HR-matting for stills
with hair, DIS for wires and plants, COD for hidden things.

## Caveats

- Holes at the frame's bottom edge: the model leaves small background specks in a dark shirt where the body runs out of
  the frame. `fill_bottom_holes` fills background components that touch the bottom edge but not the top (< 2 % of the
  frame); real background beside the body reaches the top and is kept.
- Levels: frames are decoded with swscale `accurate_rnd+full_chroma_int`. Without them ffmpeg 8.1 (arm64) reads
  tv-range footage 1-2 levels dark whenever the width is not a multiple of 16 (1080, 540), and each cutout pass wrote
  that back into the clip. `tests/test_decode_levels.py` holds the decode and the round trip to the BT.709 spec; any new
  yuv -> rgb decode that feeds an output needs the same flags.
- Clones: side copies are time-offset, so their lips are out of sync with the voice by design (the middle one is live).
- Sticker: for the first 0.2 s of the pop the frozen frame cross-fades to the clean plate; the picture is frozen while
  the voice goes on, so put it on a short line or a reaction.
- CPU effects are numpy/OpenCV at full 1080x1920 (0.03-0.4 s per frame); `--scale 0.5` for quick previews.
- The render cache keys on the code hash too, so any edit to cutout_fx.py or matte.py re-renders every cutout beat.
