---
id: identity.no-impersonation
title: No workspace impersonation
---

Never run `aw` from another workspace or worktree when doing coordination work.

`aw` derives coordination context from `.aw/workspace.yaml` in the current worktree. Running `aw` from another repo or worktree can impersonate that workspace's agent, causing:

- Messages sent as the wrong agent
- Work claimed under the wrong identity
- Confusion in coordination

**Always verify** you're in the correct worktree before running coordination commands:
```bash
aw workspace status
```
