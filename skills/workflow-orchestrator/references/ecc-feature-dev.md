<!-- ecc:commands/feature-dev.md @25278e7d -->
# Seven-phase guided feature flow (ECC graft)

A mode for a feature the user wants to walk through step by step:

1. **Discovery** — restate the request, list unknowns, ask the sharpening questions.
2. **Exploration** — trace the relevant code (jcodemunch / graphify), cite `file:line`.
3. **Clarification** — resolve the open questions with the user before designing.
4. **Architecture** — two or three options with trade-offs; the user picks.
5. **Implementation** — TDD per task on the chosen design.
6. **Review** — santa-review on the diff; fix the confirmed findings.
7. **Summary** — what shipped, what was skipped, what is left.

Each phase ends with its output on disk (or in the run folder), not only in chat.
