# Hotspot finder (jcodemunch-backed)

> Absorbed into `tech-debt-audit`. Identifies high-risk files (change frequency × complexity, 4-9x defect-rate formula) to prioritise refactoring and investigate recurring bugs.

Use `mcp__jcodemunch__get_hotspots` (frequency×complexity ranking already computed), plus `get_churn_rate` and `get_file_risk`. Replaces the POSIX-only git-history hotspot script with a cross-platform index query.
