# backend-code-review

> Absorbed into `code-review-and-quality` (P5 consolidation). Method content preserved verbatim below.

---

## Use When

- User asks for a code review of backend files (controllers, services, routes, schemas, middlewares, migrations).
- Reviewing a PR with server-side impact before merge.
- Checking correctness, maintainability, security posture, or test coverage of a recently implemented backend feature.
- Pre-merge audit of local staged changes that touch API logic, database queries, or auth.

## Do Not Use

- For frontend-only file reviews (use `frontend-code-review`).
- As a replacement for `owasp-security` when the task is specifically a security audit.
- For reviewing infrastructure-only files (hooks, CI pipelines) where no application logic changes.

# Backend code review

Workflow and structure adapted from [google-gemini/gemini-cli `code-reviewer`](https://github.com/google-gemini/gemini-cli/tree/main/.gemini/skills/code-reviewer). Preflight commands are **not** pinned to `npm run preflight`; choose what the repository documents.

## Workflow

### 1. Determine review target

- **Remote PR:** if the user gives a PR number or URL (e.g. “Review PR #123”), target that PR.
- **Local changes:** if they ask to “review my changes”, use staged and/or unstaged diffs.

### 2. Preparation

#### Remote PRs

1. **Checkout** (when using GitHub CLI):

   ```bash
   gh pr checkout <PR_NUMBER>
   ```

2. **Preflight:** run the project’s standard checks from repo docs (see below).

3. **Context:** read the PR description and existing review comments.

#### Local changes

1. **Identify changes:** `git status`; `git diff` and/or `git diff --staged`.
2. **Preflight (optional for small diffs):** offer to run the repo’s lint/tests when changes are non-trivial.

### 3. Preflight by repository type

- **Node / package.json:** prefer `npm run lint`, `pnpm lint`, `yarn lint`, or a documented `test` / `ci` script.
- **Go + Makefile:** e.g. `make lint` and `go test ./...` when present.
- **Repo guide:** if **`AGENTS.md`** (or equivalent) exists, use it for verification commands and layout conventions.
- **Unknown:** infer from `README`, `CONTRIBUTING`, or CI workflow files; otherwise ask the user which command to run.

### 4. In-depth analysis

Cover:

- **Correctness** — logic, edge cases, API contracts, migrations applied safely
- **Maintainability** — structure, naming, fits existing service/route/schema patterns
- **Readability** — clarity and consistency with project style
- **Efficiency** — query N+1, unnecessary allocations, hot paths
- **Security** — authz, injection, secrets, unsafe deserialization
- **Error handling** — HTTP errors, DB errors, rollback, user-visible messages
- **Testability** — unit/integration coverage; missing cases for new behavior

Optional pattern checklist (not mandatory): [references/examples/sample-go-service-layout-checklist.md](references/examples/sample-go-service-layout-checklist.md).

### 5. Provide feedback

#### Structure

- **Summary** — high-level overview
- **Findings**
  - **Critical** — bugs, security, data loss risk, breaking changes
  - **Improvements** — design, performance, maintainability
  - **Nitpicks** — style/minor (optional)
- **Conclusion** — Approved / Request changes (with reasons)

#### Tone

Be constructive and specific; explain *why* each change matters.

### 6. Cleanup (remote PRs only)

After the review, ask whether to switch back to the default branch (`git checkout main` or equivalent).

## References

- [source-attribution.md](references/source-attribution.md)
- [examples/sample-go-service-layout-checklist.md](references/examples/sample-go-service-layout-checklist.md)
