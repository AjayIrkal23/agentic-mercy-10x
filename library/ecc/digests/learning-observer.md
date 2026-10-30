---
name: ecc-digest-learning-observer
description: ECC's continuous-learning observer (tool-call capture, a background model that writes instinct files, a session evaluator and activity tracker); the reusable idea is capture with layered skip rules and a scrubber, then offline distillation into confidence-tiered instincts.
---
<!-- ecc-digest:learning-observer@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Learning observer

## What it is
ECC's learning loop has a capture side and an analysis side. `scripts/hooks/observe-runner.js` finds a bash and runs the observe script on every tool call (pre and post, asynchronously, standard and strict profiles). Each record holds the timestamp, event, tool, session, project and the truncated input or output, passed through one regex scrubber for keys, tokens and passwords, and lands in a per-project JSONL file under `<learning-state-dir>`, rotated at 10 MB. Capture skips subagents, the minimal profile, an explicit opt-out variable, observer sessions themselves and a `disabled` marker file. The observer, off by default, wakes on a timer, takes the last 500 observations and runs a small model headless with only Read and Write tools to write instinct files (YAML frontmatter with trigger, confidence, domain and scope, then Action and Evidence sections). `scripts/lib/observer-sessions.js` holds the leases that keep the observer alive only while a session is open, and `scripts/lib/llm-summary.js` produces short summaries. `scripts/hooks/evaluate-session.js` is the deprecated v1 evaluator: it counts user messages and logs a line, extracting nothing. `scripts/hooks/session-activity-tracker.js` appends a sanitized per-tool row with git diff previews for ECC 2.0.

## The reusable idea
Capture cheaply and analyse offline. The capture hook must never slow a tool call, so it is asynchronous, truncates every field and scrubs secrets before writing; layered skip rules keep it out of subagents and out of its own analysis runs, which avoids feedback loops. Distillation then turns repeated evidence into rules with confidence tied to frequency (per the study note: three to five occurrences give 0.5, six to ten give 0.7, eleven or more give 0.85, capped). Untrusted observation text is labelled as data in the analysis prompt. The study note also records a gap worth avoiding: the documented confidence updates (+0.05 per confirmation, decay per week) are implemented nowhere.

## Why not adopted
The workbench's own learning package covers this with `hooks/tools/instincts.py` and its state under `<learning-state-dir>`, wired through `hooks/dispatch.py`, plus the skill-effectiveness and router-weight tools. A nested headless session on this machine would also run the user's full hook chain. The capture rules and the confidence tiers informed that package; the Node and bash runtime is not taken.

## Upstream paths
- `scripts/hooks/evaluate-session.js`
- `scripts/hooks/observe-runner.js`
- `scripts/hooks/session-activity-tracker.js`
- `scripts/lib/llm-summary.js`
- `scripts/lib/observer-sessions.js`
