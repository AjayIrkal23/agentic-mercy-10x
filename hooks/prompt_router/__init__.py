"""prompt_router — the single-process UserPromptSubmit router (v3, 2026-09-27).

classify ONCE (word-boundary floor + FE/BE/API/docs/mobile surfaces) -> rank <= 4
skills by surface/intent -> pointer / WORKFLOW / MCP / LIBRARY routes -> agent/act
suggestion -> session-manifest dedup -> ONE hookSpecificOutput.additionalContext emit
(marker `<!-- prompt-router v3 -->`). Runs as the `router` link of
`dispatch.py user-prompt-submit`.

Modules:
  classify   S1  TaskProfile from trigger-floor.json (KeywordMatcher) + modules/surface;
                 UI veto + MODEL_ROUTING surface swap (R3.6)
  cues           negation window, phrase intents, noun-only LARGE demotion (C-04, C-12)
  policy         emit policy: hard/soft enforcement, chat/question gating, skill lines,
                 UI line, routing cap, session model (C-05, C-10, C-11, C-12, C-14, C-17)
  select     S2  ranked skill selection, alias collapse, existence filter, demote clamp,
                 dispatch tiering
  budget     S5  tier-ascending ordering (no drops)
  manifest       per-session dedup (never suppresses a first fire; reset after compaction)
  router         orchestrator / hook entry point
  modules/       surface, mcp_routes, code_intel, model_advice (package model-routing),
                 asset_auth, workflow_routes, library_routes (package library)

Pure Python 3 stdlib; fail-open at module and router level.
"""
