---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
<!-- ecc:rules/python/hooks.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Python Hooks

> This file extends [common/hooks.md](../common/hooks.md) with Python specific content.

## PostToolUse Hooks

Configure in `~/.claude/settings.json`:

- **black/ruff**: Auto-format `.py` files after edit
- **mypy/pyright**: Run type checking after editing `.py` files

## Warnings

- Warn about `print()` statements in edited files (use `logging` module instead)
