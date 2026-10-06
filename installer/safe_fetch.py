"""safe_fetch.py — verified downloads and contained ZIP extraction for the user-space installs.

``download`` takes https URLs only (redirects too), streams to ``<dest>.part``, compares the byte count
with Content-Length (urllib returns a short read without an error), checks a pinned SHA-256 (a given
hash must be 64 hex characters; ``require_hash`` makes it mandatory) and renames only after
that, so a truncated or tampered archive never becomes ``dest``. A rename Windows denies (Defender /
the indexer hold the fresh file open) is retried for ``RENAME_WAIT_S``. ``extract_zip_prefix`` is the
contained ZIP extractor; the tar one lives in ``safe_tar`` (``extract_prefix`` is re-exported here).
Pure stdlib.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib.platform import pid_alive  # noqa: E402
from safe_tar import _escapes, _inside, extract_prefix  # noqa: E402,F401 (re-exported: userspace)

_UA = {"User-Agent": "agentic-mercy-installer"}
RENAME_WAIT_S = 10.0  # how long a denied rename is retried (A5v2-02)


def _open(url: str, timeout: float):
    if not url.startswith(("https://", "http://")):  # urllib would also open file:// and ftp://
        raise ValueError(f"refusing non-http url: {url[:40]}")
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout)  # noqa: S310


class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect may only lead to https (a downgrade to http or another scheme is refused)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError(f"refusing redirect to a non-https url: {newurl[:60]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_https(url: str, timeout: float):
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https url: {url[:40]}")
    opener = urllib.request.build_opener(_HttpsRedirect)
    return opener.open(urllib.request.Request(url, headers=_UA), timeout=timeout)


def fetch(url: str, timeout: float = 60) -> bytes:
    with _open(url, timeout) as r:  # http stays allowed here: the ollama probe is http://127.0.0.1
        return r.read()


def _rename(src, dst) -> None:
    """``os.replace``, retried with backoff while Windows answers PermissionError (a scanner or the
    search indexer holds a freshly written file or directory open) for up to ``RENAME_WAIT_S``."""
    end, pause = time.monotonic() + RENAME_WAIT_S, 0.05
    while True:
        try:
            return os.replace(src, dst)
        except PermissionError:
            if time.monotonic() >= end:
                raise
            time.sleep(pause)
            pause = min(pause * 2, 1.0)


def download(url: str, dest, timeout: float = 900, sha256: str | None = None,
             opener: Callable = _open_https, require_hash: bool = False) -> None:
    """Download ``url`` (https) to ``dest`` or raise OSError (truncated / checksum / no valid pinned
    hash); never leaves a partial. A given ``sha256`` that is not 64 hex characters is refused, not skipped."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https url: {url[:40]}")
    if (require_hash or sha256 is not None) and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256 or ""):
        raise OSError("no valid pinned sha256 for this download — refused")
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
        if sha256 is not None and digest.hexdigest() != sha256.lower():
            raise OSError("checksum mismatch — refused")
        _rename(part, dest)
    finally:
        if part.exists():
            part.unlink()


MAX_PATH = 240  # Windows' 260 minus headroom for what a tool writes under its own dir
_RESERVED = re.compile(r"(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[\d¹²³]|LPT[\d¹²³])(\..*)?$",
                       re.IGNORECASE)


def _bad_zip_part(part: str) -> bool:
    """A name Windows cannot (or must not) create: reserved device, trailing dot/space, a colon
    (drive or NTFS stream)."""
    return bool(_RESERVED.match(part)) or part.endswith((".", " ")) or ":" in part


def _merge_into(tmp: Path, dest: Path) -> None:
    """Move tmp's top-level entries into dest (one rename when dest is new; else replace entry by
    entry, so a half-installed dest is repaired and unrelated files stay)."""
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        _rename(tmp, dest)
        return
    for item in tmp.iterdir():
        target = dest / item.name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
        _rename(item, target)
    shutil.rmtree(tmp, ignore_errors=True)


def _sweep_stale(dest: Path) -> None:
    """Remove leftover ``<dest>.tmp-<pid>`` dirs, but never a live OTHER process's: a second installer
    or the daily self-heal must not delete the extraction another one is in the middle of (A5v2-04)."""
    for stale in dest.parent.iterdir():
        if stale.name.startswith(dest.name + ".tmp-"):
            pid = stale.name.rsplit("-", 1)[-1]
            if not (pid.isdigit() and int(pid) != os.getpid() and pid_alive(int(pid))):
                shutil.rmtree(stale, ignore_errors=True)


def extract_zip_prefix(zf, dest, *, strip: int = 1, only: Callable[[str], bool] | None = None) -> int:
    """Contained zip -> prefix extraction, the same contract as ``extract_prefix``: absolute / drive /
    ``..`` names (either separator), symlink entries and Windows-reserved names are skipped. A file
    whose INSTALLED path would pass ``MAX_PATH`` fails the whole extraction (OSError): skipping it
    would leave a tool without part of itself. Files land in ``<dest>.tmp-<pid>`` and move into
    ``dest`` only after the whole archive is out, so an interrupted extraction never leaves a
    half-installed tool."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    final = Path(os.path.abspath(dest))
    tmp = final.with_name(dest.name + f".tmp-{os.getpid()}")
    _sweep_stale(dest)
    tmp.mkdir()
    root = tmp.resolve()
    n = 0
    try:
        for info in zf.infolist():
            name = info.filename
            parts = PurePosixPath(name.replace("\\", "/")).parts[strip:]
            if (not parts or _escapes(name) or (info.external_attr >> 28) == 0xA
                    or any(_bad_zip_part(p) for p in parts)):
                continue
            rel = Path(*parts)
            if only and not only(rel.as_posix()):
                continue
            out = tmp / rel
            if not _inside(out.parent, root):
                continue
            if len(str(final / rel)) > MAX_PATH:  # the tmp dir adds <= 12 chars of the 20 headroom
                raise OSError(f"path too long for Windows ({MAX_PATH}): {final / rel}; "
                              "use a shorter tools dir or enable LongPathsEnabled")
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as fh:
                shutil.copyfileobj(src, fh)
            n += 1
        _merge_into(tmp, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return n
