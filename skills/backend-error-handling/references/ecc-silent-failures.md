<!-- ecc:skills/error-handling, agents/silent-failure-hunter.md @25278e7d -->
# Silent failures (ECC graft)

## Result pattern

For expected failures (validation, not-found, conflict) return a typed result
(`{ ok: true, value } | { ok: false, error }`) instead of throwing; exceptions are for the
unexpected.

## Retry with jitter and a cap

Retry only idempotent operations, with exponential backoff plus random jitter, a max attempt
count and a total deadline. Log each retry with the attempt number; give up loudly.

## Silent-failure hunt list

Search the diff for each; every hit is fixed or justified in a comment:

- an empty `catch {}` or `except: pass`;
- a promise that is never awaited or `.catch`-ed;
- a default value returned on error that looks like success (`return []` on a failed fetch);
- log-and-continue where the caller needed to know (`console.error(e)` then carry on);
- an error swallowed into `null` without a reason.
