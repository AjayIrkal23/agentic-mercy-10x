# Dify-specific business-logic rules (optional)

**Applicability:** Use **only** when reviewing code that matches the Dify repository layout and patterns (e.g. paths like `web/app/components/workflow/nodes/...`). For other codebases, **skip this file entirely**.

## Can't use workflowStore in Node components (Dify)

IsUrgent: True

### Description

File path pattern of node components: `web/app/components/workflow/nodes/[nodeName]/node.tsx`

Node components are also used when creating a RAG Pipe from a template, but in that context there is no workflowStore Provider, which can cause a blank screen. See upstream discussion: [langgenius/dify#29168](https://github.com/langgenius/dify/issues/29168).

### Suggested fix

Follow Dify’s documented hooks for React Flow state instead of workflow store imports in those entry contexts.

---

_Source: vendored from [langgenius/dify frontend-code-review](https://github.com/langgenius/dify/tree/main/.agents/skills/frontend-code-review) and scoped here to avoid false positives on unrelated repos._
