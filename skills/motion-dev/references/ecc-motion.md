<!-- ecc:skills/motion-foundations, skills/motion-patterns, skills/motion-advanced @25278e7d -->
# Motion foundations (ECC graft)

- **Tokens, not literals:** durations (`fast` 150 ms, `base` 200–250 ms, `slow` 350–400 ms)
  and easings (standard, enter, exit) live in the design tokens; components reference them.
- **Reduced motion is mandatory:** every animation has a `prefers-reduced-motion` fallback
  (instant or opacity-only); `useReducedMotion()` in Motion components.
- **Layout animations only on transforms:** animate `transform` and `opacity`; never width,
  height, top or left on a hot path. Use `layout` / FLIP for size changes.
- One purpose per animation (feedback, orientation, continuity); decoration without a purpose
  is cut.
