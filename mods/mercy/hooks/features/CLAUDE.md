<!-- dox:child v1 -->
# `mods/mercy/hooks/features/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

<One or two lines: the responsibility of this directory. What kind of files belong,
what does NOT belong here.>

## Local conventions

- <e.g. naming pattern, file-size cap, import boundaries specific to this folder>
- <e.g. "every X must register in Y" / "do not import from Z">

## Key files

| File | Role |
|------|------|
| `alerts.tsx` | <what it does> |
| `auto.tsx` | <what it does> |
| `bridge.ts` | <what it does> |
| `cmds.tsx` | <what it does> |
| `deck.tsx` | <what it does> |
| `lifecycle.ts` | session start/end, ledger and deck state, auto-resume after a usage limit (shared `state/resume-lock/<sid>`), and the per-session flag `state/mercy-mod.active.d/<sid>.json` (every 30 s; `ts 0` at a real end and for the old id on `/clear` or an in-process resume) |
| `memwatch.tsx` | polls `state/mem-pressure.json` every 15 s for the band, pane memory tab and status line; in-pane toast per tier change, never a desktop notification (that is `hooks/tools/memwatch.py`'s) |
| `model-caps.ts` | `agent.spawn` cap at the plan tier ceiling and the usage-guard step-down (`lib/modelcaps.ts`); `hooks/opus-guard.py` stays the floor |
| `mtools.ts` | <what it does> |
| `prompts.ts` | <what it does> |
| `pulse.tsx` | <what it does> |
| `restyle.tsx` | <what it does> |
| `stop.ts` | <what it does> |
| `toolflow.ts` | <what it does> |

## Gotchas / fragile spots

- <non-obvious thing that breaks if you're not careful>

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: <links to deeper `*/CLAUDE.md`, or "none">
- Related repo docs: <link to the numbered doc / CODEX.md section — link, don't restate>
