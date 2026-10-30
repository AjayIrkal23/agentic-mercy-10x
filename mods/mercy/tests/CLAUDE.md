<!-- dox:child v1 -->
# `mods/mercy/tests/` — local rules (dox)

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
| `auto.test.ts` | <what it does> |
| `brainstore.test.ts` | <what it does> |
| `bridge.test.ts` | <what it does> |
| `commands.test.ts` | <what it does> |
| `context.test.ts` | <what it does> |
| `deck.test.ts` | <what it does> |
| `hooks.test.ts` | <what it does> |
| `lib.test.ts` | <what it does> |
| `memwatch.test.ts` | <what it does> |
| `modelcaps.test.ts` | `capModel` rules and the `model-caps` feature against a fake `agent.spawn` (tier ceiling, no policy file → untouched) |
| `policy.test.ts` | <what it does> |
| `ports.test.ts` | <what it does> |
| `psshell.test.ts` | <what it does> |
| `resume-lock.test.ts` | pure `lib/resumelock.ts` rules: `decideResumeLock`, `lockBody`, `flagBody` |
| `resume.test.ts` | <what it does> |
| `shellparse.test.ts` | <what it does> |
| `stopgate.test.ts` | <what it does> |
| `toast.test.ts` | <what it does> |
| `ui.test.tsx` | <what it does> |
| `winshell.test.ts` | <what it does> |

## Gotchas / fragile spots

- <non-obvious thing that breaks if you're not careful>

## Up / down

- Parent: [`../../CLAUDE.md`](../../CLAUDE.md)
- Children: <links to deeper `*/CLAUDE.md`, or "none">
- Related repo docs: <link to the numbered doc / CODEX.md section — link, don't restate>
