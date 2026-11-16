# Third-party code, data and weights

One file per pack. Every piece of code copied or ported is MIT, Apache-2.0 or BSD; GPL/AGPL projects supplied ideas only.
Model weights are downloaded at setup into `~/.cache`, never committed.

| pack | file | in short |
|---|---|---|
| caption templates | [captions.md](captions.md) | own code; ideas from pycaps, remotion-captions-kit (MIT), HyperFrames components (Apache-2.0); OFL font metrics |
| kinetic type | [kinetic.md](kinetic.md) | own code; techniques from hyperframes-launches (Apache-2.0), claude-motion, bang-motion, iart-ai, brag (MIT) |
| shader looks + emoji | [shaders.md](shaders.md) | Paper Shaders bundled (Apache-2.0, LICENSE/NOTICE in `templates/vendor`); Fluent Emoji (MIT) fetched into `library/emoji` |
| transitions + film looks | [looks.md](looks.md) | xfade-easing expression files (MIT) in `scripts/vendor/xfade-easing`; LUTs generated with Spectral Film LUT (MIT) |
| person matte + cutout effects | [matte.md](matte.md) | BiRefNet-portrait / BiRefNet_lite and the other ZhengPeng7 weights (MIT) via rembg/transformers in an optional venv; own effect code; bria refused |
| audio QA | [audioqa.md](audioqa.md) | ClearerVoice (Apache-2.0), silero-vad (MIT) |
| workflow | [workflow.md](workflow.md) | own code; ideas only (OpenMontage is AGPL) |
| fonts | [fonts.md](fonts.md) | 8 OFL families; Playfair Display (Reserved Font Name) ships unmodified |
| models | [models.md](models.md) | MediaPipe Face Landmarker bundled (Apache-2.0); YuNet (MIT) and SFace (Apache-2.0) downloaded |
| sound effects + music | [audio.md](audio.md) | Mixkit, downloaded on your machine, never shipped; their licence limits |
| runtime tools + services | [runtime.md](runtime.md) | HyperFrames, GSAP, whisper, Gemini, ElevenLabs, macOS Vision |
| Seoul list recipe | `recipes/seoul-list/` | own code; Inter Tight + Playfair Display woff2 (SIL OFL 1.1, `templates/fonts/LICENSE-*.txt`; Playfair ships unmodified, see [fonts.md](fonts.md)); Fluent emoji (MIT); `send-swoosh` = Mixkit #166 (Mixkit free SFX licence); no brand logos or the reference's cartoon gloves are bundled |


Older: `references/UPSTREAM-LICENSE` (take-selection, mariagorskikh/talking-head-reel, MIT).
