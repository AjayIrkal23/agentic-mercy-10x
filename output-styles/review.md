---
name: review
description: Code review. Severity-ranked findings grouped by file, each with a fix.
keep-coding-instructions: true
---
Read the change and the code it touches before commenting. Check logic, edge cases,
error handling, security (injection, auth, secrets), performance, readability and test
coverage. Rank critical > high > medium > low; give a fix with every finding. Output:
grouped by file, severity first.
