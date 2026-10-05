"""CI coverage added by WP7 (audit 2026-10-05 I-04, I-06, I-14). Text checks only:
PyYAML is optional on the runners and these pin the presence of each step."""
from __future__ import annotations

import re
from pathlib import Path

CI = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ubuntu_leg_runs_the_lowest_middle_and_newest_python():
    for ver in ("3.10", "3.12", "3.14"):
        assert f'python: "{ver}"' in CI, ver


def test_every_action_is_pinned_to_a_commit_sha():
    uses = re.findall(r"uses:\s*(\S+)", CI)
    assert uses and all(re.search(r"@[0-9a-f]{40}$", u) for u in uses), uses


def test_render_check_runs_against_a_rendered_temp_file():
    assert re.search(r"render\.py --check --out \S+ --user \S+", CI)


def test_mods_job_runs_validate_tests_and_tsc():
    assert "scripts/validate_mods.py" in CI and "tsc -p" in CI and "claude-code@" in CI


def test_sandboxed_install_ci_rehearsal():
    assert "install.py --ci" in CI and "CLAUDE_CONFIG_DIR" in CI and "git diff --exit-code" in CI
