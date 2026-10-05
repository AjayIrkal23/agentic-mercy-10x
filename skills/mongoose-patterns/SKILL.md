---
name: mongoose-patterns
description: 'Mongoose and MongoDB patterns for Node services: lean reads with projections, index-backed filters and sorts, ObjectId casting in aggregation pipelines, timestamps, soft-delete filters and safe one-off backfills.'
when_to_use: Use when writing or reviewing Mongoose models, queries, aggregations, indexes or data backfills, or when a Mongo query is slow.
metadata:
  schema: 1
  category: backend
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - mongoose
    - mongodb
    - mongo query
    - mongoose schema
    - mongoose model
    - mongoose lean
    - use lean
    - projection
    - aggregate pipeline
    - aggregation pipeline
    - objectid
    - compound index
    - slow mongo query
    - soft delete
    - backfill
    - explain plan
    intents: []
---
# Mongoose patterns

The project contract wins: read the repo's `CLAUDE.md` / `CODEX.md` / `server_docs/`
first (site-sync-vista: tenant scope from `req.user`, `.lean()` + projection, index-backed
filters, `{ timestamps: true }`, `AppError` for failures). These are the defaults when the
repo is silent.

## Reads

- Read paths use `.lean()` and an explicit projection: `Model.find(filter, "name status
  updatedAt").lean()`. Hydrated documents are for code that calls `save()` or document
  methods.
- Every query is tenant-scoped from the authenticated user, never from a client-sent
  `companyId`: `{ companyId: req.user.companyId, ... }` (site-sync-vista derives it with
  `resolveHomeCompanyId`).
- Lists paginate server-side: `sort` on a whitelisted key, then `skip`/`limit` (or a
  range cursor on `_id`/`createdAt` for deep pages), and `countDocuments` with the same
  filter. Never fetch everything and slice in JS.
- `populate` costs one extra query per path; for lists, prefer a projection on the
  populate (`populate({ path: "owner", select: "name" })`) or a `$lookup` in one
  aggregation.

## Indexes

- Every field in a list filter, sort or `$match` is backed by an index. Compound order:
  equality fields first, then sort fields, then range fields (ESR).
- Declare indexes on the schema (`schema.index({ companyId: 1, status: 1, updatedAt: -1 })`)
  and let the repo's index-management step build them; do not call `createIndex` from
  request code.
- Check a suspect query with `explain("executionStats")`: `IXSCAN` and
  `totalDocsExamined` close to `nReturned` is healthy; `COLLSCAN` on a large collection
  needs an index.

## Aggregation

- Mongoose casts query filters but **not** aggregation pipelines. Cast ids and dates
  yourself: `{ $match: { companyId: new Types.ObjectId(companyId), createdAt: { $gte:
  new Date(from) } } }`. A string id in `$match` silently matches nothing.
- Put `$match` (index-backed) first, `$project` early to drop wide fields, `$limit`
  before `$lookup` when the result is paged.
- Validate an id before casting (`Types.ObjectId.isValid(id)`) and throw the repo's 400
  error instead of letting a cast error escape as 500.

## Schemas

- `{ timestamps: true }` on every schema (site-sync-vista non-negotiable 8).
- Soft delete = a field (`deletedAt` or `isDeleted`) plus a filter on **every** read and
  count. Prefer one shared filter helper or a query middleware over remembering it per
  call; add the field to the relevant compound indexes.
- Enumerations: `enum` on the schema path and the same values in the route schema.
- Keep models thin: statics or services own logic, not pre-save hooks with side effects.

## Writes and backfills

- Updates are atomic operators (`$set`, `$inc`, `$push`) with the tenant in the filter;
  `findOneAndUpdate(..., { new: true, runValidators: true })` when you need the result.
- Multi-document invariants use a session/transaction only when the deployment is a
  replica set; say so instead of assuming.
- One-off backfills: a script that is idempotent (filter on "not yet migrated"), batched
  (`bulkWrite` in chunks of a few hundred), dry-run by default, and logs counts. Run it
  only with the user's OK against a real database.

## Tests

Use the repo's existing setup (vitest with an in-memory Mongo or mocked models). Assert
on the filter and projection a service builds, the tenant scope, and the cast types in
pipelines.

## Not this skill

SQL / Postgres (`postgres-patterns`), API envelope design (`api-contract-standards`),
general service layering (`service-layer-standards`).
