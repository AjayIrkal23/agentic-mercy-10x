<!-- ecc:rules/react, rules/react/coding-style.md, rules/react/hooks.md, rules/react/patterns.md, rules/react/security.md, rules/react/testing.md, skills/react-patterns @25278e7d -->
# React rules (ECC graft)

- **When not to `useEffect`:** derived values are computed during render; event-driven work
  belongs in the event handler; data fetching goes through the query layer. An effect is for
  syncing with something outside React.
- **Cleanup:** every subscription, timer, listener or abort-able request in an effect returns
  a cleanup that undoes it.
- **Stale closures:** list every value the effect or callback reads in its deps; use the
  functional updater (`setX(x => x + 1)`) when the next state depends on the previous.
- **External stores:** subscribe with `useSyncExternalStore`, not an effect + setState.
- **Derived vs stored state:** store the minimum; derive the rest. Two pieces of state that
  must agree are one piece of state.
- **No setState during render** (outside the documented "adjust state on prop change" pattern).
- **Security:** never `dangerouslySetInnerHTML` with unsanitised input; no secrets in client
  bundles.
