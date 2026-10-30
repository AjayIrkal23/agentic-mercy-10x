# Continuous learning (instincts)

The workbench learns per-project working habits from tool use, scores them, and shows the strong ones at session start. The model is the ollama that `OLLAMA_HOST` in `settings.user.json` names. Learning never spends Claude quota.

With a remote `OLLAMA_HOST`, jcodemunch AI summaries send source snippets and the learning step sends scrubbed command digests and file paths to that host over plain HTTP; use a host you trust, or leave it unset.

## Why

ECC's continuous-learning-v2 observes tool calls, distils habits ("instincts") and surfaces them. We keep that idea and drop its daemon, its Haiku observer and its Claude-quota cost. What is left: three Python files, two async exec links (PostToolUse and PostToolUseFailure) and one daily step, with ollama as the only model.

## Pipeline

| Stage | What | Where |
|---|---|---|
| capture | one scrubbed row of at most 2 KB per tool call; skip list; infra roots skipped. Failed calls arrive through PostToolUseFailure and are logged `ok: false` with the scrubbed error clipped to 160 chars | `hooks/observe-log.py`, async exec links `observe-log` and `observe-log-failure` |
| store | per-project JSONL; rows older than 30 days dropped by `state-cleanup`; evolve compacts to `max_rows_per_project` | `state/learning/<repo_key>/observations.jsonl` |
| evolve | at least 20 new rows per project; one `/api/chat` call per project; model from `learning.config.json` `model` | `hooks/tools/instincts.py evolve`, self-heal step `learning-evolve` |
| score | start 0.3, +0.1 per re-observation, cap 0.95, -0.05 per idle week (derived at read time), prune below 0.2 | `instincts.py` `merge`, `effective` |
| promote | the same habit in at least 2 projects at a mean of 0.8 or more | `state/learning/instincts/global.jsonl` |
| surface | at most 3 lines at 0.7 or more; project rows rank +0.25 | `session_notices.instinct_lines` -> aggregator notices |

## Row and file formats

```
hooks/lib/ollama.py        host() -> str                        platform.ollama_url()
                           alive(timeout_s=1.5) -> bool         GET <host>/api/tags; any HTTP answer = True; refused/timeout/other = False
                           chat(model, messages, timeout_s=60, *, options=None) -> str | None   POST <host>/api/chat stream=false; None = down/timeout/missing model/bad reply
                           models(timeout_s=3) -> list[str] | None                             names from /api/tags (status only)
state/learning/<repo_key>/observations.jsonl   {"ts": 1761750000.123, "sid": "<session_id>", "tool": "Edit", "summary": "<scrubbed <= ~1.5 KB>", "ok": true, "files": ["rel/path.py"], "error"?: "<scrubbed <= 160 chars, failures only>"}
                                                one JSON object per line, <= 2048 bytes per line, appended with plat.append_line
state/learning/<repo_key>/evolve.json          {"cursor_ts": <float>, "last_run": <float>, "runs": <int>, "last_result": "evolved +2 ~1 -0"}   locked_update
state/learning/instincts/<repo_key>.jsonl      {"id": "<sha1(norm text)[:12]>", "text": "<= 140 chars", "domain": "workflow|testing|tooling|git|code-style|debugging|docs|infra",
                                                "confidence": 0.3..0.95 (stored, undecayed), "seen": 1, "first": <ts>, "last": <ts>, "promoted": false, "source": "ollama|import:<name>"}
state/learning/instincts/global.jsonl          same row + "promoted": true, "projects": ["<repo_key>", ...]
state/learning/evolve.lock                     daily_lock.try_lock; a held lock prints "busy" and exits 0
instincts.lines(cwd, limit=3, min_confidence=0.7) -> list[str]   called by session_notices.instinct_lines through exec(); read-only, no network
```

`<repo_key>` is `lib.model_mode.repo_key(cwd)`: `<root name>-<sha1(root)[:12]>`, where root is the git root, else the resolved cwd.

Effective confidence, the only value compared against thresholds: `max(0, confidence - 0.05 * floor(idle seconds / 604800))`. It is never written back, so a daily run stays idempotent.

## What never happens

