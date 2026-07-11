"""prompt_router — the single-process unified prompt router (P1).

Charter v3 §1/§2: classify ONCE -> ranked select -> priority-ordered ~24k
budget -> session-manifest dedup -> ONE additionalContext emit. Replaces ~15
sequential injector subprocesses with one in-process pipeline whose trigger
surface is a provable superset of the legacy stack (trigger-floor.json).

Modules:
  classify   S1  single TaskProfile from the trigger floor
  select     S2  ranked skill selection + suggest/dispatch tiering (auto_dispatch_threshold)
  budget     S5  priority-ordered token budget (tier-0 first, drops logged)
  manifest   S2  session-manifest dedup (suppress verbatim re-injection, never a first fire)
  router         orchestrator; modes: default (live), --shadow (log-only), --stop (stub)
  modules/       S3 delegates that IMPORT the original injector hooks (P1-T4)

Pure Python 3 stdlib; fail-open at module and router level.
"""
