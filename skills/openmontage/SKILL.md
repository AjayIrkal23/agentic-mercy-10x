---
name: openmontage
description: 'OpenMontage agentic video production system (pinned local checkout): pipeline-driven edit, compose and review of finished videos from your own clips, with Remotion and ffmpeg renders, captions, titles, music beds and QA.'
when_to_use: Use when a video has to be assembled, composed, edited or reviewed end to end (a film, explainer, montage, reel or ad built from generated takes), when the user names OpenMontage, Remotion or a montage pipeline, or when ffmpeg alone would mean hand-writing a whole edit. Footage itself still comes from OpenArt or Higgsfield.
metadata:
  schema: 1
  category: media
  platforms:
  - linux
  - darwin
  triggers:
    keywords:
    - openmontage
    - open montage
    - montage
    - remotion
    - video pipeline
    - compose the video
    - assemble the film
    - explainer video
    - title card
    - lower third
---

# OpenMontage

OpenMontage (OpenMontageInc/OpenMontage, AGPL-3.0) is an app the agent works inside: YAML pipelines
(`pipeline_defs/`), stage-director skills (`skills/pipelines/<pipeline>/<stage>-director.md`), a Python tool
registry (`tools/`) and Remotion / HyperFrames / ffmpeg renderers. It is not vendored into `~/.claude`. A
pinned checkout lives outside it:

```bash
python3 ~/.claude/scripts/openmontage_engine.py --path    # where it is (default ~/.local/share/openmontage)
python3 ~/.claude/scripts/openmontage_engine.py --check   # 0 = checkout at the pin and `make setup` done
python3 ~/.claude/scripts/openmontage_engine.py           # install or repair it (one-shot, a few minutes)
```

The installer and the daily self-heal run the last command on their own. When `--check` fails mid-task,
run it yourself before you start; never ask the user to.

## How to work in it

1. `cd` into the checkout and read its `AGENT_GUIDE.md`: its routing rules (onboarding, reference analysis,
   Rule Zero "every video goes through a pipeline", preflight, the stage directors, the append-only
   `decision_log`) apply inside the checkout, except where the local rules below say otherwise.
2. Use its interpreter: `<checkout>/.venv/bin/python` (`make preflight` lists what works on this machine).
3. Work happens in `<checkout>/projects/<id>/` (gitignored there). Copy the deliverables into the user's own
   project folder at the end (for a film repo: that film's `build/`), and say where they are.

## Local rules (override AGENT_GUIDE.md and its bundled skills)

- **No servers, studios or browsers.** Never run `python -m backlot open`, `npx hyperframes preview`,
  `npx remotion studio`, `npm start`, `python -m http.server` or anything that opens a browser. Renders are
  one-shot commands (`npx remotion render …`, the HyperFrames render, `make preflight`, `make demo`).
  Skip the Backlot step of pipeline init and carry on.
- **Remotion by default.** `make setup` installs it. Use HyperFrames only when the user
  asks; then do not offer the choice again.
- **No API keys in chat.** Never run its `setup-api-key` skill, never print "paste your key", never write
  keys with `echo >>`. Keys live in `<checkout>/.env`, which the user fills. A provider without a key is
  simply unavailable: use the zero-key path (ffmpeg, Remotion, local Piper TTS, local faster-whisper).
- **Footage and pictures come from the project's own generator.** OpenMontage has no OpenArt tool and
  reaches Higgsfield only through an API key. Generate takes and stills with the OpenArt MCP or the
  Higgsfield skills, as the project's CLAUDE.md says, and hand the files to OpenMontage as inputs. Never
  pull stock (Pexels, Pixabay, Unsplash, Mixkit, Coverr, archive.org, `pixabay_music`) unless the user asks.
- **Paid calls.** Before any paid call, name the tool, provider, model and expected cost, as its guide
  asks; a project's credit rules (one option per take, drafts first) win.
- **Files through Write / Edit,** never shell redirection (its bundled ffmpeg skill writes concat lists
  with `echo >`; use the Write tool for those).
- Its bundled skills (`.claude/skills`, `.agents/skills`) are references inside the checkout; they are not
  installed into `~/.claude` (several duplicate local skills). Never copy OpenMontage source into another
  repo (AGPL).
- Never `git pull`, reset or edit tracked files in the checkout; `openmontage_engine.py` owns the pin.

## Where it fits

| Job | Tool |
|---|---|
| Generate a take or still | OpenArt MCP / Higgsfield skills (per the project) |
| Probe, cut, join, sync, loudness, captions, delivery checks | `ffmpeg-skill` |
| Talking-head take picking, pause trimming, word-timed captions, SFX levels | `ghost-editor` |
| Whole-video assembly: pipeline, titles, lower thirds, music bed, compose, review | `openmontage` |

The project's own rules (its CLAUDE.md: frame size, logo bug, caption limits, loudness, delivery) win over
OpenMontage defaults.
