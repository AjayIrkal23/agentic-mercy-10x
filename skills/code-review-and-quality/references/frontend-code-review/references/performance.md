# Rule catalog — performance

## Stable data reads for complex visual editors

IsUrgent: True
Category: Performance

### Description

For large graph/flow/editors (e.g. React Flow, custom canvases), prefer the library’s documented hooks/stores for reading and mutating graph state instead of ad-hoc mirroring that desynchronizes UI and model state.

## Complex prop stability

IsUrgent: False
Category: Performance

### Description

Only require stable object, array, or map props when there is a clear reason: the child is memoized, the value participates in effect/query dependencies, the value is part of a stable-reference API contract, or profiling shows avoidable re-renders. Do not request `useMemo` for every inline object by default.

Risky:

```tsx
<HeavyComp
  config={{
    provider: 'x',
    detail: 'y',
  }}
/>
```

Better when stable identity matters:

```tsx
const config = useMemo(
  () => ({
    provider: 'x',
    detail: 'y',
  }),
  [provider, detail]
)

<HeavyComp config={config} />
```

Update this file when your team edits Performance rules.
