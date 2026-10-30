# No shell writes

Files are written with `Edit` / `Write` / `ctx_patch` only. Bash runs things; it never
writes files.

| Banned in Bash | Why |
|---|---|
| `sed -i`, `perl -i`, `ruby -i`, `--in-place` | in-place edit, no reviewable diff, bypasses every write gate |
| `python3 -c "…open(…,'w')"`, `node -e`, `python3 - <<EOF` with a write in the body | interpreter-mediated write |
| `cat > f <<EOF`, `cat <<EOF > f`, `tee f`, `echo`/`printf > f`, `awk … > f && mv` | redirect write |
| `grep -r` / `find` / `ls -R` to discover code | that is jcodemunch's job |

Allowed in Bash: builds, tests, linters, `git`, package managers, `rm` / `mv` / `mkdir`,
and read-only inspection (`cat`, `sed -n`, `grep`, `python3 -c` that only prints).
Writes whose only targets are under `/tmp`, the scratchpad, or `*.log` are fine.

A denied or gated tool is a **route**, not an obstacle: switch to the sanctioned tool for
that job (`Edit` after a `Read`, `ctx_patch` inside the repo, `Write` for new files).
Never re-implement the denied tool's job in the shell, and never batch edits into one
script because it is faster — take the N `Edit` calls. If there is genuinely no
sanctioned path, stop and say so.

`bash-write-gate` advises once per kind per session (deny only with
`BASH_WRITE_GATE_DENY_SHELL_WRITES=1`). "Never do X in this repo" → a hookify rule
(skill `hookify-rules`).
