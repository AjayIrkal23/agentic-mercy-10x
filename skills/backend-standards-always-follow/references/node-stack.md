# Node / TS / Fastify / Mongo variants

> The active backend stack is **Go (GO_UDP)**; the main skill body is Go-first. This reference holds the Node/TypeScript equivalents for teams on a Node stack.

- **Server:** Fastify route/plugin/hook structure mirrors the Go handler/service/middleware split described in the main skill.
- **Validation:** zod/typebox schemas play the role of the Go request structs + validation tags.
- **Persistence:** Mongoose/Prisma models mirror the Go repository layer; keep `{ timestamps: true }` (or equivalent) for report queries.
- **Errors:** a centralized Fastify error hook + an `AppError` class mirror the Go centralized error handler + typed error taxonomy.

Everything else (contracts, list/query semantics, layering, security) is stack-agnostic — follow the main skill.
