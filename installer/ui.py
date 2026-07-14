#!/usr/bin/env python3
"""ui.py — the VISUAL installer server (`python install.py ui`).

A stdlib-only local web app: starts an http.server on 127.0.0.1:<free-port>, serves
installer/ui.html, opens your browser, and exposes a small JSON API backed by the
SAME engine as the CLI (detect / deps / verify). No Electron, no Node build, no
extra installs — identical on Ubuntu and Windows.

API:
  GET  /                -> ui.html
  GET  /api/status      -> {env, target, candidates, sections, hard}   (live workflow status)
  GET  /api/browse      -> native folder picker (subprocess tkinter; graceful fallback)
  GET  /api/progress    -> the running install job {running, done, ok, steps[]}
  POST /api/target {path}   -> validate + select the .claude folder to install into
  POST /api/install     -> start the real install in a background thread

Every install step streams into /api/progress so the UI shows them one-by-one.
settings.json is rendered ONLY when absent (an existing one is never overwritten).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect as _detect   # type: ignore  # noqa: E402
import deps as _deps       # type: ignore  # noqa: E402
import verify as _verify   # type: ignore  # noqa: E402
from lib import platform as plat  # type: ignore  # noqa: E402

UI_HTML = _ROOT / "installer" / "ui.html"

_LOCK = threading.Lock()
_JOB: dict = {"running": False, "done": False, "ok": None, "steps": []}
_STATE: dict = {"target": str(plat.claude_dir())}


def _status_norm(status_str: str) -> str:
    u = status_str.upper()
    if "MISSING" in u or "FAIL(" in u or u == "FAIL":
        return "fail"
    if u.startswith("WARN") or "WOULD" in u or "SKIP" in u or "MANUAL" in u:
        return "warn"
    return "ok"  # PRESENT / INSTALLED / ADDED / OK / kept


def _append(kind: str, name: str, status_str: str) -> None:
    with _LOCK:
        _JOB["steps"].append({
            "kind": kind, "name": name,
            "status": _status_norm(status_str), "detail": status_str,
            "ts": round(time.time(), 2),
        })


def _candidate_paths() -> list:
    out, seen = [], set()
    for p in (os.environ.get("CLAUDE_CONFIG_DIR"),
              str(Path("~/.claude").expanduser()),
              str(_ROOT),
              str(Path.home() / ".claude")):
        if p and p not in seen and Path(p).is_dir():
            seen.add(p)
            out.append(p)
    return out


def _run_install() -> None:
    with _LOCK:
        if _JOB["running"]:
            return
        _JOB.update(running=True, done=False, ok=None, steps=[])
    try:
        os.environ["CLAUDE_CONFIG_DIR"] = _STATE["target"]
        env = _detect.detect()
        for n, s in _deps.check_prereqs(env):
            _append("prereq", n, s)
        for n, s in _deps.install_deps(env):
            _append("dep", n, s)
        for n, s in _deps.register_mcps(env):
            _append("mcp", n, s)
        for n, s in _deps.install_plugins(env):
            _append("plugin", n, s)
        st = Path(_STATE["target"]) / "settings.json"
        if not st.exists():
            try:
                import render  # type: ignore
                plat.atomic_write(st, render.render(subs=env.tokens))
                _append("settings", "settings.json", "INSTALLED")
            except Exception as exc:  # noqa: BLE001
                _append("settings", "settings.json", f"WARN({exc})")
        else:
            _append("settings", "settings.json", "PRESENT (kept — not overwritten)")
        for n, s in _deps.run_post_steps(env):
            _append("post", n, s)
        with _LOCK:
            _JOB["ok"] = True
    except Exception as exc:  # noqa: BLE001
        _append("error", "install", f"FAIL({exc})")
        with _LOCK:
            _JOB["ok"] = False
    finally:
        with _LOCK:
            _JOB.update(running=False, done=True)


def _browse() -> dict:
    """Native folder picker in an isolated subprocess (no tkinter threading issues).
    Fails gracefully to a hint when tkinter / a display is unavailable."""
    code = (
        "import tkinter, tkinter.filedialog as fd\n"
        "r = tkinter.Tk(); r.withdraw()\n"
        "try:\n r.attributes('-topmost', True)\nexcept Exception:\n pass\n"
        "print(fd.askdirectory(title='Select your .claude folder') or '')\n"
    )
    cp = plat.run([sys.executable, "-c", code], timeout=180)
    if cp.returncode == 0:
        return {"path": (cp.stdout or "").strip()}
    return {"error": "no native folder picker here (tkinter/display unavailable) — type the path instead"}


def _status_payload() -> dict:
    os.environ["CLAUDE_CONFIG_DIR"] = _STATE["target"]
    env = _detect.detect()
    sections, hard = _verify.collect(env, target=Path(_STATE["target"]))
    return {
        "env": {"os": env.os_name, "python": env.python, "node": env.node,
                "git": bool(env.git), "claude": bool(env.claude_cli),
                "uv": bool(env.uv), "npm": bool(env.npm)},
        "target": _STATE["target"],
        "candidates": _candidate_paths(),
        "sections": sections,
        "hard": hard,
    }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        b = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):  # noqa: N802
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            try:
                self._send(200, UI_HTML.read_bytes(), "text/html; charset=utf-8")
            except Exception as exc:  # noqa: BLE001
                self._send(500, f"ui.html missing: {exc}", "text/plain")
        elif p == "/api/status":
            try:
                self._json(_status_payload())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
        elif p == "/api/progress":
            with _LOCK:
                self._json(dict(_JOB))
        elif p == "/api/browse":
            self._json(_browse())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        p = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            data = {}
        if p == "/api/target":
            path = str(data.get("path", "")).strip()
            cand = Path(path).expanduser() if path else None
            if cand and cand.is_dir():
                _STATE["target"] = str(cand)
                self._json({"ok": True, "target": _STATE["target"]})
            else:
                self._json({"ok": False, "error": "that folder does not exist"}, 400)
        elif p == "/api/install":
            threading.Thread(target=_run_install, daemon=True).start()
            self._json({"started": True})
        else:
            self._json({"error": "not found"}, 404)


def main(argv=None) -> int:
    if not UI_HTML.is_file():
        print(f"ui.html not found at {UI_HTML}", file=sys.stderr)
        return 1
    host = "127.0.0.1"
    srv = ThreadingHTTPServer((host, 0), _Handler)
    port = srv.server_address[1]
    url = f"http://{host}:{port}/"
    print("\n  ┌───────────────────────────────────────────────┐")
    print(f"  │  Visual installer:  {url:<26}│")
    print("  │  Opening your browser…  (Ctrl+C here to stop)  │")
    print("  └───────────────────────────────────────────────┘\n")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
