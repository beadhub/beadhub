export const config = {
  discord: {
    token: requiredEnv("DISCORD_TOKEN"),
    channelId: requiredEnv("DISCORD_CHANNEL_ID"),
    guildId: requiredEnv("DISCORD_GUILD_ID"),
    webhookUrl: requiredEnv("DISCORD_WEBHOOK_URL"),
    /** Optional AI orchestrator channel (separate from agent chat) */
    aiChannelId: env("DISCORD_AI_CHANNEL_ID", ""),
    aiWebhookUrl: env("DISCORD_AI_WEBHOOK_URL", ""),
    /** Ordis coordinator channel — flat conversation (no threads) */
    ordisChannelId: env("DISCORD_ORDIS_CHANNEL_ID", ""),
    ordisWebhookUrl: env("DISCORD_ORDIS_WEBHOOK_URL", ""),
  },
  beadhub: {
    url: env("BEADHUB_URL", "http://localhost:8000"),
    apiKey: env("BEADHUB_API_KEY", ""),
    internalAuthSecret: env("BEADHUB_INTERNAL_AUTH_SECRET", ""),
    projectId: env("BEADHUB_PROJECT_ID", ""),
  },
  controlPlane: {
    apiKey: env("CONTROL_PLANE_API_KEY", ""),
    projectId: env("CONTROL_PLANE_PROJECT_ID", ""),
  },
  redis: {
    url: env("REDIS_URL", "redis://localhost:16379/0"),
  },
  health: {
    port: parseInt(env("HEALTH_PORT", "3001"), 10),
  },
  orchestrator: {
    alias: env("ORCHESTRATOR_ALIAS", "orchestrator"),
  },
  /** Recently relayed message IDs — prevents echo loops */
  echoSuppressionTtlMs: 60_000,
  /** Max Discord message length before splitting */
  maxDiscordMessageLength: 1900,
} as const;

function env(key: string, fallback: string): string {
  return process.env[key] ?? fallback;
}

function requiredEnv(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

