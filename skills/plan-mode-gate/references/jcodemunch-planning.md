# jcodemunch Planning Tool Reference

## Essential Tools for Planning

### 1. plan_turn
**Purpose:** Analyze query against codebase and return confidence + recommended symbols.

**When to use:** FIRST jcodemunch call when entering plan mode or code mode.

```json
{
  "query": "add geofence alert feature",
  "repo": "rohithambar/gps-monitor",
  "max_recommended": 10
}
```

**Output:** Confidence level (high/medium/low), recommended symbols/files, guidance.

### 2. assemble_task_context
**Purpose:** Auto-classify task and return source-attributed context capsule.

**When to use:** After plan_turn, to get the best N tokens of context.

```json
{
  "task": "implement geofence alerts on admin dashboard",
  "repo": "rohithambar/gps-monitor",
  "token_budget": 8000,
  "intent": "extend"
}
```

**Output:** Classified intent, anchor symbols, blast radius, runtime signals.

### 3. get_ranked_context
**Purpose:** Query-less, token-budgeted overview of relevant code.

**When to use:** When you want "the best N tokens of context for this task" without specifying exact symbols.

```json
{
  "query": "geofence admin dashboard alert",
  "repo": "rohithambar/gps-monitor",
  "token_budget": 4000
}
```

### 4. get_repo_health
**Purpose:** One-call triage snapshot of entire repository.

**When to use:** At session start to understand codebase health.

```json
{
  "repo": "rohithambar/gps-monitor",
  "days": 90
}
```

**Output:** Symbol counts, dead code %, average complexity, top hotspots, dependency cycles.

### 5. get_blast_radius
**Purpose:** Find all files affected by changing a symbol.

**When to use:** Before modifying or deleting any existing symbol.

```json
{
  "symbol": "calculateGeofence",
  "repo": "rohithambar/gps-monitor",
  "include_source": true,
  "call_depth": 1
}
```

### 6. get_impact_preview
**Purpose:** Show what breaks if a symbol is removed or renamed.

**When to use:** Before deleting or renaming symbols.

```json
{
  "symbol_id": "src/utils/geofence.js::calculateGeofence#function",
  "repo": "rohithambar/gps-monitor"
}
```

### 7. search_symbols
**Purpose:** Find functions/classes by name or description.

**When to use:** When looking for specific functionality in the codebase.

```json
{
  "query": "geofence alert notification",
  "repo": "rohithambar/gps-monitor",
  "max_results": 10,
  "detail_level": "standard"
}
```

## Planning Workflow with jcodemunch

```
1. list_repos → Check if indexed
   └─ Not indexed? → index_folder

2. plan_turn(query=<task>)
   └─ Get confidence + recommended symbols

3. get_repo_health
   └─ Understand codebase state

4. assemble_task_context(task=<task>)
   └─ Get auto-extracted relevant context

5. search_symbols (if needed)
   └─ Find specific functions/classes

6. get_blast_radius (if modifying existing code)
   └─ Find affected files

7. Write plan referencing all findings
```

## Token Budget Guidelines

| Task Complexity | plan_turn | assemble_task_context | get_ranked_context |
|-----------------|-----------|----------------------|-------------------|
| Simple (1-2 files) | 5 symbols | 4000 tokens | 2000 tokens |
| Medium (3-5 files) | 10 symbols | 8000 tokens | 4000 tokens |
| Complex (5+ files) | 20 symbols | 12000 tokens | 8000 tokens |
