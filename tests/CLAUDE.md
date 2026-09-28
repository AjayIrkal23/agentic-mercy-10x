<!-- dox:child v1 -->
# `tests/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename tests.

## What lives here

Repo-level tests for the installer, doctor, settings template/render, skills catalog and
portability. Hook unit tests live in `../hooks/tests/`. `fixtures/hook-events/*.json` are
synthetic event payloads (one per event, incl. subagent-start, teammate-idle,
post-tool-use-failure, post-compact, config-change).

## Local conventions

- Run: `python3 -m pytest tests -q` (CI runs it on Ubuntu + Windows).
- Tests must not touch the live `~/.claude`: sandbox `HOME`/`CLAUDE_CONFIG_DIR` and set
  `CLAUDE_HOOK_DOCTOR=1`.
- No PyYAML or other non-stdlib imports (the CI interpreter is bare).

## Key files

| File | Role |
|------|------|
| `test_installer.py`, `test_doctor.py` | installer + doctor smoke, read-only doctor in a sandbox |
| `test_render_settings.py`, `test_template_contract.py` | render equivalence; template has no MCP block, no home literal, no "lean-ctx" |
| `test_mcp_secret_transport.py` | secret-safe MCP registrations |
| `test_validate_skills.py`, `test_vendor_sources.py` | skill validation; vendored skills match `skills-sources.json` + R10 |
| `test_ci_portability.py`, `test_portability_gate.py` | CI-green regressions; portability grep-gates |

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
