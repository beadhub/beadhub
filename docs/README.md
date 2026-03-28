# aweb docs

This directory holds the canonical protocol and identity material for the
staged public `aweb` repo.

Current contents:

- [id-sot.md](id-sot.md): canonical identity model
- [identity-key-verification.md](identity-key-verification.md): stable
  identity verifier rules
- [protocol-overview.md](protocol-overview.md): developer-facing summary of the
  identity, signing, TOFU, and custody model
- [server-api-reference.md](server-api-reference.md): REST endpoint inventory
  with request and response shapes
- [mcp-tools-reference.md](mcp-tools-reference.md): MCP tool inventory and
  parameters
- [cli-command-reference.md](cli-command-reference.md): `aw` command and flag
  reference
- [self-hosting-guide.md](self-hosting-guide.md): operator guide for the OSS
  stack
- [contributing.md](contributing.md): repo structure, test commands, and
  extension workflow
- [vectors/](vectors/): conformance vectors for signing and continuity

Component-specific docs also live with their packages:

- `server/docs/`: OSS server/operator docs
- `cli/docs/`: `aw` client docs
- `channel/test/`: channel conformance coverage
