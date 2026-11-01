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
import shutil  # noqa: F401  (tests patch deps.shutil.which; winutil.which delegates to the same module)
import site
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
if str(_ROOT / "installer") not in sys.path:  # doctor_mcp (pin_drift) lives beside this file
    sys.path.insert(0, str(_ROOT / "installer"))
from lib import platform as plat  # noqa: E402
import mcp_restore  # noqa: E402
import npm_pack  # noqa: E402
import npx_cache  # noqa: E402
import release_bin  # noqa: E402
import winpath  # noqa: E402
import winutil  # noqa: E402
from npx_cache import prune_npx_cache, warm_npx  # noqa: E402,F401 (the npx-cache helpers, importable here)

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
    return {"PYTHON": env.python, "NODE": env.node, "CLAUDE_DIR": claude_dir,
            "USER_SITE": str(Path(site.getusersitepackages())), "HOME": str(Path.home()),
            "OLLAMA_URL": plat.ollama_url()}


_LAUNCHER = re.compile(r"(.+?)((?:\s+-\S+)*)")


def _words(value) -> list[str]:
    """A launcher value as argv: ``py -3`` -> ['py', '-3'], but ``C:/Users/John Smith/x/python.exe`` stays
    ONE element (CreateProcess would try ``<drive>:\\Users\\John.exe`` first): the program is everything
    up to the trailing ``-flag`` words."""
    m = _LAUNCHER.fullmatch(str(value).strip())
    return [m.group(1), *m.group(2).split()] if m else []


def _sub(cmd: list, tokens: dict) -> list:
    """Materialize a command template into argv, splitting a whole-element
    interpreter token (``{PYTHON}`` -> 'py -3' -> ['py','-3']; a path with spaces stays whole) but
    doing a plain in-place replace for embedded path tokens (``{CLAUDE_DIR}/x.py``)."""
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
            out.extend(_words(whole_token_hit))
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


def _bins_for(dep: dict) -> list[str]:
    """The CLIs an npm-global dep puts in npm's bin dir: its ``link_bins``, else its ``which`` when it
    installs with ``npm install -g`` (lean-ctx, tdd-guard and mmx-cli had no link_bins: F1)."""
    if "link_bins" in dep:
        return [str(n) for n in dep["link_bins"]]
    argv = [str(a) for a in (dep.get("install") or [])]
    return [dep["which"]] if dep.get("which") and argv[:3] == ["npm", "install", "-g"] else []


def _link_bins(names: list, env, dry_run: bool) -> str:
    """POSIX: symlink npm -g CLIs into ~/.local/bin (on every shell's PATH through the claude-workbench
    block) so a shell or a GUI-launched Claude Code without npm's bin dir still finds them. The source is
    npm's own prefix bin first (F1: node unpacked under ~/.local/opt with only node/npm/npx linked leaves
    it off PATH, so `which` found nothing), else `which`. A dangling link of that name (a removed node
    version) is replaced; a real file or a working link is left alone."""
    if env.os_name != "posix":
        return ""
    local_bin = Path.home() / ".local" / "bin"
    done = []
    for n in names:
        found = npm_bin(n)
        src = str(found) if found else winutil.which(n)
        dst = local_bin / n
        if not src or dst.exists() or Path(src).parent == local_bin:
            continue
        if dry_run:
            done.append(f"would-link {n}")
            continue
        try:
            local_bin.mkdir(parents=True, exist_ok=True)
            if dst.is_symlink():  # dangling (exists() is False for a broken link)
                dst.unlink()
            dst.symlink_to(src)
            done.append(f"linked {n}")
        except OSError:
            pass
    return f" ({', '.join(done)})" if done else ""


_NPM_ROOT_G: list = []  # memo: [Path | None]


def _npm_prefix_args() -> list[str]:
    """A sandbox-HOME rehearsal (AGENTIC_MERCY_SANDBOX=1) installs npm globals under $HOME/.npm-global,
    never into the real nvm / system prefix."""
    if os.environ.get("AGENTIC_MERCY_SANDBOX") == "1":
        return ["--prefix", str(Path.home() / ".npm-global")]
    return []


def npm_root_g() -> Path | None:
    """`npm root -g` (with the sandbox prefix when set); None when npm is absent or fails. A found root is
    memoised; a miss is not (node can land later in the same install pass, and a test's failing fake
    npm must not stick for the rest of the process)."""
    if _NPM_ROOT_G:
        return _NPM_ROOT_G[0]
    root = None
    try:
        cp = plat.run(["npm", "root", "-g", *_npm_prefix_args()], timeout=15)
        out = (cp.stdout or "").strip() if cp.returncode == 0 else ""
        root = Path(out.splitlines()[-1]) if out else None
    except Exception:  # noqa: BLE001
        root = None
    if root is not None:
        _NPM_ROOT_G.append(root)
    return root


