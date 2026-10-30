#!/usr/bin/env python3
"""vendor_library.py — vendor ECC prose into library/ecc per library/ecc/VENDOR.json.

  vendor_library.py --source <ECC checkout> --sha <40-hex> [--out library/ecc] [--vendor-json PATH] [--keep-tmp]

Copies only Markdown (+ small json/yaml/csv/txt sample data under examples/), sanitises every file
(Prompt Defense block, learning-state paths, personal paths, agent ``model:`` lines, README marketing
sections), marks lines that contradict workbench rules with ``<!-- ecc-conflict: <kind> -->``, writes
``<!-- ecc:<path>@<sha> -->`` headers, UPSTREAM.json and catalogue.json (registry command titles and
context-pack trigger phrases, so build_library_index.py --check needs no checkout), then runs
validate_imports on the result; a finding aborts before the swap so the previous library stays.
Hand-written ``digests/`` survive the swap. Deterministic: sorted walk, LF, no timestamps.
Exit 0 ok, 1 validation findings, 2 usage error / drifted checkout / VENDOR list mismatch.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

_DATA_SUFFIX = {".json", ".yaml", ".yml", ".csv", ".txt"}
_CODE_SUFFIX = {".py", ".js", ".ts", ".sh", ".ps1", ".mjs", ".cjs"}
_DEFENSE_RE = re.compile(r"(?m)^## Prompt Defense Baseline\n\n(?:- [^\n]*\n)+(?:\n|\Z)")
_HOMUNCULUS_RE = re.compile(r"(?:~|\$HOME|\$\{HOME\})/\.claude/homunculus")
_XDG_RE = re.compile(r"\$\{XDG_DATA_HOME:-~/\.local/share\}/ecc-homunculus")
_WIN_FWD_RE = re.compile(r"\b[A-Za-z]:/Users/(?!<)[^/\s`'\"]+")
_WIN_ANY_RE = re.compile("[A-Za-z]:" + r"\\+Users\\+(?!<)[^\\\s`'\"]+")
_HOME_ANY_RE = re.compile("/home/" + r"(?!\.\.\.)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TICK_RE = re.compile(r"`([^`]+)`")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_CONFLICTS = [(k, re.compile(p)) for k, p in [
    ("commit", r"\bgit\s+(?:commit|add\s+-A|add\s+\.)(?:\s|$)|\bgh\s+pr\s+(?:create|merge)\b"),
    ("push", r"\bgit\s+(?:push|tag)\b"),
    ("server", r"\b(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?(?:dev|start|serve)\b|\bvite\b(?![.-]|\s+build)"
               r"|\bnext\s+dev\b|\buvicorn\b|\bflask\s+run\b|\bmanage\.py\s+runserver\b|\brails\s+s(?:erver)?\b"
               r"|\bphp\s+artisan\s+serve\b|\bcargo\s+run\b|\bgo\s+run\b|\bpm2\s+start\b"),
    # `>>` only after whitespace: `List<User>>` / `Arc<Mutex<T>>` generics are not shell appends
    ("shell-write", r"\bsed\s+-i\b|\bperl\s+-i\b|\btee\s|(?:^|\s)>>(?!>)\s*[^\s&]|\bcat\s*>|\becho\s[^>|]*[^-=>2]>\s*[^\s&>=]"),
    ("no-verify", r"--no-verify\b"),
    ("race", r"\bgo\s+(?:build|test)\s+.*-race\b"),
]]


def _vi():
    spec = importlib.util.spec_from_file_location("validate_imports", ROOT / "scripts" / "validate_imports.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _git(src: Path, *args: str) -> str | None:
    cp = plat.run(["git", "-C", str(src), *args], timeout=20)
    return cp.stdout.strip() if cp.returncode == 0 else None


def _split_fm(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 3)
    if end != -1:
        return text[: end + 5], text[end + 5:]
    if text.endswith("\n---"):
        return text + "\n", ""
    return "", text


def _strip_h2(body: str, titles) -> str:
    want = {t.strip() for t in titles}
    out, skipping = [], False
    for line in body.split("\n"):
        if line.startswith("## "):
            skipping = line[3:].rstrip("# ").strip() in want
        if not skipping:
            out.append(line)
    return "\n".join(out)


def sanitize_paths(text: str) -> str:
    text = _HOMUNCULUS_RE.sub("<learning-state-dir>", text)
    text = _XDG_RE.sub("<learning-state-dir>", text)
    text = _WIN_FWD_RE.sub("%USERPROFILE%", text)
    text = _WIN_ANY_RE.sub("%USERPROFILE%", text)
    return _HOME_ANY_RE.sub("~/", text)


def _conflict_kind(text: str) -> str | None:
    return next((k for k, rx in _CONFLICTS if rx.search(text)), None)


def _mark_conflicts(body: str) -> tuple[str, set[str]]:
    lines, out, kinds, fenced = body.split("\n"), [], set(), False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fenced = not fenced
            out.append(line)
            continue
        kind = None
        if not line.lstrip().startswith("#"):
            target = line if fenced else " ".join(_TICK_RE.findall(line))
            kind = _conflict_kind(target) if target else None
        is_row = line.lstrip().startswith("|")
        if kind and is_row and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            kind = None  # never mark a table header row
        if kind:
            kinds.add(kind)
            if is_row and not fenced:
                out.append(f"{line} <!-- ecc-conflict: {kind} -->")  # a new line would split the table
                continue
            indent = line[: len(line) - len(line.lstrip())] if fenced else ""
            out.append(f"{indent}<!-- ecc-conflict: {kind} -->")
        out.append(line)
    return "\n".join(out), kinds


def _licence(rel: str, cfg: dict) -> str | None:
    return next((lic for k, lic in sorted((cfg.get("licences") or {}).items()) if rel.startswith(k + "/")), None)


def sanitize(text: str, rel: str, kind: str, sha: str, cfg: dict) -> str:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    fm, body = _split_fm(text)
    body = _DEFENSE_RE.sub("", body)
    body = sanitize_paths(body)
    fm = sanitize_paths(fm)
    if kind == "agent":
        fm = re.sub(r"(?m)^model:.*\n", "", fm)
    if kind == "guide":
        body = _strip_h2(body, ((cfg.get("guides") or {}).get(Path(rel).name) or {}).get("strip_h2", []))
    body, _ = _mark_conflicts(body)
    lic = _licence(rel, cfg)
    header = f"<!-- ecc:{rel}@{sha} -->\n" + (f"<!-- licence: {lic} (upstream) -->\n" if lic else "")
    return fm + header + body.lstrip("\n").rstrip("\n") + "\n"


def _md_under(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*.md") if p.is_file()) if d.is_dir() else []


def build_plan(src: Path, cfg: dict) -> list[tuple[str, str, str]]:
    """[(src_rel, out_rel, kind)]; raises FileNotFoundError when a listed SKILL.md is missing."""
    plan: list[tuple[str, str, str]] = []
    for name in cfg.get("skills", []):
        if not (src / "skills" / name / "SKILL.md").is_file():
            raise FileNotFoundError(f"skills/{name}/SKILL.md")
        plan.append((f"skills/{name}/SKILL.md",) * 2 + ("skill",))
    extra = [f"{n}/{d}" for n in cfg.get("skills_keep_references", []) for d in ("references", "reference")]
    for d in extra + list(cfg.get("skills_extra_md_dirs", [])):
        for p in _md_under(src / "skills" / d):
            rel = p.relative_to(src).as_posix()
            plan.append((rel, rel, "skill"))
    for d in cfg.get("rules", []):
        for p in sorted((src / "rules" / d).glob("*.md")):
            plan.append((f"rules/{d}/{p.name}",) * 2 + ("rules",))
    if cfg.get("rules_readme"):
        plan.append((cfg["rules_readme"], "rules/README.md", "rules"))
    plan += [(f"agents/{f}", f"agents/{f}", "agent") for f in cfg.get("agents", [])]
    plan += [((f if "/" in f else f"commands/{f}"), f"commands/{Path(f).name}", "command")
             for f in cfg.get("commands", [])]
    for e in cfg.get("examples", []):
        p = src / e
        if p.is_file():
            plan.append((e, f"examples/{p.name}", "example"))
            continue
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            sfx = f.suffix.lower()
            if sfx in _CODE_SUFFIX or (sfx != ".md" and (sfx not in _DATA_SUFFIX or f.stat().st_size > 65536)):
                continue
            r = f.relative_to(p).as_posix()
            out = f"examples/docs-{r.replace('/', '-')}" if e == "docs/examples" else f"examples/{p.name}/{r}"
            plan.append((f.relative_to(src).as_posix(), out, "example"))
    for g in sorted(cfg.get("guides") or {}):
        plan.append((g, f"guides/{g}", "guide"))
    return sorted(set(plan), key=lambda t: t[1])


def _demote(body: str) -> str:
    """Prefix every Markdown heading with one more `#` (fenced shell comments untouched)."""
    out, fenced = [], False
    for ln in body.split("\n"):
        if _FENCE_RE.match(ln):
            fenced = not fenced
        out.append("#" + ln if not fenced and re.match(r"#{1,5} ", ln) else ln)
    return "\n".join(out)


def troubleshooting(src: Path, sources: list[str]) -> str:
    parts = ["# Troubleshooting (merged from ECC)\n"]
    for s in sources:
        p = src / s
        parts.append(f"\n## Source: {s}\n")
        files = [p] if p.is_file() else _md_under(p)
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace").lstrip("﻿").replace("\r\n", "\n")
            _, body = _split_fm(text)
            if p.is_dir():
                parts.append(f"\n<!-- file: {f.relative_to(src).as_posix()} -->\n")
            parts.append(_demote(body))
        if p.is_dir():
            scripts = sorted(x.relative_to(src).as_posix() for x in p.rglob("*")
                             if x.is_file() and x.suffix.lower() != ".md")
            if scripts:
                parts.append("\nScripts not vendored: " + ", ".join(scripts) + "\n")
    return "\n".join(parts)


def catalogue(src: Path, cfg: dict) -> dict:
    cmds = {Path(f).stem for f in cfg.get("commands", [])}
    skills = set(cfg.get("skills", []))
    titles: dict[str, str] = {}
    try:
        reg = json.loads((src / "docs" / "COMMAND-REGISTRY.json").read_text(encoding="utf-8"))
        for c in reg.get("commands", []):
            name = str(c.get("command", "")).lstrip("/")
            if name in cmds and c.get("description"):
                titles[name] = str(c["description"]).strip()
    except (OSError, ValueError, AttributeError):
        pass
    trig: dict[str, list[str]] = {}
    try:
        packs = json.loads((src / "manifests" / "context-packs" / "skill-triggers@1.json").read_text(encoding="utf-8"))
        for key, phrases in (packs.get("triggers") or {}).items():
            name = key.split(":", 1)[-1]
            if name in skills and isinstance(phrases, list):
                trig[name] = list(dict.fromkeys(str(x).strip().lower() for x in phrases if str(x).strip()))
    except (OSError, ValueError, AttributeError):
        pass
    return {"command_titles": dict(sorted(titles.items())), "skill_triggers": dict(sorted(trig.items()))}


def _dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _swap(tmp: Path, out: Path) -> None:
    if (out / "digests").is_dir():
        shutil.move(str(out / "digests"), str(tmp / "digests"))
    if out.exists():
        shutil.rmtree(out)
    try:
        tmp.rename(out)
    except PermissionError:  # Windows: an indexer briefly holds a handle
        time.sleep(0.2)
        tmp.rename(out)


def vendor(src: Path, sha: str, out: Path, cfg: dict, vendor_json: Path | None = None, keep_tmp: bool = False) -> int:
    src, out = Path(src), Path(out)
    head = _git(src, "rev-parse", "HEAD")
    if head != sha:
        print(f"vendor_library: checkout is at {head}, expected {sha}")
        return 2
    commit_date = _git(src, "show", "-s", "--format=%cI", sha) or ""
    try:
        plan = build_plan(src, cfg)
    except FileNotFoundError as exc:
        print(f"vendor_library: VENDOR.json lists a missing file: {exc}")
        return 2
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    classes: dict[str, int] = {}
    skipped: list[str] = []
    for src_rel, out_rel, kind in plan:
        text = (src / src_rel).read_text(encoding="utf-8", errors="replace").lstrip("﻿").replace("\r\n", "\n")
        if not text.strip():
            skipped.append(src_rel)
            continue
        if src_rel.endswith(".md"):
            text = sanitize(text, src_rel, kind, sha, cfg)
        else:
            text = sanitize_paths(text)
        _write(tmp / out_rel, text)
        classes[kind] = classes.get(kind, 0) + 1
    if cfg.get("troubleshooting"):
        merged = troubleshooting(src, cfg["troubleshooting"])
        _write(tmp / "docs/troubleshooting.md", sanitize(merged, cfg["troubleshooting"][0], "doc", sha, cfg))
        classes["doc"] = classes.get("doc", 0) + 1
    n = sum(classes.values())
    up = cfg.get("upstream") or {}
    _write(tmp / "UPSTREAM.json", _dump({"repo": up.get("repo", ""), "sha": sha, "commit_date": commit_date,
                                         "files": n, "classes": classes, "digests": sorted(cfg.get("digests") or {}),
                                         "code_not_vendored": sorted(cfg.get("skills_code_not_vendored") or [])}))
    _write(tmp / "catalogue.json", _dump(catalogue(src, cfg)))
    if vendor_json and Path(vendor_json).is_file():
        (tmp / "VENDOR.json").write_bytes(Path(vendor_json).read_bytes())
    else:
        _write(tmp / "VENDOR.json", _dump(cfg))
    rc = _vi().main([str(tmp)])
    if rc != 0:
        if not keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        print("vendor_library: validation failed; the previous library is untouched")
        return 1
    _swap(tmp, out)
    if skipped:
        print("skipped_empty: " + ", ".join(skipped))
    print(f"vendored {n} files -> {out.as_posix()}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="vendor_library.py", description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", default=str(ROOT / "library" / "ecc"))
    ap.add_argument("--vendor-json", default=None)
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha):
        print("vendor_library: --sha must be 40 hex characters")
        return 2
    vj = Path(a.vendor_json) if a.vendor_json else Path(a.out) / "VENDOR.json"
    try:
        cfg = json.loads(vj.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"vendor_library: cannot read {vj.as_posix()}: {type(exc).__name__}")
        return 2
    return vendor(Path(a.source), a.sha, Path(a.out), cfg, vendor_json=vj, keep_tmp=a.keep_tmp)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
