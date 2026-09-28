"""prompt_router — the single-process UserPromptSubmit router (v3, 2026-09-27).

classify ONCE (word-boundary floor + FE/BE/API/docs surfaces) -> rank <= 5 skills
by surface/intent -> availability-aware MCP routes -> agent/act suggestion ->
session-manifest dedup -> ONE hookSpecificOutput.additionalContext emit
(marker `<!-- prompt-router v3 -->`).

Modules:
  classify   S1  TaskProfile from trigger-floor.json (KeywordMatcher) + modules/surface
  select     S2  ranked skill selection, alias collapse, existence filter, dispatch tiering
  budget     S5  tier-ascending ordering (no drops)
  manifest       per-session dedup (never suppresses a first fire)
  router         orchestrator / hook entry point
  modules/       surface, mcp_routes, code_intel, model_advice

Pure Python 3 stdlib; fail-open at module and router level.
"""
