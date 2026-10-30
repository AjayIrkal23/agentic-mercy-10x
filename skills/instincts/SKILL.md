---
name: instincts
description: 'Shows, exports and imports the per-project habits the workbench learned from tool use (instincts), and runs the ollama evolve step on demand.'
when_to_use: Use when the user asks what the workbench has learned about a project, wants to export or import instincts, asks why a session-start "instinct" line appeared, or wants the learning step run now.
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 319
  triggers:
    keywords:
    - instincts
    - instinct status
    - learned habits
    - what have you learned
    - export instincts
    - import instincts
    - continuous learning
    - evolve instincts
    paths: []
    intents: []
---

# Instincts

An instinct is a habit of this project learned from the observation log
(`state/learning/<repo_key>/observations.jsonl`). Scored 0.3 to 0.95, it loses 0.05 per
idle week and shows at session start when it reaches 0.7 (at most 3 lines).

## Commands

Run from the project dir:

- `python3 ~/.claude/hooks/tools/instincts.py status` (`--json` for machine output)
- `python3 ~/.claude/hooks/tools/instincts.py export --min 0.7` (`--yaml` for the ECC format,
  `--global` for the promoted set, `--output FILE`)
- `python3 ~/.claude/hooks/tools/instincts.py import <file|https-url>` (`--dry-run` first;
  `--global`; https only, public hosts only, 1 MB cap, duplicates merge by text)
- `python3 ~/.claude/hooks/tools/instincts.py evolve --once` (the daily self-heal runs it;
  `DEFERRED` means the ollama named by `OLLAMA_HOST` is down and the step retries tomorrow)

## Rules

- The only model is the ollama at `OLLAMA_HOST`; never spend Claude quota or an API key on this.
- Tell the user what the step printed, in one line.
- To drop a wrong instinct, remove its row from `state/learning/instincts/<repo_key>.jsonl`
  with `Edit` and name the file in the reply (an import keeps the max confidence, so it
  cannot lower one).
- Full reference: `docs/LEARNING.md`.
