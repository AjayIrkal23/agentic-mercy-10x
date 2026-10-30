---
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
---
<!-- ecc:rules/rust/hooks.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Rust Hooks

> This file extends [common/hooks.md](../common/hooks.md) with Rust-specific content.

## PostToolUse Hooks

Configure in `~/.claude/settings.json`:

- **cargo fmt**: Auto-format `.rs` files after edit
- **cargo clippy**: Run lint checks after editing Rust files
- **cargo check**: Verify compilation after changes (faster than `cargo build`)
