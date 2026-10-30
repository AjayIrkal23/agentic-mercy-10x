"""ollama.py: the one ollama client of the learning package (docs/LEARNING.md).

Contract (R3.1):
  host() -> str                                   platform.ollama_url()
  alive(timeout_s=1.5) -> bool                    GET <host>/api/tags; any HTTP answer = True
  chat(model, messages, timeout_s=60, *, options=None) -> str | None
  models(timeout_s=3) -> list[str] | None

stdlib urllib only; the ONLY model backend of the learning package; never the Claude quota.
Tests fake the network through the module seam ``_urlopen``.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

try:
    from lib import platform as _plat
except Exception:  # pragma: no cover - fail-open
    _plat = None

_urlopen = urllib.request.urlopen  # test seam: tests monkeypatch ollama._urlopen
_UA = "claude-workbench-learning/1"
_DEFAULT_OPTIONS = {"temperature": 0}


def host() -> str:
    return _plat.ollama_url() if _plat is not None else "http://127.0.0.1:11434"


def _url(path: str) -> str:
    return host().rstrip("/") + path


def _row(kind: str, **fields: Any) -> None:
    """One telemetry row per failure: the kind and the model, never the prompt."""
    try:
        from lib import hook_telemetry
        hook_telemetry.record("learning", "ollama", kind=kind, **fields)
    except Exception:  # noqa: BLE001
        pass


def alive(timeout_s: float = 1.5) -> bool:
    """True when something answers HTTP at <host>/api/tags (any status). False on refused,
    timeout, DNS, or a malfunction: for learning, an unsure probe DEFERS (the opposite of
    index-lifecycle, where an unsure probe must not freeze indexing)."""
    try:
        req = urllib.request.Request(_url("/api/tags"), method="GET", headers={"User-Agent": _UA})
        with _urlopen(req, timeout=max(0.2, float(timeout_s))):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001 - URLError, socket.timeout, TimeoutError, ValueError
        return False


def models(timeout_s: float = 3.0) -> list[str] | None:
    """Model names from /api/tags (status only); None when down or the reply is not ollama's."""
    try:
        req = urllib.request.Request(_url("/api/tags"), method="GET", headers={"User-Agent": _UA})
        with _urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return [str(m.get("name")) for m in (data.get("models") or []) if isinstance(m, dict) and m.get("name")]
    except Exception:  # noqa: BLE001
        return None


def chat(model: str, messages: list, timeout_s: float = 60.0, *, options: dict | None = None) -> str | None:
    """POST /api/chat (stream=false). The assistant's content, or None when the box is down,
    the call timed out, the model is missing (404), or the reply is not the ollama shape."""
    body = {"model": model, "messages": messages, "stream": False,
            "options": {**_DEFAULT_OPTIONS, **(options or {})}}
    try:
        req = urllib.request.Request(_url("/api/chat"), data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": _UA})
        with _urlopen(req, timeout=float(timeout_s)) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        _row(f"chat_http_{exc.code}", model=model)
        return None
    except Exception as exc:  # noqa: BLE001
        _row("chat_down", model=model, error=type(exc).__name__)
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        _row("chat_bad_json", model=model)
        return None
    if not isinstance(data, dict) or data.get("error"):
        err = str(data.get("error"))[:80] if isinstance(data, dict) else "shape"
        _row("chat_error", model=model, error=err)
        return None
    msg = data.get("message")
    content = (msg.get("content") or "") if isinstance(msg, dict) else ""
    if not str(content).strip():
        _row("chat_empty", model=model)
        return None
    return str(content)


__all__ = ["host", "alive", "models", "chat"]