- No Claude CLI call, no API key, no network except `OLLAMA_HOST` (and an explicit `import <https-url>`).
- Edit content is never stored: write-tool rows hold paths and lengths only.
- Secrets are scrubbed twice, by key and by text shape (`hooks/lib/scrub.py`). Env-var style names count as keys (`AWS_SECRET_ACCESS_KEY=`, `PGPASSWORD=`, `GITHUB_TOKEN=`); the name stays, the value goes.
- `$HOME`, `~/.claude`, `~/.codex` and this checkout are not observed unless `observe_infra` is true.
- Box down: `DEFERRED`, and the next daily run retries.
- Nothing blocks a tool call or a session start (async link, read-only surfacing).

## Configuration

`hooks/learning.config.json`. A missing or malformed file means the defaults below.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` silences capture and evolve |
| `model` | `qwen2.5-coder:3b` | ollama model for evolve |
| `alive_timeout_s` | `1.5` | probe timeout before evolve |
| `chat_timeout_s` | `120` | one chat call per project |
| `min_new_observations` | `20` | new rows a project needs before evolve calls the model |
| `max_row_bytes` | `2048` | cap per observation line |
| `max_rows_per_project` | `5000` | evolve compacts the log to this many rows |
| `max_digest_chars` | `6000` | digest sent to the model |
| `max_instincts_per_run` | `8` | items kept from one reply |
| `skip_tools` | Read, Glob, Grep, LS, TodoWrite, TodoRead, NotebookRead, ListMcpResourcesTool, ReadMcpResourceTool | never observed; the dispatch link's `tools` regex mirrors it |
| `observe_infra` | `false` | observe the infra roots too |
| `surface` | limit 3, min 0.7, project boost 0.25, 110 chars | session-start lines |
| `confidence` | start 0.3, reaffirm 0.1, cap 0.95, decay 0.05/week, prune 0.2, promote 0.8 in 2 projects | scoring |
| `domains` | workflow, testing, tooling, git, code-style, debugging, docs, infra | allowed domains |
| `import` | 1 MB, 15 s | remote import limits |

## CLI

```
python3 ~/.claude/hooks/tools/instincts.py evolve [--once] [--all] [--cwd D] [--dry-run] [--budget S]
python3 ~/.claude/hooks/tools/instincts.py status [--json] [--cwd D]
python3 ~/.claude/hooks/tools/instincts.py export [--min X] [--yaml] [--global] [--output F] [--cwd D]
python3 ~/.claude/hooks/tools/instincts.py import <file|https-url> [--global] [--dry-run] [--min X] [--cwd D]
```

`evolve` covers every project by default; `--cwd` narrows it to one. `--budget` (600 s) is checked before each project. `export --yaml` writes the ECC instinct format. The `instincts` skill tells Claude when to run these.

## Import guard

- https only; the host is resolved before connecting, and every address must be public (no private, loopback, link-local, multicast, reserved or unspecified address).
- Redirects are not followed. 1 MB cap, 15 s timeout, content type `text/*`, YAML, JSON, Markdown or octet-stream.
- JSON arrays, JSONL and ECC YAML blocks are accepted. Confidence is clamped to 0.3..0.9. Rows merge by text hash or keyword overlap, keeping the higher confidence.
- Residual risk: DNS can change between the check and the connect (rebinding). The import is an explicit user action, so we accept it.

## Windows

The same files run there. `append_line` takes a lock on Windows and `daily_lock` uses `msvcrt`; ollama is reached over HTTP exactly as on Linux. No POSIX-only calls.

## Operations

- Lines come from `session_notices.instinct_lines`, which runs `instincts.lines()`.
- To silence learning, set `enabled: false`.
- To forget a project, remove its `state/learning/<repo_key>/` dir and `state/learning/instincts/<repo_key>.jsonl`.
- Telemetry kinds: `ollama` `chat_*`, `observe-log` `write_failed` / `error`, `instincts` `evolve_bad_reply`.
- Tests: `hooks/tests/test_ollama_lib.py`, `test_observe_log.py`, `test_instincts.py`, fixtures in `hooks/tests/fixtures/learning/`.

## Provenance

Adopted from ECC `skills/continuous-learning-v2`: the observe.sh scrub list, the instinct-cli import guard and export format, and the observer.md scoring rules, which run here as code. The project boost comes from `scripts/lib/instinct-relevance.js`. ECC's `evolve`/`promote`/`prune`/`projects` commands live as digests under `library/ecc/commands/`.
