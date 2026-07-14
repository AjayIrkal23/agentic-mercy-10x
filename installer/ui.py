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
import verify as _verify   # type: ignore  # noqa: E402
import selfheal as _selfheal  # type: ignore  # noqa: E402
from lib import platform as plat  # type: ignore  # noqa: E402

UI_HTML = _ROOT / "installer" / "ui.html"

_LOCK = threading.Lock()
_JOB: dict = {"running": False, "done": False, "ok": None, "success": None,
              "rounds": 0, "steps": []}
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


def _run_install() -> None:
    """Run the fully-automatic self-heal loop (install -> repair -> re-check until
    0 doctor FAILs). Streams every step into _JOB for the live UI."""
    with _LOCK:
        if _JOB["running"]:
            return
        _JOB.update(running=True, done=False, ok=None, success=None, rounds=0, steps=[])
    try:
        os.environ["CLAUDE_CONFIG_DIR"] = _STATE["target"]
        res = _selfheal.self_heal(Path(_STATE["target"]),
                                  emit=lambda k, n, s: _append(k, n, s))
        with _LOCK:
            _JOB["ok"] = True
            _JOB["success"] = bool(res.get("success"))
            _JOB["rounds"] = int(res.get("rounds", 0))
    except Exception as exc:  # noqa: BLE001
        _append("error", "install", f"FAIL({exc})")
        with _LOCK:
            _JOB["ok"] = False
            _JOB["success"] = False
    finally:
        with _LOCK:
            _JOB.update(running=False, done=True)


def _status_payload() -> dict:
    os.environ["CLAUDE_CONFIG_DIR"] = _STATE["target"]
    env = _detect.detect()
    sections, hard = _verify.collect(env, target=Path(_STATE["target"]))
    return {
        "env": {"os": env.os_name, "python": env.python, "node": env.node,
                "git": bool(env.git), "claude": bool(env.claude_cli),
                "uv": bool(env.uv), "npm": bool(env.npm)},
        "target": _STATE["target"],
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
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        p = self.path.split("?")[0]
        if p == "/api/install":
            # idempotent re-run trigger; the loop self-guards against double-start.
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
    print("  │  Installing automatically…  (Ctrl+C to stop)   │")
    print("  └───────────────────────────────────────────────┘\n")
    # Fully automatic: kick off the self-heal loop on boot so the user does
    # nothing — the browser just watches it run to 100%.
    threading.Thread(target=_run_install, daemon=True).start()
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
