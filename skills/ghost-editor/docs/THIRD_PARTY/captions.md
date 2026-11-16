# Third-party sources: caption templates

Files: `scripts/lib/caption-templates.mjs`, `scripts/lib/ai-tag.mjs`, `scripts/lib/metrics.json`, `scripts/font_metrics.py`.

No third-party code was copied. Everything was written for this skill; these sources were studied for ideas only:

| source | licence | what we took (ideas only) |
|---|---|---|
| pycaps, https://github.com/francozanardi/pycaps (v0.3.0) | MIT | The template names and looks `hype`, `explosive`, `line-focus`, `neo-minimal`. A template as style + splitter + animations + tagger rules. Per-word narration states. Structure tags (first/last word in a line or segment) and semantic tags exposed as CSS classes. The `limit_by_chars` splitter with "don't end a segment on a short word". |
| remotion-captions-kit, https://github.com/Fats403/remotion-captions-kit | MIT | Karaoke fill as a `clip-path: inset()` sweep driven by word progress. Pagination: break on silence, sentence ends and a character cap; avoid one-word orphans. |
| HyperFrames registry components `caption-highlight`, `caption-pill-karaoke`, `inline-highlight` (hyperframes 0.8.146) | Apache-2.0 | How a registry caption stays seek-safe: one group per time window, per-word background sweeps. |
| HyperFrames skill rule `css-marker-patterns.md` | Apache-2.0 | Highlighter-marker mechanics (an accent box sweeping behind the text); we use a hand-drawn SVG band revealed by `clip-path` plus a dark-ink text layer. |
| captioncat, https://github.com/ItisShikhar/captioncat | MIT | Skimmed for preset ideas; nothing used. |

Data: `metrics.json` holds glyph advance widths measured from the bundled OFL fonts (Inter, Montserrat, Unbounded, Oswald,
JetBrains Mono, Geist; SIL OFL 1.1) by `scripts/font_metrics.py` with fontTools (MIT) + brotli (MIT) in the optional venv
`~/.venvs/ghost-captions` (`scripts/setup_captions.sh`). Numbers only, no glyph outlines.

Service: `ai-tag.mjs` calls Google Gemini (`gemini-2.5-flash`) with `GEMINI_API_KEY`; optional, the default keyword picker is
an offline heuristic.
