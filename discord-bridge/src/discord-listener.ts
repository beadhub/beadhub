import type { Client, Message, PartialMessage, ThreadChannel } from "discord.js";
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
 * - Scripty transcribes by EDITING the original voice note message (not sending a new reply),
 *   so we catch transcriptions via the messageUpdate event.
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

  // Scripty edits the original voice note message with the transcript instead of replying.
  // Detect transcriptions by checking if the updated message ID is in our pending voice notes map.
  client.on("messageUpdate", async (_old: Message | PartialMessage, newMessage: Message | PartialMessage) => {
    console.log(`[discord-listener] messageUpdate fired: id=${newMessage.id} partial=${newMessage.partial} inPending=${pendingVoiceNotes.has(newMessage.id)}`);
    try {
      await handleVoiceNoteEdit(newMessage, sessionMap, bridgeIdentity, redis);
    } catch (err) {
      console.error("[discord-listener] Error handling message update:", err);
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
 * Handle a Scripty transcription delivered via message edit.
 * Scripty edits the original voice note message in-place with the transcript text,
 * rather than sending a new reply. We detect this by checking the updated message ID
 * against our pending voice notes map.
 *
 * Note: SCRIPTY_APP_ID is kept as a reference constant above but is not needed here —
 * the pending map already tells us this was a voice note we're waiting on.
 */
async function handleVoiceNoteEdit(
  rawMessage: Message | PartialMessage,
  sessionMap: SessionMap,
  bridgeIdentity: { workspace_id: string; alias: string },
  redis: Redis,
): Promise<void> {
  // Only process if this message ID is a pending voice note
  const pending = pendingVoiceNotes.get(rawMessage.id);
  if (!pending) return;

  // Fetch the full message if we only have a partial
  const message = rawMessage.partial ? await rawMessage.fetch() : rawMessage;

  // Guard: must be a thread in our configured channel
  if (!message.channel.isThread()) return;
  if (message.channel.parentId !== config.discord.channelId) return;

  const transcript = message.content;
  if (!transcript?.trim()) {
    // Scripty may fire a partial edit before adding content — wait for the real one
    console.log("[discord-listener] Voice note edit has no text content yet, skipping");
    return;
  }

  // Consume the pending entry
  pendingVoiceNotes.delete(rawMessage.id);

  const { authorName, threadId } = pending;
  console.log(
    `[discord-listener] Scripty transcription (via edit) for ${authorName}: "${transcript.slice(0, 80)}"`,
  );

  // Route the transcription as the original human's message
  const thread = message.channel as ThreadChannel;
  const sessionId = await sessionMap.getSessionId(threadId);

  if (!sessionId) {
    await routeToOrchestrator(redis, sessionMap, threadId, authorName, transcript);
    startTypingIndicator(thread);
    return;
  }

  const source = await sessionMap.getSource(threadId);

  if (source === "orchestrator") {
    await pushToOrchestratorInbox(redis, threadId, sessionId, authorName, transcript);
    startTypingIndicator(thread);
    return;
  }

  // BeadHub-managed thread
  await relayToBeadHub(sessionId, authorName, message, bridgeIdentity, transcript);
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
