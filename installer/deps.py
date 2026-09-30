#!/usr/bin/env python3
"""deps.py — idempotent dependency + MCP-server installation (P6-T5).

Reads ``installer/manifest.json``. Every step is idempotent: a present tool is
SKIPPED (never reinstalled), a registered MCP server is SKIPPED. Under ``--ci``
every ``ci_stub`` step is skipped (CI has no network / no ``claude`` CLI; the
manifest is the contract the doctor asserts). Pure stdlib; all OS branching via
``hooks/lib/platform.py``. Nothing here raises — a failed optional step is a WARN.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

MANIFEST = _ROOT / "installer" / "manifest.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _exec_tokens(env) -> dict:
    """Tokens for the installer's OWN subprocess commands — CLAUDE_DIR is the
    REAL path (not the ${HOME}/.claude render token, which only Claude Code
    expands). PYTHON/NODE may be multi-word (e.g. 'py -3').

    Every ``{CLAUDE_DIR}/...`` the installer *executes* (post-step scripts, the
    graphify launcher) is a REPO-LOCAL file. When installing FROM a checkout that
    is not yet ~/.claude — a fresh `git clone` elsewhere, or the CI runner where
    `actions/checkout` lands the repo in the workspace and ~/.claude is the empty
    runner home — those files live under the installer's own repo root (``_ROOT``),
    not under the real ~/.claude. Resolve them against ``_ROOT`` whenever the two
    differ so install-from-checkout works anywhere; when the repo already IS
    ~/.claude (``_ROOT == real``) this is byte-identical to the old behavior."""
    real = env.real_dir or str(plat.claude_dir())
    claude_dir = str(_ROOT) if str(_ROOT) != real else real
    return {"PYTHON": env.python, "NODE": env.node, "CLAUDE_DIR": claude_dir}


def _sub(cmd: list, tokens: dict) -> list:
    """Materialize a command template into argv, splitting a whole-element
    interpreter token (``{PYTHON}`` -> 'py -3' -> ['py','-3']) but doing a plain
    in-place replace for embedded path tokens (``{CLAUDE_DIR}/x.py``)."""
    out: list[str] = []
    for part in cmd:
        s = str(part)
        whole_token_hit = None
        for k, v in tokens.items():
            tok = "{" + k + "}"
            if s == tok:
                whole_token_hit = v
                break
        if whole_token_hit is not None:
            out.extend(str(whole_token_hit).split())
            continue
        for k, v in tokens.items():
            s = s.replace("{" + k + "}", str(v))
        out.append(s)
    return out


def _importable(module: str, env) -> bool:
    """True when ``import <module>`` succeeds under the target interpreter.
    Used for Python-library deps (e.g. PyYAML) that have no ``which`` CLI."""
    cp = plat.run(_sub(["{PYTHON}", "-c", f"import {module}"], _exec_tokens(env)), timeout=30)
    return cp.returncode == 0


def _link_bins(names: list, env, dry_run: bool) -> str:
    """POSIX: symlink npm -g binaries (nvm prefix) into ~/.local/bin so shells that
    don't source nvm (Claude Code launched from a GUI) still find them."""
    if env.os_name != "posix":
        return ""
    local_bin = Path.home() / ".local" / "bin"
    done = []
    for n in names:
        src = shutil.which(n)
        dst = local_bin / n
        if not src or dst.exists() or dst.is_symlink() or Path(src).parent == local_bin:
            continue
        if dry_run:
            done.append(f"would-link {n}")
            continue
        try:
            local_bin.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
            done.append(f"linked {n}")
        except OSError:
            pass
    return f" ({', '.join(done)})" if done else ""


