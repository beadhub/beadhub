import {
  ChannelType,
  WebhookClient,
  type Client,
  type Guild,
  type TextChannel,
  type ThreadChannel,
} from "discord.js";
import { config } from "./config.js";
import type { SessionMap } from "./session-map.js";

/** displayName/username (lowercased) → Discord user ID, built at startup */
const discordMentionMap = new Map<string, string>();

/** Agent alias → emoji prefix */
const AGENT_AVATARS: Record<string, string> = {
  orchestrator: "🎯",
  alice: "🔧",
  bob: "📐",
  charlie: "⚙️",
  dave: "🎨",
  eve: "🧪",
};

/** Known agent aliases for bold @mentions */
const AGENT_ALIASES = new Set(Object.keys(AGENT_AVATARS));

let cachedWebhook: WebhookClient | null = null;

/**
 * Fetch guild members and build a displayName → user ID map for @mentions.
 * Call once at startup after the client is ready.
 */
export async function loadGuildMembers(client: Client): Promise<void> {
  const guild = await client.guilds.fetch(config.discord.guildId);
  const members = await guild.members.fetch();
  for (const [id, member] of members) {
    if (member.user.bot) continue;
    // Index by both display name and username (lowercased)
    discordMentionMap.set(member.displayName.toLowerCase(), id);
    if (member.user.username.toLowerCase() !== member.displayName.toLowerCase()) {
      discordMentionMap.set(member.user.username.toLowerCase(), id);
    }
  }
  console.log(`[discord] Loaded ${discordMentionMap.size} mention targets from guild members`);
}

/**
 * Get the pre-configured webhook client from DISCORD_WEBHOOK_URL.
 * No Manage Webhooks permission needed.
 */
export function getWebhook(): WebhookClient {
  if (cachedWebhook) return cachedWebhook;
  cachedWebhook = new WebhookClient({ url: config.discord.webhookUrl });
  console.log(`[discord] Using pre-configured webhook`);
  return cachedWebhook;
}

/**
 * Find or create a Discord thread for a BeadHub chat session.
 * Thread name: "alice ↔ bob" (sorted participant aliases).
 */
export async function getOrCreateThread(
  channel: TextChannel,
  sessionMap: SessionMap,
  sessionId: string,
  participants: string[],
): Promise<ThreadChannel> {
  // Check cache first
  const existingId = await sessionMap.getThreadId(sessionId);
  if (existingId) {
    try {
      const thread = await channel.threads.fetch(existingId);
      if (thread) {
        // Unarchive if needed
        if (thread.archived) {
          await thread.setArchived(false);
        }
        return thread;
      }
    } catch {
      // Thread deleted or inaccessible — create a new one
    }
  }

  const sorted = [...participants].sort();
  const threadName = sorted.join(" ↔ ");

  const thread = await channel.threads.create({
    name: threadName,
    type: ChannelType.PublicThread,
    reason: `BeadHub chat session ${sessionId}`,
  });

  await sessionMap.setWithSource(sessionId, thread.id, "beadhub");
  console.log(`[discord] Created thread "${threadName}" for session ${sessionId}`);
  return thread;
}

/**
 * Send a message to a Discord thread using the webhook,
 * impersonating the agent via username override.
 */
export async function sendAsAgent(
  webhook: WebhookClient,
  thread: ThreadChannel,
  alias: string,
  body: string,
): Promise<void> {
  const emoji = AGENT_AVATARS[alias] ?? "🤖";
  const username = `${emoji} ${alias}`;
  const content = applyMentions(body);

  // Split long messages
  const chunks = splitMessage(content, config.maxDiscordMessageLength);
  for (const chunk of chunks) {
    await webhook.send({
      content: chunk,
      username,
      threadId: thread.id,
    });
  }
}

/**
 * Replace known names in message body with Discord mentions.
 * - Human names from DISCORD_MENTION_MAP → real <@USER_ID> mentions
 * - Agent aliases → bold **@alias**
 */
function applyMentions(text: string): string {
  let result = text;

  // Real Discord @mentions for humans (case-insensitive word boundary match)
  for (const [name, userId] of discordMentionMap) {
    const re = new RegExp(`\\b${escapeRegex(name)}\\b`, "gi");
    result = result.replace(re, `<@${userId}>`);
  }

  // Bold @mentions for agent aliases
  for (const alias of AGENT_ALIASES) {
    const re = new RegExp(`\\b${escapeRegex(alias)}\\b`, "gi");
    result = result.replace(re, `**@${alias}**`);
  }

  return result;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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
