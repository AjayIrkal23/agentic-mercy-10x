# Change coupling (jcodemunch-backed)

> Absorbed into `tech-debt-audit`. Reveals temporal coupling / shotgun-surgery and hidden dependencies **without** POSIX-only git-history shell pipelines.

Use `mcp__jcodemunch__get_coupling_metrics` (files that change together), `mcp__jcodemunch__get_churn_rate`, and `mcp__jcodemunch__get_related_symbols` / `find_importers` to find architectural violations and cross-module dependencies. No shell history pipelines or GNU coreutils date arithmetic — the index computes the temporal-coupling graph directly.
