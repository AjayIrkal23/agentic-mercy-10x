"""scripts/split_machines_file.py: keep the imported machines file short (docs/merge/machines-split.md)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
FIX = _ROOT / "tests" / "fixtures" / "machines.sample.md"
PROD_KEYS = {"without my explicit word", "GCP VM is read-only", "Servers run IST"}


def _mod():
    spec = importlib.util.spec_from_file_location("split_machines_file", _ROOT / "scripts" / "split_machines_file.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


sm = _mod()


def _copy(tmp_path: Path, name: str = "m.md") -> Path:
    m = tmp_path / name
    m.write_bytes(FIX.read_bytes())
    return m


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _apply(m: Path, **kw):
    args = dict(budget=sm.DEFAULT_BUDGET, journal=None, terms_out=None, force_unignored=False, dry=False)
    args.update(kw)
    return sm.apply(m, **args)


def _units(text: str) -> list[list[str]]:
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if sm.UNIT_RE.match(ln)] + [len(lines)]
    return [lines[a:b] for a, b in zip(starts, starts[1:])]


def test_fixture_shape():
    text = _read(FIX)
    assert 6500 <= len(text) <= 7500
    n = sm.norm(text)
    for key in sm._KEEP_FALLBACK:
        if key not in PROD_KEYS:
            assert key in n, key
    for key in ("NEVER let the laptop sleep", "Full performance always"):
        unit = next(u for u in _units(text) if key in "\n".join(u))
        assert "\n".join(unit).index(key) > sm.DEFAULT_BUDGET, key


def test_check_before_and_after(tmp_path):
    m = _copy(tmp_path)
    # the fixture is under 6,000 only after the split; before, --check must fail when over the limit
    rc, msg = sm.check(m)
    if len(_read(m)) > sm.CHECK_LIMIT:
        assert rc == 1 and "NOT SPLIT" in msg
    rc, _ = _apply(m)
    assert rc == 0
    rc, msg = sm.check(m)
    assert rc == 0 and "split=yes" in msg


def test_check_fails_over_limit_without_marker(tmp_path):
    m = tmp_path / "big.md"
    m.write_text(_read(FIX) + ("filler line for size\n" * 40), encoding="utf-8")
    rc, msg = sm.check(m)
    assert rc == 1 and "NOT SPLIT" in msg


def test_apply_shrinks_and_keeps_directives(tmp_path):
    m = _copy(tmp_path)
    original = _read(m)
    rc, _ = _apply(m)
    assert rc == 0
    imported = _read(m)
    assert len(imported) <= sm.CHECK_LIMIT
    assert "<!-- machines-split:pointer -->" in imported
    assert "<!-- machines-split:prod-safety -->" in imported
    assert "without my explicit word" in imported and "never" in imported
    n = sm.norm(imported)
    for key in sm._KEEP_FALLBACK:
        assert key in n, key
    journal = m.with_name(sm.JOURNAL_NAME)
    jtext = _read(journal)
    cut_ids = [int(sm.CUT_RE.match(ln).group(1)) for ln in imported.split("\n") if sm.CUT_RE.match(ln)]
    tail_ids = [int(sm.TAIL_RE.match(ln).group(1)) for ln in jtext.split("\n") if sm.TAIL_RE.match(ln)]
    end_ids = [int(sm.END_RE.match(ln).group(1)) for ln in jtext.split("\n") if sm.END_RE.match(ln)]
    assert cut_ids and sorted(cut_ids) == sorted(tail_ids) == sorted(end_ids)

    # content conservation: imported (minus markers, constant blocks, lifted copies) + journal tails == original
    il = imported.split("\n")
    drop: set[int] = set()
    for i, ln in enumerate(il):
        mc = sm.CUT_RE.match(ln)
        if mc:
            drop.update(range(i - int(mc.group(2)), i + 1))
        elif ln == "<!-- machines-split:pointer -->":
            drop.update((i, i + 1))
        elif ln == "<!-- machines-split:prod-safety -->":
            drop.update(range(i, i + 4))
        elif sm.HEADER_RE.match(ln):
            drop.add(i)
    kept = [ln for i, ln in enumerate(il) if i not in drop and ln.strip()]
    tails, inside = [], False
    for ln in jtext.split("\n"):
        if sm.TAIL_RE.match(ln):
            inside = True
        elif sm.END_RE.match(ln):
            inside = False
        elif inside and ln.strip():
            tails.append(ln)
    assert Counter(kept + tails) == Counter(ln for ln in original.split("\n") if ln.strip())


def test_idempotent(tmp_path):
    m = _copy(tmp_path)
    _apply(m)
    journal = m.with_name(sm.JOURNAL_NAME)
    a, j = m.read_bytes(), journal.read_bytes()
    rc, msgs = _apply(m)
    assert rc == 0 and any("unchanged" in x for x in msgs)
    assert m.read_bytes() == a and journal.read_bytes() == j


def test_undo_exact(tmp_path):
    m = _copy(tmp_path)
    original = m.read_bytes()
    _apply(m)
    rc, _ = sm.undo(m, None, False)
    assert rc == 0
    assert m.read_bytes() == original
    assert not m.with_name(sm.JOURNAL_NAME).exists()


def test_regrowth(tmp_path):
    m = _copy(tmp_path)
    _apply(m)
    lines = _read(m).split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("- **Laptop replica**"))
    marker = next(i for i in range(start, len(lines)) if sm.CUT_RE.match(lines[i]))
    old_max = max(int(sm.CUT_RE.match(ln).group(1)) for ln in lines if sm.CUT_RE.match(ln))
    extra = [f"  regrowth line {n:02d}: the laptop gained another paragraph of notes to keep it long." for n in range(20)]
    lines[marker + 1:marker + 1] = extra
    regrown = "\n".join(lines)
    assert len("\n".join(extra)) >= 1500
    m.write_text(regrown, encoding="utf-8")
    rc, _ = _apply(m)
    assert rc == 0
    ids = [int(sm.CUT_RE.match(ln).group(1)) for ln in _read(m).split("\n") if sm.CUT_RE.match(ln)]
    assert max(ids) == old_max + 1 and len(ids) == len(set(ids))
    # undo goes all the way back to the regrown file before the first split
    rc, _ = sm.undo(m, None, False)
    assert rc == 0
    # in original terms the 20 lines sit at the end of the Laptop replica unit
    full = _read(FIX).split("\n")
    li = next(i for i, ln in enumerate(full) if ln.startswith("- **Cloud VMs**"))
    want = "\n".join(full[:li] + extra + full[li:])
    assert _read(m) == want


def test_terms(tmp_path):
    got = sm.terms(_read(FIX))
    assert got == sorted({"198.51.100.7", "203.0.113.10", "192.0.2.44", "gpu-example-01", "DESKTOP-EXAMPLE",
                          "vmi0000000", "abcdefghij0123456789klmn", "zyxwvutsrq9876543210ponm",
                          "192.0.2.80", "198.51.100.9", "build-EXAMPLE12A-E10", "instance-20990101-000000",
                          "LAPTOP-EXAMPLE42", "abcdefghij0123456789wxyz", "zyxw9876543210abcdefghij"})
    assert not any("notasecret" in t for t in got)
    m = _copy(tmp_path)
    out = tmp_path / "scripts" / "grep_gates.machine_terms.json"
    rc, _ = _apply(m, terms_out=out)
    assert rc == 0
    data = json.loads(_read(out))
    assert data["schema"] == 1 and data["terms"] == got
    assert "notasecret" not in _read(out)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_refusal(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    m = _copy(tmp_path)
    before = m.read_bytes()
    rc, msgs = _apply(m)
    assert rc == 2 and any("REFUSED" in x for x in msgs)
    assert m.read_bytes() == before
    assert not m.with_name(sm.JOURNAL_NAME).exists()
    (tmp_path / ".gitignore").write_text(f"/{sm.JOURNAL_NAME}\n/scripts/{sm.TERMS_NAME}\n", encoding="utf-8")
    rc, _ = _apply(m)
    assert rc == 0


def test_missing_file_skips(tmp_path, capsys):
    assert sm.main(["--check", "--file", str(tmp_path / "none.md")]) == 0
    assert "SKIP" in capsys.readouterr().out


def test_keys_match_directives():
    d = _ROOT / "docs" / "DIRECTIVES.md"
    if d.is_file():
        assert set(sm.load_keys(d)) == set(sm._KEEP_FALLBACK)
    else:
        assert sm.load_keys(None) == sm._KEEP_FALLBACK


def test_journal_not_imported(tmp_path):
    m = _copy(tmp_path)
    _apply(m)
    assert not any(ln.startswith("@") for ln in _read(m).split("\n"))
    draft = _ROOT / "docs" / "merge" / "CLAUDE.md.draft"
    if draft.is_file():
        imports = [ln for ln in _read(draft).split("\n") if ln.startswith("@")]
        assert imports == ["@CLAUDE.machines.local.md"]


def test_crlf_input(tmp_path):
    m = tmp_path / "m.md"
    m.write_bytes(_read(FIX).replace("\n", "\r\n").encode("utf-8"))
    rc, msgs = _apply(m)
    assert rc == 0
    assert b"\r\n" not in m.read_bytes()
    assert any("CRLF" in x for x in msgs)


def test_budget_shrink_lifts_wrapped_key():
    text = _read(FIX)
    out, tails = sm.split_text(text, budget=200)
    assert tails
    assert "never ask me to run sudo" in sm.norm(out)


def test_stale_journal_ids_never_collide(tmp_path):
    m = _copy(tmp_path)
    _apply(m)
    m.write_bytes(FIX.read_bytes())  # a fresh copy beside the old journal (acceptance re-run)
    original = m.read_bytes()
    rc, _ = _apply(m)
    assert rc == 0
    jtext = _read(m.with_name(sm.JOURNAL_NAME))
    ids = [int(sm.TAIL_RE.match(ln).group(1)) for ln in jtext.split("\n") if sm.TAIL_RE.match(ln)]
    assert len(ids) == len(set(ids)) == 6
    rc, _ = sm.undo(m, None, False)
    assert rc == 0 and m.read_bytes() == original


def test_unwritable_journal_leaves_machines_file_unchanged(tmp_path):
    m = _copy(tmp_path)
    before = m.read_bytes()
    bad_journal = tmp_path / "journal-is-a-dir"
    bad_journal.mkdir()
    rc, msgs = _apply(m, journal=bad_journal)
    assert rc == 2 and "FAILED" in msgs[0]
    assert m.read_bytes() == before
    assert not list(tmp_path.glob(".tmp-*"))


def test_terms_write_failure_leaves_both_files_unchanged(tmp_path):
    m = _copy(tmp_path)
    before = m.read_bytes()
    terms_dir = tmp_path / "terms-dir"
    terms_dir.mkdir()
    rc, msgs = _apply(m, terms_out=terms_dir)
    assert rc == 2 and "FAILED" in msgs[0]
    assert m.read_bytes() == before and not m.with_name(sm.JOURNAL_NAME).exists()


def test_terms_live_shapes():
    text = ("hostname\n    `instance-20990101-000000`, Ubuntu 26.04\n"
            "`u@198.51.100.7` (`box-ESC1234A-E10`, Ubuntu 22.04\n"
            "try both) (DESKTOP-EXAMPLE97, HP Omen, Windows 11\n"
            "project `p` (abcdefghij0123456789klmn): envs\n(zyxwvutsrq9876543210ponm, public :9017)\n"
            "noise: postgres 18.1, v4.2.0, sha256sum, 2026-10-15, `docker-compose.yml.bak-20990101-readtimeout`, "
            "qwen2.5-coder:3b, --resume-after-limit, id_ed25519, x86_64, E11000, RTX A5000, 9AM_10AM.mp4, "
            "postgresql-x64-99, md5-checked, R2-configured\n")
    got = set(sm.terms(text))
    assert {"instance-20990101-000000", "box-ESC1234A-E10", "DESKTOP-EXAMPLE97",
            "abcdefghij0123456789klmn", "zyxwvutsrq9876543210ponm", "198.51.100.7"} <= got
    for noise in ("18.1", "v4.2.0", "sha256sum", "2026-10-15", "docker-compose.yml.bak-20990101-readtimeout",
                  "qwen2.5-coder:3b", "--resume-after-limit", "resume-after-limit", "id_ed25519", "x86_64",
                  "E11000", "A5000", "9AM_10AM.mp4", "postgresql-x64-99", "md5-checked", "R2-configured"):
        assert noise not in got, noise


def test_dry_run_writes_nothing(tmp_path):
    m = _copy(tmp_path)
    before = m.read_bytes()
    rc, msgs = _apply(m, dry=True)
    assert rc == 0 and any("would move" in x for x in msgs)
    assert m.read_bytes() == before and not m.with_name(sm.JOURNAL_NAME).exists()


# --- final-fix 7: the imported part meets the plan row (1,300 tok = 5,200 ch) ---------------------
def test_default_budget_meets_the_plan_row():
    assert sm.CHECK_LIMIT == 5200 and sm.DEFAULT_BUDGET <= 650


def test_live_machines_file_fits_the_plan_row():
    live = Path.home() / ".claude" / sm.MACHINES_NAME
    if not live.is_file():
        pytest.skip("no machines file")
    assert len(live.read_text(encoding="utf-8")) <= sm.CHECK_LIMIT


def test_reapply_with_a_smaller_budget_roundtrips(tmp_path):
    """Split at 800, then apply again at the smaller default: the imported part shrinks, every
    directive key stays imported, and undo restores the original byte for byte."""
    m = _copy(tmp_path)
    original = _read(m)
    assert _apply(m, budget=800)[0] == 0
    at_800 = len(_read(m))
    rc, _ = _apply(m)
    assert rc == 0 and len(_read(m)) <= at_800
    n = sm.norm(_read(m))
    assert all(key in n for key in sm._KEEP_FALLBACK)
    assert any("unchanged" in x for x in _apply(m)[1])
    assert sm.undo(m, None, False)[0] == 0 and _read(m) == original
