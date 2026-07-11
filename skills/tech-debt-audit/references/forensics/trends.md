# Complexity trends (jcodemunch-backed)

> Absorbed into `tech-debt-audit`. Tracks whether files are improving, stable, or deteriorating over git history.

Use `mcp__jcodemunch__get_symbol_complexity`, `mcp__jcodemunch__get_churn_rate`, `mcp__jcodemunch__diff_health_radar`, and `mcp__jcodemunch__get_repo_health` to measure refactoring impact and validate technical-debt work. Replaces the POSIX-only shell history walk with cross-platform index queries.
