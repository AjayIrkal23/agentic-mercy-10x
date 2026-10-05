---
name: backend-performance-standards
description: Backend query efficiency, repeated DB work, file-size pressure, scaling risk, and safe optimization boundaries.
when_to_use: Use when reviewing repositories, models, SQL, or hot paths for N+1 queries, missing indexes, or scaling risk.
paths:
- '**/{repository,repositories}/**'
- '**/*.model.{ts,js}'
- '**/server/**/models/**/*.{ts,js}'
- '**/*.sql'
metadata:
  schema: 1
  category: backend
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 264
  triggers:
    keywords:
    - n+1 query
    - n+1 queries
    - missing index
    - slow query
    - slow endpoint
    - query efficiency
    - repeated queries
    - scaling risk
    - hot path
    - backend performance
    paths:
    - cmd/
    - internal/
    - server/
    intents:
    - backend
---
# Backend Performance Standards

## Overview

Use this skill when performance or scale risk is the actual concern, not as a default backend load.

## Focus Areas

- DB query count and efficiency
- repeated work across services or loops
- file-size pressure and decomposition
- index awareness
- safe optimization without contract drift

## Rules

- Avoid repeated DB calls when batching or reuse is possible.
- Avoid large synchronous loops over expensive work.
- Keep controllers thin and hot paths inside focused services/helpers.
- Preserve response shapes, DB fields, and contract keys while optimizing.
- Treat manually maintained backend source files above 250 lines as a structural violation for touched performance surfaces; split hot-path services, helpers, query builders, or mappers before adding more behavior unless the user explicitly scopes that cleanup out.

## Checklist

- Queries are bounded and efficient.
- Repeated work is reduced.
- Controllers stay thin.
- No circular dependency or duplication was introduced during optimization.
