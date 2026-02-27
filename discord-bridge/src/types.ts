/** Matches the ChatMessageEvent dataclass in beadhub events.py */
export interface ChatMessageEvent {
  workspace_id: string;
  type: "chat.message_sent";
  timestamp: string;
  project_slug: string | null;
  session_id: string;
  message_id: string;
  from_alias: string;
  to_aliases: string[];
  preview: string;
}

/** Any event from the events:* channels */
export interface BeadHubEvent {
  workspace_id: string;
  type: string;
  timestamp: string;
  project_slug?: string | null;
  [key: string]: unknown;
}

/** Message from the admin messages API */
export interface AdminMessage {
  message_id: string;
  from_agent: string;
  body: string;
  created_at: string;
}

/** Session from the admin sessions API */
export interface AdminSession {
  session_id: string;
  participants: { workspace_id: string; alias: string }[];
  last_message: string | null;
  last_from: string | null;
  last_activity: string | null;
  message_count: number;
}

/** Bridge → Orchestrator Deployment via Redis LIST */
export interface OrchestratorInboxMessage {
  thread_id: string;
  session_id: string;
  author: string;
  message: string;
  timestamp: string;
}

/** Orchestrator Deployment → Bridge via Redis LIST */
export interface OrchestratorOutboxMessage {
  thread_id: string;
  session_id: string;
  response: string;
  timestamp: string;
}

/** Source of a session mapping */
export type SessionSource = "beadhub" | "orchestrator";
