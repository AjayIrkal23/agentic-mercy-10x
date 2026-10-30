"""prompt_router.modules — pure, import-safe router helpers.

``surface``         FE/BE/API/docs surface detection (prompt paths, vocab, cwd, repo stack,
                    ECC stack indicators, package manager)
``mcp_routes``      availability-aware MCP pointers from tool-intelligence.json
                    (claude.ai connectors count as available)
``code_intel``      indexed-symbol lookup (jcodemunch sqlite index)
``model_advice``    heavy-task "dispatch the Opus judge agent" line from model-policy.json
                    (owned by package model-routing)
``asset_auth``      one login line per session when Higgsfield is registered but needs auth
``workflow_routes`` one WORKFLOW line pointing at a saved workflow (workflows/index.json)
``library_routes``  <= 2 LIBRARY lines (owned by package library; optional)

Each returns an empty result on any error; none wraps stdin or keeps state beyond
the stack-fingerprint cache.
"""
from __future__ import annotations

__all__: list[str] = []
