# Sequential Thinking Guide

## When to Use sequentialthinking

**MANDATORY for:**
- Tasks touching >5 files
- Tasks spanning >3 subsystems or modules
- Architecture or design decisions
- Complex debugging with unclear root cause
- Performance optimization requiring trade-off analysis
- Integration with external systems
- Refactoring that crosses module boundaries

**RECOMMENDED for:**
- Tasks touching 3-5 files
- New features with multiple moving parts
- API design decisions
- Database schema changes
- Security-related changes

**SKIP for:**
- Trivial isolated changes (typo fix, constant change, single prop add)
- Pure documentation updates
- File moves with no logic changes

## Usage Pattern

```json
{
  "thought": "Initial analysis of the problem...",
  "thoughtNumber": 1,
  "totalThoughts": 8,
  "nextThoughtNeeded": true
}
```

## Minimum Requirements

- **Minimum thoughts:** 5
- **Must include:** Hypothesis generation (thought 2-3)
- **Must include:** Hypothesis verification (thought 4-5)
- **Must include:** Branch/revision if hypothesis fails
- **Final thought:** Clear action plan with concrete next steps

## Thought Structure by Phase

### Phase 1: Problem Understanding (Thoughts 1-2)
- Restate the problem in your own words
- Identify constraints and requirements
- Clarify ambiguities

### Phase 2: Hypothesis Generation (Thoughts 3-4)
- Propose 2-3 possible approaches
- Evaluate trade-offs for each
- Select the most promising hypothesis

### Phase 3: Deep Analysis (Thoughts 5-7)
- Break down the selected approach into sub-tasks
- Identify dependencies and ordering
- Consider edge cases and failure modes
- Think about testing strategy

### Phase 4: Verification & Plan (Thoughts 8-10)
- Verify the hypothesis against constraints
- Check for contradictions or gaps
- Produce concrete next steps
- Define success criteria

### Phase 5: Revision (if needed)
- If verification fails, go back to Phase 2
- Revise hypothesis and re-analyze
- Document why the first approach was wrong

## Scaling Thoughts to Complexity

| Complexity | Files | Subsystems | Thoughts |
|------------|-------|------------|----------|
| Simple | 1-2 | 1 | Skip |
| Small | 3-5 | 1-2 | 5-7 |
| Medium | 5-10 | 2-3 | 8-12 |
| Large | 10-20 | 3-5 | 12-16 |
| Very Large | 20+ | 5+ | 16-20 |

## Integration with Planning

After sequentialthinking completes:
1. Extract sub-tasks from final thought
2. Map each sub-task to files
3. Use jcodemunch to verify file mappings
4. Write plan with bite-sized steps
5. Each step should correspond to one thought from the decomposition

## Anti-Patterns

| Bad Pattern | Why It's Bad |
|-------------|--------------|
| Rushing to 5 thoughts | Shallow analysis → broken plans |
| Never revising hypothesis | Confirmation bias → wrong solutions |
| No concrete next steps | Wasted thinking → no action |
| Skipping for "simple" 5-file changes | Hidden dependencies → bugs |
