#!/usr/bin/env python3
"""install.py — reproduce the ~/.claude workbench on any machine (P6-T5).

Stdlib-only bootstrap (Python >= 3.10). One command, OS auto-detected, idempotent.

  python install.py [install]     detect -> deps -> MCP register -> materialize
                                  skills -> render settings.json -> build+validate
                                  catalog (R9/R10) -> doctor
  python install.py update        git pull --ff-only -> idempotent deps ->
                                  conditional re-render -> rebuild catalog -> doctor
  python install.py doctor        health + trigger-surface verifier only
  python install.py verify        WORKFLOW TESTER — prereqs/deps/MCP/plugins/wiring
                                  status with a fix command per gap (also: check.py)
  python install.py ui            VISUAL installer — opens a local web UI to pick the
                                  .claude folder, see live status, and install step-by-step
  Flags: --ci (skip networked ci_stub steps; CI has no network / no claude CLI)
         --dry-run (print planned actions, mutate nothing)

Everything OS-branches through hooks/lib/platform.py. Nothing here raises to the
user: a step failure is reported in the summary and reflected in the doctor exit.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _require_python() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"install.py requires Python >= 3.10 (found {sys.version.split()[0]})")


def _print_rows(title: str, rows) -> None:
    print(f"== {title} ==")
    for name, status in rows:
        print(f"  {name:24s} {status}")


def _git_pull_ff() -> tuple[str, str]:
    from lib import platform as plat
    cp = plat.run(["git", "-C", str(_ROOT), "pull", "--ff-only"], timeout=120)
    return ("git pull --ff-only", "OK" if cp.returncode == 0 else f"WARN(rc={cp.returncode})")


def _render_settings(env, dry_run: bool) -> tuple[str, str]:
    import render  # type: ignore
    if dry_run:
        text = render.render(subs=env.tokens)
        return ("render settings.json", f"WOULD-WRITE {len(text)} bytes")
    text = render.render(subs=env.tokens)
    from lib import platform as plat
    ok = plat.atomic_write(_ROOT / "settings.json", text)
    return ("render settings.json", "OK" if ok else "WARN(write-failed)")


def do_install(*, ci: bool, dry_run: bool) -> int:
    import deps  # type: ignore
    import links  # type: ignore
    from detect import detect  # type: ignore
    import doctor  # type: ignore

    env = detect()
    print(f"detected: {env.os_name} python={env.python!r} node={env.node!r} "
          f"claude-cli={'yes' if env.claude_cli else 'no'} "
          f"uv={'yes' if env.uv else 'no'} npm={'yes' if env.npm else 'no'}")

    prereqs = deps.check_prereqs(env)
    _print_rows("prerequisites (install these yourself)", prereqs)
    missing_req = [n for n, s in prereqs if s.startswith("MISSING") and "optional" not in s]
    if missing_req:
        print(f"  !! MISSING required prereqs: {', '.join(missing_req)} — install them (commands above), "
              "then re-run. Steps that need them will WARN below.")

    _print_rows("dependencies", deps.install_deps(env, ci=ci, dry_run=dry_run))
    _print_rows("mcp servers", deps.register_mcps(env, ci=ci, dry_run=dry_run))
    _print_rows("plugins", deps.install_plugins(env, ci=ci, dry_run=dry_run))
    _print_rows("skill links", links.materialize(dry_run=dry_run))
    name, status = _render_settings(env, dry_run)
    print(f"== settings ==\n  {name:24s} {status}")
    _print_rows("post steps (catalog/index/validate)", deps.run_post_steps(env, ci=ci, dry_run=dry_run))

    print()
    rc = doctor.main(["--ci"] if ci else [])
    return rc


def do_update(*, ci: bool, dry_run: bool) -> int:
    import deps  # type: ignore
    from detect import detect  # type: ignore
    import doctor  # type: ignore

    env = detect()
    if not dry_run and env.git:
        name, status = _git_pull_ff()
        print(f"== update ==\n  {name:24s} {status}")
    else:
        print("== update ==\n  git pull --ff-only     " + ("(dry-run)" if dry_run else "SKIP(no-git)"))
    _print_rows("dependencies", deps.install_deps(env, ci=ci, dry_run=dry_run))
    name, status = _render_settings(env, dry_run)
    print(f"== settings ==\n  {name:24s} {status}")
    _print_rows("post steps (catalog/index/validate)", deps.run_post_steps(env, ci=ci, dry_run=dry_run))
    print()
    return doctor.main(["--ci"] if ci else [])


def do_doctor(*, ci: bool) -> int:
    import doctor  # type: ignore
    return doctor.main(["--ci"] if ci else [])


def main(argv: list[str]) -> int:
    _require_python()
    ci = "--ci" in argv
    dry_run = "--dry-run" in argv
    verbs = [a for a in argv if not a.startswith("-")]
    verb = verbs[0] if verbs else "install"
    if verb == "doctor":
        return do_doctor(ci=ci)
    if verb == "verify":
        import verify  # type: ignore
        return verify.main([])
    if verb == "ui":
        import ui  # type: ignore
        return ui.main([])
    if verb == "update":
        return do_update(ci=ci, dry_run=dry_run)
    if verb == "install":
        return do_install(ci=ci, dry_run=dry_run)
    print(f"unknown verb {verb!r}; use install | update | doctor | verify | ui")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
