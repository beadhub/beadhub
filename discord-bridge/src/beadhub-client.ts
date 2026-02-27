import { createHmac } from "crypto";
import { randomUUID } from "crypto";
import { config } from "./config.js";
import type { AdminMessage, AdminSession } from "./types.js";

/**
 * Build auth headers. Supports two modes:
 * 1. Internal HMAC auth (in-cluster) — BEADHUB_INTERNAL_AUTH_SECRET + BEADHUB_PROJECT_ID
 * 2. Bearer token — BEADHUB_API_KEY (aweb per-workspace key)
 */
function authHeaders(): Record<string, string> {
  const { internalAuthSecret, projectId, apiKey } = config.beadhub;

  if (internalAuthSecret && projectId) {
    // Internal proxy auth: HMAC-signed headers
    const principalType = "k";
    const principalId = randomUUID();
    const actorId = randomUUID();
    const msg = `v2:${projectId}:${principalType}:${principalId}:${actorId}`;
    const sig = createHmac("sha256", internalAuthSecret).update(msg).digest("hex");
    return {
      "X-BH-Auth": `${msg}:${sig}`,
      "X-Project-ID": projectId,
      "X-API-Key": principalId,
      "X-Aweb-Actor-ID": actorId,
    };
  }

  if (apiKey) {
    return { "Authorization": `Bearer ${apiKey}` };
  }

  return {};
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${config.beadhub.url}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(init?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`BeadHub ${init?.method ?? "GET"} ${path} → ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

/** Fetch the last N messages for a session (admin endpoint, no participant check). */
export async function getSessionMessages(
  sessionId: string,
  limit = 50,
): Promise<AdminMessage[]> {
  const data = await api<{ messages: AdminMessage[] }>(
    `/v1/chat/admin/sessions/${sessionId}/messages?limit=${limit}`,
  );
  return data.messages;
}

/** List all chat sessions in the project. */
export async function listSessions(limit = 200): Promise<AdminSession[]> {
  const data = await api<{ sessions: AdminSession[] }>(
    `/v1/chat/admin/sessions?limit=${limit}`,
  );
  return data.sessions;
}

/** Join a chat session as the bridge's dashboard identity. */
export async function joinSession(
  sessionId: string,
  workspaceId: string,
  alias: string,
): Promise<void> {
  await api(`/v1/chat/admin/sessions/${sessionId}/join`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId, alias }),
  });
}

/** Send a message into a chat session as a dashboard user. */
export async function sendMessage(
  sessionId: string,
  body: string,
  workspaceId: string,
  alias: string,
): Promise<string> {
  const data = await api<{ message_id: string }>(
    `/v1/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ body, workspace_id: workspaceId, alias }),
    },
  );
  return data.message_id;
}

/**
 * Get or create a dashboard identity for the bridge.
 * Returns { workspace_id, alias }.
 */
export async function getOrCreateBridgeIdentity(): Promise<{
  workspace_id: string;
  alias: string;
}> {
  return api(`/v1/dashboard/identity`, {
    method: "POST",
    body: JSON.stringify({ human_name: "Discord Bridge", alias: "discord-bridge" }),
  });
}
