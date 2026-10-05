"""invoke_templates.py — prose for the /invoke skill family, rendered by
hooks/gen-invoke-skills.py. Routing facts (acts, agents, artifacts, models, closers,
surface_routing) come from config; this module only holds the wording around them.

RUN_JSON is the ONE run.json schema (audit 2026-10-05 E-02): /invoke, the single-act
skills and the team playbook (agents/team-lead.md, which quotes it verbatim) all write
it; teammate-idle-gate and invoke-status read it. expected_artifacts values are file
names inside the run folder.
"""
from __future__ import annotations

RUN_JSON = ('{"task": "<TASK>", "slug": "<SLUG>", "run": ".claude/runs/<ts>-<slug>", '
            '"started_utc": "<ISO-8601 UTC>", "start_sha": "<git rev-parse HEAD, or null>", '
            '"acts": ["<act>"], "done": [], "models": {"<act>": "<model>"}, "team": false, '
            '"expected_artifacts": {"<subagent_type or teammate name>": "<ARTIFACT>.md"}}')

# mixed-surface impl: subagent_type -> (teammate name, artifact)
TEAMMATES = {
    "backend-implementor-specialist": ("impl-be", "IMPL-REPORT-BE.md"),
    "frontend-implementor-specialist": ("impl-fe", "IMPL-REPORT-FE.md"),
    "integrator-specialist": ("integrator", "INTEGRATION-REPORT.md"),
}

# Higgsfield is pushed only while usable: when the router (or a failed call) says it needs a
# one-time login, the model asks once and authenticates itself; assets stay pending meanwhile.
HIGGS_LOGIN = ("If Higgsfield needs its one-time login (the router says so once per session), ask the user "
               "once, batched with any other login, and use `mcp__higgsfield__authenticate`; until then "
               "report the assets as pending.")

NEW_RUN = 'RUN="$(git rev-parse --show-toplevel)/.claude/runs/$(date -u +%Y%m%dT%H%M)-$SLUG"'

ACT_NOTES = {
    "impl": ("This form always dispatches `implementation-engineer` (general/infra). For frontend- or "
             "backend-specific work prefer `/invoke impl -- <task>`, which surface-routes to the FE/BE "
             "specialists. A plan artifact in the run folder is the input; without one the implementor "
             "writes a mini-plan first."),
    "design": (f"Every raster/video/3D/audio asset comes from Higgsfield (`higgsfield-generate`). {HIGGS_LOGIN} "
               "Placeholder boxes, stock URLs and emoji icons are never acceptable."),
    "review": ("Review the target above, or this session's diff when it is empty: the agent reads the ACTUAL "
               "changed files, runs BREAKER + SIMPLIFIER + VERIFIER, returns only CONFIRMED findings "
               "(`file:line` + minimal fix) and a PASS / CHANGES REQUESTED verdict, and never edits code."),
    "debug": ("The root cause is demonstrated with evidence BEFORE a fix is proposed; the killed hypotheses "
              "are listed so nobody re-treads them."),
    "clean": ("Removes only what THIS session's diff orphaned (each verified with `check_delete_safe`); "
              "pre-existing dead code is reported, never touched."),
    "refactor": ("Runs in the main working tree: subagents never commit, so a worktree would hold nothing "
                 "to merge back, and the closers review the main tree's diff."),
}


def impl_rule(model: str, routing: dict) -> str:
    """The `impl` act rule; agent names and the mixed order come from surface_routing."""
    mixed = [a for a in routing.get("mixed") or [] if a in TEAMMATES]
    spawns = ", ".join(f'`Agent(name="{TEAMMATES[a][0]}", subagent_type="{a}", ...)`' for a in mixed)
    arts = ", ".join(f'`"{TEAMMATES[a][0]}": "{TEAMMATES[a][1]}"`' for a in mixed)
    seq = " → ".join(f"`{a}`" for a in mixed)
    return (
        f"- **`impl`** [{model}] surface-routes from the BRIEF: frontend → `{routing.get('frontend')}`; "
        f"backend → `{routing.get('backend')}` (contract-first, publishes `IMPL-REPORT-BE.md ## CONTRACT`); "
        f"general / infra → `{routing.get('general')}`.\n"
        "  Mixed (FE + BE) → you (the main session) are the team lead. A subagent cannot lead a team "
        "(teammates cannot spawn teammates), so never dispatch a `team-lead` agent: follow the playbook "
        "`~/.claude/agents/team-lead.md`. Set `run.json.team = true` and `expected_artifacts` "
        f"{{{arts}}}, then spawn {spawns}; the integrator starts once both reports exist.\n"
        "  Teams unavailable (the Agent tool rejects `name`, or no SendMessage) or the user asked for "
        f"no teams → plain sequential dispatch {seq}, each after the previous artifact exists, same "
        "artifacts keyed by `subagent_type`.\n"
        "  A plan artifact in `$RUN/` satisfies `requires: plan`; without one the implementor writes a "
        "mini-plan first."
    )


