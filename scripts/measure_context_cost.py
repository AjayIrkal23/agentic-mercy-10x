#!/usr/bin/env python3
"""measure_context_cost.py — measured always-on context cost (docs/TOKEN-BUDGET.md).

First stdout line, always: `doctrine total: N chars (~T tokens)` (CLAUDE.md + the imported
part of the machines file + rules without `paths:`). Then a Markdown table of every fixed
and per-event row with the pre-merge constant beside it. `--drafts DIR` measures
`DIR/<rel>.draft` in place of `<rel>`. Tokens = chars // 4. Never a hook; no network.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER_RE = re.compile(r"^<!-- mcp-eager-observed: (\d+) -->$", re.M)
BEFORE = {"CLAUDE.md": 5703, "CLAUDE.machines.local.md (imported part)": 22512,
          "rules/0*.md (no paths: frontmatter)": 10261, "MEMORY.md": 5305,
          "skill listing (local + plugins)": 45200, "agent descriptions": 16000,
          "session-start aggregator sample": 5500, "subagent-context sample": 1440,
          "plan-tier notice line": 0, "instinct lines": 0, "eager MCP schemas": 0}
DOCTRINE = ("CLAUDE.md", "CLAUDE.machines.local.md (imported part)", "rules/0*.md (no paths: frontmatter)")
FLOOR = DOCTRINE + ("MEMORY.md", "skill listing (local + plugins)", "agent descriptions", "eager MCP schemas")
PER_EVENT_NOTES = ("prompt router line: mean ~85 tokens per prompt", "memwatch-brake: 0 / 40 / 60 tokens (ok / warn / crit)",
                   "tdd-guard advisory: ~120 tokens per write in test-stack repos")
ECC_ADVICE = (
    "- Haiku for mechanical work (explore, docs, cleanup, verify); the plan tier picks it (`rules/04`).",
    "- MCP tools stay deferred; only `sequential-thinking` may set `alwaysLoad`.",
    "- `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH=600` caps each MCP tool description.",
    "- Compact at natural breaks (after exploration, after a milestone), never mid-change.",
    "- `/clear` between unrelated tasks; stale context costs tokens on every message.",
    "- Subagents protect the main context: they read 20 files and return a summary.",
    "- Agent teams multiply cost by the teammate count; use them only when messaging is needed.",
    "- Skills load bodies on demand; `skillOverrides` hides descriptions nobody invokes.",
)
sys.path.insert(0, str(ROOT / "hooks"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _plat():
    try:
        from lib import platform as plat
        return plat
    except Exception:  # noqa: BLE001
        return None


def _claude_dir() -> Path:
    plat = _plat()
    return plat.claude_dir() if plat else Path("~/.claude").expanduser()


def _text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def resolve(root: Path, rel: str, drafts: Path | None) -> Path | None:
    if drafts is not None and (drafts / f"{rel}.draft").is_file():
        return drafts / f"{rel}.draft"
    return root / rel if (root / rel).is_file() else None


def _has_paths(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    return end > 0 and re.search(r"^paths:", text[4:end], re.M) is not None


def rules_chars(root: Path, drafts: Path | None) -> int:
    names = {p.name for p in (root / "rules").glob("*.md")}
    if drafts is not None:
        names |= {p.name[: -len(".draft")] for p in (drafts / "rules").glob("*.md.draft")}
    total = 0
    for n in sorted(names):
        p = resolve(root, f"rules/{n}", drafts)
        t = _text(p) if p else ""
        total += 0 if _has_paths(t) else len(t)
    return total


def machines_chars(root: Path, machines: str | None) -> tuple[int, str]:
    if machines:
        cand, note = Path(machines).expanduser(), "given"
    else:
        cand, note = None, "absent"
        for p, n in ((root / "CLAUDE.machines.local.md", "live"), (_claude_dir() / "CLAUDE.machines.local.md", "live"),
                     (root / "tests" / "fixtures" / "machines.sample.md", "fixture")):
            if p.is_file():
                cand, note = p, n
                break
    if cand is None or not cand.is_file():
        return 0, "absent"
    raw = cand.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n")
    try:
        mod = _load("split_machines_file_mc", root / "scripts" / "split_machines_file.py")
        return len(mod.split_text(raw)[0]), note
    except Exception:  # noqa: BLE001
        return len(raw), f"{note}, unsplit"


def _frontmatter(path: Path) -> dict:
    try:
        mod = _load("skills_lib_mc", ROOT / "scripts" / "skills_lib.py")
        fm, _, _ = mod.read_frontmatter(path)
        return fm if isinstance(fm, dict) else {}
    except Exception:  # noqa: BLE001
        m = re.match(r"^---\s*\n(.*?)\n---", _text(path), re.S)
        return dict(re.findall(r"^([A-Za-z0-9_-]+):\s*(.*)$", m.group(1), re.M)) if m else {}


def load_overrides(root: Path, path: str | None) -> dict:
    cands = [Path(path).expanduser()] if path else [root / "docs" / "merge" / "skill-overrides.json",
                                                    _claude_dir() / "settings.json"]
    for c in cands:
        try:
            ov = json.loads(c.read_text(encoding="utf-8")).get("skillOverrides")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(ov, dict):
            return ov
    return {}


def listing_chars(root: Path, overrides: dict) -> tuple[int, str]:
    total = 0
    for p in sorted((root / "skills").glob("*/SKILL.md")):
        fm = _frontmatter(p)
        name, desc = str(fm.get("name") or p.parent.name), str(fm.get("description") or "")
        mode = overrides.get(name, "on")
        total += 0 if mode == "user-invocable-only" else len(name) + 4 + (0 if mode == "name-only" else len(desc))
    try:
        idx = json.loads((root / "hooks" / "skills-index.json").read_text(encoding="utf-8"))
        skills = idx.get("skills") if isinstance(idx.get("skills"), dict) else idx
        for k, v in skills.items():
            if ":" in k and isinstance(v, dict):
                total += len(k) + len(str(v.get("description", ""))) + 4
    except (OSError, ValueError, AttributeError):
        pass
    return total, f"{len(overrides)} overrides" if overrides else "no overrides"


def _agents(root: Path) -> list[Path]:
    return [p for p in sorted((root / "agents").glob("*.md")) if p.stem not in ("README", "team-lead")
            and _text(p).startswith("---")]


def agents_chars(root: Path) -> tuple[int, str]:
    lens = [len(str(_frontmatter(p).get("description") or "")) for p in _agents(root)]
    return sum(lens), f"max {max(lens, default=0)}"


def _hook_ctx(root: Path, script: str, payload: dict, timeout: int) -> str | None:
    path = root / "hooks" / script
    if not path.is_file():
        return None
    try:
        r = subprocess.run([sys.executable, str(path)], input=json.dumps(payload), capture_output=True,
                           encoding="utf-8", shell=False, timeout=timeout,
                           env={**os.environ, "CLAUDE_HOOK_DOCTOR": "1"})
        data = json.loads(r.stdout or "{}")
        ctx = data.get("additionalContext") or (data.get("hookSpecificOutput") or {}).get("additionalContext") or ""
        return ctx if isinstance(ctx, str) else None
    except Exception:  # noqa: BLE001
        return None


def tier_chars() -> tuple[int, str]:
    try:
        from lib import plan_tier
        n = len(plan_tier.notice_line() or "")
        return n, "" if n else "no change pending"
    except Exception:  # noqa: BLE001
        return 0, "plan_tier unavailable"


def instinct_chars(root: Path) -> tuple[int, str]:
    if not (root / "hooks" / "tools" / "instincts.py").is_file():
        return 0, "learning not installed"
    try:
        from lib import session_notices
        return len("\n".join(session_notices.instinct_lines(str(root)))), ""
    except Exception:  # noqa: BLE001
        return 0, "instinct_lines failed"


def _budget_doc(root: Path, write: str | None) -> Path:
    return Path(write).expanduser() if write else root / "docs" / "TOKEN-BUDGET.md"


def recorded(root: Path, write: str | None) -> int | None:
    m = MARKER_RE.search(_text(_budget_doc(root, write)))
    return int(m.group(1)) if m else None


def eager_servers(root: Path) -> list[str]:
    try:
        m = json.loads((root / "installer" / "manifest.json").read_text(encoding="utf-8"))
        return [str(s.get("name")) for s in m.get("mcp_servers", []) if isinstance(s, dict) and s.get("alwaysLoad")]
    except (OSError, ValueError, AttributeError):
        return []


def measure(root: Path, drafts: Path | None, a) -> list[dict]:
    def row(name, after, note=""):
        return {"name": name, "before": BEFORE[name], "after": after, "note": note}

    claude = resolve(root, "CLAUDE.md", drafts)
    rows = [row("CLAUDE.md", len(_text(claude)) if claude else 0, "draft" if claude and claude.suffix == ".draft" else "")]
    rows.append(row("CLAUDE.machines.local.md (imported part)", *machines_chars(root, a.machines)))
    rows.append(row("rules/0*.md (no paths: frontmatter)", rules_chars(root, drafts)))
    mem = _claude_dir() / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path.home())) / "memory" / "MEMORY.md"
    rows.append(row("MEMORY.md", len(_text(mem)), "" if mem.is_file() else "absent"))
    rows.append(row("skill listing (local + plugins)", *listing_chars(root, load_overrides(root, a.overrides))))
    rows.append(row("agent descriptions", *agents_chars(root)))
    for name, script, payload, t in (
            ("session-start aggregator sample", "session-start-aggregator.py",
             {"session_id": "doctor-measure", "cwd": str(root), "source": "startup"}, 20),
            ("subagent-context sample", "subagent-context.py",
             {"agent_id": "m", "agent_type": "implementation-engineer", "cwd": str(root)}, 10)):
        ctx = _hook_ctx(root, script, payload, t)
        rows.append(row(name, None if ctx is None else len(ctx), "n/a" if ctx is None else ""))
    rows.append(row("plan-tier notice line", *tier_chars()))
    rows.append(row("instinct lines", *instinct_chars(root)))
    if a.mcp_eager:
        rec = recorded(root, a.write)
        names = eager_servers(root)
        rows.append(row("eager MCP schemas", rec, ", ".join(names) or "none") if rec is not None
                    else row("eager MCP schemas", None, f"{', '.join(names) or 'none'}; unmeasured"))
    return rows


def _n(x) -> str:
    return "n/a" if x is None else f"{x:,}"


def _total(rows, names) -> int:
    return sum(r["after"] or 0 for r in rows if r["name"] in names)


def table(rows) -> str:
    out = ["| Row | Before (chars) | After (chars) | Δ | Note |", "|---|---|---|---|---|"]
    for r in rows:
        d = "n/a" if r["after"] is None else f"{r['after'] - r['before']:+,}"
        out.append(f"| {r['name']} | {_n(r['before'])} | {_n(r['after'])} | {d} | {r['note']} |")
    return "\n".join(out)


def counts(root: Path) -> list[tuple[str, int, str]]:
    def js(rel):
        try:
            return json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    chains = js("hooks/dispatch.config.json").get("chains") or {}
    links = sum(1 for ch in chains.values() if isinstance(ch, list) for ln in ch
                if isinstance(ln, dict) and ln.get("enabled") is not False)
    man = js("installer/manifest.json")
    plugins = (man.get("plugins") or {}).get("install") or []
    return [
        ("Local skills", len(list((root / "skills").glob("*/SKILL.md"))), "`ls skills/*/SKILL.md \\| wc -l`"),
        ("Plugin skills", int((js("hooks/skills-index.json").get("_meta") or {}).get("plugin_count") or 0),
         "`hooks/skills-index.json` → `_meta.plugin_count`"),
        ("Agents", len(_agents(root)), "`agents/*.md` minus README and team-lead"),
        ("Hook events wired", len(js("settings.template.json").get("hooks") or {}), "`settings.template.json` → `hooks`"),
        ("Dispatch links enabled", links, "`hooks/dispatch.config.json` → `chains`"),
        ("MCP servers", len(man.get("mcp_servers") or []), "`installer/manifest.json` → `mcp_servers`"),
        ("Plugins", len(plugins), "`installer/manifest.json` → `plugins.install`"),
        ("Vendored skill sources", len([k for k in js("hooks/skills-sources.json") if not k.startswith("_")]),
         "`hooks/skills-sources.json`"),
        ("Test files", len(list((root / "tests").glob("test_*.py"))) + len(list((root / "hooks" / "tests").glob("test_*.py"))),
         "`ls tests/test_*.py hooks/tests/test_*.py`"),
    ]


def counts_text(root: Path) -> str:
    return "\n".join(["| Thing | Count | Recompute with |", "|---|---|---|"]
                     + [f"| {t} | {c} | {how} |" for t, c, how in counts(root)])


def telemetry(root: Path) -> Path:
    env = os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR")
    return Path(env).expanduser() if env else root / "hooks" / ".telemetry"


def observed_text(tel: Path) -> str:
    per: dict[str, int] = {}
    src: dict[str, int] = {}
    for p in sorted(tel.glob("*.instructions-loaded.jsonl")) if tel.is_dir() else []:
        for ln in _text(p).splitlines():
            try:
                r = json.loads(ln)
                sid, chars = str(r.get("sid") or ""), int(r.get("chars") or 0)
            except (ValueError, TypeError, AttributeError):
                continue
            if not sid or sid.startswith("doctor-"):
                continue
            per[sid] = per.get(sid, 0) + chars
            s = str(r.get("source") or "unknown")
            src[s] = src.get(s, 0) + chars
    if not per:
        return "observed: no telemetry yet (hooks/.telemetry/*.instructions-loaded.jsonl)"
    med = int(statistics.median(per.values()))
    srcs = ", ".join(f"{k}={v:,}" for k, v in sorted(src.items()))
    return f"observed doctrine per session: median {med:,} chars over {len(per)} sessions (sources: {srcs})"


def eager_text(root: Path, write: str | None, record: int | None = None) -> str:
    names = eager_servers(root)
    rec = record if record is not None else recorded(root, write)
    fig = f"recorded /context figure: {rec:,} chars" if rec is not None else \
        "unmeasured (run /context at go-live, then --record N)"
    return f"eager MCP servers: {', '.join(names) or 'none'}\n{fig}"


def document(rows, root: Path, write: str | None, record: int | None) -> str:
    fixed = [r for r in rows if r["name"] in FLOOR]
    event = [r for r in rows if r["name"] not in FLOOR]
    rec = record if record is not None else recorded(root, write)
    lines = ["# Token budget", "",
             "Generated by `scripts/measure_context_cost.py --write`; do not edit numbers by hand.", "",
             f"Doctrine total: {_total(rows, DOCTRINE):,} chars (~{_total(rows, DOCTRINE) // 4:,} tokens); "
             f"fixed floor: {_total(rows, FLOOR):,} chars. Before: {sum(BEFORE[n] for n in DOCTRINE):,} / "
             f"{sum(BEFORE[n] for n in FLOOR):,}.", "",
             "## Fixed per session", "", table(fixed), "",
             "## Per event", "", table(event), "", *[f"- {n}" for n in PER_EVENT_NOTES], "",
             "## Observed", "", observed_text(telemetry(root)), "",
             "## Eager MCP schemas", "", eager_text(root, write, rec), ""]
    if rec is not None:
        lines += [f"<!-- mcp-eager-observed: {rec} -->", ""]
    lines += ["## How to re-measure", "",
              "- `python3 scripts/measure_context_cost.py` (first line = doctrine total)",
              "- `python3 scripts/measure_context_cost.py --write docs/TOKEN-BUDGET.md --counts --observed --mcp-eager`",
              "- `python3 scripts/measure_context_cost.py --mcp-eager --record <n>` after reading `/context`", "",
              "## Weekly manual inputs", "",
              "- `/context`: the eager MCP schema figure (feed it to `--record`).",
              "- `/doctor prompt-audit`: the system prompt as the harness sees it.",
              "- `/skill-doctor`: listing entries the harness flags as unused.", "",
              "## Token advice carried over from ECC", "", *ECC_ADVICE, ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--drafts")
    ap.add_argument("--machines")
    ap.add_argument("--overrides")
    ap.add_argument("--write")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--observed", action="store_true")
    ap.add_argument("--mcp-eager", action="store_true")
    ap.add_argument("--record", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).expanduser().resolve()
    drafts = None
    if a.drafts:
        drafts = Path(a.drafts).expanduser()
        drafts = drafts if drafts.is_absolute() else root / drafts
    if a.record is not None:
        a.mcp_eager = True
    rows = measure(root, drafts, a)
    if a.record is not None:  # the recorded figure is the eager row
        rows[-1].update(after=a.record, note=", ".join(eager_servers(root)) or "none")
    doctrine, floor = _total(rows, DOCTRINE), _total(rows, FLOOR)
    if a.json:
        print(json.dumps({"doctrine_total": doctrine, "fixed_floor": floor, "rows": rows,
                          **({"counts": {t: c for t, c, _ in counts(root)}} if a.counts else {})}, indent=1))
    else:
        print(f"doctrine total: {doctrine:,} chars (~{doctrine // 4:,} tokens)")
        print(f"fixed floor: {floor:,} chars (~{floor // 4:,} tokens)\n")
        print(table(rows))
        if a.counts:
            print("\n" + counts_text(root))
        if a.observed:
            print("\n" + observed_text(telemetry(root)))
        if a.mcp_eager:
            print("\n" + eager_text(root, a.write, a.record))
    if a.write or a.record is not None:
        out = _budget_doc(root, a.write)
        text = document(rows, root, a.write, a.record)  # before open(): "w" truncates the recorded marker
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
