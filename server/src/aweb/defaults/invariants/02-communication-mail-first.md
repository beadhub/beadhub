---
id: communication.mail-first
title: Mail-first communication
---

Default to mail (`aw mail`) for coordination.

Use mail for:
- Status updates and progress reports
- Review requests and feedback
- FYI notifications
- Non-blocking questions

## Sending Messages

```bash
aw mail send --to-alias <agent> --body "Status update: completed task-42"
aw mail send --to-alias <agent> --body "Review request: PR #123 ready" --subject "Review needed"
```

## Checking Your Inbox

```bash
aw mail inbox              # Show unread messages (default)
aw mail inbox --show-all   # Include read messages
```

## Acknowledging Messages

```bash
aw mail ack --message-id <message-id>
```

Use chat (`aw chat`) only when you need a synchronous answer to proceed. See the **communication.chat** invariant for chat details.

**Respond immediately to WAITING notifications** — someone is blocked waiting for your reply.
