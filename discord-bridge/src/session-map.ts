import type Redis from "ioredis";
import type { SessionSource } from "./types.js";

const HASH_KEY = "discord-bridge:sessions";
const REVERSE_KEY = "discord-bridge:threads";
const SOURCE_KEY = "discord-bridge:session-source";

/**
 * Bidirectional map between BeadHub session IDs and Discord thread IDs.
 * Backed by Redis hashes for persistence across restarts.
 * Tracks session source ("beadhub" | "orchestrator") for routing.
 */
export class SessionMap {
  constructor(private redis: Redis) {}

  async getThreadId(sessionId: string): Promise<string | null> {
    return this.redis.hget(HASH_KEY, sessionId);
  }

  async getSessionId(threadId: string): Promise<string | null> {
    return this.redis.hget(REVERSE_KEY, threadId);
  }

  async getSource(threadId: string): Promise<SessionSource | null> {
    return this.redis.hget(SOURCE_KEY, threadId) as Promise<SessionSource | null>;
  }

  /** Backward-compatible: sets mapping without source */
  async set(sessionId: string, threadId: string): Promise<void> {
    await this.redis.pipeline()
      .hset(HASH_KEY, sessionId, threadId)
      .hset(REVERSE_KEY, threadId, sessionId)
      .exec();
  }

  /** Sets mapping with source tracking for routing decisions */
  async setWithSource(sessionId: string, threadId: string, source: SessionSource): Promise<void> {
    await this.redis.pipeline()
      .hset(HASH_KEY, sessionId, threadId)
      .hset(REVERSE_KEY, threadId, sessionId)
      .hset(SOURCE_KEY, threadId, source)
      .exec();
  }
}
