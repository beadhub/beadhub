import { Client, GatewayIntentBits, Partials, type TextChannel } from "discord.js";
import Redis from "ioredis";
import { config } from "./config.js";
import { SessionMap } from "./session-map.js";
import { getWebhook, loadGuildMembers } from "./discord-sender.js";
import { startRedisListener } from "./redis-listener.js";
import { startDiscordListener } from "./discord-listener.js";
import { startOrchestratorRelay } from "./orchestrator-relay.js";
import { getOrCreateBridgeIdentity } from "./beadhub-client.js";

async function main(): Promise<void> {
  console.log("[bridge] Starting Discord Bridge for BeadHub...");

  // 1. Connect to Redis
  const redis = new Redis(config.redis.url);
  redis.on("error", (err) => console.error("[redis] Connection error:", err.message));
  await redis.ping();
  console.log("[redis] Connected");

  const sessionMap = new SessionMap(redis);

  // 2. Connect Discord client
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMembers,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent,
    ],
    partials: [Partials.Message, Partials.Channel, Partials.Thread],
  });

  await client.login(config.discord.token);
  console.log(`[discord] Logged in as ${client.user?.tag}`);

  // 3. Load guild members for @mentions
  await loadGuildMembers(client);

  // 4. Get the target channel
  const channel = await client.channels.fetch(config.discord.channelId);
  if (!channel || !channel.isTextBased() || channel.isDMBased()) {
    throw new Error(`Channel ${config.discord.channelId} is not a guild text channel`);
  }
  const textChannel = channel as TextChannel;
  console.log(`[discord] Target channel: #${textChannel.name}`);

  // 4. Set up webhook client from pre-configured URL
  const webhook = getWebhook();

  // 5. Get/create bridge identity in BeadHub (for human relay)
  const bridgeIdentity = await getOrCreateBridgeIdentity();
  console.log(`[beadhub] Bridge identity: ${bridgeIdentity.alias} (${bridgeIdentity.workspace_id})`);

  // 6. Start Redis → Discord listener
  await startRedisListener(
    redis,
    textChannel,
    webhook,
    sessionMap,
    config.echoSuppressionTtlMs,
    bridgeIdentity.alias,
  );

  // 7. Start Discord → BeadHub + orchestrator listener
  startDiscordListener(client, sessionMap, bridgeIdentity, redis);

  // 8. Start orchestrator outbox → Discord relay
  await startOrchestratorRelay(redis, textChannel, webhook, sessionMap);

  // 9. Health check server
  const healthServer = Bun.serve({
    port: config.health.port,
    fetch(req) {
      const url = new URL(req.url);
      if (url.pathname === "/healthz") {
        const healthy = redis.status === "ready" && client.ws.status === 0;
        return new Response(
          JSON.stringify({ ok: healthy, redis: redis.status, discord: client.ws.status }),
          {
            status: healthy ? 200 : 503,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return new Response("Not Found", { status: 404 });
    },
  });

  console.log(`[health] Listening on :${healthServer.port}/healthz`);
  console.log("[bridge] Ready — relaying BeadHub chat ↔ Discord");

  // Graceful shutdown
  const shutdown = async () => {
    console.log("[bridge] Shutting down...");
    healthServer.stop();
    client.destroy();
    redis.disconnect();
    process.exit(0);
  };

  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch((err) => {
  console.error("[bridge] Fatal error:", err);
  process.exit(1);
});
