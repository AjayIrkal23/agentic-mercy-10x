"""safe_fetch.py — verified downloads and contained tar extraction for the user-space installs.

``download`` streams to ``<dest>.part``, compares the byte count with Content-Length (urllib
returns a short read without an error), checks a pinned SHA-256 when given, and renames only after
that, so a truncated or tampered archive never becomes ``dest``. ``extract_prefix`` unpacks into a
prefix and refuses anything that would land outside it: absolute / ``..`` names, a member whose parent
resolves outside through a symlink created earlier in the same archive, symlinks and hardlinks that
point out (the stdlib ``data`` filter, where this Python has one, vets each member too). Pure stdlib.
"""
from __future__ import annotations

import copy
import hashlib
import os
import shutil
import stat
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

_UA = {"User-Agent": "agentic-mercy-installer"}


def _open(url: str, timeout: float):
    if not url.startswith(("https://", "http://")):  # urllib would also open file:// and ftp://
        raise ValueError(f"refusing non-http url: {url[:40]}")
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout)  # noqa: S310


def fetch(url: str, timeout: float = 60) -> bytes:
    with _open(url, timeout) as r:
        return r.read()


def download(url: str, dest, timeout: float = 900, sha256: str | None = None,
             opener: Callable = _open) -> None:
    """Download ``url`` to ``dest`` or raise OSError (truncated / checksum); never leaves a partial."""
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        with opener(url, timeout) as r, open(part, "wb") as out:
            want = r.headers.get("Content-Length")
            digest, got = hashlib.sha256(), 0
            for chunk in iter(lambda: r.read(1 << 20), b""):
                out.write(chunk)
                digest.update(chunk)
                got += len(chunk)
        if want and got != int(want):
            raise OSError(f"download truncated: {got} of {want} bytes")
        if sha256 and digest.hexdigest() != sha256.lower():
            raise OSError("checksum mismatch — refused")
        os.replace(part, dest)
    finally:
        if part.exists():
            part.unlink()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def _absolute(name: str) -> bool:
    """Tar names are POSIX: on Windows `Path("/abs/x").is_absolute()` is False (no drive),
    so judge them as POSIX, plus any drive (`C:x`) or backslash root."""
    return PurePosixPath(name.replace("\\", "/")).is_absolute() or bool(PureWindowsPath(name).drive)


def _escapes(name: str) -> bool:
    """A member or hardlink name that is absolute or climbs (`..`, either separator)."""
    return _absolute(name) or ".." in PurePosixPath(name.replace("\\", "/")).parts


def _vet(m: tarfile.TarInfo, rel: Path, strip: int, dest: Path) -> bool:
    """The stdlib ``data`` filter's verdict on the member as it would be written (3.12+, and the
    3.10.12 / 3.11.4 backports); always True where the filter does not exist."""
    flt = getattr(tarfile, "data_filter", None)
    if flt is None:
        return True
    c = copy.copy(m)
    c.name = rel.as_posix()
    if m.islnk():
        c.linkname = Path(*Path(m.linkname).parts[strip:]).as_posix() if Path(m.linkname).parts[strip:] else ""
    try:
        flt(c, str(dest))
        return True
    except tarfile.FilterError:
        return False


def extract_prefix(tar: tarfile.TarFile, dest, *, strip: int = 1, skip_top_files: bool = True,
                   only: Callable[[str], bool] | None = None) -> int:
    """Contained tar -> prefix extraction (see the module docstring). Returns the file count."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    n = 0
    for m in tar:
        parts = PurePosixPath(m.name).parts[strip:]
        if not parts or _escapes(m.name):
            continue
        rel = Path(*parts)
        if skip_top_files and len(parts) == 1 and not m.isdir():
            continue
        if only and not only(rel.as_posix()):
            continue
        out = dest / rel
        if not _inside(out.parent, root) or not _vet(m, rel, strip, dest):
            continue
        if m.isdir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if m.issym():
            if _absolute(m.linkname) or not _inside(out.parent / m.linkname, root):
                continue
        elif m.islnk():
            lparts = PurePosixPath(m.linkname).parts[strip:]
            if not lparts or _escapes(m.linkname):
                continue
            target = dest / Path(*lparts)
            if not _inside(target, root) or not target.is_file():
                continue
        elif not m.isfile():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.is_symlink() or out.exists():
            out.unlink()
        if m.issym():
            os.symlink(m.linkname, out)
        elif m.islnk():
            try:
                os.link(target, out)
            except OSError:
                shutil.copy2(target, out)
        else:
            src = tar.extractfile(m)
            if src is None:
                continue
            with open(out, "wb") as fh:
                shutil.copyfileobj(src, fh)
            out.chmod((stat.S_IMODE(m.mode) & 0o777) or 0o644)
        n += 1
    return n
