import type Redis from "ioredis";
import type { WebhookClient, TextChannel } from "discord.js";
import type { SessionMap } from "./session-map.js";
import type { OrchestratorOutboxMessage } from "./types.js";
import { stopTypingIndicator } from "./discord-listener.js";
import { config } from "./config.js";

const ORCHESTRATOR_OUTBOX = "orchestrator:outbox";

/**
 * Consume orchestrator responses from Redis outbox and post to Discord threads.
 * Uses BLPOP on a dedicated Redis connection to avoid blocking other operations.
 */
export async function startOrchestratorRelay(
  redis: Redis,
  channel: TextChannel,
  webhook: WebhookClient,
  sessionMap: SessionMap,
): Promise<void> {
  // Dedicated connection for blocking BLPOP
  const blpopRedis = redis.duplicate();
  blpopRedis.on("error", (err) => {
    console.error("[orchestrator-relay] Redis error:", err.message);
  });

  console.log("[orchestrator-relay] Starting BLPOP loop on", ORCHESTRATOR_OUTBOX);

  // Run in background — don't block startup
  (async () => {
    while (true) {
      try {
        const result = await blpopRedis.blpop(ORCHESTRATOR_OUTBOX, 0);
        if (!result) continue;

        const [, raw] = result;
        await handleOutboxMessage(raw, channel, webhook, sessionMap);
      } catch (err) {
        console.error("[orchestrator-relay] BLPOP error:", err);
        // Brief pause before retrying on connection errors
        await new Promise((r) => setTimeout(r, 2000));
      }
    }
  })();
}

async function handleOutboxMessage(
  raw: string,
  channel: TextChannel,
  webhook: WebhookClient,
  sessionMap: SessionMap,
): Promise<void> {
  let msg: OrchestratorOutboxMessage;
  try {
    msg = JSON.parse(raw);
  } catch (err) {
    console.error("[orchestrator-relay] Invalid JSON:", raw.slice(0, 200));
    return;
  }

  const { thread_id, session_id, response } = msg;

  // Stop typing indicator — response has arrived
  stopTypingIndicator(thread_id);

  // Fetch the thread
  let thread;
  try {
    thread = await channel.threads.fetch(thread_id);
  } catch (err) {
    console.error(`[orchestrator-relay] Could not fetch thread ${thread_id}:`, err);
    return;
  }

  if (!thread) {
    console.error(`[orchestrator-relay] Thread ${thread_id} not found`);
    return;
  }

  // Unarchive if needed
  if (thread.archived) {
    await thread.setArchived(false);
  }

  // Split long messages and send via webhook
  const chunks = splitMessage(response, config.maxDiscordMessageLength);
  for (const chunk of chunks) {
    await webhook.send({
      content: chunk,
      username: "🎯 orchestrator",
      threadId: thread.id,
    });
  }

  console.log(
    `[orchestrator->discord] Response (${response.length} chars) → thread ${thread.name ?? thread_id}`,
  );
}

function splitMessage(text: string, maxLen: number): string[] {
  if (text.length <= maxLen) return [text];

  const chunks: string[] = [];
  let remaining = text;
  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining);
      break;
    }
    // Try to split at last newline within limit
    let splitAt = remaining.lastIndexOf("\n", maxLen);
    if (splitAt <= 0) splitAt = maxLen;
    chunks.push(remaining.slice(0, splitAt));
    remaining = remaining.slice(splitAt).replace(/^\n/, "");
  }
  return chunks;
}
