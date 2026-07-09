#!/usr/bin/env bash
# ponytail: dumb cat of a standing reminder; SessionStart stdout -> session context.
# Surfaces the discovery/structure/linkage skills EVERY session so the agent always
# reaches for them. Names them; does NOT force-invoke (that'd burn tokens). Edit the
# heredoc to add/remove skills.
cat <<'EOF'
ALWAYS-ON DISCOVERY SKILLS (reach for these before exploring/scaffolding any project):
- codebase-intel-first / jcodemunch-token-saver / graphify : structural model, symbol/caller/blast-radius lookup FIRST (before Read/grep)
- project-structure-map / project-reference-linkage : dir map + cross-module links (component<->hook<->api<->controller<->route<->schema<->slice)
- codebase-start-point-guide : startup flow - right docs, contracts, scope layers
- iterative-retrieval : progressively refine context retrieval
- domain-scaffold-patterns / scaffold-standards / architect-system-design : new domain file tree, route/controller/service/schema skeleton, build-ready spec
- dox-doc-tree / update-docs : per-dir CLAUDE.md tree (read root->target), repo docs
- frontend-structure-standards / backend-standards-always-follow / service-layer-standards : where things live, layer boundaries
- dead-code-and-change-audit : stale refs, unused code, partial refactors
For "where is X / who calls X / what breaks if I change X" -> jcodemunch + graphify MCP tools beat any skill.
EOF
