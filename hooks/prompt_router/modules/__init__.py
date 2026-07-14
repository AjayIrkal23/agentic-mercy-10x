"""prompt_router.modules — router support modules.

Only ``model_advice`` remains (pure: no legacy-hook import, no state) and is
imported directly by the router's built-in path. The S3 delegate wrappers
(``intel``/``guards``/``uiux``/``seqthink``/``invoke_suite`` + ``_base``) that
imported the legacy injector hooks were **retired 2026-07-14** together with the
legacy UPS stack (the router runs on its floor-driven built-in item builders).
"""
from __future__ import annotations

__all__: list[str] = []
