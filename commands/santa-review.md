---
description: Santa Method — adversarial BREAKER + SIMPLIFIER + VERIFIER review of the session diff (or $ARGUMENTS). Catches real bugs before they ship.
argument-hint: "[optional target: files, a commit range, or a description; defaults to the current session diff]"
---

Run the **Santa Method** adversarial code review.

Dispatch the **santa-reviewer** agent via the Agent tool. Because adversarial correctness review is where subtle bugs are caught, run it on Opus (the original Santa reviews ran on Opus by design):

- `description`: `"[opus] Santa Method adversarial review — BREAKER + SIMPLIFIER + VERIFIER"`
- `subagent_type`: `"santa-reviewer"`
- `model`: `"opus"`
- `prompt`: Tell it to review **$ARGUMENTS** if that is non-empty; otherwise review **this session's diff** (`git diff` working tree + staged, plus anything written this session). Instruct it to read the ACTUAL changed files (jcodemunch / ctx_read), run all three lenses, self-verify every HIGH/MED finding, write `SANTA-REVIEW.md`, and return only CONFIRMED must-fix findings (file:line + minimal fix) plus a PASS / CHANGES-REQUESTED verdict.

After the agent returns:
1. Relay its verdict and the confirmed findings verbatim (they are the point of this command).
2. If the verdict is CHANGES REQUESTED, offer to fix each confirmed finding (do not auto-edit — the reviewer never fixes; you decide with the user).
3. Do not soften or pad the report. No confirmed bugs → say so plainly.
