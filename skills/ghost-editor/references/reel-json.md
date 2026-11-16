# reel.json: the whole edit in one file

`build.mjs` turns this into `index.html` (HyperFrames). Every time is an
ORIGINAL-recording second, as printed by `transcribe.py`, except `"end"`
(the last frame) and `"outro+N"` (N seconds into the frozen outro). A time
that falls in cut material fails the build with the beat's name. `"hold:1+0.7"` is 0.7 s into the
hold after take 1. Any on-screen text with Cyrillic switches the card font from Geist to Inter.

```jsonc
{
  "title": "why nobody cares about your launch",
  "source": "assets/talk.mp4",          // prep.sh output (voice at -16 LUFS)
  "words": "build/words.whisper.json",  // transcribe.py output
  "fps": 30,
  "outro": 3,                           // seconds of frozen last frame under the end card
  "takes": [                            // edit order; a = first word - 0.10..0.15, b = last word + 0.20..0.30
    { "a": 6.58, "b": 10.40, "note": "hook, 2nd take" },
    { "a": 10.76, "b": 14.42, "hold": 0.8 }   // hold: frozen last frame, no voice, AFTER the take: air for a meme on a
  ],                                          // tightly cut recording. Address it as "hold:<take index>+<seconds>"
  "zoom": {
    "origin": "50% 29%",                // the face; move it if the face sits elsewhere
    "snaps": [[10.76, 1.1], [16.30, 1.0]],   // instant reframes: every cut + most sentence starts, 1.0/1.1, 1.12 on a punchline
    "pushes": [{ "at": 19.8, "z": 1.1, "up": 0.4, "until": 22.4, "down": 0.2 }],  // slow push-ins, 4-6 per reel, no overlaps; until "end" holds through the outro
    "snapSfx": false                    // true = quiet whoosh on every snap; default off (dry cuts read more premium)
  },
  "captions": {
    "style": "house",                   // house: Arial bold 56, white, black outline, lower third. "pill": Geist 66 on a dark pill.
                                        // "none": the recording already has burned-in captions (never stack two caption layers)
    "group": 3,                         // words per caption (also breaks on , . ? ! and on pauses > 0.6 s)
    "highlight": null,                  // e.g. "#FFD166" to colour the spoken word; null = scale-pop only
    "size": 56,
    "fixes": { "Jithub": "GitHub" }     // whisper word -> correct word, case-insensitive
  },
  "layout": { "cardY": 990, "capBottom": 450,     // card band top, caption bottom margin (IG UI covers the bottom 450)
              "slotY": 240,                        // reaction slot top (emoji / logo / meme next to the head)
              "compact": false },                  // smaller cards for a narrow band, e.g. under burned-in captions
  "mix": { "roleDb": { "ui": -14, "whoosh": -12, "impact": -8, "meme": -3 } },  // SFX peak vs voice p95 peak, dB
  "beats": [ /* see below */ ],
  "sfx": [{ "at": 24.4, "id": "record-scratch", "db": 0, "lead": 0 }]   // extra hand-placed sounds
}
```

## Beats

All beats take `at`, `to` (optional; default 2.5 s, meme 1.8 s) and `sfx`
(optional): omit for the default, a kit id or list of ids to override,
`"none"` for silence. Card beats live in the band under the chin; `emoji`,
`logo` and `meme` share the reaction slot next to the head (one at a time,
the build warns on a double booking).

