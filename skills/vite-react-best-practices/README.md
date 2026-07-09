# Vite React Best Practices Skill

This repository contains the `vite-react-best-practices` skill, a comprehensive guide for building production-ready React Single Page Applications (SPAs) with Vite. This skill is designed to be used by AI coding assistants to provide guidance on performance, architecture, and deployment best practices.

## What's Inside?

This skill provides a collection of rules and guidelines organized into the following categories:

### 1. Vite SPA Deployment (CRITICAL)
- **Static Rewrites**: Mandatory for client-side routing.
- **Caching Strategy**: Immutable assets, no-cache index.html.
- **Build Validation**: Preview before push.
- **Environment Variables**: `VITE_` prefix and security.

### 2. React Core Performance
- **Route Splitting**: Lazy load pages.
- **Server State**: Use React Query/SWR.
- **Memoization**: When to use useMemo/useCallback.
- **Image Optimization**: CLS prevention.

### 3. Architecture & Cleanup
- **Colocation**: Feature-based structure.
- **Anti-Patterns: Import from Dist**: Avoid bundling twice.
- **Troubleshooting**: Common Vite fixes.

For a complete, compiled version of all rules, see the `AGENTS.md` file.

## Installation

You can install this skill for your AI coding assistant using the `npx skills add` command:

```bash
npx skills add claudiocebpaz/vite-react-best-practices
```

This command will install the skill for all supported AI agents found on your system, such as Gemini CLI, Claude Code, OpenCode, and others.

## Usage

Once installed, your AI coding assistant will automatically use this skill when you ask for help with tasks related to Vite and React. For example, you can ask it to:

-   "Review my Vite project for performance issues."
-   "Help me set up route splitting in my React application."
-   "What are the best practices for caching in a Vite SPA?"

## Contributing

This skill is open source and contributions are welcome. If you have suggestions for improvements or new rules, please open an issue or a pull request in the [GitHub repository](https://github.com/claudiocebpaz/vite-react-best-practices).

## More Information

You can find more information about this skill and discover others on [skills.sh](https://skills.sh/claudiocebpaz/vite-react-best-practices) and [SkillsMP](https://skillsmp.com/).