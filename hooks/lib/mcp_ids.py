"""The exact repo arguments an MCP nudge names: jcodemunch ``repo``, graphify
``project_path``, jdocmunch ``repo`` (audit 02 B-04/B-06/B-07).

A guessed id misses: jcodemunch names its index after the git remote
(``Owner/remote-name``), not the folder. The ids are read from the indexes on disk
through ``index-lifecycle.py``'s own helpers (``_index_db_for``, ``_db_meta``,
``_doc_name_for``). Read-only and fail-soft: ``""`` when unknown, never raises.
"""
from __future__ import annotations

import functools
import importlib.util
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]


@functools.lru_cache(maxsize=1)
def _lifecycle():
    """index-lifecycle.py as a module (dashed file name), None on any error."""
    try:
        spec = importlib.util.spec_from_file_location("_mcp_ids_lifecycle", _HOOKS / "index-lifecycle.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001
        return None


def project_root(path) -> "Path | None":
    """Git root of ``path`` unless it is ``$HOME``, a non-repo or an infra root
    (``~/.claude``): those are never indexed, so no id applies there."""
    try:
        if not path:
            return None
        from .code_files import git_root, is_home, is_infra_root
        root = git_root(Path(path))
        if root is None or is_home(root) or is_infra_root(root):
            return None
        return root
    except Exception:  # noqa: BLE001
        return None


def _jcodemunch(root: Path) -> str:
    mod = _lifecycle()
    db = mod._index_db_for(root) if mod else None
    val = mod._db_meta(db, "repo") if db else None
    return val if isinstance(val, str) else ""


def _jdocmunch(root: Path) -> str:
    mod = _lifecycle()
    if not mod:
        return ""
    name = mod._doc_name_for(root)
    return f"local/{name}" if (Path(mod.DOC_INDEX_DIR) / f"{name}.json").is_file() else ""


@functools.lru_cache(maxsize=8)
def ids(root: str) -> dict:
    """``{"jcodemunch": id, "graphify": project_path, "jdocmunch": id}``; ``""`` = none."""
    out = {"jcodemunch": "", "graphify": "", "jdocmunch": ""}
    if not root:
        return out
    r = Path(root)
    for key, fn in (("jcodemunch", _jcodemunch), ("jdocmunch", _jdocmunch)):
        try:
            out[key] = fn(r)
        except Exception:  # noqa: BLE001
            pass
    try:
        if (r / "graphify-out" / "graph.json").is_file():
            out["graphify"] = str(r)
    except OSError:
        pass
    return out


def call_lines(root) -> list:
    """One line per indexed surface, naming the argument to pass. [] when none."""
    got = ids(str(root or ""))
    lines = []
    if got["jcodemunch"]:
        lines.append(f'jcodemunch repo="{got["jcodemunch"]}": search_symbols / get_context_bundle / '
                     "find_references before Read or grep")
    if got["graphify"]:
        lines.append(f'graphify project_path="{got["graphify"]}": query_graph / get_neighbors for wiring')
    if got["jdocmunch"]:
        lines.append(f'jdocmunch repo="{got["jdocmunch"]}": search_sections / get_section before reading docs')
    return lines
