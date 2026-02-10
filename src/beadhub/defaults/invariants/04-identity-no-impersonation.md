---
id: identity.no-impersonation
title: No workspace impersonation
---

Never run `bdh` from another workspace or worktree.

`bdh` derives your identity from the `.beadhub` file in the current worktree. Running `bdh` from another repo or worktree can impersonate that workspace's agent, causing:

- Messages sent as the wrong agent
- Work claimed under the wrong identity
- Confusion in coordination

**Always verify** you're in the correct worktree before running bdh commands:
```bash
bdh :status    # Check your identity
```
