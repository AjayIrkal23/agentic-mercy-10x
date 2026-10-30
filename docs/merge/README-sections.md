> APPLIED 2026-10 by the integrate package; history only, not instructions.

# README patch note (package doctrine-tokens; integrate applies)

Three passages of `README.md` change. Everything else stays.

## 1. Models and teams

Replace the passage that starts with `Three layers, one truth (\`hooks/model-policy.json\`)`
(inside `<summary>Models and teams</summary>`, up to the line before `Per-project mode:`) with:

```markdown
The plan tier (`pro` / `max5` / `max20` / `api`) is detected at session start from the login
and picks the models; the agent's role picks the row. Haiku 5.5 is the default worker, Sonnet
executes on max5/max20, Opus judges on max20 only. Your `/model`, a per-turn "use opus" and a
per-project pin always win. Rules: [`rules/04-model-routing.md`](rules/04-model-routing.md);
full matrix and state files: [`docs/MODEL-ROUTING.md`](docs/MODEL-ROUTING.md).
```

and the models badge on line 11 with:

```markdown
![Models](https://img.shields.io/badge/models-Haiku_5.5_·_Sonnet_5.5_·_Opus_5.5-D97757?style=flat-square)
```

(URL-encode the middle dots as `%C2%B7` like the other badges.)

## 2. `/invoke` paragraph

Replace the passage that starts with `Opus judges spec, plan, debug, design and review;`
(the sentence ends `after a failed attempt.`) with:

```markdown
Models follow the plan tier (`rules/04-model-routing.md`); large tasks run as saved
workflows under `workflows/`.
```

## 3. What is on disk

Replace the passage that starts with `| Thing | Count | Recompute with |` (the whole table)
with the Markdown that `python3 scripts/measure_context_cost.py --counts` prints, plus one row:

```markdown
| Always-on context | <doctrine chars> chars doctrine | `python3 scripts/measure_context_cost.py` |
```

(`<doctrine chars>` = the number on the first line of `python3 scripts/measure_context_cost.py`
after the drafts are applied.) Under the table add the sentence:

```markdown
Measured context cost before and after the 2026-10 merge: `docs/TOKEN-BUDGET.md`.
```
