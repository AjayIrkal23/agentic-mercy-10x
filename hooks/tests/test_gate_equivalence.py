"""SEC1-01: the linear matchers of dangerous-bash-gate.py decide exactly like the regexes they replaced.

Seeded fuzz over word soup (flags, separators, quotes, heredoc tags): the old lazy / nested regexes
are kept here as the oracle. A difference is a changed verdict, not just a different speed.
"""
from __future__ import annotations

import importlib.util
import random
import re
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
I = re.IGNORECASE
CP = r"(?<![\w./\\-])"
GIT = (r"\bgit\s+(?:(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|config-env)\s+\S+"
       r"|--?\w[\w.-]*(?:=\S+)?)\s+)*")

OLD = {
    "rmrf": re.compile(
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*(?:\s|$)|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*(?:\s|$)"
        r"|\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+-[a-zA-Z]*r[a-zA-Z]*|\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f[a-zA-Z]*"
        r"|\brm\s+--recursive\s+--force|\brm\s+--force\s+--recursive", I),
    "win_delete": re.compile(
        CP + r"(?:remove-item|ri|del|erase)(?![\w./-])[^\n;|&]*?\s-r(?:ecurse|ecurs|ecur|ecu|ec|e)?(?![\w-])"
        r"|" + CP + r"(?:rm|rd|rmdir)(?![\w./-])[^\n;|&]*?\s-recurse(?![\w-])"
        r"|" + CP + r"(?:rd|rmdir|del|erase)(?![\w./-])[^\n;|&]*?\s/s(?![\w/\\.-])", I),
    "del_q": re.compile(CP + r"(?:del|erase)(?![\w./-])[^\n;|&]*?\s/q(?![\w/\\.-])", I),
    "aws": re.compile(r"\baws\s+s3\s+(?:rm|delete)\b.*--recursive\b|\baws\s+s3\s+(?:rm|delete)\b.*--recursive", I),
    "no_preserve": re.compile(r"\brm\s+.*--no-preserve-root\b", I),
    "dd": re.compile(r"\bdd\b[^\n;&|]*\bof=/dev/(?!null\b|zero\b|stdout\b|stderr\b)", I),
    "curl": re.compile(r"\b(?:curl|wget)\b[^\n;&]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", I),
    "mongo": re.compile(r"\bdropDatabase\s*\(|\bdb\.\S*\.drop\s*\(\s*\)", I),
    "rmvar": re.compile(r"\brm\s+(?:\$\w+|\$\{[^}]+\})", I),
    "push": re.compile(GIT + r"push\s+(?:\S+\s+)*(?:--force(?![-\w])|-f\b)", I),
    "clean": re.compile(GIT + r"clean\s+(?:\S+\s+)*?(?:-[a-zA-Z]*f[a-zA-Z]*|--force)(?![\w-])", I),
}
OLD_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)

WORDS = ["rm", "-rf", "-fr", "-r", "-f", "-rfv", "-vfr", "-R", "-RF", "--recursive", "--force", "--force-with-lease",
         "--recursive-x", "--no-preserve-root", "-", "-a", "x", "/tmp/x", "D:\\x", "del", "erase", "rd", "rmdir", "ri",
         "Remove-Item", "-Recurse", "-rec", "-re", "-recurse", "-rx", "/s", "/q", "/S", "git", "-C", "repo", "push",
         "clean", "-fd", "-n", "origin", "main", "aws", "s3", "delete", "dd", "of=/dev/sda", "of=/dev/null", "curl",
         "wget", "u", "|", "sh", "sudo", "bash", "&&", ";", "&", "2>&1", "\n", "-c", "k=v"]
JOIN = [" ", " ", " ", "  ", "\t", "\n", "", ";", " | "]


