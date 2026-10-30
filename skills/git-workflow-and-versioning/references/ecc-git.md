<!-- ecc:skills/git-workflow, skills/conventional-commit-review, agents/commit-reviewer.md, commands/pr.md, commands/prp-pr.md, commands/prp-commit.md, rules/common/git-workflow.md, scripts/lib/claude-commit-attribution.js @25278e7d -->
# Commits and PRs when the user asks (ECC graft)

Everything here applies only when the user asks for a commit or a PR; the agent never commits
or opens a PR on its own.

## Conventional commit drafting

`type(scope): summary` with type in feat, fix, refactor, docs, test, chore, perf, build, ci;
summary in the imperative, under 72 chars; body says why, not what. One logical change per
commit; a refactor and a feature are two commits.

## PR template discovery

Before writing a PR body, look for `.github/PULL_REQUEST_TEMPLATE.md`,
`.github/PULL_REQUEST_TEMPLATE/*.md` and `docs/PULL_REQUEST_TEMPLATE.md`; fill the template's
sections instead of inventing a format.

## Attribution trailer

When the session's attribution lines are present, end the commit message or PR body with
them exactly as given; never invent or duplicate a trailer.
