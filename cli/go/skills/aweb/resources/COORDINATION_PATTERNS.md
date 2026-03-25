# Coordination Patterns

## Heartbeat

Normal `aw` commands do not send a background heartbeat automatically. Use `aw heartbeat` for an explicit presence ping; long-running flows such as `aw run` handle their own wake/control behavior.

## Mail Polling

Check for new messages at session start and periodically during long tasks:

```bash
# Session start — check for anything waiting
aw mail inbox
```

Messages are automatically marked as read when fetched via `aw mail inbox`.

## Chat Wait Semantics

Two verbs make the intent explicit:

```bash
# Send and wait for a reply (120s default)
aw chat send-and-wait alice "ready to deploy?"

# Send and wait up to 5 minutes (starting a new exchange)
aw chat send-and-wait alice "need your review" --start-conversation

# Send and wait with custom timeout
aw chat send-and-wait alice "quick question" --wait 30

# Send and leave — no waiting
aw chat send-and-leave alice "done, signing off"
```

When the wait expires without a reply, the command exits with the conversation state (no error). The message is still delivered; you just didn't get a synchronous response.

### Keeping the Other Party Waiting

If you receive a chat but need time to respond:

```bash
aw chat extend-wait alice "checking the logs, 2 minutes"
```

This sends a signal that you're engaged but not ready to reply yet.

## Lock Strategies

### Short-lived locks (mutual exclusion)

For operations that should not run concurrently:

```bash
aw lock acquire --resource-key "deploy/staging" --ttl-seconds 300
# ... do the work ...
aw lock release --resource-key "deploy/staging"
```

### Long-lived locks (ownership)

For claiming a resource for an extended period:

```bash
aw lock acquire --resource-key "review/pr-42" --ttl-seconds 3600
# ... work on it, renewing periodically ...
aw lock renew --resource-key "review/pr-42" --ttl-seconds 3600
# ... done ...
aw lock release --resource-key "review/pr-42"
```

### Lock Naming Conventions

Use `/`-separated hierarchical keys for organization:

| Pattern | Example |
|---------|---------|
| `deploy/<env>` | `deploy/production` |
| `review/<item>` | `review/pr-42` |
| `build/<project>` | `build/frontend` |
| `migration/<db>` | `migration/users-db` |

This lets you list or revoke by prefix: `aw lock list --prefix "deploy/"`.

## Combining Patterns

A typical coordination flow:

1. Check inbox and pending chats
2. Acquire a lock on the shared resource
3. Do the work
4. Send a mail notification to stakeholders
5. Release the lock
