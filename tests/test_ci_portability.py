"""test_ci_portability.py — regression guards for the CI-green fix.

The two-OS CI (ci.yml) runs on a fresh `actions/checkout` under an isolated
`actions/setup-python` interpreter: no PyYAML, and `~/.claude` is the runner's
empty home dir (NOT the checkout). These tests pin the three invariants that
keep both legs green forever:

  1. the skill validator (and every skills_lib consumer) runs on a clean Python
     with no PyYAML installed — PyYAML is an optional accelerant, not a hard dep;
  2. the installer's repo-local post-step scripts resolve against the installer's
     OWN repository root (_ROOT), so install-from-checkout works anywhere;
  3. every expected MCP in the manifest roster is registered in settings.json, so
     the doctor's mcp-roster probe passes when settings.json is the only source.

Runs on ubuntu-latest AND windows-latest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


# --------------------------------------------------------------------------- #
# 1. PyYAML is optional — the toolchain never CRASHES on a yaml-less interpreter
#    (the crash — ImportError, empty stdout — is what reddened run 29178753239).
#    Full R10 fidelity needs PyYAML (test 4 + the CI install step); this only
#    pins the no-crash safety net.
# --------------------------------------------------------------------------- #
def _yaml_blocked_env(tmp_path):
    stub = tmp_path / "yaml.py"
    stub.write_text("raise ImportError('No module named yaml')\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_validate_skills_no_crash_without_pyyaml(tmp_path):
    """Block `import yaml`, run the validator: it must RUN to its summary line
    (no ImportError traceback, non-empty stdout). rc may be nonzero because the
    stdlib fallback can't reproduce yaml's exact scalar folding for the R10
    baselines — but the process no longer crashes at import."""
    cp = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "validate_skills.py")],
        capture_output=True, text=True, env=_yaml_blocked_env(tmp_path),
        timeout=180, check=False,
    )
    assert "Traceback" not in cp.stderr and "ImportError" not in cp.stderr, cp.stderr[-600:]
    assert "validate_skills:" in cp.stdout, f"validator did not run; stdout:\n{cp.stdout[-400:]}"
    assert "HARD failures" in cp.stdout


def test_skills_lib_imports_without_pyyaml(tmp_path):
    """skills_lib itself must import + enumerate skills with no PyYAML present."""
    stub = tmp_path / "yaml.py"
    stub.write_text("raise ImportError('No module named yaml')\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import skills_lib as sl;"
        "print(len(sl.skill_names()))" % str(_ROOT / "scripts")
    )
    cp = subprocess.run([sys.executable, "-c", code], capture_output=True,
                        text=True, env=env, timeout=60, check=False)
    assert cp.returncode == 0, f"rc={cp.returncode} stderr={cp.stderr[-400:]}"
    assert cp.stdout.strip().isdigit() and int(cp.stdout.strip()) > 100


def test_validate_skills_full_fidelity_with_pyyaml():
    """With PyYAML present (the CI-installed + installer-declared dep, and any
    dev box), the validator is fully faithful: 0 HARD failures, clean exit."""
    import importlib.util as _ilu
    if _ilu.find_spec("yaml") is None:
        import pytest
        pytest.skip("PyYAML not installed in this interpreter")
    cp = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "validate_skills.py")],
        capture_output=True, text=True, timeout=180, check=False,
    )
    assert cp.returncode == 0, f"rc={cp.returncode}\n{cp.stdout[-400:]}\n{cp.stderr[-300:]}"
    assert "0 HARD failures" in cp.stdout, cp.stdout[-400:]


def test_pyyaml_declared_as_installer_dep():
    """PyYAML is a declared installer dependency (import-checked), so a fresh
    `install.py install` gives a full-fidelity doctor — not a degraded one."""
    manifest = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    pyy = [d for d in manifest["deps"] if d.get("import") == "yaml"]
    assert pyy, "no PyYAML dep (import==yaml) declared in manifest"
    assert pyy[0].get("install"), "PyYAML dep has no install command"
    # the import-check resolves PRESENT here (this interpreter has yaml)
    detect = _load("detect", "installer/detect.py")
    deps = _load("deps", "installer/deps.py")
    rows = dict(deps.install_deps(detect.detect(), ci=True, dry_run=True))
    assert rows.get(pyy[0]["id"]) == "PRESENT", rows


# --------------------------------------------------------------------------- #
# 2. repo-local post-step scripts resolve against _ROOT (install-from-checkout)
# --------------------------------------------------------------------------- #
def test_post_steps_resolve_repo_local_scripts_against_root():
    """With a bogus real ~/.claude (the CI condition), the installer must still
    resolve its repo-local post-step scripts against its own checkout (_ROOT)."""
    detect = _load("detect", "installer/detect.py")
    deps = _load("deps", "installer/deps.py")
    env = detect.Env(
        os_name="posix", is_windows=False, python="python3", node="node",
        git="git", claude_cli=None, tokens={}, real_dir="/nonexistent-xyz/.claude",
    )
    rows = dict(deps.run_post_steps(env, dry_run=True))
    # validate-skills is the non-optional post-step; it must resolve, not MISS.
    assert "validate-skills" in rows, rows
    assert not rows["validate-skills"].startswith("MISSING"), rows["validate-skills"]
    assert rows["validate-skills"].startswith("WOULD-RUN"), rows["validate-skills"]
    # and the WOULD-RUN command must point at the real checkout, not the bogus dir
    assert "/nonexistent-xyz/.claude" not in rows["validate-skills"], rows["validate-skills"]


# --------------------------------------------------------------------------- #
# 3. mcp-roster: every expected MCP is in settings.json (CI's only source)
# --------------------------------------------------------------------------- #
def test_manifest_mcp_roster_all_registered_in_settings():
    manifest = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    roster = manifest["doctor_probes"]["mcp_roster"]
    settings = json.loads((_ROOT / "settings.json").read_text(encoding="utf-8"))
    have = set((settings.get("mcpServers") or {}).keys())
    missing = [m for m in roster if m not in have]
    assert not missing, f"roster MCPs missing from settings.json: {missing}"


def test_jdocmunch_registered_in_settings_and_template():
    for f in ("settings.json", "settings.template.json"):
        d = json.loads((_ROOT / f).read_text(encoding="utf-8"))
        assert "jdocmunch" in (d.get("mcpServers") or {}), f"jdocmunch missing from {f}"