def invoke_body(*, order: str, rows: str, impl: str, design_model: str, checkpoints: str,
                globs: str, mutating: str, closer_block: str) -> str:
    return f"""# /invoke $ARGUMENTS

## 1. Parse `$ARGUMENTS`

- Tokens before ` -- ` are acts (plus the optional `--run <dir>`); everything after is the TASK (empty → the request already in the conversation).
- Valid acts, canonical order: `{order}`.
- Reorder the requested acts into canonical order regardless of how they were typed.
- Unknown token → report `unknown act "<x>" — valid: {order}` and continue with the rest. No valid act → print this usage and stop.

## 2. Run folder + intel (once, yourself — no dispatch)

1. New run: `SLUG` = kebab-case of at most 4 task words (`run` if empty); `{NEW_RUN}` (no git repo → the cwd instead of the toplevel); `mkdir -p "$RUN"`. `$RUN` is absolute: every prompt and closer gets the same path. Resume: `--run <dir>` → `RUN` = that folder, made absolute; read its `run.json`, skip every act already in `run.json.done`, add the new acts to `acts`, and give the remaining agents every artifact already in `$RUN/` (BRIEF, an approved plan) as input; never redo them. Make sure `.claude/runs/` is git-ignored (add it to `.gitignore` with Edit when missing). Every file below is written with the Write/Edit tools, never a shell heredoc or redirect.
2. Intel (new run): jcodemunch `plan_turn` (query = TASK) + `assemble_task_context` on the impacted area; graphify `query_graph` only if `graphify-out/` exists; read `CODEX.md` and the root→target `CLAUDE.md` chain when present.
3. New run: `Write` tool → `$RUN/BRIEF.md`: task, surfaces (FE / BE / infra), impacted files, contracts at risk, acceptance criteria, open questions.
4. New run: `Write` tool → `$RUN/run.json`; a resumed run is updated with Edit, never replaced. The one schema (the team playbook `agents/team-lead.md` uses the same):
   `{RUN_JSON}`
   `run` is the folder relative to the repo root; `expected_artifacts` maps the dispatched `subagent_type` (or a teammate `name`) to the artifact's file name inside the run folder; `team` is true only while you lead a team. `/invoke-status`, the TeammateIdle gate and the suite gate read this file — keep it current.

Every specialist receives `$RUN/BRIEF.md` plus every artifact already in `$RUN/`; later acts start warm and never re-derive earlier context.

## 3. Dispatch — one specialist per act, canonical order

| act | agent | artifact (in `$RUN/`) | model (default) | mutates | checkpoint |
|-----|-------|-----------------------|-----------------|---------|------------|
{rows}

`model` is what opus-guard resolves by default: opus judges, sonnet executes. Execution agents escalate to opus when the prompt reports a failed previous attempt, or when it names no plan/spec artifact and the task is large. Do not pass `model=`: opus-guard ignores it for pinned agents and executors unless the user's own turn names the model ("use opus").

For each act, in order:

1. Set `run.json.expected_artifacts["<agent>"] = "<artifact>"` (the file name) before dispatching.
2. `Agent(subagent_type="<agent>", description="<act>: <TASK>", prompt=...)`. The prompt names `$RUN/BRIEF.md`, each prior artifact path, and the exact output path `$RUN/<artifact>`; opus-guard adds the model and its `[label]`. Plain delegation: no `name=` (teams only for the mixed `impl` case below).
3. Wait for it, then append the act to `run.json.done`. Artifact missing or the act failed → re-dispatch once with the prompt prefixed `Previous attempt failed: <one-line reason>.` (this escalates execution agents to opus); still failing → stop and report.

Act-specific rules:

{impl}
- **`design`** [{design_model}] — `frontend-uiux-designer`; every raster/video/3D/audio asset comes from Higgsfield (`higgsfield-generate`), never placeholders. {HIGGS_LOGIN}
- **`refactor`** — `refactor-specialist` edits the main working tree (no worktree: nothing is committed, so nothing would merge back).
- **`clean`** edits code — treat REAP edits as real changes; the closers review them.
- **Checkpoints** (after {checkpoints}): interactive session → stop, show the artifact path + a 5-line summary, ask "continue with <remaining acts>?" and wait for the answer. Non-interactive (`-p`) → continue.
- **Security auto-add**: after the last mutating act, `git diff --name-only <start_sha>` (plus untracked files) matched against {globs} — any hit and `security` not requested → add `security` to the run before the closers.

## 4. Closers — only if an act that mutates ({mutating}) ran

Skip any closer whose act already ran explicitly in this run. Artifacts go to `$RUN/`.

{closer_block}

No mutating act → no closers; say so in one line.

## 5. Finish

Mark every act `done` in `run.json`, then report: `$RUN`, the artifact list, and the verdicts (Santa PASS / CHANGES REQUESTED, security PASS / BLOCK, QA PASS / FAIL). A BLOCK or FAIL is the headline, not a footnote. To resume later: `/invoke <pending acts> --run $RUN -- <task>`.

## Fallback — Agent tool unavailable

Read `references/rosters.md` and run each act's skills yourself via the Skill tool, in canonical order. Never silently drop an act.

## Optional deterministic flow (explicit opt-in)

`~/.claude/workflows/invoke-fullstack.js` runs spec → plan → BE → FE → integrator → parallel(santa, security, docs) → qa as a Workflow script. Only the user starts it (`/invoke-fullstack`, or Workflow with `args: {{"task", "run", "slug"}}` after creating the run folder in step 2, `run` = the absolute `$RUN`). Never launch it on the user's behalf.
"""


