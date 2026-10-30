Fixture session ledger for `scripts/restore_sessions.py --dry-run --state-dir tests/fixtures/ledger`: `stale-dead` is a killed session (no `ended`) started 2026-01-01, so it is stale against any `--max-age`; `ended` closed cleanly.
pid 4190000 is above any live pid on Ubuntu (pid_max 4194304 is never reached in practice) and the zero boot_id never matches a running kernel, so both entries read as dead on every machine.
`--dry-run` writes nothing here; tests snapshot the tree before and after to prove it.
