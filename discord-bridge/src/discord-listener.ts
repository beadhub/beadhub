import type { Client, Message, ThreadChannel } from "discord.js";
import type Redis from "ioredis";
import type { SessionMap } from "./session-map.js";
import type { OrchestratorInboxMessage } from "./types.js";
import { joinSession, sendMessage } from "./beadhub-client.js";
import { markRelayed } from "./redis-listener.js";
import { config } from "./config.js";

const ORCHESTRATOR_INBOX = "orchestrator:inbox";

/** Active typing indicators keyed by thread ID */
const typingIntervals = new Map<string, Timer>();

/** Start a typing indicator loop in a thread. Fires every 8s (indicator lasts ~10s). */
export function startTypingIndicator(thread: ThreadChannel): void {
  stopTypingIndicator(thread.id);
  // Fire immediately, then every 8 seconds
  thread.sendTyping().catch(() => {});
  const interval = setInterval(() => {
    thread.sendTyping().catch(() => {});
  }, 8_000);
  typingIntervals.set(thread.id, interval);
}

/** Stop the typing indicator for a thread. */
export function stopTypingIndicator(threadId: string): void {
  const existing = typingIntervals.get(threadId);
  if (existing) {
    clearInterval(existing);
    typingIntervals.delete(threadId);
  }
}

/**
 * Listen for human replies in Discord threads and route them:
 * - New threads (no session) → orchestrator via Redis queue
 * - Existing "beadhub" threads → BeadHub API (original behavior)
 * - Existing "orchestrator" threads → orchestrator via Redis queue
 */
export function startDiscordListener(
  client: Client,
  sessionMap: SessionMap,
  bridgeIdentity: { workspace_id: string; alias: string },
  redis: Redis,
): void {
  client.on("messageCreate", async (message: Message) => {
    try {
      await handleMessage(message, sessionMap, bridgeIdentity, redis);
    } catch (err) {
      console.error("[discord-listener] Error handling message:", err);
    }
  });

  console.log("[discord-listener] Listening for thread replies (BeadHub + orchestrator routing)");
}

async function handleMessage(
  message: Message,
  sessionMap: SessionMap,
  bridgeIdentity: { workspace_id: string; alias: string },
  redis: Redis,
): Promise<void> {
  // Ignore bots (including our own webhook messages)
  if (message.author.bot) return;

  // Only handle messages in threads
  if (!message.channel.isThread()) return;

  // Only handle threads in our configured channel
  if (message.channel.parentId !== config.discord.channelId) return;

  const threadId = message.channel.id;
  const displayName = message.member?.displayName ?? message.author.username;

  // Look up existing session mapping
  const sessionId = await sessionMap.getSessionId(threadId);

  if (!sessionId) {
    // New thread with no session — route to orchestrator
    await routeToOrchestrator(redis, sessionMap, threadId, displayName, message.content);
    startTypingIndicator(message.channel);
    return;
  }

  // Check the source of this session
  const source = await sessionMap.getSource(threadId);

  if (source === "orchestrator") {
    // Orchestrator-managed thread — route to orchestrator queue
    await pushToOrchestratorInbox(redis, threadId, sessionId, displayName, message.content);
    startTypingIndicator(message.channel);
    return;
  }

  // Default: BeadHub-managed thread — relay via BeadHub API
  await relayToBeadHub(sessionId, displayName, message, bridgeIdentity);
}

/** Create a new session and route to orchestrator inbox */
async function routeToOrchestrator(
  redis: Redis,
  sessionMap: SessionMap,
  threadId: string,
  displayName: string,
  content: string,
): Promise<void> {
  const sessionId = crypto.randomUUID();
  await sessionMap.setWithSource(sessionId, threadId, "orchestrator");

  await pushToOrchestratorInbox(redis, threadId, sessionId, displayName, content);
  console.log(
    `[discord->orchestrator] New session ${sessionId.slice(0, 8)}... for thread ${threadId}`,
  );
}

/** Push message to orchestrator:inbox Redis list */
async function pushToOrchestratorInbox(
  redis: Redis,
  threadId: string,
  sessionId: string,
  author: string,
  message: string,
): Promise<void> {
  const payload: OrchestratorInboxMessage = {
    thread_id: threadId,
    session_id: sessionId,
    author,
    message,
    timestamp: new Date().toISOString(),
  };

  await redis.rpush(ORCHESTRATOR_INBOX, JSON.stringify(payload));
  console.log(
    `[discord->orchestrator] ${author} in thread ${threadId}: ${message.slice(0, 80)}`,
  );
}

/** Relay message to BeadHub API (original behavior) */
async function relayToBeadHub(
  sessionId: string,
  displayName: string,
  message: Message,
  bridgeIdentity: { workspace_id: string; alias: string },
): Promise<void> {
  // Join the session if we haven't already (idempotent)
  await joinSession(
    sessionId,
    bridgeIdentity.workspace_id,
    bridgeIdentity.alias,
  );

  // Format: include the Discord username so agents know who's speaking
  const body = `[${displayName} via Discord] ${message.content}`;

  // Send to BeadHub
  const messageId = await sendMessage(
    sessionId,
    body,
    bridgeIdentity.workspace_id,
    bridgeIdentity.alias,
  );

  // Mark as relayed so we don't echo it back to Discord
  markRelayed(messageId, config.echoSuppressionTtlMs);

  console.log(
    `[discord->beadhub] ${displayName} in thread ${message.channel.isThread() ? message.channel.name : "?"}: ${message.content.slice(0, 80)}`,
  );
}
