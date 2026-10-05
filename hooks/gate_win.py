"""gate_win.py - the Windows / PowerShell spellings dangerous-bash-gate.py has to see through (A4v2-01).

Pure regexes and two tiny helpers, no state, stdlib only. Every pattern is linear in the command length
(a gate that times out decides nothing): no nested quantifier, no `head[^;]*tail` restart, and the only
bounded run (`[^,)'"]{0,300}`) is bounded on purpose, so a longer path reads as "not a temp dir".
"""
from __future__ import annotations

import re

# `"<dir>\Git\cmd\git.exe"` / `'/c/Windows/.../powershell.exe'`: quote stripping would turn the
# program into `""` and hide the command, so a quoted path to one of the four programs the gate knows is
# rewritten to its bare name first.
QUOTED_EXE = re.compile(r"""["'][^"'\n]*[\\/]((?:git|powershell|pwsh|cmd)(?:\.exe)?)["']""", re.IGNORECASE)

_CONTINUATION = re.compile(r"\\\r?\n")  # bash: `\<newline>`
_PS_CONTINUATION = re.compile(r"[`\\]\r?\n")  # PowerShell: backtick-newline (and the bash form)
_PIPE_NEWLINE = re.compile(r"\|[ \t]*\r?\n")  # a trailing `|` continues the pipeline on the next line

# `... | Remove-Item` (any flags): the pipeline deletes whatever the producer lists, recursion included.
# `rm` / `rd` / `rmdir` are Remove-Item aliases only in the PowerShell tool.
PIPE_DELETE = re.compile(r"\|\s*(?:remove-item|ri|del|erase)(?![\w./-])", re.IGNORECASE)
PIPE_DELETE_PS = re.compile(r"\|\s*(?:remove-item|ri|del|erase|rm|rd|rmdir)(?![\w./-])", re.IGNORECASE)

# `[IO.Directory]::Delete(path, $true)`, `(Get-Item x).Delete($true)`, VisualBasic `DeleteDirectory(...)`.
DOTNET_DELETE = re.compile(
    r"\[(?:system\.)?io\.directory\]::delete\b|\bdeletedirectory\s*\(|\)\.delete\s*\(\s*\$true\s*\)",
    re.IGNORECASE)
DOTNET_FIRST_ARG = re.compile(r"(?:delete|deletedirectory)\s*\(\s*['\"]?([^,)'\"]{0,300})", re.IGNORECASE)

STATEMENT_SPLIT = re.compile(r"&&|\|\||;|\n")  # a lone `|` stays: it is the pipeline being judged


def normalise(cmd: str) -> str:
    return QUOTED_EXE.sub(r"\1", cmd)


def join_lines(text: str, powershell: bool) -> str:
    """The shell runs a continued line as one command, so the patterns must too."""
    if not powershell:
        return _CONTINUATION.sub(" ", text)
    return _PIPE_NEWLINE.sub("| ", _PS_CONTINUATION.sub(" ", text))


def pipeline_producer_args(statement: str) -> list[str]:
    """Lower-cased `/` paths the first stage of a pipeline names (`gci -Path X -Recurse | ...` -> `[x]`)."""
    first = statement.split("|", 1)[0].replace('"', "").replace("'", "")
    words = [w for w in re.split(r"[\s,]+", first)[1:] if w and not w.startswith("-")]
    return [w.replace("\\", "/").lower() for w in words]
