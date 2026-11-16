# Third-party sources: workflow tools (approval sheet, render report, taste, save_style)

No code was copied from any of these projects; every file is our own code. The table lists where the ideas came from.

| repo | licence | what we took (ideas only) | where it went |
|---|---|---|---|
| https://github.com/calesthio/OpenMontage | AGPL-3.0 | Ideas only (AGPL): the storyboard as a hard approval gate before the expensive step; a board built from files the pipeline already writes; a post-render self-review that must pass before the video is shown | `scripts/approval_sheet.py`, `scripts/render_report.py` |
| https://github.com/veedstudio/open-edit | Apache-2.0 | The render, look at frames, fix, re-render loop; re-rendering only what changed | the 3-round fix loop in SKILL.md |
| https://github.com/browser-use/video-use | MIT | Self-eval at every cut boundary and at the first and last 2 s, capped at 3 passes before the user is told; an approved plan before execution; a per-project memory file | cut and hook frames in `approval_sheet.py`, the `hook` check and the 3-round cap in `render_report.py` |
| https://github.com/mocchalera/video-os-v2 | MIT | A `render-report.json` that reconciles planned and actual duration and gaps, and a QA, fix, recompile loop of at most 3 iterations | `render_report.py` (report shape, round counter) |
| https://github.com/FireRedTeam/FireRed-OpenStoryline | Apache-2.0 | A "save this edit as a style" step that distils a finished timeline into a reusable profile | `scripts/save_style.py` |
| https://github.com/Q00/ReelBrain | no licence declared | Ideas only: feedback kept as explicit preference records with provenance, a prior and not evidence, editable or deletable by the creator | `taste.json`, `scripts/taste.py`, `scripts/lib/taste.mjs` |
| Kinocut | Apache-2.0 | blackdetect, loudness and an opening-seconds check as a release floor | the `black` and `hook` checks |
| https://github.com/notivn/AIEV | MIT | A fast draft render for approval, then the final render | `approval_sheet.py --frames draft` |

Run-time tools, not bundled: ffmpeg/ffprobe (blackdetect, freezedetect, silencedetect, ebur128), the HyperFrames CLI
(`snapshot`, `lint`, `render`), numpy.

`taste.json` in the private repo is seeded from the user's own feedback (memory notes, ~/.claude/CLAUDE.md) and the skill's
"Rules that came from getting it wrong"; each rule says which (`from: user | skill`). The public edition ships it empty.
