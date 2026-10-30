"""lib/blast_radius.py: the ONE importer counter (gateguard-write-gate + bash-write-gate) and the
sensitive/secret target classifier. Pure Python walk (no grep: Windows has none), segment-based
classification (`authors.md` and `monkey.ts` are not matches), over-budget scans fail open."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import blast_radius as br  # noqa: E402

_PY = {  # the five Python import forms of test_gateguard
    "app/checkout.py": "import shop.payments_core\n",
    "app/invoice.py": "from shop.payments_core import charge\n",
    "shop/ledger.py": "from .payments_core import charge\n",
    "app/sub/refunds.py": "def f():\n    from ..shop.payments_core import refund\n",
    "app/report.py": "from shop import other, payments_core\n",
}
_TS = {  # the four TS/JS forms of test_gateguard_wp3
    "src/a.ts": "import { W } from './components/Widget'\n",
    "src/b.tsx": "import W from \"../components/Widget\";\n",
    "src/c.js": "const W = require('./components/Widget.js')\n",
    "src/d.ts": "export { W } from './components/Widget'\n",
}


def _write(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


@pytest.fixture
def pyrepo(tmp_path_factory):
    root = tmp_path_factory.mktemp("brrepo")
    (root / ".git").mkdir()
    _write(root, {"shop/payments_core.py": "def charge():\n    pass\n", **_PY,
                  "app/notes.py": "# payments_core handles charges\nfrom payments_core_extra import thing\n"})
    return root, root / "shop" / "payments_core.py"


@pytest.fixture
def tsrepo(tmp_path_factory):
    root = tmp_path_factory.mktemp("brrepo")
    (root / ".git").mkdir()
    _write(root, {"src/components/Widget.tsx": "export const W = 1\n", **_TS,
                  "src/e.ts": "// moved from ./components/Widget\n",
                  "src/f.ts": "import G from './components/WidgetGroup'\n"})
    return root, root / "src" / "components" / "Widget.tsx"


def test_python_importers_are_found_and_counted(pyrepo):
    root, target = pyrepo
    found = {Path(e["path"]).name for e in br.importers(str(target), str(root))}
    assert found == {"checkout.py", "invoice.py", "ledger.py", "refunds.py", "report.py"}
    assert br.count(str(target), str(root)) == 5


def test_ts_importers_skip_comments_and_sibling_stems(tsrepo):
    root, target = tsrepo
    found = {Path(e["path"]).name for e in br.importers(str(target), str(root))}
    assert found == {"a.ts", "b.tsx", "c.js", "d.ts"}
    assert br.count(str(target), str(root)) == len(found)


def test_root_defaults_to_the_project_root(tsrepo):
    root, target = tsrepo
    assert Path(br.project_root(str(target))).resolve() == root.resolve()
    assert br.count(str(target)) == 4


def test_project_root_never_climbs_to_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    (home / ".git").mkdir()  # even a git-ish HOME is a container, not a repo
    f = home / "loose_module.py"
    f.write_text("x = 1\n", encoding="utf-8")
    assert Path(br.project_root(str(f))).resolve() == home.resolve()
    sub = home / "proj" / "x.py"
    sub.parent.mkdir()
    sub.write_text("x = 1\n", encoding="utf-8")
    assert Path(br.project_root(str(sub))).resolve() == sub.parent.resolve()


def test_over_budget_scan_fails_open(pyrepo):
    root, target = pyrepo
    assert br.importers(str(target), str(root), budget_s=0.0) == []


def test_short_stems_are_never_scanned(tsrepo):
    root, _ = tsrepo
    assert br.importers(str(root / "src" / "app.ts"), str(root)) == []


def test_constants():
    assert br.THRESHOLD == 5
    assert br.EXCLUDE_DIRS >= {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv", ".next",
                               ".turbo", "coverage", "target"}


@pytest.mark.parametrize("path,want", [
    ("src/auth/session.ts", "sensitive"), ("server/payment/charge.py", "sensitive"), ("billing/x.ts", "sensitive"),
    ("db/migrations/0003_x.sql", "sensitive"), (".github/workflows/ci.yml", "sensitive"),
    ("Dockerfile", "sensitive"), ("api/Dockerfile.prod", "sensitive"), ("app/security/csp.ts", "sensitive"),
    (".env", "secret"), (".env.local", "secret"), ("config/.env.production", "secret"),
    ("certs/server.pem", "secret"), ("~/.ssh/id_ed25519", "secret"), ("id_rsa.pub", "secret"),
    ("infra/secrets.yaml", "secret"), ("credentials.json", "secret"), ("keys/stripe.txt", "secret"),
    ("api.key", "secret"),
    ("src/components/Widget.tsx", None), ("authors.md", None), ("docs/payment-flow.md", None),
    (".env.example", None), ("monkey.ts", None),
])
def test_sensitivity_table(path, want):
    assert br.sensitivity(path) == want, path
    assert br.sensitivity(path.replace("/", "\\")) == want, path


def test_sensitivity_label_names_the_match():
    assert br.sensitivity_label("src/auth/session.ts") == "auth/"
    assert br.sensitivity_label(".env") == ".env"
    assert br.sensitivity_label("api/Dockerfile.prod") == "Dockerfile"
    assert br.sensitivity_label("src/x.ts") == ""