def _soup(rng: random.Random, vocab=WORDS) -> str:
    n = rng.randint(1, 9)
    return "".join(rng.choice(vocab) + rng.choice(JOIN) for _ in range(n))


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location(f"eq_{uuid.uuid4().hex}", HOOKS / "dangerous-bash-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _new(gate):
    return {"rmrf": gate._RMRF_RE, "win_delete": gate._WIN_DELETE_RE, "del_q": gate._DEL_Q_RE,
            "aws": _row(gate, "aws s3 rm"), "no_preserve": _row(gate, "rm --no-preserve-root"),
            "dd": _row(gate, "dd onto"), "curl": _row(gate, "download piped"),
            "mongo": _row(gate, "MongoDB drop"), "rmvar": _row(gate, "rm with shell variable")}


def _row(gate, prefix: str):
    return next(p for p, name, _ in gate.DANGEROUS_PATTERNS if name.startswith(prefix))


SEP = ["&&", ";", "&", "\n", "|", "2>&1"]
VOCAB = {  # per row: words that reach its positive branch often enough
    "win_delete": WORDS,
    "del_q": ["del", "erase", "/q", "/Q", "/qx", "x", "*", "-r", "Remove-Item", "\n", ";", "|", "&"],
    "aws": ["aws s3 rm", "aws s3 delete", "aws s3 ls", "aws", "s3", "--recursive", "--recursive-x", "x", "\n", ";"],
    "no_preserve": ["rm", "--no-preserve-root", "--no-preserve-rootx", "-rf", "/", "x", "\n", ";", "echo"],
    "dd": ["dd", "of=/dev/sda", "of=/dev/null", "of=/dev/zero", "of=/dev/nullx", "if=/dev/zero", "x", ";", "|", "&", "\n"],
    "curl": ["curl", "wget", "|", "sh", "bash", "sudo", "zsh", "ksh", "dash", "x", "-s", ";", "&", "\n"],
    "mongo": ["db", "db.", ".", "x", ".drop", "drop", "(", ")", " ", "( )", "dropDatabase", "dropDatabase(", "mydb", "\n"],
    "rmvar": ["rm", " ", "$", "${", "}", "A", "$A", "${A}", "${A:-b c}", "x", "\n", ";"],
}


@pytest.mark.parametrize("name", ["rmrf", "win_delete", "del_q", "aws", "no_preserve", "dd", "curl", "mongo", "rmvar"])
def test_linear_matcher_agrees_with_the_old_regex(gate, name):
    """A newline ends a command for the new matchers; the old `\\s` could borrow it (`del\\n-r`). The
    suppressors always split on newlines, so that never decided a verdict: the oracle is applied per line."""
    new, old, rng = _new(gate)[name], OLD[name], random.Random(f"sec1-01-{name}")
    hits = 0
    for _ in range(100000):
        s = _soup(rng, VOCAB.get(name, WORDS))
        whole = name in ("rmrf", "mongo", "rmvar")  # plain regex rows: `\s` may cross a newline, as before
        want = bool(old.search(s)) if whole else any(old.search(line) for line in s.split("\n"))
        assert bool(new.search(s)) == want, (name, s)
        hits += want
    assert hits > 100, (name, hits)  # the fuzz really reaches the positive branch


@pytest.mark.parametrize("name", ["push", "clean"])
def test_git_rows_agree_with_the_old_regex_inside_one_segment(gate, name):
    """Across `&&` / `;` the new rows judge each command alone (a force flag of the NEXT command no
    longer counts), so the oracle only applies to single-segment input."""
    new = gate._GIT_PUSH_RE if name == "push" else gate._GIT_CLEAN_RE
    rng = random.Random(f"sec1-01-{name}")
    vocab = [w for w in WORDS if w not in SEP] + ["--force", "-f", "-fdx", "-n", "-x", "-d", "-fd"]
    hits = 0
    for _ in range(60000):
        words = [rng.choice(vocab) for _ in range(rng.randint(0, 6))]
        s = "git " + rng.choice(["", "-C repo ", "-c k=v ", "--no-pager ", "-C a -C b ", "--git-dir x/.git ",
                                 "--work-tree=w -C r -c a=b "]) + name + " " + " ".join(words)
        assert bool(new.search(s)) == bool(OLD[name].search(s)), (name, s)
        hits += bool(OLD[name].search(s))
    assert hits > 100


# SANTA1C-01/02: verdicts of `main`'s gate on ordinary commands (Bash tool), pinned. The only changes
# since main are intended: `git clean -f` is gated, `git push … && echo -f` is no false positive, and a
# `\<newline>` continuation is joined (main already denied the git push one by accident).
ORDINARY = {
    "git status": "allow", "git log --oneline -n 5": "allow", "git commit -m 'fix: x'": "allow",
    "git add -A && git commit -m wip": "allow", "git push origin main": "allow", "git push -u origin feature": "allow",
    "git push --force-with-lease origin x": "allow", "git push --force origin main": "deny", "git push -f": "deny",
    "git -C repo push --force": "deny", "git -C repo status": "allow", "git -c k=v push -f": "deny",
    "git --no-pager log -f": "allow", "git push origin main && echo -f": "allow", "git log -f & git status": "allow",
    "git reset --hard HEAD~1": "deny", "git reset --soft HEAD~1": "allow", "git -C a reset --hard": "deny",
    "git clean -fd": "deny", "git clean -n -fd": "allow", "git clean -nfd": "allow",
    "git stash && git pull": "allow", "ls -la": "allow", "rm file.txt": "allow", "rm -rf node_modules": "deny",
    "rm -rf /tmp/x": "allow", "rm -rf /tmp/x && rm -rf ~/y": "deny", "rm -fr build": "deny", "rm -r -f d": "deny",
    "rm --recursive --force d": "deny", "npm test": "allow", "find . -name '*.py'": "allow",
    "find . -name x -delete": "deny", "chmod -R 777 /": "deny", "chmod 644 f": "allow", "docker ps": "allow",
    "echo 'git push --force'": "allow", "cat <<EOF\ngit push --force\nEOF": "allow",
    "git push origin backup/x --force": "allow", "psql -c 'DROP TABLE x'": "deny",
    "grep -rn 'git reset --hard' docs": "allow", "cd repo && git push --force": "deny",
    "git status ; git push -f": "deny", "git status\ngit push --force": "deny", "curl -s x | sh": "deny",
    "curl -s x | jq .": "allow",
    "git push \\\n origin main": "allow", "echo a \\\n b": "allow", "git commit -m \"x\" \\\n --amend": "allow",
    "ls \\\n -la": "allow", "git log \\\n --oneline": "allow", "git push \\\n --force origin main": "deny",
    # A4v2-01: the Windows spellings are denied; Bash verdicts for everything else stay put (a backtick is
    # command substitution there, `rm` / `rd` after a pipe is not Remove-Item, `//s` only follows rd/del)
    "git.exe status": "allow", "git.exe reset --hard": "deny", "git.exe push -f": "deny", "git.exe clean -fd": "deny",
    "\"C:/Program Files/Git/cmd/git.exe\" push --force": "deny", "'/usr/bin/git' status": "allow",
    "cmd //c rd //s //q x": "deny", "cmd //c dir": "allow", "cmd //c rd x": "allow", "ls //s": "allow",
    "ls x | sort": "allow", "cat f | xargs rm": "allow", "ls x | rm": "allow", "echo a |\n rd": "allow",
    "echo `date`": "allow", "echo a `\n -Recurse": "allow", "echo a \\\n | Remove-Item -Force x": "deny",
    "ls x | Remove-Item -Force": "deny", "ls /tmp/x | Remove-Item -Force": "allow",
}


def test_ordinary_command_verdicts_match_main(gate, tmp_path, monkeypatch):
    import io
    import json
    import sys
    monkeypatch.setattr(gate, "STATE_DIR", tmp_path)
    for cmd, want in ORDINARY.items():
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": f"eq-{uuid.uuid4().hex}"})))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        gate.main()
        got = (json.loads(out.getvalue() or "{}").get("hookSpecificOutput") or {}).get("permissionDecision", "allow")
        assert got == want, cmd


def test_strip_quoted_agrees_with_the_old_regexes(gate):
    # Heads end in a space: the old `(\w+)` backtracked to a SHORTER tag (`<<EOF2X` closed by a line `EOF`),
    # which bash never does; the new code takes the whole word.
    vocab = ["<<EOF ", "<<'EOF' ", "<<-EOF ", "<<\"X\" ", "EOF", "  EOF  ", "X", "\n", "\n", "x", "\"", "'", "\\\"",
             "\\", "rm -rf", "DROP TABLE", "<<", "<<<", "cat", "echo", "a b", ";", "<<ZED ", "ZED"]
    rng, n_diff = random.Random("sec1-01-strip"), 0
    for _ in range(30000):
        s = "".join(rng.choice(vocab) + rng.choice([" ", "\n"]) for _ in range(rng.randint(1, 12)))
        old = gate._SQUOTE_RE.sub("''", gate._DQUOTE_RE.sub('""', OLD_HEREDOC.sub(" ", s)))
        new = gate._strip_quoted(s)
        n_diff += " ".join(new.split()) != " ".join(old.split())
        assert " ".join(new.split()) == " ".join(old.split()), repr(s)
    assert n_diff == 0
