import type { Client, Message, ThreadChannel } from "discord.js";
import { MessageFlags } from "discord.js";
import type Redis from "ioredis";
import type { SessionMap } from "./session-map.js";
import type { OrchestratorInboxMessage } from "./types.js";
import { joinSession, sendMessage } from "./beadhub-client.js";
import { markRelayed } from "./redis-listener.js";
import { config } from "./config.js";

const ORCHESTRATOR_INBOX = "orchestrator:inbox";

/**
 * Scripty voice transcription bot application ID.
 * Verify against message.applicationId in bridge logs if this changes.
 */
const SCRIPTY_APP_ID = "811652199100317726";

/** Pending voice notes awaiting Scripty transcription: Discord message ID → author info */
interface PendingVoiceNote {
  authorName: string;
  threadId: string;
  timestamp: number;
}
const pendingVoiceNotes = new Map<string, PendingVoiceNote>();

/** Returns true if the message is a Discord voice note (audio-only, no text). */
function isVoiceNote(message: Message): boolean {
  return message.flags.has(MessageFlags.IsVoiceMessage);
}

/** Store a voice note pending Scripty transcription. Prunes entries older than 5 minutes. */
function storePendingVoiceNote(message: Message): void {
  if (!message.channel.isThread()) return;
  const authorName = message.member?.displayName ?? message.author.username;
  pendingVoiceNotes.set(message.id, {
    authorName,
    threadId: message.channel.id,
    timestamp: Date.now(),
  });
  // Prune stale entries (older than 5 minutes)
  const cutoff = Date.now() - 5 * 60 * 1000;
  for (const [id, entry] of pendingVoiceNotes) {
    if (entry.timestamp < cutoff) pendingVoiceNotes.delete(id);
  }
}

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
 *
 * Special handling:
 * - Voice notes (MessageFlags.IsVoiceMessage) are stored pending Scripty transcription
 * - Scripty bot replies (applicationId === SCRIPTY_APP_ID) are remapped as the original human's message
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
  // Scripty transcription: remap as the original voice note sender (before general bot filter)
  if (message.author.bot && message.applicationId === SCRIPTY_APP_ID) {
    if (message.channel.isThread() && message.channel.parentId === config.discord.channelId) {
      await handleScriptyTranscription(message, sessionMap, bridgeIdentity, redis);
    }
    return;
  }

  // Ignore all other bots (including our own webhook messages)
  if (message.author.bot) return;

  // Only handle messages in threads
  if (!message.channel.isThread()) return;

  // Only handle threads in our configured channel
  if (message.channel.parentId !== config.discord.channelId) return;

  const threadId = message.channel.id;
  const displayName = message.member?.displayName ?? message.author.username;

  // Drop voice notes — store pending entry so Scripty transcription can be remapped
  if (isVoiceNote(message)) {
    storePendingVoiceNote(message);
    console.log(
      `[discord-listener] Voice note from ${displayName} in thread ${threadId} — awaiting Scripty`,
    );
    return;
  }

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

/**
 * Handle a Scripty transcription reply.
 * Resolves the original voice note author and relays the transcription as their message.
 */
async function handleScriptyTranscription(
  message: Message,
  sessionMap: SessionMap,
  bridgeIdentity: { workspace_id: string; alias: string },
  redis: Redis,
): Promise<void> {
  const transcription = message.content;
  if (!transcription?.trim()) {
    console.log("[discord-listener] Scripty message has no text content, skipping");
    return;
  }

  const thread = message.channel as ThreadChannel;
  const threadId = thread.id;
  const referencedMessageId = message.reference?.messageId;

  // Resolve the original voice note author
  let authorName: string | null = null;

  // Primary: check pending voice notes map (populated when voice note was received)
  if (referencedMessageId) {
    const pending = pendingVoiceNotes.get(referencedMessageId);
    if (pending) {
      authorName = pending.authorName;
      pendingVoiceNotes.delete(referencedMessageId);
      console.log(`[discord-listener] Resolved voice note author "${authorName}" from pending map`);
    }
  }

  // Fallback: fetch the referenced message from Discord to get the original author
  if (!authorName && referencedMessageId) {
    try {
      const refMsg = await thread.messages.fetch(referencedMessageId);
      if (refMsg && !refMsg.author.bot) {
        authorName = refMsg.member?.displayName ?? refMsg.author.username;
        console.log(
          `[discord-listener] Resolved voice note author "${authorName}" by fetching referenced message`,
        );
      }
    } catch (err) {
      console.warn(
        `[discord-listener] Could not fetch referenced message ${referencedMessageId}:`,
        err,
      );
    }
  }

  if (!authorName) {
    console.warn(
      `[discord-listener] Could not determine voice note author in thread ${threadId}, dropping Scripty message`,
    );
    return;
  }

  console.log(
    `[discord-listener] Scripty transcription for ${authorName}: "${transcription.slice(0, 80)}"`,
  );

  // Route the transcription as the original human's message
  const sessionId = await sessionMap.getSessionId(threadId);

  if (!sessionId) {
    await routeToOrchestrator(redis, sessionMap, threadId, authorName, transcription);
    startTypingIndicator(thread);
    return;
  }

  const source = await sessionMap.getSource(threadId);

  if (source === "orchestrator") {
    await pushToOrchestratorInbox(redis, threadId, sessionId, authorName, transcription);
    startTypingIndicator(thread);
    return;
  }

  // BeadHub-managed thread
  await relayToBeadHub(sessionId, authorName, message, bridgeIdentity, transcription);
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
  contentOverride?: string,
): Promise<void> {
  // Join the session if we haven't already (idempotent)
  await joinSession(
    sessionId,
    bridgeIdentity.workspace_id,
    bridgeIdentity.alias,
  );

  const content = contentOverride ?? message.content;
  // Format: include the Discord username so agents know who's speaking
  const body = `[${displayName} via Discord] ${content}`;

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
    `[discord->beadhub] ${displayName} in thread ${message.channel.isThread() ? message.channel.name : "?"}: ${content.slice(0, 80)}`,
  );
}
