# Pre-Code Check Hook

## Trigger
Before first code edit in a session.

## Validation Checklist
1. Has `using-superpowers` been invoked this session?
2. Has jcodemunch `plan_turn` been run?
3. Has `get_blast_radius` been run if modifying existing code?
4. Are relevant skills loaded?

## Action
If any gate is incomplete, inject:
```text
[CODE MODE GATE INCOMPLETE]
Before editing code, complete the pre-flight checklist:
1. Invoke using-superpowers skill
2. Run jcodemunch plan_turn and get_ranked_context
3. Run get_blast_radius if modifying existing symbols
4. Load relevant domain skills

Complete PLAN_GATE announcement before proceeding.
```

## Silent Mode
If all gates pass, exit silently.
