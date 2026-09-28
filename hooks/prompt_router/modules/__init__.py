"""prompt_router.modules — pure, import-safe router helpers.

``surface``      FE/BE/API/docs surface detection (prompt paths, vocab, cwd, repo stack)
``mcp_routes``   availability-aware MCP pointers from tool-intelligence.json
``code_intel``   indexed-symbol lookup (jcodemunch sqlite index)
``model_advice`` heavy-task /model nudge from model-policy.json

Each returns an empty result on any error; none wraps stdin or keeps state beyond
the stack-fingerprint cache.
"""
from __future__ import annotations

__all__: list[str] = []