def delegator_body(act: str, agent: str, artifact: str, note: str) -> str:
    note = f"\n{note}\n" if note else ""
    return f"""Run the **{act}** act for: $ARGUMENTS

This is `/invoke {act}` without the closers; `~/.claude/skills/invoke/SKILL.md` governs anything not said here.

1. Run folder: `--run <dir>` in the arguments → reuse that folder (absolute path) and update its `run.json` with Edit; otherwise create a new one exactly as `/invoke` §2 (`{NEW_RUN}`, `BRIEF.md`, `run.json` with `"acts": ["{act}"]`). Never write into any other existing run folder.
2. Set `run.json.expected_artifacts["{agent}"] = "{artifact}"`.
3. `Agent(subagent_type="{agent}", description="{act}: <task>", prompt=...)`. The prompt names `$RUN/BRIEF.md`, every artifact already in `$RUN/`, and the exact output path `$RUN/{artifact}`. No `model=`: opus-guard routes it (pins, escalation, per-project mode). Artifact missing or the act failed → re-dispatch once with the prompt prefixed `Previous attempt failed: <one-line reason>.`
4. Append `{act}` to `run.json.done`, then report the artifact path and a one-paragraph verdict.
{note}"""


def rosters_body(acts: list[dict], banner: str) -> str:
    parts = ["# /invoke fallback rosters", "", banner, "",
             "Read ONLY when the Agent tool is unavailable. Invoke each act's skills via the Skill tool, "
             "in canonical order.", ""]
    for a in acts:
        parts += [f"## `{a['act']}` — {a['agent']} → `{a['artifact']}`", ""]
        parts += [f"- `{s}`" for s in a["local_skills"]]
        parts += [f"- `superpowers:{s}`" for s in a["superpowers_skills"]]
        parts.append("")
    return "\n".join(parts)


STATUS_BODY = (
    "Report where the current `/invoke` work stands. Read-only.\n\n"
    "1. Repo root first: `git rev-parse --show-toplevel` (no repo → the cwd), so a subdirectory session "
    "still finds the runs. Run = the folder the user named, else the newest "
    "`ls -dt <root>/.claude/runs/*/ | head -1`. Read its `run.json` (`task`, `acts`, `done`, `models`, "
    "`team`, `expected_artifacts`).\n"
    "2. Pending acts = `acts` minus `done`. Every `expected_artifacts` value is a file name inside the run "
    "folder: say whether `<run>/<file>` exists; missing ones are the blockers.\n"
    "3. Verdict lines, when the reports exist in the run folder: `SANTA-REVIEW.md` "
    "(PASS / CHANGES REQUESTED), `SECURITY-REPORT.md` (PASS / BLOCK), `VERIFY-REPORT.md` (PASS / FAIL).\n"
    "4. Gate state: `~/.claude/hooks/.telemetry/*.suite-gate.json` for this conversation, if present.\n"
    "5. Print: run path · done / pending · artifacts present / missing · verdicts · suggested resume "
    "`/invoke <pending acts> --run <run path> -- <task>` (it reuses the folder, the BRIEF and every "
    "finished artifact).\n\n"
    "No `.claude/runs/` folder → say so and suggest `/invoke <acts> -- <task>`."
)

UTILITIES = {
    "invoke-session": {
        "description": ("Session init — index/graph freshness, memory + CODEX load, repo orientation, "
                        "dox check -> ready report."),
        "extra": {},
        "body": ("Run the session-init flow: verify jcodemunch + graphify freshness (rebuild only if STALE), "
                 "load Memory MCP + CODEX.md, orient (get_repo_map), confirm the dox root, print a READY "
                 "report."),
    },
    "invoke-status": {
        "description": ("Where am I? — newest .claude/runs/ run.json: acts done/pending, artifacts "
                        "present/missing, gate state, suggested `--run` resume command."),
        "extra": {"allowed-tools": "Read, Glob, Bash(ls:*), Bash(cat:*), Bash(git rev-parse:*)"},
        "body": STATUS_BODY,
    },
    "invoke-update": {
        "description": ("Upstream skill sync — check vendored third-party skills against their pinned "
                        "sources, update on confirmation, then re-verify provenance (R10)."),
        "extra": {"disable-model-invocation": "true"},
        "body": (
            "Sync vendored third-party skills with their pinned upstreams (`hooks/skills-sources.json`).\n\n"
            "1. `python3 ~/.claude/scripts/vendor_skill.py --all --check` — report drift per skill "
            "(exit 1 = drift).\n"
            "2. Only after the user confirms: `python3 ~/.claude/scripts/vendor_skill.py --all`.\n"
            "3. `python3 ~/.claude/scripts/build_provenance.py --check` — report the R10 result.\n\n"
            "Never run step 2 without an explicit yes — it touches the network and git."
        ),
    },
}
