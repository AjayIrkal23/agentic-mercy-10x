"""relocation.py — merge-copy the bundle into ``~/.claude`` (split out of ``bootstrap.py``).

Merge-overwrite, never delete: bundle files replace the target's, everything else the user has
stays. On the FIRST install a differing file of the user's own is kept once as ``<name>.pre-install``
(a copy with the original's permissions, dropped again if the overwrite fails). A read-only target gets its bit cleared and one retry; any
file that still cannot be copied (a lock held by antivirus or a running Claude Code, a path past
MAX_PATH) is LISTED, never swallowed, and a failure under a bundle sentinel item stops the install.
Windows copies with ``copyfile`` + ``copystat`` so the zip's Zone.Identifier stream is not inherited.
Pure stdlib.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import stat
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

_SKIP_COPY_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
# sentinel bundle items that prove a complete install is present at the target.
_BUNDLE_ITEMS = ("skills", "hooks", "agents", "rules", "scripts", "installer",
                 "settings.template.json", "install-ui.py")
PRE_INSTALL = ".pre-install"


def missing_items(target: Path) -> list[str]:
    """Bundle sentinels absent at the target (empty list == looks installed)."""
    target = Path(target)
    return [n for n in _BUNDLE_ITEMS if not (target / n).exists()]


def _copy(src: Path, dst: Path) -> None:
    """Windows: ``copyfile`` + ``copystat``. ``copy2`` also copies NTFS alternate streams, so every
    relocated file would inherit the zip's Zone.Identifier (mark of the web)."""
    if plat.IS_WINDOWS:
        shutil.copyfile(src, dst)
        shutil.copystat(src, dst)
    else:
        shutil.copy2(src, dst)


def _put(src: Path, dst: Path, kept: list | None) -> None:
    """Copy src over dst. With ``kept`` (a list: the FIRST install), a dst that already exists with
    DIFFERENT bytes (the user's own CLAUDE.md, a same-named skill or agent) is kept once as
    ``<name>.pre-install`` (copied BEFORE the overwrite, so a failing disk cannot lose the original, and
    deleted again when the overwrite fails: never a copy for a file that was not replaced); an
    existing kept copy is never overwritten. ``kept=None`` (a re-run on a complete install)
    overwrites plainly: the differences are files the installer regenerated. A read-only target
    gets its bit cleared and one retry; a second PermissionError (a lock) propagates."""
    keep, made = dst.with_name(dst.name + PRE_INSTALL), False
    try:
        if kept is not None and dst.is_file() and not dst.is_symlink():
            if not keep.exists() and not filecmp.cmp(src, dst, shallow=False):
                made = True  # the original goes first (with its permissions) and is removed again if it is not replaced
                _copy(dst, keep)
        try:
            _copy(src, dst)
        except PermissionError:
            if not dst.exists():
                raise
            os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
            _copy(src, dst)
    except BaseException:
        if made:
            try:
                os.chmod(keep, stat.S_IREAD | stat.S_IWRITE)  # Windows will not delete a read-only copy
                keep.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    if made:
        kept.append(dst.name)


def _fail(failed: list | None, root: Path | None, path: Path, exc: OSError) -> None:
    if failed is not None:
        rel = Path(path).relative_to(root).as_posix() if root else str(path)
        failed.append((rel, f"{type(exc).__name__}: {exc}"))


def _copy_tree(src: Path, dst: Path, kept: list | None = None, failed: list | None = None,
               root: Path | None = None) -> int:
    """Merge-copy src -> dst, overwriting collisions (on the first install the user's differing
    files are kept as ``*.pre-install``), keeping dst extras. Failures go to ``failed`` as
    ``(path relative to root, error)``."""
    n = 0
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if d not in _SKIP_COPY_DIRS]
        out = dst / Path(dp).relative_to(src)
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _fail(failed, root, out, exc)
            continue
        for fn in fns:
            try:
                _put(Path(dp) / fn, out / fn, kept)
                n += 1
            except OSError as exc:
                _fail(failed, root, out / fn, exc)
    return n


def fatal_failures(failed: list) -> list:
    """The failed copies under a bundle sentinel item: without them the install cannot go on."""
    return [f for f in failed if f[0].split("/")[0] in _BUNDLE_ITEMS]


def relocate(src: Path, target: Path, emit=None, failed: list | None = None) -> int:
    """Move the bundle's content into ~/.claude, replacing bundle files in place.

    User runtime dirs already at the target are preserved (merge, never wipe).
    On the FIRST install (bundle items missing at the target) a differing file of the user's own
    is kept once as ``<name>.pre-install`` (one summary line is printed). Every file that could not
    be copied is appended to ``failed`` and the first five are printed; the status line is ``OK``
    only without failures. Returns the number of files copied."""
    src, target = Path(src), Path(target)
    failed = [] if failed is None else failed
    kept: list[str] | None = [] if missing_items(target) else None
    if emit is None:
        def emit(kind, name, status):  # noqa: E731
            print(f"  [{kind}] {name}: {status}")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    total = 0
    for item in sorted(src.iterdir()):
        if item.name in _SKIP_COPY_DIRS:
            continue
        try:
            if item.resolve() == target.resolve():   # overlap guard
                continue
        except OSError:
            pass
        dest = target / item.name
        if item.is_dir():
            total += _copy_tree(item, dest, kept, failed, target)
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                _put(item, dest, kept)
                total += 1
            except OSError as exc:
                _fail(failed, target, dest, exc)
    if failed:
        emit("relocate", str(target), f"PARTIAL — {total} files replaced, {len(failed)} failed")
        for rel, err in failed[:5]:
            print(f"  failed: {rel}: {err}")
        if len(failed) > 5:
            print(f"  ... and {len(failed) - 5} more")
    else:
        emit("relocate", str(target), f"OK — {total} files replaced into ~/.claude")
    if kept:
        print(f"  Kept {len(kept)} of your files as *{PRE_INSTALL} next to the originals "
              f"(e.g. {', '.join(sorted(set(kept))[:3])}).")
    return total
