"""secrets_scan.py — layer 2 of the go-live secrets check: known values, key names only in output."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
FIX = _ROOT / "tests" / "fixtures" / "secrets"


def _mod():
    spec = importlib.util.spec_from_file_location("secrets_scan", _ROOT / "scripts" / "secrets_scan.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


S = _mod()
_VALUES = {"PLANTED_KEY": "plantedsecretvalue", "URLISH": "p@ss/word+x", "QUOTED": "quotedsecret99"}


def test_values_from_file_only_loads_long_values(tmp_path):
    assert S.load_values(values_from=[FIX / "values.env"], live=False, claude_dir=tmp_path) == _VALUES


def test_forms():
    f = S.forms("p@ss/word+x")
    assert {"p@ss/word+x", "p%40ss%2Fword%2Bx", "cEBzcy93b3JkK3g", "p@ss\\/word+x"} == f
    assert json.dumps("p@ss/word+x")[1:-1] in f  # the JSON form equals the plain one: deduped
    assert len(S.forms("quotedsecret99")) == 2


def test_clean_tree_passes(capsys):
    assert S.scan_tree(FIX / "clean", _VALUES) == []
    rc = S.main(["--known-values", "--tree", str(FIX / "clean"), "--values-from", str(FIX / "values.env")])
    assert rc == 0
    assert "secrets_scan: 0 hits (3 values, 1 files)" in capsys.readouterr().out


def test_planted_tree_reports_key_names_only(capsys):
    hits = set(S.scan_tree(FIX / "planted", _VALUES))
    assert hits == {("PLANTED_KEY", "planted/a.md", 3), ("PLANTED_KEY", "planted/b.json", 1),
                    ("URLISH", "planted/c.txt", 1), ("QUOTED", "planted/d.md", 1), ("URLISH", "planted/d.md", 2)}
    rc = S.main(["--known-values", "--tree", str(FIX / "planted"), "--values-from", str(FIX / "values.env")])
    out = capsys.readouterr().out
    assert rc == 1 and "PLANTED_KEY planted/a.md:3" in out
    for leak in ("plantedsecretvalue", "cGxhbnRlZ", "quotedsecret99", "p%40ss", "p@ss"):
        assert leak not in out


def test_diff_text_is_scanned_with_line_numbers():
    diff = "\n".join(["diff --git a/docs/x.md b/docs/x.md", "--- a/docs/x.md", "+++ b/docs/x.md",
                      "@@ -1,2 +10,3 @@", " context one", "-removed plantedsecretvalue", " context two",
                      "+plantedsecretvalue", ""])
    assert S.scan_diff(diff, _VALUES) == [("PLANTED_KEY", "diff:docs/x.md", 12)]


def test_empty_value_set_passes(tmp_path, capsys):
    short = tmp_path / "short.env"
    short.write_text("A=abc\nB=\n", encoding="utf-8")
    rc = S.main(["--known-values", "--tree", str(FIX / "planted"), "--values-from", str(short)])
    assert rc == 0 and "0 values loaded" in capsys.readouterr().out


def test_missing_tree_is_usage_error(tmp_path):
    assert S.main(["--known-values", "--values-from", str(FIX / "values.env")]) == 2
    assert S.main(["--tree", str(FIX / "clean")]) == 2


def test_machines_terms_extraction():
    text = ("- **Box** — `alice@198.51.100.7` (`host-ab12`, Ubuntu 24.04, kernel 6.8.0-1) `vmi0001234` and "
            "`qwen2.5-coder:3b` and `v1.2.3` and `~/.claude/x1` and `settings.user.json` and `PYTHONUTF8=1`")
    t = S.machine_terms(text)
    assert t["MACHINES_IPV4_1"] == "198.51.100.7"
    assert t["MACHINES_LOGIN_1"] == "alice@198.51.100.7"
    assert sorted(v for k, v in t.items() if k.startswith("MACHINES_TERM_")) == ["host-ab12", "vmi0001234"]
    for v in ("qwen2.5-coder:3b", "v1.2.3", "24.04", "6.8.0-1"):
        assert v not in t.values()


def test_machines_terms_windows_home():
    t = S.machine_terms("profile `" + "C:" + "\\Users\\Someone\\.claude` here")
    assert any(k.startswith("MACHINES_WINHOME_") for k in t)


def test_live_sources_are_optional(tmp_path):
    home = tmp_path / "h"
    assert S.load_values(values_from=[], live=True, claude_dir=tmp_path, home=home) == {}
    (tmp_path / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "A" * 20, "expiresAt": 1},
                                                            "mcpOAuth": {"x": {"accessToken": ""}}}), encoding="utf-8")
    assert S.load_values(values_from=[], live=True, claude_dir=tmp_path, home=home) == {
        "CREDENTIALS_claudeAiOauth_accessToken": "A" * 20}
    (tmp_path / ".credentials.json").unlink()
    (tmp_path / "settings.user.json").write_text(
        json.dumps({"env": {"OLLAMA_HOST": "http://198.51.100.9:11434"}, "theme": "dark"}), encoding="utf-8")
    assert S.load_values(values_from=[], live=True, claude_dir=tmp_path, home=home) == {
        "SETTINGS_env_OLLAMA_HOST": "http://198.51.100.9:11434"}
    (tmp_path / "settings.user.json").unlink()
    toml = home / ".config" / "lean-ctx" / "config.toml"
    toml.parent.mkdir(parents=True)
    toml.write_text('api_key = "' + "k" * 12 + '"\nname = "' + "x" * 12 + '"\n', encoding="utf-8")
    assert S.load_values(values_from=[], live=True, claude_dir=tmp_path, home=home) == {"LEANCTX_api_key": "k" * 12}


def test_binary_and_large_files_skipped(tmp_path):
    tree = tmp_path / "t"
    tree.mkdir()
    (tree / "big.txt").write_text("plantedsecretvalue\n" + "a" * (3 * 1024 * 1024), encoding="utf-8")
    (tree / "bin.dat").write_bytes(b"\x00\x01plantedsecretvalue")
    (tree / "img.png").write_bytes(b"plantedsecretvalue")
    assert S.scan_tree(tree, _VALUES) == []


def test_windows_paths_posix_in_output(tmp_path):
    tree = tmp_path / "t"
    (tree / "sub" / "deep").mkdir(parents=True)
    (tree / "sub" / "deep" / "f.md").write_text("plantedsecretvalue\n", encoding="utf-8")
    assert S.scan_tree(tree, _VALUES) == [("PLANTED_KEY", "t/sub/deep/f.md", 1)]


def test_never_prints_values_even_in_debug(capsys):
    S.main(["--known-values", "--tree", str(FIX / "planted"), "--values-from", str(FIX / "values.env"),
            "--debug-lengths"])
    out = capsys.readouterr().out
    assert "PLANTED_KEY 18 chars" in out
    assert "plantedsecretvalue" not in out and "quotedsecret99" not in out


def test_allow_key_and_plain_username_rules(tmp_path, capsys):
    env = tmp_path / "v.env"
    env.write_text("PLANTED_KEY=plantedsecretvalue\nDB_USER=dbadminuser\nDB_PASS=changeme\n"
                   "BOX_LOGIN=someone@198.51.100.4\n",
                   encoding="utf-8")
    vals = S.load_values(values_from=[env], live=False, claude_dir=tmp_path)
    assert set(vals) == {"PLANTED_KEY", "BOX_LOGIN"}
    rc = S.main(["--known-values", "--tree", str(FIX / "planted"), "--values-from", str(env),
                 "--allow-key", "PLANTED_KEY"])
    assert rc == 0 and "PLANTED_KEY" not in capsys.readouterr().out


def test_values_match_on_token_boundaries_only():
    pairs = S._pairs({"K": "trailhead"})
    assert S._scan_lines(["https://x/trailheadvalidationbucket/a.mp4"], pairs, "f", [1]) == []
    assert S._scan_lines(["PASS=trailhead"], pairs, "f", [1]) == [("K", "f", 1)]
    assert S._scan_lines(["user:trailhead@host", "`trailhead`", "x trailhead."], pairs, "f", [1, 2, 3]) == [
        ("K", "f", 1), ("K", "f", 2), ("K", "f", 3)]
    assert S._scan_lines(["prefixtrailhead", "trailhead2"], pairs, "f", [1, 2]) == []


def test_encoded_forms_keep_boundaries():
    pairs = S._pairs({"K": "p@ss/word1"})  # url-encoded and slash-escaped forms come from forms()
    assert S._scan_lines(["u=p%40ss%2Fword1&x"], pairs, "f", [1]) == [("K", "f", 1)]
    assert S._scan_lines(['"p@ss\\/word1"'], pairs, "f", [1]) == [("K", "f", 1)]


def test_non_alphanumeric_value_edges_need_no_boundary():
    pairs = S._pairs({"K": "-dashsecret!"})  # edges that are not alphanumeric match wherever they sit
    assert S._scan_lines(["x-dashsecret!y"], pairs, "f", [1]) == [("K", "f", 1)]


def test_real_readme_launch_links_are_not_hits():
    """A short value that is only the prefix of a long word in README.md (a public bucket name in the launch
    links) is not a hit (go-live step 06). The prefix is derived here: no tracked file names the real value."""
    text = (_ROOT / "README.md").read_text(encoding="utf-8")
    longs = sorted(set(re.findall(r"(?<![A-Za-z0-9])([a-z]{20,})(?![A-Za-z0-9])", text)))
    values = {f"K{i}": w[:9] for i, w in enumerate(longs) if not re.search(rf"\b{w[:9]}\b", text)}
    lines = text.splitlines()
    assert S._scan_lines(lines, S._pairs(values), "README.md", range(1, len(lines) + 1)) == []


def test_allow_drops_a_value(capsys):
    rc = S.main(["--known-values", "--tree", str(FIX / "planted"), "--values-from", str(FIX / "values.env"),
                 "--allow", "plantedsecretvalue", "--allow", "p@ss/word+x", "--allow", "quotedsecret99"])
    assert rc == 0
