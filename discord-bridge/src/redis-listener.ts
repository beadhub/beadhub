import type Redis from "ioredis";
import type { TextChannel, WebhookClient } from "discord.js";
import type { BeadHubEvent, ChatMessageEvent } from "./types.js";
import type { SessionMap } from "./session-map.js";
import { getSessionMessages, listSessions } from "./beadhub-client.js";
import { getOrCreateThread, sendAsAgent } from "./discord-sender.js";

/** Set of message_ids we've already relayed (echo suppression + dedup). */
const recentlyRelayed = new Set<string>();

export function markRelayed(messageId: string, ttlMs: number): void {
  recentlyRelayed.add(messageId);
  setTimeout(() => recentlyRelayed.delete(messageId), ttlMs);
}

export function wasRelayed(messageId: string): boolean {
  return recentlyRelayed.has(messageId);
}

/**
 * Subscribe to all workspace event channels via PSUBSCRIBE events:*
 * and relay chat.message_sent events to Discord.
 */
export async function startRedisListener(
  redis: Redis,
  channel: TextChannel,
  webhook: WebhookClient,
  sessionMap: SessionMap,
  echoTtlMs: number,
  bridgeAlias: string,
): Promise<void> {
  // ioredis requires a duplicate client for subscriptions
  const sub = redis.duplicate();

  sub.on("error", (err) => {
    console.error("[redis] Subscription error:", err.message);
  });

  await sub.psubscribe("events:*");
  console.log("[redis] PSUBSCRIBE events:* — listening for chat events");

  sub.on("pmessage", async (_pattern: string, _chan: string, message: string) => {
    try {
      const event: BeadHubEvent = JSON.parse(message);
      if (event.type !== "chat.message_sent") return;

      const chatEvent = event as unknown as ChatMessageEvent;

      // Skip messages sent by the bridge itself (human Discord replies relayed to BeadHub)
      if (chatEvent.from_alias === bridgeAlias) return;

      await handleChatMessage(chatEvent, channel, webhook, sessionMap, echoTtlMs);
    } catch (err) {
      console.error("[redis] Error handling event:", err);
    }
  });
}

async function handleChatMessage(
  event: ChatMessageEvent,
  channel: TextChannel,
  webhook: WebhookClient,
  sessionMap: SessionMap,
  echoTtlMs: number,
): Promise<void> {
  // Dedup: same chat message fires on each participant's channel
  if (wasRelayed(event.message_id)) return;
  markRelayed(event.message_id, echoTtlMs);

  // Fetch full message body (event.preview is truncated to 80 chars)
  const messages = await getSessionMessages(event.session_id, 1);
  const latest = messages.at(-1);
  if (!latest) {
    console.warn(`[bridge] No messages found for session ${event.session_id}`);
    return;
  }

  // Double-check this is the message we expect
  if (latest.message_id !== event.message_id) {
    // Race condition: a newer message was sent. Fetch more to find ours.
    const all = await getSessionMessages(event.session_id, 20);
    const target = all.find((m) => m.message_id === event.message_id);
    if (!target) {
      console.warn(`[bridge] Could not find message ${event.message_id}`);
      return;
    }
    await relayToDiscord(target.from_agent, target.body, event, channel, webhook, sessionMap);
    return;
  }

  await relayToDiscord(latest.from_agent, latest.body, event, channel, webhook, sessionMap);
}

async function relayToDiscord(
  fromAlias: string,
  body: string,
  event: ChatMessageEvent,
  channel: TextChannel,
  webhook: WebhookClient,
  sessionMap: SessionMap,
): Promise<void> {
  // Build participant list: sender + recipients
  const participants = [event.from_alias, ...event.to_aliases];
  const uniqueParticipants = [...new Set(participants)];

  const thread = await getOrCreateThread(
    channel,
    sessionMap,
    event.session_id,
    uniqueParticipants,
  );

  await sendAsAgent(webhook, thread, fromAlias, body);
  console.log(
    `[bridge] ${fromAlias} → thread "${thread.name}": ${body.slice(0, 80)}...`,
  );
}
