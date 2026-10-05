"""WP5 (audit 2026-10-05, E-01..E-15 + santa-diff P7): /invoke run folders, the team
path, agent contracts and preload weight. Generator output is checked through
render_all (no disk writes); agent files are read as they are on disk."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "hooks"
AGENTS_DIR = ROOT / "agents"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


gen = _load("gen_invoke_skills_wp5", HOOKS / "gen-invoke-skills.py")
blocks = _load("gen_agent_skill_blocks_wp5", HOOKS / "gen-agent-skill-blocks.py")
CFG = json.loads((HOOKS / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))
POLICY = json.loads((HOOKS / "model-policy.json").read_text(encoding="utf-8"))
RENDER = gen.render_all(CFG, POLICY)
INVOKE = RENDER[gen.SKILLS_DIR / "invoke" / "SKILL.md"]
STATUS = RENDER[gen.SKILLS_DIR / "invoke-status" / "SKILL.md"]
ACTS = gen.load_acts(CFG)
DELEGATORS = {a["act"]: RENDER[gen.SKILLS_DIR / f"invoke-{a['act']}" / "SKILL.md"] for a in ACTS}
TEAM = (AGENTS_DIR / "team-lead.md").read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return dict(re.findall(r"^([\w-]+):\s*(.*?)\s*$", m.group(1), re.M)) if m else {}


def _agent(name: str) -> str:
    return (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _agent_files() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in AGENTS_DIR.glob("*.md") if p.stem != "README"}


# --- E-01: the main session leads a mixed impl; fallback = surface_routing.mixed ------

def test_mixed_impl_is_led_by_the_main_session():
    assert "spawn `team-lead`" not in INVOKE and "plain subagent" not in INVOKE
    mixed = CFG["categories"]["IMPLEMENT"]["surface_routing"]["mixed"]
    assert " → ".join(f"`{a}`" for a in mixed) in INVOKE  # sequential fallback, single-sourced
    for agent in mixed:
        name, artifact = gen.TEAMMATES[agent]
        assert f'name="{name}", subagent_type="{agent}"' in INVOKE
        assert f'"{name}": "{artifact}"' in INVOKE
    assert "you (the main session) are the team lead" in INVOKE


def test_team_lead_is_a_playbook_not_a_spawnable_agent():
    assert not TEAM.startswith("---")  # no frontmatter: Claude Code does not load it as an agent
    assert "main session" in TEAM
    assert "team-lead" not in POLICY["agent_pins"]["opus"]
    assert "team-lead" not in blocks.AGENT_SKILLS


# --- E-02: one run.json schema, artifacts relative to the run folder -----------------

def test_one_run_json_schema_in_invoke_and_team_playbook():
    for key in ("task", "slug", "run", "started_utc", "start_sha", "acts", "done", "models",
                "team", "expected_artifacts"):
        assert f'"{key}"' in gen.RUN_JSON, key
    assert gen.RUN_JSON in INVOKE
    assert gen.RUN_JSON in TEAM
    assert '"$RUN/' not in INVOKE  # values are bare file names inside the run folder
    assert '"IMPL-REPORT-BE.md"' in TEAM


# --- E-05: single-act skills dispatch through the guard and keep run.json -------------

def test_single_act_skills_route_through_the_guard_and_keep_run_json():
    for a in ACTS:
        text = DELEGATORS[a["act"]]
        fm = _frontmatter(text)
        assert "context" not in fm and "model" not in fm and "agent" not in fm, a["act"]
        assert "newest" not in text, a["act"]
        assert "--run" in text and "run.json" in text, a["act"]
        assert f'subagent_type="{a["agent"]}"' in text, a["act"]


# --- E-06: resume reuses the run folder ---------------------------------------------

def test_invoke_resume_reuses_the_run_folder():
    assert "--run <dir>" in INVOKE
    assert "skip every act already in `run.json.done`" in INVOKE
    assert "--run <run path>" in STATUS
    assert "git rev-parse --show-toplevel" in STATUS


# --- E-08: absolute run path; refactor runs in the main tree --------------------------

def test_run_path_is_absolute_and_refactor_has_no_worktree():
    assert 'RUN="$(git rev-parse --show-toplevel)/.claude/runs/' in INVOKE
    ref = _agent("refactor-specialist")
    assert "isolation" not in _frontmatter(ref)
    assert "isolation: worktree" not in ref


# --- E-09: every act's artifact is named in its agent's own contract ------------------

def test_every_act_artifact_is_named_in_its_agent_body():
    missing = {a["agent"]: a["artifact"] for a in ACTS
               if a["artifact"].split("{")[0] not in _agent(a["agent"])}
    assert not missing, missing


def test_agents_write_to_the_dispatched_path_not_only_the_project_root():
    bad = [n for n, t in _agent_files().items() if "in the project root" in t]
    assert not bad, bad


# --- E-07: preload weight per spawn --------------------------------------------------

CAP = 20_000
CAP_EXCEPTIONS = {"frontend-uiux-designer": 30_000}  # design-taste-frontend alone is ~21.8k


def _skill_file(name: str) -> Path | None:
    if ":" not in name:
        p = ROOT / "skills" / name / "SKILL.md"
        return p if p.is_file() else None
    plug, skill = name.split(":", 1)
    for pat in (f"plugins/cache/*/{plug}/*/skills/{skill}/SKILL.md",
                f"plugins/marketplaces/*/plugins/{plug}/skills/{skill}/SKILL.md"):
        hit = next(iter(sorted(ROOT.glob(pat))), None)
        if hit:
            return hit
    return None


def test_preload_weight_per_spawn_is_capped():
    canon = blocks._canon()
    heavy = {}
    for agent, raw in blocks.AGENT_SKILLS.items():
        chars = len(_agent(agent))
        for s in blocks._collapse(raw, canon)[:blocks.MAX_SKILLS]:
            f = _skill_file(s)
            chars += len(f.read_text(encoding="utf-8")) if f else 0
        tokens = chars // 4
        if tokens > CAP_EXCEPTIONS.get(agent, CAP):
            heavy[agent] = tokens
    assert not heavy, heavy


def test_doubt_driven_is_never_a_persona_preload():
    # skills/doubt-driven-development: "Do NOT add this skill to a persona's skills: frontmatter"
    assert not [a for a, s in blocks.AGENT_SKILLS.items() if "doubt-driven-development" in s]


# --- E-10 / E-11 / E-14: agent bodies follow the doctrine -----------------------------

def test_agent_bodies_follow_doctrine():
    files = _agent_files()
    for name, text in files.items():
        assert "per-task commit" not in text, name
        assert "the lead commits" not in text, name
        assert "memory: user" not in text, name
    assert "--config auto" not in files["security-sentinel"]
    assert "GO_UDP" not in files["backend-implementor-specialist"]
    assert "make tdd" not in files["backend-implementor-specialist"]
    integ = files["integrator-specialist"]
    assert "with the real backend" not in integ
    assert "BLOCKED-NEEDS-RUNNING-APP" in integ


# --- E-12: doctrine drift in docs and texts I own -------------------------------------

def test_model_doc_drift_fixed():
    readme = (AGENTS_DIR / "README.md").read_text(encoding="utf-8")
    assert "17 specialists + `team-lead`" not in readme
    assert "`memory: user`" not in readme
    wmg = (HOOKS / "workflow-model-guard.py").read_text(encoding="utf-8")
    assert "UI/UX agentType -> opus" not in wmg
    assert "team-lead" not in wmg
    assert "consumed by /invoke" not in POLICY["task_matrix"]["_comment"]
    assert "xhigh" in POLICY["effort_defaults"]["closers"]


# --- santa-diff P7: `model-mode show` reads the state dir the guards read -------------

def test_model_mode_show_reads_the_guards_state_dir(tmp_path):
    cfg = tmp_path / "cfg"
    (cfg / "state").mkdir(parents=True)
    (cfg / "state" / "opus-only-mode").write_text("", encoding="utf-8")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(cfg), CLAUDE_HOOK_STATE_DIR=str(tmp_path / "other"))
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "model-mode.py"), "show"],
                          cwd=tmp_path, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "global kill-switch  : opus" in proc.stdout
    assert not (tmp_path / "other").exists()
