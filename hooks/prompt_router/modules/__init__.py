"""prompt_router.modules — pure, import-safe router helpers.

``surface``      FE/BE/API/docs surface detection (prompt paths, vocab, cwd, repo stack)
``mcp_routes``   availability-aware MCP pointers from tool-intelligence.json
``code_intel``   indexed-symbol lookup (jcodemunch sqlite index)
``model_advice`` heavy-task "dispatch the Opus judge agent" line from model-policy.json
``asset_auth``   one login line per session when Higgsfield is registered but needs auth

Each returns an empty result on any error; none wraps stdin or keeps state beyond
the stack-fingerprint cache.
"""
from __future__ import annotations

__all__: list[str] = []