def npm_bin_dir() -> Path | None:
    """Where `npm install -g` puts CLIs: <prefix>/bin on POSIX (`npm root -g` is <prefix>/lib/node_modules),
    the prefix itself on Windows (`npm root -g` is <prefix>\\node_modules)."""
    root = npm_root_g()
    if root is None:
        return None
    return root.parent if plat.IS_WINDOWS else root.parent.parent / "bin"


def npm_bin(name: str) -> Path | None:
    """``name`` in npm's global bin dir (the ``.cmd`` / ``.exe`` shim on Windows), or None."""
    d = npm_bin_dir()
    if d is None:
        return None
    for ext in (".cmd", ".exe", "") if plat.IS_WINDOWS else ("",):
        p = d / (name + ext)
        if p.is_file():
            return p
    return None


def npm_installed_bins(manifest: dict | None = None) -> list[str]:
    """The linked CLIs npm actually installed: the doctor row cli-on-path checks each on the shell PATH."""
    m = manifest if manifest is not None else _load_manifest()
    return [n for d in m.get("deps", []) for n in _bins_for(d) if npm_bin(n)]


def npm_pkg_present(pkg: str | None) -> bool:
    """A global npm package that ships no bin (`which` cannot see it): its package.json under npm root -g."""
    if not pkg:
        return False
    root = npm_root_g()
    return bool(root and (root / pkg / "package.json").is_file())


def _run_install(argv: list):
    """Run an install argv; an ``&&`` element splits it into steps, run in order until one fails."""
    steps: list[list] = [[]]
    for a in argv:
        steps.append([]) if a == "&&" else steps[-1].append(a)
    steps = [s + _npm_prefix_args() if s[:3] == ["npm", "install", "-g"] else s for s in steps]
    for step in steps:
        cp = npm_pack.install(step) if npm_pack.needs_pack(step) else plat.run(step, timeout=600)
        if cp.returncode != 0:
            break
    return cp


def _finish(dep: dict, status: str, env, dry_run: bool) -> str:
    """After PRESENT / INSTALLED: the pinned release binary of a script-less npm package (lean-ctx, F2),
    then the ~/.local/bin links (F1). A binary that could not be placed is the row's WARN."""
    key = dep.get("release_binary")
    if key:
        cfg = (_load_manifest().get("user_space") or {}).get(key) or {}
        root = npm_root_g()
        pkg_dir = root / cfg["npm_pkg"] if root is not None and cfg.get("npm_pkg") else None
        ok, note = release_bin.ensure(cfg, pkg_dir, dry_run=dry_run)
        if not ok:
            return f"WARN({dep['id']} binary: {note})"
        status += note
    return status + _link_bins(_bins_for(dep), env, dry_run)


def _uv_tool_ok(spec: dict) -> bool | None:
    """A uv tool's venv holds ``spec.version`` of ``spec.name`` and imports ``spec.import`` (jcodemunch-mcp
    without its ``openai`` extra could not embed: Rohit's PC, round 2). None when uv or the venv is absent
    (a pipx or hand install: left alone)."""
    cp = plat.run(["uv", "tool", "dir"], timeout=30)
    out = (cp.stdout or "").strip() if cp.returncode == 0 else ""
    if not out:
        return None
    venv = Path(out.splitlines()[-1].strip()) / spec["name"]
    py = venv / ("Scripts/python.exe" if plat.IS_WINDOWS else "bin/python")
    if not py.is_file():
        return None
    mods = ", ".join(["importlib.metadata as m"] + ([spec["import"]] if spec.get("import") else []))
    cp = plat.run([str(py), "-c", f"import {mods}; print(m.version({spec['name']!r}))"], timeout=60)
    lines = (cp.stdout or "").strip().splitlines()
    return cp.returncode == 0 and bool(lines) and lines[-1].strip() == spec["version"]


