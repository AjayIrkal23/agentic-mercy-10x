---
name: zoom-out
description: Tell the agent to zoom out and give broader context or a higher-level perspective. Use when
  you're unfamiliar with a section of code or need to understand how it fits into the bigger picture.
disable-model-invocation: true
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 42
triggers:
  keywords:
  - agent
  - bigger
  - broader
  - code
  - context
  - fits
  - give
  - higher-level
  - need
  - perspective
  - picture
  - section
  - tell
  - understand
  - unfamiliar
  - zoom
  paths: []
  intents:
  - general
---
I don't know this area of code well. Go up a layer of abstraction. Give me a map of all the relevant modules and callers, using the project's domain glossary vocabulary.
