<!-- ecc:the-shortform-guide.md#skills-first @25278e7d -->
# Skills first (ECC graft)

- A skill is the canonical home of a capability; a slash command is only a shim that loads
  the skill with arguments.
- New capability → write or extend a skill. Add a command only when the user wants a short
  name to type, and keep its body to the skill call.
- An agent is for work that needs its own context window (a clean slate, a cap on turns);
  its body names the skills it preloads instead of restating them.
