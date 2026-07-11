"""prompt_router.modules — S3 delegates (P1-T4).

``collect(profile, ctx)`` aggregates the delegate items. Delegates IMPORT the
original injector hooks in-process (Charter §3). They are GATED:

  router.config.json -> delegates.enabled           (default False)
  router.config.json -> delegates.enabled_in_shadow (default False)

Default OFF: the router's built-in item builders (fast, pure, floor-driven) are
the operational behavior; the delegates reuse EXACT legacy logic and are
activated at/after cutover (when the legacy stack is flipped off) so a stateful
legacy hook never double-fires beside its still-installed twin during the shadow
window (Charter §2). Delegate modules are imported lazily so router startup does
not load the legacy hooks unless delegates are enabled.

model_advice is pure (no legacy hook, no state) and is emitted from the router's
built-in path directly — it is intentionally NOT in this delegate set.
"""
from __future__ import annotations

_DELEGATE_MODULES = ("intel", "guards", "uiux", "seqthink", "invoke_suite")


def _enabled(ctx: dict) -> bool:
    cfg = (ctx.get("config") or {}).get("delegates") or {}
    if not cfg.get("enabled", False):
        return False
    if ctx.get("mode") == "shadow" and not cfg.get("enabled_in_shadow", False):
        return False
    return True


def collect(profile, ctx: dict) -> list[dict]:
    """Return merged delegate items, or [] when delegates are gated off. Fail-open."""
    if not _enabled(ctx):
        return []
    payload = ctx.get("payload") or {}
    ctx = dict(ctx)
    ctx["profile"] = profile
    out: list[dict] = []
    import importlib

    for name in _DELEGATE_MODULES:
        try:
            mod = importlib.import_module(f"prompt_router.modules.{name}")
            fn = getattr(mod, "items", None)
            if callable(fn):
                res = fn(payload, ctx)
                if isinstance(res, list):
                    out.extend(res)
        except Exception:  # noqa: BLE001 - a broken delegate never breaks routing
            continue
    return out


__all__ = ["collect"]
