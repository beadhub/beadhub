## Contributor Notes

This directory contains the Go implementation of the `aw` client and library.

Keep these invariants:

- Do not change the `aw <-> aweb` wire contract as part of packaging or repo-layout work.
- Keep the identity model aligned with the canonical `aweb` docs:
  - workspace
  - identity
  - alias
  - address
- Treat `awid` as the stable identity boundary for the Go client.
- Prefer small, reviewable refactors over compatibility shims.

Useful checks:

```bash
go test ./...
make build
```

When editing docs here, keep them aligned with the staged public repo docs at:

- `../../docs/id-sot.md`
- `../../server/docs/identity-key-verification.md`