| type | fields | default sound | use when the speaker says |
|---|---|---|---|
| `big` | `text`, `sub`, `count` (count up a number) | whoosh-cine + impact (text slam) | a number, a duration, a claim they would put on a website |
| `chips` | `items: [{text \| icon \| src, label, bg, fg, invert, at}]` | pop per chip (round-robin) | a list of names or numbers, one chip per spoken word |
| `strike` | `text`, `strikeAt` | whoosh | "not X", a myth, a claim they dismiss |
| `quote` | `header`, `lines: [{text, at, big}]` | impact on the `big` line | what someone told them |
| `list` | `lines: [{text, at}]`, `stamp`, `stampAt`, `stampSfx` | pop per line, impact + buzzer on the stamp | a list they then dismiss |
| `emoji` | `emoji` (a glyph) or `name` (a slug from `library/emoji/set.json`), `size` (Fluent, default 260, keep <= 280), `fluent: false`, `x`, `y` | pop | a feeling (push in on the speaker at the same time). When the glyph or name is in the Fluent set (`scripts/emoji_fetch.py`), an animated 3D emoji pops in with overshoot, leans toward the head and floats; otherwise the font glyph pops |
| `logo` | `icon` (simple-icons slug) or `src`, `bg`, `invert` | pop | a product or company that should land alone |
| `meme` | `id` (library), `audio` (false = mute the clip's own sound), `in` (start later in the clip), `w`, `x`, `y`, `tilt`, `db` | clip: its own audio; image: its `sfx` or vine-boom | a punchline, a reaction, a wait. ON or just after the punchline word, never before |
| `endcard` | `title`, `line`, `url` (usually `at: "outro+0"`) | whoosh | the close |
| `broll` | `src` (an mp4 in the project), `in` (seconds into the clip), `zoom` ([from, to], default [1, 1.08]), `grade`, `mode: "split"` (clip fills the top `h` px, default 960; the speaker plate slides down by `shift`, default 560, once per run of adjacent split beats) | none (set `sfx` to add one) | a full-screen video cutaway on the word it illustrates (e.g. AI B-roll from MiniMax H3); captions stay on top, the clip is muted |
| `title` | `words: [{text, at}]` (or `text`), `y`, `size`, `font`, `weight`, `tracking`, `anim` (`pop` or `blur`), `color`, `glow` | none (set `sfx`) | giant uppercase display words above the head that land on their spoken times (reference styles: @iphone_igor pops, @rpn blur-in) |

`icon` slugs come from simpleicons.org (fetched at build time, CC0).

## Style, platform, look (top level)

- `style`: a preset from `styles/` (see `references/styles.md`); reel.json overrides it.
- `platform`: `instagram` (default), `tiktok`, `shorts` or `all`. It sets the safe area captions and cards stay inside.
- `sfxProfile`: `restrained` (structural hits only), `standard`, `rich` (adds a whoosh to every snap).
- `look`: `{grade: "<css filter>", grain: 0.07, vignette: 0.45}`, the film look over the speaker plate. `grade` and
  `film` colour the speaker's face, so the build ignores them unless `look.asked` holds the user's words asking for a
  graded look (the face stays as shot by default; broll_qa.py `as_shot` fails a regrade). Grain and vignette stay allowed.
- `look.film`: a film-stock look baked into the speaker plate before the build (cards, captions and brand colours stay
  true): `"look": {"film": "vision3_500t", "grain": 1, "halation": 0.2}`. Stocks: `portra400`, `vision3_500t` (night),
  `eterna500`, `ektachrome100d`, `trix400` (B&W), `cinestill800t` (`python3 $S/scripts/film_look.py list`). It needs
  `assets/talk.film.mp4`: `python3 $S/scripts/film_look.py apply assets/talk.mp4 assets/talk.film.mp4 --look <stock>` (the
  build stops with that command when the plate is missing or older than talk.mp4; `look.plate` names another file). With
  `film`, the CSS `grade` and `grain` are ignored (the grain is in the plate); `vignette` still applies. The LUTs live in
  `library/luts` (`bash $S/scripts/setup_looks.sh` generates them once; applying needs only ffmpeg).
- `transitions`: eased transitions at take changes, rendered by `python3 $S/scripts/transitions.py reel $P` into
  `assets/tx/` and laid over the cut as short clips inside the camera wrappers (the edit's timing and the voice are
  untouched; the voice stays a hard cut). A list `[{"after": 0, "type": "dissolve", "dur": 0.2}, {"after": 3, "type": "whip"}]`
  (`after` = take index) or one rule for every take change `{"default": "dissolve", "dur": 0.2, "skip": [4]}`. Types:
  `dissolve zoom_blur soft_wipe crosswarp warp_wipe dip_black` (subtle), `whip scaled_push flash static_wipe` (punchy), or
  any xfade-easing name (`transitions.py list --all`); optional `ease` (`cubic-bezier(...)`, `ease-in-out`, `back-out`) and
  `sfx` (punchy ones get a whoosh or impact by default, subtle ones none; `false` = silent). A take that ends on a `hold`
  gets no transition. Re-run `transitions.py reel` after any change to the takes or the plate (the build refuses stale
  windows). Hard cuts stay the default; a 0.2 s dissolve hides a jump cut; at most 2 punchy ones per reel.
- `look.shader`: Paper Shaders overlays on the speaker plate, above the video and under cards and captions: `"film-grain"`
  (boiling grain re-seeded 12x/s and a slow warm/cool drift, soft-light) or `"halftone"` (print dots in the shadows, the lit
  face stays clean), a list of them, or objects `{"look": "halftone", "opacity": 0.3}`; `"over": "all"` also covers cards and
  scenes (still under captions). Don't combine with `look.grain`. Runtime: `templates/vendor/hf-paper.js`, driven by the
  HyperFrames seek time (seek-safe); qa.py scans the render for one-frame flicker.
- `matte: true`: cut the speaker out for the `behind` beats with BiRefNet-portrait (`scripts/matte.py`: guided upsample,
  edge decontamination, temporal filter), only for the source seconds the behind beats show; every other frame is
  transparent. Cached as `assets/talk-matte.webm` + `.json` (a signature of the source and settings): it rebuilds itself
  when talk.mp4 or the behind beats change. Slow model: ~2.3-3 s per matted frame on an M3 Air (~4-5 min per behind word).
  Needs the optional venv (`bash $S/scripts/setup_matte.sh`, ~2.4 GB with weights); without it the build falls back to
  `hyperframes remove-background` (u2net, whole file, softer and jumpier edges; delete `assets/talk-matte.webm` after a
  re-cut on that path). Object form: `{stride: 2}` (model on every 2nd frame, ~2x faster), `{inferSize: "768x768"}`,
  `{all: true}` (whole source), `{model: "birefnet-hrsod"}`, `{engine: "hyperframes"}` (the old path).
- `look.cutout`: a reel-wide `selective` (speaker in colour, the world graded), `spotlight` or `bg-blur` baked into the plate
  by `scripts/cutout_fx.py` (BiRefNet lite, matte venv; same frames, timestamps and audio, the takes play the new plate):
  `"look": {"cutout": {"fx": "selective", "look": "film"}}` (+ that effect's options, `model` default `lite@512`, `batch` 4,
  `plate` default `assets/talk.<fx>.mp4`). The whole source goes through the model once (65 s of source: ~12 min on an M3 Air, alpha 6.6 + effect 4.9),
  so it is an explicit step: the build stops with the exact command when the plate is missing, older than the source or
  made with other options. With `look.film` too, the cutout plate is made from the film plate. transitions.py cuts its
  windows from it.
- `cover`: `{"headline": "THE FEED|MAKES US|*ANGRIER*", "at": 17.9, "colors": "#ff6a1a,#5a0a26"}` (`accent`, `stroke`,
  `coverScale`, `model`): `approval_sheet.py` cuts the speaker out of the frame at `at` (original seconds; omitted = the
  sharpest still frame of the first 4 s) onto a gradient with rays and the headline, writes `build/cover-9x16.jpg`
  (Reels cover) + `build/cover-16x9.jpg` (YouTube) and shows both on the sheet. Headline = words the speaker says;
  `*line*` gets the accent box.
- `cutout: {model: "lite@768"}`: the default model for every cutout beat.
- `captions.phrases: {"a call for reach": "Coffer Reach"}` fixes multi-word whisper errors.
- `captions.upper: true`: uppercase captions.
- `captions.style: "mini"`: small captions at a fixed height (`y`, default 1360; `splitY`, default 985, during split-screen B-roll), `font`, `size` (40), `weight`, `tracking`, `upper`, `stroke` (px dark outline, for serif captions over bright B-roll). For reference looks with tiny bottom captions. `captions.keywordStyle: "serif"`: highlight words become a glowing serif italic (cinematic).
- `captions.style` also takes six **caption templates** (`scripts/lib/caption-templates.mjs`; line widths come from the real
  font metrics in `scripts/lib/metrics.json`, so every seek has the same layout):
  - `hype`: 1-3 big uppercase words punch in one at a time; the spoken word sits in a coloured box, the keyword in a second colour (Montserrat 900).
  - `explosive`: the phrase waits dimmed; the spoken word grows into its slot, turns hot and shakes; a keyword fires a flash (Unbounded 800).
  - `line-focus`: a lyrics view: the current line is white, the next waits at 35 %, the stack slides up per line (Inter 700).
  - `neo-minimal`: small lowercase letter-spaced words fade up out of a blur; a hairline under the keyword (Inter 500).
  - `karaoke-fill`: the whole phrase is on screen and a colour fill sweeps through each word as it is spoken (Montserrat 800).
  - `highlighter`: words appear as spoken; one keyword per phrase gets a hand-drawn marker swipe (Inter 800).
  Options (all optional, read from reel.json's own `captions` block only, never from a style preset): `accent` (a hex, or
  `"brand"`), `accent2` (hype's keyword box), `keywords: ["..."]` (force them; `false` = none; default one per group by a
  length/importance score), `ai: true` (Gemini picks the keywords via `scripts/lib/ai-tag.mjs`, cached in
  `build/ai-tags.json`, needs GEMINI_API_KEY), `group` (max words per group), `font` / `size`, `y` (a fixed top; omit it to
  keep the face-aware placer). Every word span gets classes `kw`, `num`, `w-first`/`w-last`, `l-first`/`l-last` and
  `t-<tag>` from the AI tagger. Templates hide under full-screen scenes like the other styles.
- `upstream`: a cut list when `source` is itself a pre-cut of a longer raw take (`build/edl_map.json` as
  `[{a, b, start, end, note}]`, or a cut.json `{segments: [[a, b, text]...]}`). Only the workflow tools read it: the approval
  sheet shows raw times and the cuts inside the source, the render report maps problems to raw seconds (`--upstream FILE`
  does the same per run).
- `face`: the path to the face track, default `build/face.json` (run `scripts/face_track.py`). Without it, captions sit at a fixed height and the build warns.

New beat:

| type | fields | default sound | use for |
|---|---|---|---|
| `behind` | `text`, `at`, `to`, `size` (auto-fits the width), `y` (auto: head height), `color`, `front: true` (the same word OVER the speaker; needs no matte), `through: true` (the word slides right to left and passes through the speaker: behind the head left of the face centre, in front right of it; it crosses the face centre half-way, so set `at`/`to` symmetric around the spoken word) | impact (`through`: whoosh as it crosses) | the 2-4 biggest words, BEHIND the speaker (needs `matte`) |
| `cutout` | `fx` (`bg-swap` `bg-blur` `selective` `spotlight` `sticker` `neon` `clones` `pop`), the effect's options in camelCase (`bg`, `bg2`, `switch`, `radius`, `look`, `dim`, `hold`, `stickerScale`, `colors`, `offsets`, `frame`, `brk`, ... see references/cutout-fx.md), `release` (s to ease back into the take, default 0.3; sticker: auto-fitted `hold` instead, and `freeze` = the original second of the frame that becomes the sticker, default `at`: look at it, a blink or a half-word mouth makes a bad sticker), `model` (default `cutout.model`, else `lite@1024`) | none (set `sfx`) | one moment where the world around the speaker changes: a new place (bg-swap), focus on the words (bg-blur, spotlight, selective), a reaction (sticker, clones), a reveal (neon, pop). Must sit inside ONE take (the build stops otherwise). Pre-rendered by `scripts/cutout_fx.py` (matte venv), ~1 min per 2.5 s beat with lite on an M3 Air, cached in `assets/fx/`. At most 2 per reel |

```jsonc
{ "type": "cutout", "fx": "bg-swap",   "at": 16.00, "to": 18.50, "bg": "assets/broll/walk.png" },   // or a video / "#hex,#hex"
{ "type": "cutout", "fx": "bg-blur",   "at": 30.10, "to": 33.00, "radius": 26 },
{ "type": "cutout", "fx": "selective", "at": 41.00, "to": 43.20, "look": "bw" },                     // bw | noir | film
{ "type": "cutout", "fx": "spotlight", "at": 12.40, "to": 14.80, "dim": 0.3 },
{ "type": "cutout", "fx": "sticker",   "at": 16.50, "to": 19.80, "freeze": 16.62, "sfx": "pop" },    // freezes the frame at `freeze` (default `at`)
{ "type": "cutout", "fx": "neon",      "at": 52.00, "to": 55.00, "colors": "#38f6ff,#ff3df2" },
{ "type": "cutout", "fx": "clones",    "at": 8.00,  "to": 11.00, "offsets": [0, 0.4, 0.8] },
{ "type": "cutout", "fx": "pop",       "at": 22.00, "to": 25.00, "frame": "phone", "bg": "#ff7a18,#7a0b2e" },
{ "type": "behind", "text": "EVERYWHERE", "at": 19.10, "to": 20.98, "through": true }                       // crosses on 20.04
```

The cutout window is snapped to the frame grid: its first frame is exactly the source frame the take shows there and it
holds exactly the beat's frames (no head jump at the edges, no drift against the voice); it plays inside the camera
wrappers, so zooms and the look apply, and captions stay on top. A `behind` word overlapping a cutout would show the
original footage over the effect (the build warns), and so would a full-screen scene hide it.

## Motion layer (scripts/lib/motion.mjs)

Top-level fields:

- `brand`: `{accent, accentDark, ink, capSize, font, onAccent}`. `onAccent` is the text colour on accent pills, tags and highlights (default white; set a dark ink for light accents like lime or yellow). A 60/30/10 kit: one accent, a darker accent for text on light scenes, ink for dark text. `font: "Montserrat"` is bundled with Latin and Cyrillic.
- `zoom.base`: a constant punch-in on the speaker, for example `1.8` with `origin` at the face. `pushes[].sfx` puts a whoosh on a push-in.
- `captions.style: "editorial"`:
  - Lowercase lines of `group` words.
  - The spoken word resolves out of blur in bold white. The previous line relaxes to a light weight.
  - A block is two lines, or a tag pill plus two lines.
  - `tags: ["for Gen Z", "Gen Z"]` renders those phrases as tilted accent pills. List longer phrases first.
  - `highlight: ["fundamental"]` wipes an accent box behind the word.
  - `y` is the top of the block (default 1150).
- `music`: `{id | src, db: -20, fadeIn, fadeOut, start, duck}`. `duck: [{from, to, db: -8}]` dips the bed in those edit-time windows (speech in a music-led montage). The bed is set `db` below the -16 LUFS voice, from the track's own measured loudness. The library is `library/music/manifest.json`.

`scene` beats are full-screen graphic scenes over the continuing voice. Captions hide during a scene unless `captions: true`.

- **Shader backgrounds:** any scene's `bg` may be a Paper Shaders look instead of a colour: `{"look": "warm-grain"}`,
  `mesh-calm` (pastel, dark ink), `ink-warp` (blue marbling), `god-rays`, `dither-retro`, `fluted-self` (ribbed glass over a
  still of the speaker, the flutes slide), or a raw shader `{"shader": "warp", "preset": "Passion", "params": {...},
  "speed": 1.2}` (any of the 30 in `templates/vendor/paper-shaders.json`, Paper's own prop names). Busy looks put a soft
  scrim behind the word. With a dark look, give `card` lines `color: "#fff"`.
- **Transitions:** `in` is `blur` (default), `expand`, `wipe`, `glitch` or `cut`. A style can set `scenes.default_in`. `out` is `blur` (default) or `cut`. A scene that ends where an expand or wipe scene starts stays underneath for 0.45 s.
- **Sound:** default sounds are listed per kind below; expand and wipe also get a whoosh.

| kind | fields | what it looks like |
|---|---|---|
| `card` | `bg`, `y`, `lines:[{text, at, size, color}]`, `pill:{text, at, size, gap}`, `cursor:{clickAt, dx, dy}` | Centred text plus a tilted accent pill; a cursor flies in and clicks it (ring, press). Sounds: pop, then click |
| `stats` | `bg:"accent"`, `badges:[{value, sub, at, label:"follow **bold part**", labelAt}]`, `centerY`, `gap` | Glass ring badges land big (whoosh). On `labelAt` they shrink into a row with the label typed beside them, and earlier rows re-centre |
| `fly3d` | `bg`, `items:[{text, sub, at, x, y, z, size}]`, `cam:{from, to}`, `focus`, `ease` | Words in 3D space; a camera dolly moves through them, and blur and grey level follow the distance to focus. Seek-safe painter. Sounds: riser, whoosh per word |
| `image` | `src`, `zoom:[1, 1.1]`, `grade`, `captions: true` | A full-bleed still with a slow push. AI B-roll comes from `scripts/broll_gen.py` |
| `ui` | `title`, `label`, `prompt:{text, at, cps}`, `lines:[{text, at}]`, `y` | Dark app/terminal window: the prompt types in (typing sound), result lines tick in with checks. Product launches |
| `device` | `src` (an image) or `lines:[{text, at, me}]`, `label`, `y` | A phone frame rises and floats; an image or a mini chat whose bubbles pop in |
| `kinetic` | `text` (`*keyword*`, `_filler_`), `bg`, `size`, `zoom`, `pullback`, `pip`, `pipX`, `pipY` | Full-screen word-by-word type aligned to the spoken words; a camera glides from word to word, then pulls back. `pip: true` shrinks the speaker into a round window |
| `word` | `text` (1-3 words), `at`, `size`, `ink`, `y`, `bg` (usually a shader look) | The words resolve from blur, centred on the scene background (Clean OS grammar), e.g. `{"type": "scene", "kind": "word", "at": 41.34, "to": 42.85, "text": "on repeat", "bg": {"look": "ink-warp"}}` |
| `sentence` | `bg`, `lines:["...", "..."]`, `hero:{text, at, size, color}`, `sub:{text, at, cross, crossAt}` | Words ink in as they are spoken (matched to the transcript), then shrink up while a big accent hero lands (impact). The `cross` word gets a drawn X |

## Stan style: split-screen tool tutorials (scripts/lib/stan.mjs, recipes/stan-style)

Six beat types and one caption style for a seated talking head that explains a tool with screen recordings. Measured on
the reference (README in the recipe has the anatomy, an annotated example and the pipeline). Icons everywhere are
`{emoji | icon | src, label, size, bg, invert}` (a Fluent emoji slug from library/emoji, a simple-icons slug fetched at
build time, or the user's own image; brand logos are never bundled) or a bare emoji slug.

| type | fields | default sound | what it does |
|---|---|---|---|
| `panel` | `src` (screen recording, 1080p+), `in`, `to`, `behind` (default true), `h` (band px, 768), `gap` (eyes under the band, 80), `pos` (object-position), `zoom` ([from, to]), `clicks` (recording seconds; default the `clicks` of `<src>.json`; `false` = none), `clickSfx` | click-1 per click | the recording fills the top band (cover-cropped) BEHIND the speaker: the speaker's BiRefNet cut-out (scripts/matte.py, only the panel seconds, cached in assets/talk-matte.webm; needs the matte venv) is drawn over it in a second copy of the camera wrappers (pipM > baseM > snapM > pushM > punchM; every camera tween drives both); it pops in 1.05 -> 1 and out 1 -> 0.95; the speaker moves down only as far as the eyes need to sit `gap` px under the band (face.json + the camera zoom), once per run of adjacent panels; the next panel pops in over the previous one (it stays up 0.2 s longer) with no speaker move |
| `hook` | `title` (1-2 lines), `icons` (a row, or `[[above], [below]]`), `iconSize` (150), `size` (62), `y` (250) | pop (none at frame 0) | icon rows around a black-on-white strip title over the speaker; it moves up off the eyes and warns when it cannot |
| `diagram` | `nodes: [{id, x, y, emoji\|icon\|src\|text, label, size, at}]`, `links: [{from, to, at, dur, bend, dot, width}]`, `bg`, `ink`, `sfx` | whoosh in, marker-scribble per line | white full-screen frame entered by a zoom-blur from the speaker; icons pop, curved black lines draw on (stroke-dashoffset on the timeline), a ringed dot at a line's end; captions turn black, one word at a time, at y 1378 |
| `step` | `n`, `title`, `icons`, `label` ("Step" / "Шаг"), `size` (46), `iconSize` (88) | pop | «[Step n]» + title + icons stacked just above the chest caption, under the chin; both move down when the face sits low (warns when it still covers the chin) |
| `cta` | `word`, `text` (`{word}` template; default «Comment "{word}" for the prompt» / «Напиши "{word}" в комментариях»), `logo`, `size` | pop | the comment-keyword label + logo in the step's place |
| `aside` | `text`, `y`, `size` (66), `italic` | none | «*text*» upright above the head (a spoken joke); moves up off the eyes |

`captions.style: "chest"`: small white lowercase phrases (`maxWords` 6, `maxChars` 30, break on sentence ends, pauses
> 0.45 s and commas after 3 words; no punctuation, no box, soft shadow) centred at `y` 1305 with `size` 38 that CUT in on
their first word. `single: [[a, b]]` (original seconds): one bigger word at a time (`wordSize` 66) at the same height;
every diagram is single and black (`inkY` 1378). `top: [[a, b]]` and `emphasis: ["word", {word, at}]`: one word at a time
at the forehead (`topY` 557, `topSize` 64); under a panel they stay at the chest. `strobe: ["word"]`: a few quick blinks
(not in the reference). `lower: false` keeps the case. Every caption is logged to build/caption_layout.json (modes
`chest-phrase`, `chest-single`, `chest-top`, `-ink`) so render_report.py checks the safe area; captions move under the chin
when the speaker sits low (the build warns).

## Kinetic type: `textfx` beats (scripts/lib/kinetic.mjs)

Kinetic type over the footage, or on a full-screen ground with `bg`. Words land on their spoken onsets (matched to the
transcript; unspoken text falls back to a stagger). Captions hide during the beat unless `captions: true`. Without `y`
the face-aware placer puts the block below the chin. A style can set defaults per kind in `textfx: { <kind>: {...} }`.
Give every block a `to`: the default 2.5 s is short, and the build warns when text holds less than max(1 s, 0.3 s per word)
after it settles. One or two per minute, on the line that carries the idea.

| kind | fields | what it looks like |
|---|---|---|
| `hook` | `key`, `word`, `sub`, `layout:"row"\|"stack"`, `keySize`, `wordSize`, `zoomFrom`, `punchAt`, `punch`, `settle`, `footage:false` | Frame 0 already shows a giant key word cropped by the frame; it pulls back into a claim lockup while the footage (punched in at frame 0) settles, then punches again on the spoken word. For the first 1.5-3 s. Sounds: whoosh, impact |
| `drum` | `items:[..]`, `lead`, `tail`, `loop:{at \| word}`, `size`, `slots` | Words on a 3D cylinder; it rolls in and turns to land each word as it is spoken; `loop` spins back to the first word. Sounds: tick per step, whoosh on the loop |
| `scramble` | `lines:[..]` or `text`, `lead`, `upper`, `shake`, `shakeAt`, `font` | Glyphs from the text's own script cycle and lock left to right on the spoken word; the line never reflows. Sounds: typing, impact on the lock |
| `flipstack` | `items:[..]`, `card:{bg, ink, radius}`, `lastAccent`, `shakeAt`, `flat` | One card per word flips down onto a messy pile on its spoken word. Sounds: pop per card, whoosh on the shake |
| `headline` | `lines:["...", "*marked words*"]`, `mark:{style: under\|marker\|box\|strike, at}`, `swap:{text, at, strikeAt}` | Words rise from masks; a boiling brush mark draws under the marked words. `swap` = "not X -> Y". Sounds: whoosh on the mark |
| `spring` | `text`, `upper`, `sub:{text}`, `from: drop\|rise`, `font` | Letters drop on a squash-and-stretch spring: section titles ("PART TWO"). Sound: whoosh |

Common fields: `y` (block centre px), `size`, `weight`, `font` (any bundled family, default Montserrat), `color`, `accent`
(default `brand.accent`), `bg` (colour, `"accent"` or a CSS gradient: full-screen ground), `pocket: false` (no dark pocket
behind the type over footage), `exit` (seconds, default 0.35). Word lists take strings or `{text, at}` (original seconds).
All knobs with their defaults:

| kind | fields (defaults) |
|---|---|
| `hook` | `key` ("4"), `word` (uppercased unless `upper:false`), `sub`, `layout` (`stack`/`row`), `keySize` 270, `wordSize` 118, `subSize` 54, `keyColor` ("accent"), `zoomFrom` 2.7 (type scale at frame 0), `startY` 880, `pullAt` (t0+0.14), `pullDur` 0.6, `punchAt` (the spoken `word`), `footFrom` 1.24, `punch` 1.13, `settle` 1.07, `footage:false` |
| `drum` | `items`, `lead`, `tail`, `loop: {at \| word, dur 0.95}`, `size` 120, `slots` (max(6, 2N)), `spacing` 1.12, `rows` 2.9, `turn` 0.38, `rollIn` 0.55, `drumColor` ("accent"), `leadSize`/`tailSize` 60 |
| `scramble` | `lines` or `text`, `lead`, `upper`, `start`, `preroll` 0.45, `lockLead` 0.55, `lockTail` 0.22, `rate` 18 glyph steps/s, `jitter` (0.08 x size px), `symbols` (true), `shake` (true) / `shakeAt` / `shakeAmp` 12, `tracking` |
| `flipstack` | `items`, `size` 76, `card: {bg "#fff", ink "#111", radius 30, pad 46, minW 600, h}`, `offset` (0.7 x card h), `scaleStep` 0.06, `dimStep` 0.22, `mess` 3.2 deg, `lastAccent`, `shakeAt`, `flat`, `freq` 1.25, `zeta` 0.42, `early` 0.12 |
| `headline` | `lines` (string or `{text, size, weight, color}`; `*...*` marks words), `mark: {style, at, dur 0.5}`, `swap: {text, at, strikeAt, outAt, gap 0.3, size, dim 0.6}`, `boil: false` |
| `spring` | `text`, `upper`, `sub: {text, size 54, weight, color}`, `keyColor`, `from` (`drop`/`rise`), `stagger` 0.045, `tilt` 16, `freq` [1.6, 2.1, 2.8], `zeta` 1/3, `start`, `early` 0.1 |

The `hook` punches the `#punch` wrapper around the footage (inside `#push`, so it multiplies
with snaps and pushes, and the person matte moves with it).

```json
{ "type": "textfx", "kind": "drum", "at": 39.0, "to": 43.8, "lead": "replay",
  "items": [{ "text": "the talk", "at": 39.38 }, "rethink", "reply"], "loop": { "at": 41.34 }, "tail": "and round again" }
```

Helpers:

- `scripts/autocut.py talk.mp4 --noise -30` prints `takes` for a single clean take. It cuts pauses from the audio, because whisper's word times hide them.
- Scene times may sit up to 1.2 s inside a removed pause; they snap to the next kept moment.
- Each whisper word belongs to the one take it overlaps most, so boundary words are never duplicated.

## What the build enforces (warnings, printed after the SFX table)

- the same meme sound twice in one reel
- meme sounds < 8 s apart; > 3.5 meme sounds per minute
- > 14 whoosh/impact/meme hits per minute (a layered whoosh+impact counts once)
- a meme sound landing on speech (put it in a pause: extend the take's `b` to keep the air, or place it on the end of the punchline word)
- the reaction slot double-booked
- an em dash in on-screen text
- a `textfx` block whose text holds less than max(1 s, 0.3 s per word) after it settles
- a `textfx` block with no room beside the face (give it `bg` or a `y`)
