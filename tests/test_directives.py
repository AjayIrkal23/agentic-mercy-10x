"""Every standing directive stays in the always-on prompt (docs/DIRECTIVES.md).

TEXT and SOFT rows: each sentence_key must sit in a file the harness loads every session
(CLAUDE.md, rules/0*.md, output-styles/caveman.md, the imported part of the machines
file, the session-start aggregator sample). HOOK rows: the first backticked code path in
`mechanism` must exist. `docs/**` is never searched, so the checklist cannot satisfy
itself. Env DIRECTIVES_ROOT (relative to the repo or absolute) = a drafts dir whose
`<rel>.draft` files replace the root files (pre-integrate mode).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
STRENGTHS = {"TEXT", "SOFT", "HOOK"}
ALWAYS_ON = ["CLAUDE.md", "rules/00-tool-precedence.md", "rules/01-no-shell-writes.md",
             "rules/02-lifecycle.md", "rules/03-thinking.md", "rules/04-model-routing.md",
             "output-styles/caveman.md"]
COLUMNS = ["#", "directive", "sentence_key", "source", "mechanism", "strength"]
_PATH_RE = re.compile(r"`([^`\s]*(?:\.py|\.ts|\.json|\.gitignore))(?:::[^`]*)?`")


def norm(s: str) -> str:  # same rule as split_machines_file.norm
    return " ".join(s.replace("`", "").replace("*", "").split())


def _cells(row: str) -> list[str]:
    s = row.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    cells, cur, code = [], [], False
    for ch in s:
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def load_directives(path: Path) -> list[dict]:
    """Rows of the first Markdown table with the six columns. Raises ValueError on a duplicate
    or non-contiguous id, an unknown strength, or a TEXT/SOFT row without a key."""
    rows, in_table = [], False
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.lstrip().startswith("|"):
            if in_table:
                break
            continue
        cells = _cells(ln)
        if not in_table:
            in_table = cells == COLUMNS
            continue
        if set(ln.replace("|", "").strip()) <= {"-", ":", " "}:
            continue
        if len(cells) != len(COLUMNS):
            raise ValueError(f"row has {len(cells)} cells: {ln}")
        row = dict(zip(COLUMNS, cells))
        keys = [k.strip() for span in re.findall(r"`([^`]*)`", row["sentence_key"])
                for k in span.split(" || ") if k.strip()]
        rows.append({"id": int(row["#"]), "directive": row["directive"], "keys": keys,
                     "source": row["source"], "mechanism": row["mechanism"], "strength": row["strength"]})
    for want, r in enumerate(rows, 1):
        if r["id"] != want:
            raise ValueError(f"row ids must run 1..N without gaps; got {r['id']} at position {want}")
        if r["strength"] not in STRENGTHS:
            raise ValueError(f"row {r['id']}: unknown strength {r['strength']!r}")
        if r["strength"] in ("TEXT", "SOFT") and not r["keys"]:
            raise ValueError(f"row {r['id']}: {r['strength']} row without a sentence_key")
    return rows


def resolve(root: Path, rel: str, drafts: Path | None) -> Path | None:
    """<drafts>/<rel>.draft when it exists, else <root>/<rel> when it exists, else None."""
    if drafts is not None and (drafts / f"{rel}.draft").is_file():
        return drafts / f"{rel}.draft"
    return root / rel if (root / rel).is_file() else None


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def machines_text(root: Path) -> str:
    """Imported part (after an in-memory split) of the first existing machines file."""
    for cand in (root / "CLAUDE.machines.local.md", _claude_dir() / "CLAUDE.machines.local.md",
                 root / "tests" / "fixtures" / "machines.sample.md"):
        if cand.is_file():
            try:
                mod = _load("split_machines_file_dt", root / "scripts" / "split_machines_file.py")
                return mod.split_text(cand.read_bytes().decode("utf-8").replace("\r\n", "\n"))[0]
            except Exception:  # noqa: BLE001 — a tmp root has no script
                return ""
    return ""


def aggregator_sample(root: Path) -> str:
    """additionalContext of a doctor-mode session-start aggregator run; '' on any failure."""
    script = root / "hooks" / "session-start-aggregator.py"
    if not script.is_file():
        return ""
    try:
        r = subprocess.run([sys.executable, str(script)], shell=False, encoding="utf-8", capture_output=True,
                           input=json.dumps({"session_id": "directives", "cwd": str(root), "source": "startup"}),
                           env={**os.environ, "CLAUDE_HOOK_DOCTOR": "1"}, timeout=20)
        data = json.loads(r.stdout or "{}")
        ctx = data.get("additionalContext") or (data.get("hookSpecificOutput") or {}).get("additionalContext")
        return ctx if isinstance(ctx, str) else ""
    except Exception:  # noqa: BLE001
        return ""


def corpus(root: Path, drafts: Path | None) -> dict[str, str]:
    out = {}
    for rel in ALWAYS_ON:
        p = resolve(root, rel, drafts)
        if p is not None:
            out[rel] = norm(p.read_text(encoding="utf-8"))
    out["machines"] = norm(machines_text(root))
    out["aggregator"] = norm(aggregator_sample(root))
    return out


def check(root: Path, directives: Path, drafts: Path | None, strict_keys: bool = False) -> list[str]:
    rows = load_directives(directives)
    texts = corpus(root, drafts)
    fails = []
    for r in rows:
        if r["strength"] in ("TEXT", "SOFT") or (strict_keys and r["keys"]):
            for k in r["keys"]:
                if not any(norm(k) in t for t in texts.values()):
                    fails.append(f'row {r["id"]} ({r["directive"]}): key "{k}" not in any always-on file')
        if r["strength"] == "HOOK":
            m = _PATH_RE.search(r["mechanism"])
            if m and not (root / m.group(1)).exists():
                fails.append(f"row {r['id']}: mechanism path {m.group(1)} missing")
    return fails


def _drafts() -> Path | None:
    env = os.environ.get("DIRECTIVES_ROOT")
    if not env:
        return None
    p = Path(env)
    return p if p.is_absolute() else _ROOT / p


DIRECTIVES = _ROOT / "docs" / "DIRECTIVES.md"


def test_table_parses():
    rows = load_directives(DIRECTIVES)
    assert [r["id"] for r in rows] == list(range(1, 33))
    assert all(r["strength"] in STRENGTHS for r in rows)
    assert all(r["keys"] for r in rows if r["strength"] in ("TEXT", "SOFT"))


def test_every_directive_is_loaded():
    fails = check(_ROOT, DIRECTIVES, _drafts())
    assert fails == [], "\n".join(fails)


def test_text_key_only_under_docs_fails(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("nothing here\n", encoding="utf-8")
    (tmp_path / "rules").mkdir()
    (tmp_path / "docs").mkdir()
    d = tmp_path / "docs" / "DIRECTIVES.md"
    d.write_text("| # | directive | sentence_key | source | mechanism | strength |\n|---|---|---|---|---|---|\n"
                 "| 1 | docs only | `only in docs` | CLAUDE.md | text | TEXT |\n", encoding="utf-8")
    (tmp_path / "docs" / "notes.md").write_text("only in docs\n", encoding="utf-8")
    fails = check(tmp_path, d, None)
    assert len(fails) == 1 and fails[0].startswith("row 1 ")


def test_hook_rows_name_existing_files():
    fails = [f for f in check(_ROOT, DIRECTIVES, _drafts()) if "mechanism path" in f]
    assert fails == [], "\n".join(fails)
    hook_rows = [r for r in load_directives(DIRECTIVES) if r["strength"] == "HOOK"]
    assert all(_PATH_RE.search(r["mechanism"]) for r in hook_rows)


def test_machines_corpus_is_the_imported_part():
    text = machines_text(_ROOT)
    assert "without my explicit word" in text
    assert "machines-split:tail" not in text


def test_docs_never_searched():
    assert not any(label.startswith("docs/") for label in corpus(_ROOT, _drafts()))


def test_aggregator_sample_bounded():
    sample = aggregator_sample(_ROOT)
    if not sample:
        pytest.skip("aggregator produced no sample in this environment")
    assert len(sample) <= 5500
