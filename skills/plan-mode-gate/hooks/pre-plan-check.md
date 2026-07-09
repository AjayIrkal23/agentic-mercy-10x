# Pre-Plan Check Hook

## Trigger
Before `EnterPlanMode` activates.

## Validation Checklist
1. Has `using-superpowers` been invoked this session?
2. Is the repo indexed by jcodemunch?
3. Does the task involve external libraries?
4. Is the task complex enough for sequential thinking?

## Action
If any gate is incomplete, inject:
```text
[PLAN MODE GATE INCOMPLETE]
Before entering plan mode, complete the pre-flight checklist:
1. Invoke using-superpowers skill
2. Run jcodemunch plan_turn and assemble_task_context
3. Use sequentialthinking if task is complex
4. Use Context7 for external libraries

Complete PLAN_GATE announcement before proceeding.
```

## Silent Mode
If all gates pass, exit silently.
