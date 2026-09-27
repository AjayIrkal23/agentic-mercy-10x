---
description: Review animation/motion code against the Emil + Apple craft bar — easing, duration, interruptibility, performance, reduced-motion.
argument-hint: "[file/dir/component, or empty for the session diff]"
---

# /motion-review

Review motion against the craft bar. Before this existed, motion review was only
reachable as a side effect of the full `/invoke design` or `/invoke review` act —
there was no way to ask "just check my animations".

**Target:** `$ARGUMENTS` — if empty, review the motion in this session's diff.

## Run

1. **Load the bar.** Read `~/.claude/skills/review-animations/SKILL.md` and its
   `STANDARDS.md` (exact easing curves, duration tables, spring configs). For
   gesture/physical motion also read `~/.claude/skills/apple-design/SKILL.md`.

2. **Find the motion.** CSS `transition` / `animation` / `@keyframes`, Tailwind
   `transition-*` / `duration-*` / `animate-*`, Framer Motion / Motion One
   (`initial`, `animate`, `exit`, `variants`, `whileHover`, `whileTap`,
   `layoutId`), springs, GSAP, Lenis, `requestAnimationFrame`.

3. **Check each against the Ten Non-Negotiable Standards.** At minimum:
   - **Easing direction** — enter animations ease **OUT**. `ease-in` on an
     entrance is a defect, not a nit.
   - **Duration** — ≤400ms for UI chrome. Longer only for deliberate,
     large-surface transitions.
   - **Bounce** — none by default. **Exception:** gesture-released motion
     (drag-to-dismiss, flick, swipe) may use a subtle spring, `bounce: 0.1–0.3`,
     damping ~0.8–1.0. See the precedence section in `rules/ui-ux-playbook.mdc`.
   - **Interruptibility** — anything the user can grab must be reversible
     mid-flight, starting from the current on-screen value.
   - **Performance** — animate `transform`/`opacity`; never `width`/`height`/
     `top`/`left`. Blur/backdrop-filter/clip-path are legitimate when they stay
     smooth.
   - **Reduced motion** — every animation needs a `prefers-reduced-motion`
     alternative. Non-optional.
   - **Purpose & frequency** — motion that fires on every render, or that a user
     sees hundreds of times a day, should be shorter or absent. Sometimes the
     right answer is no animation.

4. **Report.** Group by severity. For each finding: `file:line`, what's wrong,
   the exact corrected value (curve, ms, config). Default to flagging —
   approval is earned, not assumed.

## Related

- Whole-codebase motion audit with executable plans → `improve-animations`
- A static surface that may deserve motion → `find-animation-opportunities`
  (restraint-first; expect most candidates rejected)
- Naming an effect before building it → `animation-vocabulary`
- Add motion to an existing surface → `/impeccable animate`

## Note

The `impeccable-design-gate` PreToolUse hook already blocks writes that trip
`bounce-easing`, `layout-transition`, ease-in-on-enter, >400ms durations, or
missing `prefers-reduced-motion`. This command is the deeper judgment pass on
top of that mechanical floor — it catches what a regex cannot: whether the
motion is *right*, not merely permitted.
