# Anti-Pattern: Importing from Dist

Never import files from the `dist/`, `build/`, or generated output folders of your libraries or your own project.

## Why it matters
- **Bundling double:** You might include the same library twice (once source, once bundled).
- **Optimization loss:** Pre-bundled code cannot be effectively tree-shaken by your Vite build.
- **Dev-Experience:** Source maps often break, making debugging impossible.

## Incorrect
```tsx
import { Button } from 'expensive-library/dist/bundle.js';
import { Helper } from '../dist/utils.js';
```

## Correct
Import the source modules or the main package entry point.

```tsx
import { Button } from 'expensive-library'; // Let Node/Vite resolve "main" or "exports"
import { Helper } from '../utils'; // Import source TS/JS
```
