# Rule catalog — code quality

## Conditional class names use a shared helper

IsUrgent: True
Category: Code Quality

### Description

Ensure conditional CSS is handled via your project’s shared class-merge utility (for example `cn`, `clsx`, or `classnames`) instead of ad-hoc ternaries that are hard to scan, **unless** the stack standard explicitly prefers raw strings for that layer.

### Suggested fix pattern

```ts
import { cn } from '@/lib/utils' // or your project’s canonical helper
const labelClass = cn(isActive ? 'text-primary-600' : 'text-gray-500')
```

## Utility-first styling (Tailwind-first when Tailwind is standard)

IsUrgent: True
Category: Code Quality

### Description

When the project standardizes on Tailwind, favor Tailwind utility classes instead of adding new CSS modules **unless** a combination is unmaintainable in utilities (complex selectors, keyframes, etc.).

## Classname ordering for easy overrides

### Description

When writing components, place the incoming `className` prop **after** the component’s own class values so consumers can override or extend styling.

Example:

```tsx
import { cn } from '@/lib/utils'

const Button = ({ className }: { className?: string }) => (
  <button type="button" className={cn('rounded-md px-3 py-2', className)} />
)
```

Update this file when your team adds, edits, or removes Code Quality rules so the catalog stays accurate.
