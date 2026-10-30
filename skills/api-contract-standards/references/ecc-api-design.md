<!-- ecc:skills/api-design, skills/contract-first @25278e7d -->
# API design (ECC graft)

- **Consumer-first:** write the contract from the screen or client that calls it; the
  server shape follows, not the table layout.
- **Cursor pagination** for lists that grow (`?cursor=&limit=`, response `nextCursor`);
  offset only for small, stable sets.
- **Error envelope:** every error has a stable machine `code` and a human `message`
  (plus `details` for field errors); clients branch on `code`, never on `message`.
- **Versioning rule:** additive changes stay in the current version; removing or renaming a
  field, or changing its type, is a new version (or a deprecation window), never a silent edit.
