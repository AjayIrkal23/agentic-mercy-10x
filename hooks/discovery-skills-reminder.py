#!/usr/bin/env python3
"""discovery-skills-reminder.py — always-on discovery-skills reminder (P6-T2 port).

Portable 1:1 replacement for ``discovery-skills-reminder.sh`` (zero bash in the
live hook path). Prints the SAME standing reminder text verbatim to stdout, which
dispatch injects as SessionStart/prompt additionalContext. Names the discovery/
structure/linkage skills every session; does NOT force-invoke (that would burn
tokens). The .sh is retained only as the 30-day flip-back path.

Edit ``_REMINDER`` to add/remove skills (mirror the .sh heredoc if it is ever
un-retired).
"""

from __future__ import annotations

import sys

_REMINDER = """ALWAYS-ON DISCOVERY SKILLS (reach for these before exploring/scaffolding any project):
- codebase-intel-first / jcodemunch-token-saver / graphify : structural model, symbol/caller/blast-radius lookup FIRST (before Read/grep)
- project-structure-map / project-reference-linkage : dir map + cross-module links (component<->hook<->api<->controller<->route<->schema<->slice)
- codebase-start-point-guide : startup flow - right docs, contracts, scope layers
- iterative-retrieval : progressively refine context retrieval
- domain-scaffold-patterns / scaffold-standards / architect-system-design : new domain file tree, route/controller/service/schema skeleton, build-ready spec
- dox-doc-tree / update-docs : per-dir CLAUDE.md tree (read root->target), repo docs
- frontend-structure-standards / backend-standards-always-follow / service-layer-standards : where things live, layer boundaries
- dead-code-and-change-audit : stale refs, unused code, partial refactors
For "where is X / who calls X / what breaks if I change X" -> jcodemunch + graphify MCP tools beat any skill.
"""


def main() -> int:
    # The .sh ignored argv (it accepted a "prompt" arg but only cat'd the heredoc).
    sys.stdout.write(_REMINDER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
