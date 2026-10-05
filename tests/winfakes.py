"""Shared fakes for the Windows base-tool tests (no network, no registry, no process).

``FakeRegistry`` is the ``registry`` seam of ``winpath`` / ``wintools``: get / set / broadcast,
recording every call and the value KIND written (REG_EXPAND_SZ vs REG_SZ). Nothing here imports
``winreg`` or touches the real ``HKCU``.
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import zipfile
from pathlib import Path

import pytest

ENV = "Environment"


@pytest.fixture(autouse=True)
def short_limit(tmp_path, monkeypatch):
    """A7v2-02: the zip extractor's MAX_PATH (240) judged the fixture's absolute path, so a long pytest
    basetemp failed tests that are not about path length (those live in test_safe_fetch_zip). The limit
    here is the temp dir's own length + 200: every fixture entry is far under it, at any basetemp.
    Import into a test module (``from winfakes import short_limit  # noqa: F401``) and it is autouse."""
    import safe_fetch
    monkeypatch.setattr(safe_fetch, "MAX_PATH", len(str(tmp_path)) + 200)


class FakeRegistry:
    def __init__(self, values: dict | None = None, machine: dict | None = None):
        self.values = dict(values or {})  # {(key, name): (value, kind)}
        self.machine = dict(machine or {})  # {name: (value, kind)}: HKLM\...\Environment, read-only
        self.calls: list[tuple] = []

    def get(self, name, key=ENV):
        self.calls.append(("get", key, name))
        return self.values.get((key, name))

    def get_machine(self, name):
        self.calls.append(("get_machine", name))
        return self.machine.get(name)

    def set(self, name, value, kind, key=ENV):
        self.calls.append(("set", key, name, value, kind))
        self.values[(key, name)] = (value, kind)

    def broadcast(self):
        self.calls.append(("broadcast",))

    def sets(self) -> list[tuple]:
        return [c for c in self.calls if c[0] == "set"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class Runs:
    """A ``run`` recorder: ``runs.calls`` is the argv list; ``rc``/``out`` per program name."""

    def __init__(self, rc: dict | None = None, out: dict | None = None, effect=None):
        self.calls: list[list[str]] = []
        self.rc, self.out, self.effect = rc or {}, out or {}, effect

    def __call__(self, argv, **_kw):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if self.effect:
            self.effect(argv)
        key = argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        key = key[:-4] if key.endswith(".exe") else key
        out = self.out.get(key, "")
        out = out(argv, _kw) if callable(out) else out  # a callable sees the call (env, cwd ...)
        return subprocess.CompletedProcess(argv, self.rc.get(key, 0), out, "")


def signature_out(by: dict | None = None, default: str = "Valid\nAnthropic, PBC"):
    """The fake ``powershell`` of the Authenticode probe: ``Status\\nSimpleName`` for the file named in
    ``env['AM_FILE']`` (``by`` maps a file-name suffix to the reply)."""
    def out(_argv, kw):
        f = str((kw.get("env") or {}).get("AM_FILE", ""))
        return next((v for k, v in (by or {}).items() if f.endswith(k)), default)
    return out


class World:
    """A fake Windows profile for ``ensure_wintools``: tools dir (spaces + non-ASCII), home, a
    ``which`` that scans the process PATH like the real one, fake assets whose pinned hashes are
    rewritten into a copy of the manifest, a ``run`` that mimics the installers' side effects."""
    OUT = {"node": "v22.23.3", "claude": "2.1.288 (Claude Code)",
           "powershell": signature_out({"PortableGit-2.56.0-64-bit.7z.exe": "Valid\nJohannes Schindelin"})}

    def __init__(self, tmp_path, manifest: dict, arch: str = "AMD64", real_hashes: bool = False):
        import copy
        import os
        self.os = os
        self.home = tmp_path / "home dir"
        self.tools = self.home / "Jürgen Müller" / "agentic tools"  # inside the profile: no outside-dir warning
        self.env = {"AGENTIC_MERCY_TOOLS_DIR": str(self.tools), "USERPROFILE": str(self.home),
                    "PATH": "", "PROCESSOR_ARCHITECTURE": arch}
        self.manifest = copy.deepcopy(manifest)
        self.registry, self.urls, self.shas, self.found = FakeRegistry(), [], [], {}
        self.blobs: dict[str, bytes] = {}
        win = self.manifest["user_space"]["windows"]
        zips = {"node": {"node-vV/node.exe": b"N", "node-vV/npm.cmd": b"C", "node-vV/node_modules/npm/p.json": b"{}"},
                "uv": {"uv.exe": b"U", "uvx.exe": b"X"}, "gh": {"bin/gh.exe": b"G", "LICENSE": b"L"},
                "ollama": {"ollama.exe": b"O", "lib/ollama/a.dll": b"d"}}
        for tool, cfg in win.items():
            if not isinstance(cfg, dict) or "url" not in cfg:
                continue
            for a, tag in cfg["arch"].items():
                blob = zip_bytes({**zips[tool], f"arch-{a}.txt": b"x"}) if tool in zips else f"{tool}-{a}".encode()
                self.blobs[self._url(cfg, a)] = blob
                if not real_hashes:
                    cfg["sha256"][a] = sha(blob)
        self.runs()

    @staticmethod
    def _url(cfg, a):
        return cfg["url"].format(version=cfg["version"], tag=cfg.get("tag", ""), arch=cfg["arch"][a])

    def which(self, name):
        if name in self.found:
            return self.found[name]
        for d in self.env["PATH"].split(self.os.pathsep):
            for ext in (".exe", ".cmd"):
                if d and (Path(d) / (name + ext)).is_file():
                    return str(Path(d) / (name + ext))
        return None

    def download(self, url, dest, timeout=900, sha256=None, **_k):
        self.urls.append(url)
        self.shas.append(sha256)
        data = self.blobs.get(url, b"fake-not-the-pinned-bytes")
        if sha256 and sha(data) != sha256.lower():
            raise OSError("checksum mismatch — refused")
        Path(dest).write_bytes(data)

    def effect(self, argv):
        """What the real SFX / `claude.exe install` / npm would leave behind."""
        out = next((a[2:] for a in argv if a.startswith("-o")), None)
        if out:  # PortableGit SFX
            for rel in ("bin/bash.exe", "cmd/git.exe", "usr/bin/sh.exe"):
                p = Path(out) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x")
        if len(argv) > 1 and argv[1] == "install":  # claude.exe install <version>
            p = self.home / ".local" / "bin" / "claude.exe"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        if argv[1:4] == ["config", "set", "prefix"] and self.run.rc.get("npm.cmd", 0) == 0:
            self.prefix = argv[4]  # what `npm config set prefix` would persist in ~/.npmrc

    def _npm(self, argv, _kw):
        return self.prefix if argv[1:4] == ["config", "get", "prefix"] else ""

    def runs(self, **kw):
        self.prefix = ""
        self.run = Runs(out={**self.OUT, "npm.cmd": self._npm, **kw.pop("out", {})}, effect=self.effect, **kw)
        return self.run

    def ensure(self, *, ci=False, dry_run=False, **over):
        import wintools
        from types import SimpleNamespace
        args = dict(ci=ci, dry_run=dry_run, run=self.run, download_fn=self.download, which=self.which,
                    registry=self.registry, disk_free=lambda p: 10 ** 12, environ=self.env)
        args.update(over)
        return wintools.ensure_wintools(SimpleNamespace(os_name="windows"), self.manifest, **args)
