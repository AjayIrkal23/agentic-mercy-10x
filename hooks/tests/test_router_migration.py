"""FIX-r2 H2: a migration / port / rewrite "from A to B" is IMPLEMENT; a size-L invoke chain that writes
(tests, docs) but names no code-mutating act gets `impl`; size L drops the SMALL intent."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import classify as C  # noqa: E402
from test_workflow_routes import _args, _items, home  # noqa: E402,F401 (fixture)

BIG = ("Migrate the whole backend from Express to Fastify across all 40 route files, add tests for every "
       "route, update the docs, then run a full security review and a Santa review of the result")


def test_big_migration_is_a_large_implementation():
    p = C.classify({"prompt": BIG, "cwd": "/tmp/x"})
    assert "IMPLEMENT" in p.intents and p.size == "L" and "SMALL" not in p.intents
    assert "impl" in p.acts


def test_port_from_a_to_b_is_implement():
    p = C.classify({"prompt": "Port the auth service from Python to Go", "cwd": "/tmp/x"})
    assert "IMPLEMENT" in p.intents and "impl" in p.acts


@pytest.mark.parametrize("prompt", ["why did the dev port change from 3000 to 3001 after the deploy?",
                                    "how do I convert this date from UTC to IST in my head",
                                    "how do I read this date in IST in my head"])
def test_a_from_to_question_is_not_implement(prompt):
    # SANTA-FINAL hooks F7: the phrase cue skips questions
    assert "IMPLEMENT" not in C.classify({"prompt": prompt, "cwd": "/tmp/x"}).intents


def test_negated_migration_is_not_implement():
    p = C.classify({"prompt": "no need to migrate from X to Y, just review it", "cwd": "/tmp/x"})
    assert "IMPLEMENT" not in p.intents


def test_workflow_acts_carry_impl_before_security(home):
    acts = _args(_items(BIG)[0]["text"])["acts"]
    assert "impl" in acts and acts.index("impl") < acts.index("security")


def test_read_only_large_chain_gets_no_impl(home):
    it = _items("run a full security review and an audit across all 40 route files of the whole system")
    if it and "invoke" in it[0]["text"]:
        assert "impl" not in _args(it[0]["text"])["acts"]


def test_docs_only_large_chain_gets_no_impl(home):
    it = _items("update the documentation for the entire codebase, every module and every README from scratch")
    assert _args(it[0]["text"])["acts"] == ["docs"]


def test_tests_only_large_chain_gets_no_impl(home):
    it = _items("add tests across the whole codebase for every module from scratch")
    assert _args(it[0]["text"])["acts"] == ["test"]
