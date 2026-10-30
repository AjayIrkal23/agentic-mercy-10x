---
name: ecc-digest-llm-sdk
description: ECC's small Python LLM SDK (one provider interface with Claude, OpenAI, OpenAI-compatible and Ollama backends, a prompt builder, a tool executor and a model-selector CLI); the reusable idea is a minimal provider ABC with capability flags.
---
<!-- ecc-digest:llm-sdk@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# LLM SDK

## What it is
`src/llm` is a Python package with a module entry point. `core/interface.py` defines an abstract provider: `generate(input) -> output`, `list_models()`, `validate_config()`, capability methods `supports_tools()` (true by default) and `supports_vision()` (false by default), and `get_default_model()`; `core/types.py` holds the input, output, model-info and provider-type types, and a provider error class carries the provider, a code and details. `providers/` has backends for Claude, OpenAI, OpenAI-compatible servers, Ollama and a reasoning-model variant. `prompt/builder.py` assembles prompts (its templates package is empty at the vendored commit), `tools/executor.py` runs tool calls, and `cli/selector.py` is an interactive model picker. The study note lists it with ECC's harness adapters and dashboards as irrelevant to a single-harness setup and did not review it in depth.

## The reusable idea
When a script must talk to more than one model backend, keep the seam this small: one abstract class with a single generate method over plain input and output types, capability flags instead of provider checks scattered through callers, a config validation method that runs before the first call, and one error type that records which provider failed. Callers then switch backends by configuration and never import a vendor SDK directly.

## Why not adopted
The workbench calls models through Claude Code itself, and the code-index summaries use a local or LAN Ollama through the indexers' own clients; no workbench script needs a multi-provider SDK. Adding one would bring network egress to other providers and code nobody maintains here.

## Upstream paths
- `src/llm`
