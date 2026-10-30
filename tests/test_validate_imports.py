"""validate_imports.py (grep gate G7): classes U P V W S M over vendored/imported text."""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
FIX = _ROOT / "tests" / "fixtures" / "validate_imports"


def _mod():
    spec = importlib.util.spec_from_file_location("validate_imports", _ROOT / "scripts" / "validate_imports.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


VI = _mod()

# Secret-shaped strings are assembled here so no tracked file holds one (gitleaks, the write guard).
_SECRETS = "\n".join([
    "aws " + "AKIA" + "ABCDEFGHIJKLMNOP",
    "gh " + "ghp_" + "a" * 36,
    "-----BEGIN " + "RSA PRIVATE " + "KEY-----",
    'password: "' + "hunter2" * 2 + '"',
    "key " + "sk-ant-" + "api03-" + "x" * 20,
    'password: "<fill-me>"',
    'token = "${TOKEN}"',
]) + "\n"


def _bad(tmp_path: Path) -> Path:
    dst = tmp_path / "bad"
    shutil.copytree(FIX / "bad", dst)
    (dst / "secrets.txt").write_text(_SECRETS, encoding="utf-8", newline="\n")
    return dst


@pytest.fixture(autouse=True)
def _no_shipped_allowlist(request, monkeypatch):
    """Fixture tests must not depend on the shipped allowlist; only the shipped-allowlist test reads it."""
    if "shipped" not in request.node.name:
        monkeypatch.setattr(VI, "_ALLOW", ())


def test_clean_tree_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(VI, "_DEFAULT_TERMS", tmp_path / "absent.json")
    assert VI.scan([FIX / "clean"]) == []
    assert VI.main([str(FIX / "clean")]) == 0


def test_each_bad_class_is_reported_once_per_line(tmp_path):
    found = VI.scan([_bad(tmp_path)], terms=["example-box-01"])
    assert Counter(f["cls"] for f in found) == {"U": 3, "P": 3, "V": 3, "W": 2, "S": 5, "M": 5}
    lines = {(Path(f["file"]).name, f["line"]) for f in found}
    assert ("machine.txt", 6) not in lines and ("machine.txt", 7) not in lines
    assert ("unpinned.txt", 4) not in lines
    assert ("secrets.txt", 6) not in lines and ("secrets.txt", 7) not in lines
    assert {f["line"] for f in found if f["cls"] == "U"} == {1, 2, 3}


def test_json_report_shape(tmp_path, capsys):
    bad = _bad(tmp_path)
    rc = VI.main(["--json", "--terms", str(tmp_path / "none.json"), str(bad)])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 1
    assert set(data) == {"findings", "counts"}
    for f in data["findings"]:
        assert set(f) == {"cls", "file", "line", "rule", "excerpt"}
        assert len(f["excerpt"]) <= 80
    for secret in ("hunter2hunter2", "AKIA" + "ABCDEFGHIJKLMNOP", "ghp_" + "a" * 36, "x" * 20):
        assert secret not in out
    s_ex = [f["excerpt"] for f in data["findings"] if f["cls"] == "S"]
    assert any(e.startswith('password: ***') for e in s_ex)


def test_machine_terms_file_is_optional_and_case_insensitive(tmp_path, monkeypatch):
    bad = _bad(tmp_path)
    terms = tmp_path / "terms.json"
    terms.write_text(json.dumps({"terms": ["Example-Box-01"]}), encoding="utf-8")
    hits = [f for f in VI.scan([bad], classes={"M"}, terms=VI.load_terms(terms))]
    assert any(f["rule"] == "machine-term:1" for f in hits)
    assert all("example-box" not in f["excerpt"].lower() for f in hits)
    monkeypatch.setattr(VI, "_DEFAULT_TERMS", tmp_path / "absent.json")
    rules = sorted(f["rule"] for f in VI.scan([bad], classes={"M"}))
    assert rules == ["ptyxis-spawn", "rfc1918", "rfc1918", "rfc1918"]


def test_gitignored_files_are_skipped_inside_a_work_tree(tmp_path, monkeypatch):
    import subprocess
    tree = tmp_path / "t"
    (tree / "sub").mkdir(parents=True)
    bad = "x = '/home/" + "someone/secret/path'\n"
    (tree / "sub" / "ignored.md").write_text(bad, encoding="utf-8")
    (tree / ".gitignore").write_text("sub/ignored.md\n", encoding="utf-8")
    assert VI.scan([tree / "sub"]) != []                       # no .git: reported
    subprocess.run(["git", "init", "-q", str(tree)], check=True, capture_output=True)
    assert VI.scan([tree / "sub"]) == []                       # ignored in a work tree: skipped
    monkeypatch.setattr(VI, "RESPECT_GITIGNORE", False)
    assert VI.scan([tree / "sub"]) != []                       # --no-gitignore


def test_binary_and_excluded_dirs_are_skipped(tmp_path):
    bidi = "\u202e"
    for rel in ("node_modules/x.txt", ".git/x", "__pycache__/a.pyc"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(bidi, encoding="utf-8")
    (tmp_path / "big.txt").write_text(bidi + "a" * (3 * 1024 * 1024), encoding="utf-8")
    (tmp_path / "img.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00" + bidi.encode("utf-8"))
    assert VI.scan([tmp_path]) == []


def test_personal_path_placeholders_allowed(tmp_path):
    home, users = "/" + "home/", "/" + "Users/"
    text = "\n".join([home + "user/x", home + "username/x", home + "<user>/x", home + ".../x",
                      users + "<you>/x", "$HOME/x", "~/x", "https://github.com/user/repo"]) + "\n"
    (tmp_path / "p.txt").write_text(text, encoding="utf-8")
    assert VI.scan([tmp_path], classes={"P"}) == []


def test_class_filter(tmp_path, capsys):
    rc = VI.main(["--class", "U,P", "--json", str(_bad(tmp_path))])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert {f["cls"] for f in data["findings"]} == {"U", "P"}


def test_missing_path_is_usage_error(tmp_path):
    assert VI.main([str(tmp_path / "nope")]) == 2


def test_vendored_upstream_header_skips_prose_rules_only(tmp_path):
    body = "\n".join(["<!-- ecc:skills/x/SKILL.md@" + "a" * 40 + " -->", "vlan 192.168.10.1",
                      "terminal ptyxis-spawn", "avoid `pkg@latest`", 'password = "hunter2hunter2"',
                      "key " + "AKIA" + "ABCDEFGHIJKLMNOP", "/" + "home/alice/x"]) + "\n"
    (tmp_path / "v.md").write_text(body, encoding="utf-8")
    rules = [f["rule"] for f in VI.scan([tmp_path], terms=[])]
    assert rules == ["ptyxis-spawn", "aws-key", "home-path"]


def test_dot_claude_sidecar_dirs_are_skipped(tmp_path):
    d = tmp_path / "t"
    (d / ".claude" / "x").mkdir(parents=True)
    (d / ".claude" / "x" / "a.json").write_text('"/' + 'home/someone/.claude"', encoding="utf-8")
    (d / "ok.md").write_text("fine\n", encoding="utf-8")
    assert VI.scan([d]) == []


def test_dot_state_hook_residue_is_skipped(tmp_path):
    """hooks/.state is gitignored runtime state; a session breadcrumb holds the workspace path (JUDGE-FIX G3)."""
    d = tmp_path / "hooks"
    (d / ".state" / "index").mkdir(parents=True)
    (d / ".state" / "abc.breadcrumb.json").write_text('{"workspace": "/' + 'home/someone/CODE_FILES/x"}', encoding="utf-8")
    (d / ".state" / "index" / "r.json").write_text('"/' + 'home/someone/.claude"', encoding="utf-8")
    (d / "ok.py").write_text("fine\n", encoding="utf-8")
    assert VI.scan([d]) == []
    assert VI.scan([tmp_path]) == []


def test_allowlist_drops_named_rules_per_path_glob(tmp_path, capsys):
    d = tmp_path / "t"
    (d / "skills" / "x").mkdir(parents=True)
    (d / "hooks" / "tests").mkdir(parents=True)
    (d / "skills" / "x" / "SKILL.md").write_text("npx shadcn" + "@latest add button\n", encoding="utf-8")
    (d / "hooks" / "tests" / "t.py").write_text("unit = 'ptyxis-" + "spawn-aaaa.scope'\n", encoding="utf-8")
    (d / "other.md").write_text("npx shadcn" + "@latest add\n", encoding="utf-8")
    allow = {"schema": 1, "allow": [{"path": "skills/**", "rules": ["at-latest", "npx-unpinned"], "why": "upstream"},
                                    {"path": "hooks/tests/**", "rules": ["ptyxis-spawn"], "why": "OOM fixtures"}]}
    f = tmp_path / "allow.json"
    f.write_text(json.dumps(allow), encoding="utf-8")
    found = VI.scan([d], allow=VI.load_allowlist(f), root=d)
    assert [(Path(x["file"]).name, x["rule"]) for x in found] == [("other.md", "at-latest")]
    assert VI.main([str(d), "--allowlist", str(f), "--root", str(d)]) == 1
    assert VI.main([str(d / "skills"), str(d / "hooks"), "--allowlist", str(f), "--root", str(d)]) == 0
    assert "(2 allowlisted)" in capsys.readouterr().out
    assert VI.main([str(d / "skills"), "--no-allowlist", "--root", str(d)]) == 1


def test_allowlist_star_glob_rules_and_missing_file(tmp_path):
    assert VI.load_allowlist(tmp_path / "absent.json") == []  # absent -> no allow, never an error
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    assert VI.load_allowlist(tmp_path / "bad.json") == []
    allow = [{"path": "docs/archive/**", "rules": ["*"]}]
    assert VI._allowed("docs/archive/2026/a.md", "at-latest", allow) is True
    assert VI._allowed("docs/a.md", "at-latest", allow) is False
    assert VI._allowed("docs/archive/a.md", "home-path", [{"path": "docs/archive/**", "rules": ["at-latest"]}]) is False
    assert VI._allowed("a\\b.py", "unicode-feff", [{"path": "a/b.py", "rules": ["unicode-*"]}]) is True


def test_shipped_allowlist_is_valid_and_five_dirs_scan_clean():
    """The built-in allowlist makes the go-live five-dir run exit 0; every entry carries a reason."""
    allow = VI.load_allowlist()
    assert allow and all(set(e) >= {"path", "rules", "why"} and e["why"] for e in allow)
    assert not [e for e in allow if "*" in e["rules"] and not e["path"].startswith("docs/archive")]
    paths = [_ROOT / p for p in ("library", "skills", "agents", "hooks", "docs") if (_ROOT / p).exists()]
    found = VI.scan(paths, allow=allow, root=_ROOT)
    assert found == [], [f"{f['cls']} {f['file']}:{f['line']} {f['rule']}" for f in found[:20]]


def test_windows_path_regex_built_without_literal():
    src = inspect.getsource(VI)
    assert re.search("C:" + r"\\|/home/[A-Za-z]", src) is None  # split: G3 scans this file too
