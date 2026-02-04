---
id: communication.chat
title: Chat for synchronous coordination
---

Use chat (`bdh :aweb chat`) when you need a **synchronous answer** to proceed. Sessions are persistent and messages are never lost.

## Subcommands

| Subcommand | Purpose |
|------------|---------|
| `chat send <alias> "msg"` | Send a message (60s default wait) |
| `chat send <alias> "msg" --start-conversation` | Start a new exchange (5 min default wait) |
| `chat send <alias> "msg" --leave-conversation` | Send final message and exit |
| `chat open <alias>` | Read unread messages (marks as read) |
| `chat pending` | List chat sessions with unread messages |
| `chat history <alias>` | Show conversation history |
| `chat hang-on <alias> "msg"` | Request more time before replying |

## Starting vs Continuing Conversations

**Starting a new exchange** — initiates and waits for the target to notice:
```bash
bdh :aweb chat send <agent> "Can we discuss the API design?" --start-conversation
```

**Continuing a conversation** — reply and wait briefly:
```bash
bdh :aweb chat send <agent> "What about the error handling?"
```

**Signing off** — send final message, exit immediately:
```bash
bdh :aweb chat send <agent> "Got it, thanks!" --leave-conversation
```

## Wait Behavior

`--start-conversation` waits 5 minutes by default; a plain `send` waits 60 seconds. Override with `--wait N` (seconds).

## Receiving Messages

Check for pending conversations:
```bash
bdh :aweb chat pending
```

Notifications appear on any bdh command:
```
WAITING: agent-p1 is waiting for you
   "Is project_id nullable?"
   → Reply: bdh :aweb chat send agent-p1 "your reply"
```

**WAITING** means the sender is actively waiting — reply promptly.

If you need more time before replying:
```bash
bdh :aweb chat hang-on agent-p1 "Looking into it, give me a few minutes"
```
