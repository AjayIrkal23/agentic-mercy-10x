"""build_workflows.py — render the saved workflow library (MERGE-PLAN R3.2).

Renders ``workflows/src/<name>.js.tpl`` into ``workflows/<name>.js`` for one plan tier, plus
``workflows/index.json`` (routing data for hooks/prompt_router/modules/workflow_routes.py) and
``workflows/.rendered.json`` (``{schema, tier, usage_guard, policy_sha, content_sha}``, read by
hooks/workflow-model-guard.py ``_saved()``). The record is deterministic (no timestamp), so a
re-render of the committed tier leaves the tree clean.

Token grammar inside a template: ``{{model:<role>}}`` -> ``tiers.<tier>.roles.<role>`` of
hooks/model-policy.json; ``{{model:<role>:up}}`` -> ``tiers.<tier>.escalate.<role>`` (base when absent).
With the usage guard active every literal steps down (lib/usage_guard.step_down); every literal is
clamped to the tier ceiling (lib/plan_tier.cap). An unknown role token is an error (exit 2).

Callers: installer/render.py post_step ``build-workflows``, hooks/tools/selfheal-daily.py step
``workflows``, hooks/plan-tier-detect.py on a tier change and lib/usage_guard on a flip (both spawn
it detached with no arguments: the no-arg run reads the live tier/usage state and writes
``<root>/workflows``). It never spawns anything and never deletes a file.

Usage: build_workflows.py [--tier pro|max5|max20|api] [--usage on|off|auto] [--out DIR] [--src DIR]
       build_workflows.py --check [--out DIR] [--src DIR]
Exit codes: 0 ok; 1 ``--check`` found drift (DRIFT/MISSING/EXTRA/NOT-RENDERED); 2 bad template,
policy or index. ``--check`` re-renders from the RECORDED tier and writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # the checkout that owns this script (worktree-safe)
HOOKS, POLICY = ROOT / "hooks", ROOT / "hooks" / "model-policy.json"
SRC, OUT = ROOT / "workflows" / "src", ROOT / "workflows"
TIERS = ("pro", "max5", "max20", "api")
TOKEN = re.compile(r"\{\{model:([a-z]+)(:up)?\}\}")
HEADER = ("// GENERATED from workflows/src/{name}.js.tpl by scripts/build_workflows.py (tier {tier}{ug}). "
          "Do not edit; edit the template.\n")
META_RE = re.compile(r"export\s+const\s+meta\s*=\s*\{")
META_PHASE = re.compile(r"\{\s*title:\s*'([^']+)'(?:\s*,\s*model:\s*'(\w+)')?\s*\}")
_ORDER = ["haiku", "sonnet", "opus", "fable"]

sys.path.insert(0, str(HOOKS))
try:
    from lib import plan_tier, usage_guard  # noqa: E402
except Exception:  # noqa: BLE001 - the policy JSON alone still renders
    plan_tier = usage_guard = None  # type: ignore[assignment]
try:
    from lib import platform as _plat  # noqa: E402
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore[assignment]


def _die(msg: str) -> None:
    raise SystemExit(f"build_workflows: {msg}")


def _field(key: str, block: str) -> str:
    mo = re.search(rf"^\s*{key}:\s*'((?:[^'\\]|\\.)*)'", block, re.M)
    return mo.group(1) if mo else ""


def load_policy() -> dict:
    try:
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("tiers"), dict):
            raise ValueError("no tiers")
        return data
    except (OSError, ValueError):
        _die("cannot read hooks/model-policy.json")
    return {}  # unreachable


def policy_sha(policy_bytes: bytes) -> str:
    return hashlib.sha256(policy_bytes).hexdigest()[:12]


def _state_dir() -> Path:
    env = os.environ.get("CLAUDE_HOOK_STATE_DIR")
    if env:
        return Path(env).expanduser()
    if plan_tier is not None:
        return plan_tier.state_dir_ro()
    return ROOT / "state"


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def live_tier() -> str:
    if plan_tier is not None:
        try:
            return str(plan_tier.read()["tier"])
        except Exception:  # noqa: BLE001
            pass
    t = _load_json(_state_dir() / "plan-tier.json").get("tier")
    return t if t in TIERS else "max20"


def live_usage() -> bool:
    """state/usage-guard.json `active`; never calls usage_guard.state() (that writes and respawns us)."""
    return bool(_load_json(_state_dir() / "usage-guard.json").get("active"))


def _order(policy: dict) -> list:
    o = policy.get("model_order")
    return o if isinstance(o, list) and o else _ORDER


def _step_down(model: str, role: str, tier: str, policy: dict) -> str:
    if usage_guard is not None:
        return usage_guard.step_down(model, role, tier, policy)
    order = _order(policy)
    ug = ((policy["tiers"].get(tier) or policy["tiers"]["api"]).get("usage_guard") or {})
    if model not in order:
        return model
    if role == "judge":
        return str(ug.get("judge") or "sonnet")
    down = "sonnet" if model == "fable" else order[max(0, order.index(model) - 1)]
    ceil = str(ug.get("ceiling") or "sonnet")
    return down if ceil not in order or order.index(down) <= order.index(ceil) else ceil


def _cap(model: str, tier: str, policy: dict) -> str:
    if plan_tier is not None:
        return plan_tier.cap(model, tier)
    order = _order(policy)
    c = (policy["tiers"].get(tier) or policy["tiers"]["api"]).get("ceiling")
    if model not in order or c not in order:
        return model
    return model if order.index(model) <= order.index(c) else c


def resolve(policy: dict, tier: str, usage: bool, role: str, up: bool = False) -> str:
    blk = policy["tiers"].get(tier) or policy["tiers"]["api"]
    base = blk["roles"].get(role)
    if base is None:
        raise KeyError(role)
    m = (blk.get("escalate") or {}).get(role, base) if up else base
    if usage:
        m = _step_down(m, role, tier, policy)
    return _cap(m, tier, policy)


def render(text: str, name: str, policy: dict, tier: str, usage: bool) -> str:
    blk = policy["tiers"].get(tier) or policy["tiers"]["api"]

    def sub(mo: re.Match) -> str:
        try:
            return resolve(policy, tier, usage, mo.group(1), bool(mo.group(2)))
        except KeyError:
            _die(f"{name}.js.tpl: unknown role token {{{{model:{mo.group(1)}}}}}; roles: {sorted(blk['roles'])}")
        return ""  # unreachable

    body = TOKEN.sub(sub, text.replace("\r\n", "\n"))
    if "{{model:" in body:
        _die(f"{name}.js.tpl: unrendered token")
    head = HEADER.format(name=name, tier=tier, ug=", usage-guard" if usage else "")
    return head + body.rstrip("\n") + "\n"


def meta_end(script: str) -> int:
    """Index just past the meta literal (brace-matched, strings skipped; lib/workflow_script algorithm)."""
    m = META_RE.search(script)
    if not m:
        return -1
    i, depth, quote, n = m.end() - 1, 0, None, len(script)
    while i < n:
        c = script[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"', "`"):
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def parse_meta(script: str, stem: str) -> dict:
    m = META_RE.search(script)
    end = meta_end(script)
    if not m or end < 0:
        _die(f"{stem}: no `export const meta = {{...}}` literal")
    block = script[m.start():end]
    name = _field("name", block)
    if name != stem:
        _die(f"{stem}: meta name {name!r} must equal the file stem")
    phases = [{"title": t, **({"model": md} if md else {})} for t, md in META_PHASE.findall(block)]
    return {"name": name, "description": _field("description", block), "whenToUse": _field("whenToUse", block),
            "phases": phases}


def build_index(rendered: dict, src_index: dict) -> list:
    names = {k for k in src_index if not k.startswith("_")}
    have = {k[:-3] for k in rendered if k.endswith(".js")}
    for n in sorted(names ^ have):
        _die(f"{n}: template and index.src.json entry must both exist")
    out = []
    for name in sorted(names):
        e, meta = src_index[name], parse_meta(rendered[f"{name}.js"], name)
        out.append({"name": name, "file": f"{name}.js", "triggers": list(e.get("triggers") or []),
                    "acts": list(e.get("acts") or []), "min_size": str(e.get("min_size") or "S"),
                    "phases": meta["phases"], "args_schema": dict(e.get("args_schema") or {"type": "object"}),
                    "description": meta["description"], "whenToUse": meta["whenToUse"]})
    return out


def render_all(policy: dict, tier: str, usage: bool, src: Path = SRC) -> dict:
    files = {}
    for tpl in sorted(src.glob("*.js.tpl")):
        name = tpl.name[: -len(".js.tpl")]
        files[f"{name}.js"] = render(tpl.read_text(encoding="utf-8"), name, policy, tier, usage)
    src_index = _load_json(src / "index.src.json")
    if not src_index:
        _die(f"cannot read {src / 'index.src.json'}")
    index = build_index(files, src_index)
    files["index.json"] = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return files


def _same(path: Path, text: str) -> bool:
    try:
        return path.read_bytes() == text.encode("utf-8")
    except OSError:
        return False


def content_sha(tier: str, usage: bool, sha: str, files: dict) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode("utf-8") + b"\0" + files[name].encode("utf-8") + b"\0")
    h.update(f"{tier}|{int(usage)}|{sha}".encode("utf-8"))
    return h.hexdigest()


def rendered_record(tier: str, usage: bool, sha: str, files: dict) -> dict:
    """Deterministic: a pure function of (tier, usage, policy sha, rendered bytes). A render that
    reproduces committed content reproduces the committed record byte for byte, so a usage-guard
    flip and flip-back, or a replica re-render, never leaves the tree modified. Nothing time-based."""
    return {"schema": 1, "tier": tier, "usage_guard": usage, "policy_sha": sha,
            "content_sha": content_sha(tier, usage, sha, files)}


def _write(path: Path, text: str) -> None:
    """Atomic LF write (plat.atomic_write opens in text mode without newline=, i.e. CRLF on Windows,
    which would make --check report drift there)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        if _plat is not None:
            _plat.replace_file(tmp, path)  # retries a denied replace on Windows
        else:
            os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_outputs(out: Path, files: dict, record: dict) -> list:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in files.items():
        if not _same(out / name, text):
            _write(out / name, text)
            written.append(str(out / name))
    rec = json.dumps(record, sort_keys=True) + "\n"
    if not _same(out / ".rendered.json", rec):
        _write(out / ".rendered.json", rec)
        written.append(str(out / ".rendered.json"))
    return written