def install_deps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for dep in manifest.get("deps", []):
        did = dep["id"]
        which = dep.get("which")
        imp = dep.get("import")
        exists = dep.get("exists")
        if ((which and shutil.which(which)) or (imp and _importable(imp, env))
                or (exists and Path(exists).expanduser().exists())):
            results.append((did, "PRESENT" + _link_bins(dep.get("link_bins", []), env, dry_run)))
            continue
        install_cmd = dep.get(f"install_{env.os_name}") or dep.get("install")
        if ci and dep.get("ci_stub"):
            results.append((did, "SKIP(ci-stub)" if not dry_run or not install_cmd
                            else f"WOULD-INSTALL: {' '.join(install_cmd)}"))
            continue
        if not install_cmd:
            results.append((did, "MISSING(no-installer)" if not dep.get("optional") else "SKIP(optional-absent)"))
            continue
        if dry_run:
            results.append((did, f"WOULD-INSTALL: {' '.join(install_cmd)}"))
            continue
        cp = plat.run(_sub(install_cmd, _exec_tokens(env)), timeout=600)
        ok = cp.returncode == 0
        results.append((did, ("INSTALLED" + _link_bins(dep.get("link_bins", []), env, False))
                        if ok else f"WARN(rc={cp.returncode})"))
    return results


