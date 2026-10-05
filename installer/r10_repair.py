"""r10_repair.py — R10 line-ending repair for the self-heal loop (the "47 HARD" fix).

Split out of selfheal.py (250-line limit); selfheal re-exports ``worktree_is_clean`` and
``git_restore_worktree`` for bootstrap.py. See selfheal.py's docstring for the why.
Pure stdlib.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402


def _git_clean(root: Path, pathspec: str) -> bool:
    """True iff ``git status --porcelain -- <pathspec>`` ran and printed nothing."""
    st = plat.run(["git", "-C", str(root), "status", "--porcelain", "--", pathspec], timeout=60)
    return st.returncode == 0 and not (st.stdout or "").strip()


def _git_restore_clean(root: Path, pathspec: str) -> bool:
    """``checkout -- <pathspec>`` with the exact committed bytes, ONLY when that
    pathspec is clean — a checkout over local edits would discard them."""
    if not _git_clean(root, pathspec):
        return False
    cp = plat.run(["git", "-C", str(root), "-c", "core.autocrlf=false",
                   "checkout", "--", pathspec], timeout=180)
    return cp.returncode == 0


def worktree_is_clean(root: Path) -> bool:
    """True iff ``root`` is a git checkout with no uncommitted change at all."""
    root = Path(root)
    return (root / ".git").exists() and bool(shutil.which("git")) and _git_clean(root, ".")


def git_restore_worktree(root: Path) -> bool:
    """PRIMARY R10 fix: restore a CLEAN clone to its pristine committed bytes.

    Uses the git object store, so files land exactly as committed (correct for
    dirs that mix LF and CRLF). Returns False (no-op) when the target is not a
    git checkout, git is unavailable, the tree has ANY uncommitted change (a
    ``checkout -- .`` would discard it), or ``root`` is this very repo
    (``_ROOT``, src == target) — the live workbench is never reset."""
    root = Path(root)
    if not (root / ".git").exists() or not shutil.which("git"):
        return False
    if root.resolve() == _ROOT:
        return False
    return _git_restore_clean(root, ".")


def _norm_bytes(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def repair_r10_drift(target: Path) -> int:
    """FALLBACK R10 fix (safe): for each locked content-hash skill dir whose hash
    currently mismatches its baseline, normalize CRLF->LF and KEEP it only if the
    dir then matches the baseline; otherwise revert. Never corrupts a dir. Returns
    the number of dirs healed."""
    try:
        import skills_lib as sl  # type: ignore
    except Exception:  # noqa: BLE001
        return 0
    prov_path = Path(target) / "hooks" / "skills-provenance.json"
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return 0
    healed = 0
    for name, meta in prov.items():
        if name.startswith("_") or not isinstance(meta, dict):
            continue
        if meta.get("hashBasis") != "content-hash":
            continue
        d = sl.SKILLS_DIR / name
        baseline = meta.get("baselineHash")
        if not d.is_dir() or not baseline:
            continue
        if sl.dir_content_hash(d) == baseline:
            continue  # already correct
        snap: dict[Path, bytes] = {}
        for fp in d.rglob("*"):
            if not fp.is_file():
                continue
            try:
                b = fp.read_bytes()
            except OSError:
                continue
            if b"\x00" in b or b"\r" not in b:
                continue
            snap[fp] = b
            try:
                fp.write_bytes(_norm_bytes(b))
            except OSError:
                pass
        if sl.dir_content_hash(d) == baseline:
            healed += 1
        else:
            for fp, b in snap.items():  # normalize didn't match baseline — revert
                try:
                    fp.write_bytes(b)
                except OSError:
                    pass
    return healed


def _locked_skill_names(target: Path) -> list[str]:
    """Names of the locked (vendored) skills: ``hooks/skills-sources.json`` when
    present (WP-9), else the legacy ``hooks/skills-provenance.json`` keys."""
    for rel in ("hooks/skills-sources.json", "hooks/skills-provenance.json"):
        try:
            data = json.loads((Path(target) / rel).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            return [n for n, m in data.items() if not n.startswith("_") and isinstance(m, dict)]
    return []


def heal_line_endings(target: Path, emit) -> None:
    # Never `checkout -- .` here: restore ONLY locked skill dirs that are clean,
    # one pathspec at a time, so no local edit anywhere can be discarded.
    target = Path(target)
    if (target / ".git").exists() and shutil.which("git"):
        healed = [n for n in _locked_skill_names(target)
                  if (target / "skills" / n).is_dir() and _git_restore_clean(target, f"skills/{n}")]
        if healed:
            emit("repair", "git-restore", f"OK ({len(healed)} clean locked skill dirs)")
    n = repair_r10_drift(target)
    if n:
        emit("repair", "line-endings", f"OK ({n} skill dirs healed)")