def check(out: Path, src: Path = SRC) -> int:
    rec = _load_json(out / ".rendered.json")
    if not rec or rec.get("tier") not in TIERS:
        print(f"NOT-RENDERED {out}")
        return 1
    policy = load_policy()
    usage = bool(rec.get("usage_guard"))
    files = render_all(policy, rec["tier"], usage, src)
    bad = 0
    if rec.get("content_sha") != content_sha(rec["tier"], usage, policy_sha(POLICY.read_bytes()), files):
        print("DRIFT .rendered.json (content_sha)")
        bad += 1
    for name, text in files.items():
        p = out / name
        if not p.is_file():
            print(f"MISSING {name}")
            bad += 1
        elif not _same(p, text):
            print(f"DRIFT {name}")
            bad += 1
    if policy_sha(POLICY.read_bytes()) != rec.get("policy_sha"):
        print("DRIFT .rendered.json (policy changed)")
        bad += 1
    for extra in sorted(p.name for p in out.glob("*.js") if p.name not in files):
        print(f"EXTRA {extra}")
        bad += 1
    if bad:
        return 1
    print(f"OK {sum(1 for n in files if n.endswith('.js'))} scripts, tier {rec['tier']}")
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description="Render workflows/src/*.js.tpl for a plan tier.")
    ap.add_argument("--tier", choices=TIERS)
    ap.add_argument("--usage", choices=("on", "off", "auto"), default="auto")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.check:
            return check(a.out, a.src)
        tier = a.tier or live_tier()
        usage = live_usage() if a.usage == "auto" else a.usage == "on"
        policy = load_policy()
        files = render_all(policy, tier, usage, a.src)  # render everything before writing anything
        record = rendered_record(tier, usage, policy_sha(POLICY.read_bytes()), files)
        written = write_outputs(a.out, files, record)
        if not a.quiet:
            n = sum(1 for k in files if k.endswith(".js"))
            print(f"rendered {n} scripts for tier {tier}{' (usage-guard)' if usage else ''} -> {a.out}: "
                  f"{len(written)} file(s) changed")
        return 0
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 2
        raise
    except Exception as e:  # noqa: BLE001
        print(f"build_workflows: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
