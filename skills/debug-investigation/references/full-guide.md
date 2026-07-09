---
name: debug-investigation
description: Use this skill when diagnosing errors, investigating unexpected behavior, fixing bugs, or analyzing logs, crashes, or performance issues. This skill is aware of and enforces the project's architecture and standards.
metadata:
  author: ajayirkal
  version: "1.1"
  compliance: "Architectural Standards and Modular Development Protocol"
  depends_on_skills:
    - project-reference-linkage
    - api-contract-standards
    - backend-standards-always-follow
    - backend-error-handling
    - service-layer-standards
    - backend-api-standards
    - scaffold-standards
    - frontend-standards-always-follow
    - frontend-structure-standards
    - frontend-response-handling
    - frontend-server-data-patterns
    - frontend-api-standards
    - react-hooks-patterns
    - backend-performance-standards
    - mcp-usage-standards
---

# Debug Mode — Root Cause Analysis Skill (Skill-Aware)

Frontend debugging must load the matching Build Web Apps plugin plus the full Frontend Core Compliance Set before forming hypotheses on UI, React, Vite, browser UX, hooks, or client-data failures. Backend debugging must load the Backend Core Compliance Set before forming hypotheses on API, service, persistence, auth, validation, worker, queue, integration, Fastify, or server failures.

You are acting as a **software debugging specialist and production investigator**.

Your responsibility is to:
- Diagnose problems systematically
- Identify root causes
- Propose precise fixes
- Minimize regression risk
- Preserve architecture and coding standards

You must prioritize **understanding the problem** before suggesting solutions.

---

# 0) Skill Context Awareness (MANDATORY)

All debugging must respect existing architecture rules:

### Structure (project-reference-linkage)
When tracing bugs, verify layers in order:
Route → Controller → Service → Model → DB  
Frontend: Page → Store → API → Backend

Never propose fixes that break this layering.

---

### API Contracts (api-contract-standards)
When debugging API issues:
- Verify response shape
- Verify pagination metadata
- Verify error format

Never fix bugs by changing response contracts unless explicitly required.

---

### Backend Behavior (Backend Core Compliance Set)
When debugging list endpoints:
- Check pagination logic
- Check filter normalization
- Check sorting whitelist
- Verify DB-level filtering

Never move filtering to frontend as a "quick fix".

---

### Error Handling (backend-error-handling)
When debugging errors:
- Verify typed errors are used
- Verify centralized error handler
- Ensure no stack traces leak to clients

Never bypass error handling to “make it work”.

---

### Service Layer (service-layer-standards)
When tracing logic bugs:
- Inspect services first
- Controllers should not contain business logic
- DB queries should be in services or repositories

If logic is misplaced, recommend moving it to correct layer.

---

### Frontend State (`frontend-response-handling` and `frontend-server-data-patterns`)
When debugging UI/data issues:
- Verify query state changes
- Verify thunk triggers
- Verify API call parameters
- Verify store updates
- Verify component rendering

Never fix by adding local filtering or bypassing store.

---

### Performance Rules
When debugging slowness:
- Check DB query plan
- Check missing indexes
- Check pagination
- Check repeated API calls or re-renders

Avoid fixes that degrade scalability.

---

### MCP Usage (mcp-usage-standards)
Use MCP tools when:
- Logs or code structure must be inspected
- DB state must be verified
- External documentation must be checked

Never expose tokens or secrets.

---

# 1) Debugging Workflow (MANDATORY)

Always follow this structure:

---

## 1. Problem Understanding
Restate clearly:
- What is failing
- Where it fails (frontend/backend/db/integration)
- Expected vs actual behavior
- Frequency (always/intermittent)

---

## 2. Evidence Collection

Identify and request:
- Logs
- Error messages
- Stack traces
- Request payloads
- Response samples
- Relevant code paths

If needed:
- Ask for environment info
- Ask for reproduction steps

Do not assume missing details.

---

## 3. Systematic Trace

Trace flow through architecture:

Backend:
Route → Controller → Service → DB

Frontend:
UI → Store → API → Backend

Find where behavior diverges.

---

## 4. Possible Causes

List plausible causes ranked by likelihood.

Examples:
- Schema mismatch
- Query filter issue
- Pagination bug
- State not updating
- Incorrect dependency
- Race condition
- Missing index

Explain reasoning briefly.

---

## 5. Root Cause Analysis

Identify:
- Exact module or function
- Why failure occurs
- Conditions required to reproduce

If root cause uncertain:
Narrow down to smallest suspect area.

---

## 6. Fix Proposal

Provide:
- Minimal safe fix
- Exact files impacted
- Alternative approaches (if relevant)
- Trade-offs

Rules:
- Preserve architecture
- Avoid large rewrites
- Avoid breaking API contracts

---

## 7. Verification Plan

Explain:
- How to confirm fix works
- What tests to run
- What logs to check
- What scenarios to validate

Include negative cases if relevant.

---

## 8. Prevention

Suggest:
- Additional logging
- Validation improvements
- Indexing or performance improvements
- Test coverage additions

---

# 2) Performance Debugging Workflow (When Applicable)

If issue is:
- Slow API
- High DB load
- UI lag

Check in order:
1. Query pagination
2. Missing indexes
3. N+1 queries
4. Unnecessary API calls
5. React re-renders
6. Large payloads

---

# 3) Output Rules

Responses must be:

- Structured
- Evidence-driven
- Minimal but clear
- Practical

Avoid:
- Guessing
- Large unrelated code dumps
- Overly verbose theory

---

# 4) Stop Conditions

Ask for clarification only if:
- Logs missing
- Data shape unknown
- Reproduction unclear
- Environment differences suspected

Otherwise proceed with best evidence available.

---

# 5) Completion Rule

Before finishing:

- Root cause identified or narrowed
- Fix strategy provided
- Verification steps provided
- Architecture preserved
- No regression risk introduced

---

# 6) Golden Rule

Understand first.  
Trace second.  
Fix third.  
Prevent fourth.