def install_deps(env, *, ci: bool = False, dry_run: bool = False,
                 skip_optional: bool = False) -> list[tuple[str, str]]:
    """Install what is missing; ``skip_optional`` leaves the manifest's optional deps alone (the
    daily self-heal: an absent optional dep is the user's choice)."""
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for dep in manifest.get("deps", []):
        if skip_optional and dep.get("optional"):
            continue
        did = dep["id"]
        which = dep.get("which")
        imp = dep.get("import")
        exists = dep.get(f"exists_{env.os_name}") or dep.get("exists")
        bins = _bins_for(dep)
        stale = False
        if ((which and (winutil.which(which) or (which in bins and npm_bin(which))))
                or (imp and _importable(imp, env))
                or (exists and Path(exists).expanduser().exists()) or npm_pkg_present(dep.get("npm_pkg"))):
            stale = bool(not ci and dep.get("uv_tool") and _uv_tool_ok(dep["uv_tool"]) is False)
            if not stale:
                results.append((did, _finish(dep, "PRESENT", env, dry_run)))
                continue
        install_cmd = dep.get(f"install_{env.os_name}") or dep.get("install")
        argv = _sub(install_cmd, _exec_tokens(env)) if install_cmd else []  # real paths, not {HOME} / {PYTHON}
        if stale and argv[:3] == ["uv", "tool", "install"] and "--force" not in argv:
            argv = argv[:3] + ["--force"] + argv[3:]  # same version, missing extra: --upgrade alone keeps the venv
        if ci and dep.get("ci_stub"):
            results.append((did, "SKIP(ci-stub)" if not dry_run or not install_cmd
                            else f"WOULD-INSTALL: {' '.join(argv)}"))
            continue
        if not install_cmd:
            results.append((did, "MISSING(no-installer)" if not dep.get("optional") else "SKIP(optional-absent)"))
            continue
        if dry_run:
            results.append((did, f"WOULD-INSTALL: {' '.join(argv)}"))
            continue
        cp = _run_install(argv)
        ok = cp.returncode == 0
        results.append((did, _finish(dep, "INSTALLED", env, False) if ok else f"WARN(rc={cp.returncode})"))
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
    ``cmd /c <shim> …``; only a name that resolves to a real ``.exe`` (a uv tool, the ``py`` launcher)
    stays direct. A name that does not resolve yet (the npm-global dir is not on this process's PATH
    until a new terminal) is wrapped too, never registered bare (A5v2-03): ``cmd`` finds it later."""
    if "--" not in cmd or cmd.index("--") + 1 >= len(cmd):
        return cmd
    i = cmd.index("--") + 1
    if not (winutil.which(cmd[i]) or "").lower().endswith(".exe"):
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
        if srv.get("which") and not (dry_run or ci) and not winutil.which(srv["which"]):
            # a server whose binary failed to install stays unregistered (roster WARN), not a cli-on-path FAIL
            results.append((name, f"SKIP(no {srv['which']} on PATH)"))
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
    ``{OLLAMA_URL}`` is resolved first (so a new ``OLLAMA_HOST`` reaches the live
    entries); other tokens stay skipped. Secrets (``env_from``) and existing extra
    env keys are never touched."""
    try:
        live = json.loads(user_config_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError):
        return []
    out: list[tuple[str, str]] = []
    ollama = plat.ollama_url()
    for srv in _load_manifest().get("mcp_servers", []):
        name, add = srv["name"], srv["add"]
        want = dict(s.split("=", 1) for i, a in enumerate(add)
                    if a == "-e" and "{" not in (s := add[i + 1].replace("{OLLAMA_URL}", ollama)))
        entry = live.get(name)
        if not entry or not want:
            continue
        cur = entry.get("env") or {}
        missing = {k: v for k, v in want.items() if cur.get(k) != v}
        if not missing:
            continue
        if dry_run or not winutil.which("claude"):
            out.append((name, f"WOULD-SET-ENV: {sorted(missing)}"))
            continue
        out.append((name, mcp_restore.replace_entry(
            name, {**entry, "env": {**cur, **missing}}, entry, f"ENV-SET {sorted(missing)}")))
    return out


def reconcile_mcp_always_load(*, dry_run: bool = False) -> list[tuple[str, str]]:
    """Manifest servers that declare ``alwaysLoad`` (the mandated MCPs since 2026-10-31) get the key in the live
    ~/.claude.json entry: remove + add-json of the SAME entry (mcp_restore.replace_entry). Servers the
    manifest does not mention, or that are not registered, are left alone."""
    try:
        live = json.loads(user_config_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError):
        return []
    out: list[tuple[str, str]] = []
    for srv in _load_manifest().get("mcp_servers", []):
        if "alwaysLoad" not in srv or srv["name"] not in live:
            continue
        want, entry = bool(srv["alwaysLoad"]), live[srv["name"]]
        if entry.get("alwaysLoad") is want:
            continue
        if dry_run or not winutil.which("claude"):
            out.append((srv["name"], f"WOULD-SET-ALWAYS-LOAD {str(want).lower()}"))
            continue
        out.append((srv["name"], mcp_restore.replace_entry(
            srv["name"], {**entry, "alwaysLoad": want}, entry, f"ALWAYS-LOAD {str(want).lower()}")))
    return out


