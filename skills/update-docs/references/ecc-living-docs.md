<!-- ecc:skills/living-docs-governance, commands/update-docs.md @25278e7d -->
# Four doc roles (ECC graft)

Classify each doc before editing it; one doc, one role:

| Role | Answers | Example |
|---|---|---|
| reference | "what exactly is X?" | API tables, config keys |
| how-to | "how do I do Y?" | runbooks, recipes |
| explanation | "why is it like this?" | architecture notes, ADRs |
| tutorial | "teach me from zero" | onboarding walkthroughs |

A change in behavior updates the reference first; how-tos that use it next; explanations only
when the reason changed.
