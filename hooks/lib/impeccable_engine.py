"""The ONE Impeccable engine lookup (2026-11-03), shared by hooks/ui-quality-autorun.py,
scripts/impeccable_engine.py (install post-step + daily self-heal) and the doctor's design-trio row.

The vendored launcher (skills/impeccable/scripts/impeccable, impeccable.cmd on Windows) downloads the
engine pinned in scripts/VERSION into ``${IMPECCABLE_HOME:-~/.impeccable}/bin/<version>/`` and writes
``<binary>.verified`` only after the SHA-256 check against the vendored engine-checksums.txt. A binary
without that stamp is never used here. ``$IMPECCABLE_BIN`` is the operator's explicit choice.
"""
from __future__ import annotations

import os
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "impeccable"


def version(skill_dir: Path = SKILL_DIR) -> str:
    try:
        return (skill_dir / "scripts" / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def cached_binary(skill_dir: Path = SKILL_DIR) -> Path | None:
    """The verified engine binary, or None (never a download)."""
    explicit = os.environ.get("IMPECCABLE_BIN")
    if explicit:
        return Path(explicit) if Path(explicit).is_file() else None
    ver = version(skill_dir)
    if not ver:
        return None
    home = Path(os.environ.get("IMPECCABLE_HOME") or Path.home() / ".impeccable")
    binary = home / "bin" / ver / ("impeccable.exe" if os.name == "nt" else "impeccable")
    return binary if binary.is_file() and Path(f"{binary}.verified").is_file() else None


def launcher_argv(skill_dir: Path = SKILL_DIR) -> list[str] | None:
    """argv prefix that runs the vendored launcher on this OS (it fetches the engine when missing).
    Windows: the bare ``.cmd`` path; ``lib.platform.run`` runs a ``.cmd`` target under ``cmd /c``."""
    scripts = skill_dir / "scripts"
    if os.name == "nt":
        cmd = scripts / "impeccable.cmd"
        return [str(cmd)] if cmd.is_file() else None
    sh = scripts / "impeccable"
    return ["sh", str(sh)] if sh.is_file() else None
