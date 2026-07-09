# Component Colocation and Architecture

Organize code by **Feature**, not by **Technology**. Avoid monolithic `components/` or `hooks/` folders that become dumping grounds.

## Why it matters
- **Discoverability:** Related code is easier to find.
- **Maintainability:** Deleting a feature is safe (delete one folder) vs hunting files across the codebase.

## Incorrect
Grouping by file type.

```
src/
  components/
    Header.tsx
    Button.tsx
    LoginForm.tsx
    UserProfile.tsx
  hooks/
    useLogin.ts
    useProfile.ts
  utils/
    authHelpers.ts
```

## Correct
Group by Feature (Domain). Shared UI goes in `components/`.

```
src/
  features/
    Auth/
      LoginForm.tsx
      useLogin.ts
      authHelpers.ts
    User/
      UserProfile.tsx
      useProfile.ts
  components/ (Shared UI)
    Button.tsx
    Header.tsx
```
