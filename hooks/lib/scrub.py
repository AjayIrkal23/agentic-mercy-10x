"""scrub.py: credential redaction for logs that leave a hook (package learning, docs/LEARNING.md).

``scrub(text)``    credential-looking values -> [REDACTED]; keys and ordinary text stay.
``scrub_obj(obj)`` walks dict/list/str: a value under a credential-named key becomes
                   [REDACTED] whole, every other string goes through ``scrub``.

Sources unified: ECC continuous-learning-v2 observe.sh (key list + 1-8 separator chars +
optional scheme + 8-256 value chars; bounded after a real 100 % CPU incident),
index-lifecycle.py ``_scrub`` and blocking-doc-enforcer.py ``_SECRET_PATTERNS`` (token
shapes). Bounded quantifiers only: linear time on any input. Stdlib only.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
# a key that names a credential: the ECC observe.sh list + index-lifecycle's suffix forms
_KEY = (r"(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|passw(?:or)?d|authorization|credentials?"
        r"|auth(?:[_-]?token)?|token)")
# key <sep>{1,8} [scheme] value{8,256}. Group 1 is the whole name: any [A-Za-z0-9_-] prefix glued to
# the key (AWS_SECRET_ACCESS_KEY, PGPASSWORD, DB_PASSWORD, GITHUB_TOKEN), so env-var names are caught
# and stay visible. The lookbehind starts a match only at the head of a name run (one try per run:
# linear); the trailing `\b` keeps token_store / test_token_refresh / AUTH_TOKEN_TTL / tokenizer intact.
_NAME = r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]*" + _KEY + r")\b"
_KV_RE = re.compile(r"(?i)" + _NAME + r"([\"'\s:=\\]{1,8})((?:bearer|basic|token|bot)\s+)?([A-Za-z0-9_\-/.+=]{8,256})")
# key: "value" / key = 'value' in JSON-ish text where the value may hold other characters
_KV_QUOTED_RE = re.compile(r"(?i)" + _NAME + r"([\"']?\s*[:=]\s*[\"'])([^\"'\n]{8,256})([\"'])")
# well-known token shapes (index-lifecycle + blocking-doc-enforcer, union)
_TOKEN_RE = re.compile(
    r"(?<![\w-])(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|hf_[A-Za-z0-9]{20,}"
    r"|eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*)(?![\w-])")
_URL_CREDS_RE = re.compile(r"(?<=://)[^/\s:@]{1,128}:[^@\s/]{1,256}(?=@)")
_PK = "PRIVATE " + "KEY-----"  # split so no file holds a literal key header
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]{0,40}" + _PK + r"[\s\S]{0,4000}?(?:-----END [A-Z ]{0,40}" + _PK + r"|$)")
_KEY_NAME_RE = re.compile(r"(?i)^(?:[\w-]*(?:" + _KEY + r"))$")


def scrub(text: str) -> str:
    """Credential-looking values -> [REDACTED]; keys and ordinary text stay. Linear time.
    Order: private-key block (its body would otherwise be chopped by the KV rule), URL
    credentials, quoted KV, bare KV, token shapes."""
    if not text:
        return text
    s = _PRIVATE_KEY_RE.sub(REDACTED, text)
    s = _URL_CREDS_RE.sub(REDACTED, s)
    s = _KV_QUOTED_RE.sub(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(4), s)
    s = _KV_RE.sub(lambda m: m.group(1) + m.group(2) + (m.group(3) or "") + REDACTED, s)
    return _TOKEN_RE.sub(REDACTED, s)


def scrub_obj(obj: Any, depth: int = 0) -> Any:
    """Walk dict/list/str (depth <= 6): a value under a credential-named key becomes
    [REDACTED] whole; every other string goes through scrub()."""
    if depth > 6:
        return REDACTED
    if isinstance(obj, dict):
        return {k: (REDACTED if isinstance(k, str) and _KEY_NAME_RE.match(k) else scrub_obj(v, depth + 1))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub_obj(v, depth + 1) for v in obj]
    if isinstance(obj, str):
        return scrub(obj)
    return obj


__all__ = ["scrub", "scrub_obj", "REDACTED"]
