"""Tests for hooks/lib/ollama.py: the learning package's one ollama client.

Every network call is faked through the module seam ``ollama._urlopen``; the only real
socket is a refused connect to a closed local port (test 4).
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HOOKS))
from lib import ollama, platform as plat  # noqa: E402


class _Resp:
    def __init__(self, body: bytes, status: int = 200):
        self._b, self.status = body, status

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def headers(self):
        return {"Content-Type": "application/json"}


def _fake(monkeypatch, body=b"{}", exc=None, record=None):
    def fake(req, timeout=None):
        if record is not None:
            record.append((req.full_url, req.get_method(), req.data, timeout))
        if exc:
            raise exc
        return _Resp(body)
    monkeypatch.setattr(ollama, "_urlopen", fake)


def _http_error(code):
    return urllib.error.HTTPError("http://x/api", code, "nf", {}, None)


def test_host_is_platform_ollama_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    assert ollama.host() == "http://127.0.0.1:9"
    monkeypatch.setenv("OLLAMA_HOST", "192.0.2.10")
    assert ollama.host() == "http://192.0.2.10:11434"
    monkeypatch.setenv("OLLAMA_HOST", "")
    assert ollama.host() == plat.ollama_url()


def test_alive_true_on_any_http_answer(monkeypatch):
    _fake(monkeypatch, body=b'{"models": []}')
    assert ollama.alive() is True
    _fake(monkeypatch, exc=_http_error(404))
    assert ollama.alive() is True


def test_alive_false_on_refused_timeout_or_malfunction(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    for exc in (urllib.error.URLError("refused"), socket.timeout(), TimeoutError(), ValueError("bad url")):
        _fake(monkeypatch, exc=exc)
        assert ollama.alive() is False, exc
    rec: list = []
    _fake(monkeypatch, record=rec)
    ollama.alive()
    ollama.alive(timeout_s=0.2)
    assert rec[0][0] == "http://127.0.0.1:9/api/tags" and rec[0][1] == "GET"
    assert rec[0][3] == 1.5 and rec[1][3] == 0.2


def test_alive_against_a_closed_port_is_quick(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    t0 = time.monotonic()
    assert ollama.alive(timeout_s=1.0) is False
    assert time.monotonic() - t0 < 3.0


def test_chat_posts_the_ollama_shape_and_returns_content(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    body = json.dumps({"message": {"role": "assistant", "content": '[{"text":"x"}]'}, "done": True}).encode()
    rec: list = []
    _fake(monkeypatch, body=body, record=rec)
    msgs = [{"role": "user", "content": "hi"}]
    assert ollama.chat("m", msgs, options={"num_predict": 800}) == '[{"text":"x"}]'
    url, method, data, timeout = rec[0]
    assert url.endswith("/api/chat") and method == "POST"
    assert json.loads(data) == {"model": "m", "messages": msgs, "stream": False,
                                "options": {"temperature": 0, "num_predict": 800}}
    assert timeout == 60.0
    ollama.chat("m", msgs, timeout_s=120)
    assert rec[1][3] == 120


def test_chat_none_on_every_failure(monkeypatch):
    msgs = [{"role": "user", "content": "hi"}]
    cases = [dict(exc=urllib.error.URLError("down")), dict(exc=_http_error(404)), dict(body=b"not json"),
             dict(body=b'{"error": "model not found"}'), dict(body=b'{"message": {"content": ""}}'),
             dict(exc=socket.timeout())]
    for kw in cases:
        _fake(monkeypatch, **kw)
        assert ollama.chat("m", msgs) is None, kw


def test_chat_failure_leaves_one_telemetry_row(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path))
    msgs = [{"role": "user", "content": "SECRET PROMPT"}]
    _fake(monkeypatch, exc=_http_error(404))
    assert ollama.chat("m", msgs) is None
    _fake(monkeypatch, exc=urllib.error.URLError("down"))
    assert ollama.chat("m", msgs) is None
    files = list(tmp_path.glob("hook-fires-*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    rows = [json.loads(ln) for ln in text.splitlines()]
    assert [r["kind"] for r in rows] == ["chat_http_404", "chat_down"]
    assert all(r["link_id"] == "ollama" for r in rows)
    assert "messages" not in text and "SECRET PROMPT" not in text


def test_models_lists_names_or_none(monkeypatch):
    _fake(monkeypatch, body=b'{"models": [{"name": "qwen2.5-coder:3b"}, {"name": "all-minilm:latest"}]}')
    assert ollama.models() == ["qwen2.5-coder:3b", "all-minilm:latest"]
    _fake(monkeypatch, exc=urllib.error.URLError("down"))
    assert ollama.models() is None
    _fake(monkeypatch, body=b"{bad")
    assert ollama.models() is None


def test_no_quota_path_in_source():
    src = (_HOOKS / "lib" / "ollama.py").read_text(encoding="utf-8")
    for bad in ("subprocess", "claude -p", "ANTHROPIC_API_KEY"):
        assert bad not in src, bad
    assert "anthropic" not in src.lower()