def user_config_file() -> Path:
    """Claude Code's global config: $CLAUDE_CONFIG_DIR/.claude.json else ~/.claude.json."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg and Path(cfg).resolve() != (Path.home() / ".claude").resolve():
        return Path(cfg) / ".claude.json"
    return Path.home() / ".claude.json"


def registered_user_mcps() -> set[str]:
    """Exact names of user-scope MCP servers (the only live MCP store, D13)."""
    try:
        d = json.loads(user_config_file().read_text(encoding="utf-8"))
        return set((d.get("mcpServers") or {}).keys())
    except (OSError, ValueError):
        return set()


def _win_shell_wrap(cmd: list[str]) -> list[str]:
    """Windows: Claude Code spawns MCP stdio servers WITHOUT a shell, so an npm
    ``.cmd``/``.bat`` shim (``npx``, ``lean-ctx``) never starts. Register it as
    ``cmd /c <shim> …``; real ``.exe`` servers and the ``py`` launcher stay direct."""
    if "--" not in cmd or cmd.index("--") + 1 >= len(cmd):
        return cmd
    i = cmd.index("--") + 1
    found = (shutil.which(cmd[i]) or "").lower()
    if cmd[i].lower() == "npx" or found.endswith((".cmd", ".bat")):
        return cmd[:i] + ["cmd", "/c"] + cmd[i:]
    return cmd


def _mcp_argv(srv: dict, env) -> list[str]:
    windows = env.os_name != "posix"
    cmd = _sub(srv["windows_add"] if windows and srv.get("windows_add") else srv["add"], _exec_tokens(env))
    extra: list[str] = []
    for var in srv.get("env_from", []):
        if os.environ.get(var):
            extra += ["-e", f"{var}={os.environ[var]}"]
    if extra:  # right after the server name (commander's -e is variadic)
        i = cmd.index(srv["name"]) + 1
        cmd[i:i] = extra
    return _win_shell_wrap(cmd) if windows else cmd


def _redact(cmd: list[str], srv: dict) -> str:
    names = set(srv.get("env_from", []))
    return " ".join(f"{c.split('=', 1)[0]}=***" if c.split("=", 1)[0] in names else c for c in cmd)


def register_mcps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    have = registered_user_mcps()
    for srv in manifest.get("mcp_servers", []):
        name = srv["name"]
        if name in have:
            results.append((name, "PRESENT"))
            continue
        if srv.get("posix_only") and env.os_name != "posix" and not srv.get("windows_add"):
            results.append((name, "SKIP(posix-only)"))
            continue
        cmd = _mcp_argv(srv, env)
        if dry_run or (ci and srv.get("ci_stub")):
            results.append((name, f"WOULD-ADD: {_redact(cmd, srv)}"))
            continue
        if not env.claude_cli:
            results.append((name, "SKIP(no-claude-cli)"))
            continue
        cp = plat.run(cmd, timeout=60)
        results.append((name, "ADDED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))
    return results


# --------------------------------------------------------------------------- #
# lean-ctx config: merge the required keys, never clobber the rest of the file
# --------------------------------------------------------------------------- #
def leanctx_config_path() -> Path:
    return Path.home() / ".config" / "lean-ctx" / "config.toml"


def _toml_val(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else json.dumps(v)


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """[(section_name, start, end)] — '' is the top-level table before the first header."""
    heads = [(i, m.group(1).strip()) for i, ln in enumerate(lines)
             if (m := re.match(r"^\s*\[([^\[\]]+)\]\s*$", ln))]
    out, prev_i, prev_name = [], 0, ""
    for i, name in heads:
        out.append((prev_name, prev_i, i))
        prev_i, prev_name = i + 1, name
    out.append((prev_name, prev_i, len(lines)))
    return out


def leanctx_required() -> dict:
    """{table: {key: value}} from the manifest ('top' = root table)."""
    cfg = _load_manifest().get("leanctx_config") or {}
    return {k: v for k, v in cfg.items() if isinstance(v, dict)}


def _tables(required: dict):
    return [("" if t == "top" else t, ks) for t, ks in required.items()]


def merge_leanctx_text(text: str, required: dict) -> str:
    """Set required keys in the TOML text. ``required`` = {"top": {...}, "<table>": {...}};
    'top' means the root table. Existing unrelated keys/comments are preserved."""
    lines = text.splitlines()
    for table, keys in _tables(required):
        for key, val in keys.items():
            want = f"{key} = {_toml_val(val)}"
            sec = next((s for s in _sections(lines) if s[0] == table), None)
            if sec is None:  # create the table at the end
                lines += ["", f"[{table}]", want]
                continue
            _, start, end = sec
            hit = next((i for i in range(start, end)
                        if re.match(rf"^\s*{re.escape(key)}\s*=", lines[i])), None)
            if hit is not None:
                lines[hit] = want
            else:
                ins = end
                while ins > start and not lines[ins - 1].strip():
                    ins -= 1  # keep trailing blank lines after the key
                lines.insert(ins, want)
    return "\n".join(lines) + "\n"


def leanctx_config_gaps(required: dict, path: Path | None = None) -> list[str] | None:
    """None if the config file is absent, else the list of keys not at the required value."""
    p = path or leanctx_config_path()
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    try:
        import tomllib  # 3.11+
        data = tomllib.loads(text)
        return [f"{t or 'root'}.{k}" for t, ks in _tables(required) for k, v in ks.items()
                if (data if not t else data.get(t, {})).get(k, object()) != v]
    except ImportError:  # 3.10: re-merge and compare (whitespace-normalized)
        norm = "\n".join(text.splitlines()) + "\n"
        return [f"{t or 'root'}.{k}" for t, ks in _tables(required)
                for k, v in ks.items() if merge_leanctx_text(norm, {t or "top": {k: v}}) != norm]
    except ValueError as exc:  # tomllib.TOMLDecodeError
        return [f"unparseable: {exc}"]


def configure_lean_ctx(*, dry_run: bool = False) -> tuple[str, str]:
    required = leanctx_required()
    p = leanctx_config_path()
    if leanctx_config_gaps(required, p) == []:
        return ("lean-ctx-config", "PRESENT (compliant)")
    if dry_run:
        return ("lean-ctx-config", f"WOULD-WRITE {p}")
    old = p.read_text(encoding="utf-8") if p.is_file() else ""
    p.parent.mkdir(parents=True, exist_ok=True)
    if old:  # recoverable copy before touching the user's config
        p.with_name(p.name + ".bak-installer").write_text(old, encoding="utf-8")
    p.write_text(merge_leanctx_text(old, required), encoding="utf-8")
    return ("lean-ctx-config", "OK(merged)")


def reconcile_mcp_env(*, dry_run: bool = False) -> list[tuple[str, str]]:
    """For MCP servers already registered, add the manifest's literal ``-e K=V``
    pairs that are missing/different (telemetry-off flags …) via the claude CLI
    (remove + add-json of the SAME entry with env merged — nothing else changes).
    Secrets (``env_from``) and existing extra env keys are never touched."""
    try:
        live = json.loads(user_config_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError):
        return []
    out: list[tuple[str, str]] = []
    for srv in _load_manifest().get("mcp_servers", []):
        name, add = srv["name"], srv["add"]
        want = dict(add[i + 1].split("=", 1) for i, a in enumerate(add)
                    if a == "-e" and "{" not in add[i + 1])
        entry = live.get(name)
        if not entry or not want:
            continue
        cur = entry.get("env") or {}
        missing = {k: v for k, v in want.items() if cur.get(k) != v}
        if not missing:
            continue
        if dry_run or not shutil.which("claude"):
            out.append((name, f"WOULD-SET-ENV: {sorted(missing)}"))
            continue
        new = {**entry, "env": {**cur, **missing}}
        plat.run(["claude", "mcp", "remove", "--scope", "user", name], timeout=60)
        cp = plat.run(["claude", "mcp", "add-json", "--scope", "user", name, json.dumps(new)], timeout=60)
        if cp.returncode != 0:  # never leave the server unregistered
            plat.run(["claude", "mcp", "add-json", "--scope", "user", name, json.dumps(entry)], timeout=60)
        out.append((name, f"ENV-SET {sorted(missing)}" if cp.returncode == 0 else f"WARN(rc={cp.returncode}, restored)"))
    return out


def run_post_steps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for step in manifest.get("post_steps", []):
        sid = step["id"]
        cmd = _sub(step["cmd"], _exec_tokens(env))
        if ci and step.get("network"):
            results.append((sid, f"WOULD-RUN(network): {' '.join(cmd)}"))
            continue
        # The script path is the FIRST '.py' arg — NOT cmd[1]. On Windows the
        # {PYTHON} token expands to a multi-word launcher ('py -3'), so _sub emits
        # ['py','-3','<...>/x.py',...] and cmd[1] is '-3', not the script. Reading
        # cmd[1] there false-reported every post-step as MISSING(script)/SKIP even
        # though the scripts exist. Scan for the '.py' element so it is correct on
        # every OS regardless of how many tokens {PYTHON} expands to.
        script = next((c for c in cmd if str(c).endswith(".py")), None)
        target = Path(script) if script else None
        if target and not target.exists():
            results.append((sid, "SKIP(script-absent)" if step.get("optional") else "MISSING(script)"))
            continue
        if dry_run:
            results.append((sid, f"WOULD-RUN: {' '.join(cmd)}"))
            continue
        cp = plat.run(cmd, timeout=300)
        ok = cp.returncode == 0
        results.append((sid, "OK" if ok else (f"WARN(rc={cp.returncode})" if step.get("optional") else f"FAIL(rc={cp.returncode})")))
    return results


def check_prereqs(env) -> list[tuple[str, str]]:
    """Report REQUIRED prerequisites that the installer does NOT auto-install
    (python3/node/git/claude). A MISSING required prereq blocks a full setup —
    the user must install it (per-OS command included) and re-run. Never mutates."""
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for p in manifest.get("prereqs", []):
        pid = p["id"]
        if shutil.which(p.get("which", pid)):
            results.append((pid, "PRESENT"))
            continue
        hint = p.get(f"install_{env.os_name}") or p.get("install_posix") or "see README prereqs"
        tag = "MISSING" if p.get("required") else "MISSING(optional)"
        results.append((pid, f"{tag} -> {hint}"))
    return results


def _present(root: Path, pat: str) -> bool:
    """True if a path (glob or literal) exists under root."""
    if any(c in pat for c in "*?["):
        return any(root.glob(pat))
    return (root / pat).exists()


def installed_plugins() -> set[str]:
    """Exact ``plugin@marketplace`` ids from ``claude plugin list --json``."""
    cp = plat.run(["claude", "plugin", "list", "--json"], timeout=40)
    try:
        return {p["id"] for p in json.loads(cp.stdout or "[]") if isinstance(p, dict) and "id" in p}
    except (ValueError, TypeError):
        return set()


def install_plugins(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    """Add plugin marketplaces + install the workbench plugins (via the claude
    CLI), then any manifest-declared local/manual packages. Idempotent: an
    already-present local install is left untouched. Fail-open: a bad step
    WARNs, never crashes."""
    manifest = _load_manifest()
    plugins = manifest.get("plugins", {})
    results: list[tuple[str, str]] = []
    tokens = _exec_tokens(env)
    target = Path(env.real_dir or str(plat.claude_dir()))

    # --- marketplace + CLI-installed plugins (need the claude CLI) ---
    plan = dry_run or ci
    if not env.claude_cli and not plan:
        results.append(("marketplace-plugins", "SKIP(no-claude-cli)"))
    else:
        try:
            known = set(json.loads((target / "plugins" / "known_marketplaces.json")
                                   .read_text(encoding="utf-8")))
        except (OSError, ValueError):
            known = set()
        for mk in plugins.get("marketplaces", []):
            mid = mk["id"]
            if mid in known:
                results.append((f"mkt:{mid}", "PRESENT"))
                continue
            if plan:
                results.append((f"mkt:{mid}", f"WOULD-ADD: {' '.join(mk['add'])}"))
                continue
            cp = plat.run(_sub(mk["add"], tokens), timeout=90)
            results.append((f"mkt:{mid}", "ADDED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))

        installed = installed_plugins() if env.claude_cli else set()
        for pl in plugins.get("install", []):
            pid = pl["id"]
            if pid in installed:
                results.append((f"plugin:{pid}", "PRESENT"))
                continue
            cmd = ["claude", "plugin", "install", pid, "--scope", "user"]
            if plan:
                results.append((f"plugin:{pid}", f"WOULD-INSTALL: {' '.join(cmd)}"))
                continue
            cp = plat.run(cmd, timeout=180)
            results.append((f"plugin:{pid}", "INSTALLED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))

    # --- local/manual installs need node, not the Claude CLI ---
    for man in plugins.get("manual", []):
        mid = man["id"]
        if any(_present(target, p) for p in man.get("detect_paths", [])):
            results.append((f"local:{mid}", "PRESENT (already installed)"))
            continue
        cmd = man.get("install_cmd")
        if not cmd:
            results.append((f"manual:{mid}", f"MANUAL -> {man.get('note', '')[:70]}"))
            continue
        if ci:
            results.append((f"local:{mid}", "SKIP(ci-stub)"))
            continue
        if not env.node:
            results.append((f"local:{mid}", f"SKIP(needs node/npm) -> {' '.join(cmd)}"))
            continue
        if dry_run:
            results.append((f"local:{mid}", f"WOULD-INSTALL: {' '.join(cmd)}"))
            continue
        # possibly-interactive third-party installer: close stdin + bound the wait.
        cp = plat.run(_sub(cmd, tokens), timeout=int(man.get("install_timeout", 420)),
                      stdin_devnull=True)
        results.append((f"local:{mid}", "INSTALLED"
                        if cp.returncode == 0
                        else f"WARN(rc={cp.returncode}) — run manually: {' '.join(cmd)}"))
    return results


if __name__ == "__main__":
    from detect import detect  # type: ignore

    e = detect()  # read-only plan: every mutating step is reported as WOULD-*
    for label, rows in [("prereqs", check_prereqs(e)),
                        ("deps", install_deps(e, dry_run=True)),
                        ("mcp", register_mcps(e, dry_run=True)),
                        ("mcp-env", reconcile_mcp_env(dry_run=True)),
                        ("plugins", install_plugins(e, dry_run=True)),
                        ("lean-ctx", [configure_lean_ctx(dry_run=True)]),
                        ("post", run_post_steps(e, dry_run=True))]:
        print(f"== {label} ==")
        for name, status in rows:
            print(f"  {name:22s} {status}")