def reconcile_mcp_pins(*, dry_run: bool = False, run=None) -> list[tuple[str, str]]:
    """Re-register user-scope npx/uvx MCP servers whose live package spec differs from the
    manifest's exact pin: remove + ``add-json`` of the SAME entry with only the spec in
    ``args`` swapped (env copied verbatim, restore on failure). OAuth/http servers and
    servers the manifest does not pin are skipped. Idempotent; takes effect next session.
    Not a dry run: ``npx_cache.maintenance`` prunes half-written npx cache entries, then warms
    each re-pinned npx package once, sequentially (``run(argv, timeout) -> (rc, out)`` is
    injectable; with no ``run``, ``AGENTIC_MERCY_SKIP_BASE_TOOLS`` (offline) skips both)."""
    import doctor_mcp  # type: ignore
    try:
        live = json.loads(user_config_file().read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError):
        return []
    out: list[tuple[str, str]] = []
    changed: list[tuple[str, str]] = []
    for name, have, want in doctor_mcp.pin_drift(_load_manifest(), live):
        entry = live[name]
        args = [str(a) for a in entry.get("args") or []]
        new_args = [doctor_mcp.swap_spec(a, have, want) for a in args]
        spec = f"{have} -> {want}"
        if new_args == args:
            out.append((name, f"SKIP(spec-not-in-args): {spec}"))
        elif dry_run:
            out.append((name, f"WOULD-PIN: {spec}"))
        elif not winutil.which("claude"):
            out.append((name, "SKIP(no-claude-cli)"))
        else:
            status = mcp_restore.replace_entry(name, {**entry, "args": new_args}, entry, f"PINNED {spec}")
            out.append((name, status))
            if status.startswith("PINNED") and re.search(r"\bnpx\b", " ".join([str(entry.get("command"))] + args)):
                changed.append((name, want))
    if not dry_run and (run or not os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS")):
        out += npx_cache.maintenance(changed, run)
    return out


def warm_added_npx(rows: list[tuple[str, str]], *, dry_run: bool = False, run=None) -> list[tuple[str, str]]:
    """Start each ``npx -y <spec>`` server that ``register_mcps`` just ADDED once, one at a time, so its
    npm install (markdownify's preinstall builds a Python venv) happens here, not in the first session's
    MCP initialize. Skipped like the pin warm-up: dry run, or offline (``AGENTIC_MERCY_SKIP_BASE_TOOLS``)
    with no injected ``run``. [(server, "WARMED <spec>" | "NOT-WARMED(rc=N) <spec>")]."""
    if dry_run or (run is None and os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS")):
        return []
    added = {name for name, status in rows if str(status).startswith("ADDED")}
    todo: list[tuple[str, str]] = []
    for srv in _load_manifest().get("mcp_servers", []):
        argv = [str(a) for a in srv.get("add") or []]
        if srv["name"] in added and "npx" in argv:
            i = argv.index("npx")
            if argv[i + 1:i + 2] == ["-y"] and len(argv) > i + 2:
                todo.append((srv["name"], argv[i + 2]))
    warmed = npx_cache.warm_npx([spec for _, spec in todo], run)
    return [(name, f"{status} {spec}") for (name, _), (spec, status) in zip(todo, warmed)]


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
        if cp.returncode == 3:  # a step that cannot apply here (no user manager): SKIP, never FAIL (FI-6)
            last = next((ln.strip() for ln in reversed((cp.stdout or "").splitlines()) if ln.strip()), "")
            results.append((sid, f"SKIP({last or 'rc=3'})"))
            continue
        ok = cp.returncode == 0
        results.append((sid, "OK" if ok else (f"WARN(rc={cp.returncode})" if step.get("optional") else f"FAIL(rc={cp.returncode})")))
    return results


def check_prereqs(env) -> list[tuple[str, str]]:
    """Report REQUIRED prerequisites that the installer does NOT auto-install
    (python3/node/git/claude). A MISSING required prereq blocks a full setup —
    the user must install it (per-OS command included) and re-run. Never mutates."""
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    windows = env.os_name == "windows"
    for p in manifest.get("prereqs", []):
        pid = p["id"]
        if windows and p.get("probe") == "python":  # `py -3` / python.exe that runs >= 3.10, never the Store stub
            # the cwd-safe which, the tools-dir python and the interpreter running us (install.ps1's own)
            found = winutil.pick_python(winutil.which, plat.run, tools=winpath.tools_dir(), current=sys.executable)
        else:
            found = winutil.which(p.get("which", pid))
            found = None if windows and found and winutil.store_stub(found) else found
        if found:
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
