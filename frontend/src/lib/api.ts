// API client for BeadHub OSS
// In standalone mode, all requests go to same origin
// In embedded mode, auth headers are injected by the parent gateway

import type {
  ApiClient as DashboardApiClient,
  WorkspacePresence,
  Claim,
  EscalationSummary,
  EscalationDetail,
  BeadIssue,
  InboxMessage,
  PendingConversation,
  ChatSession,
  StartChatResponse,
  ChatMessage,
  SessionListItem,
  SessionListResponse,
  MessageHistoryItem,
  MessageHistoryResponse,
  AdminSessionParticipant,
  AdminSessionListItem,
  AdminSessionListResponse,
  JoinSessionResponse,
  DashboardIdentity,
  DashboardConfig,
  Invariant,
  RolePlaybook,
  SelectedRole,
  ActivePolicy,
  PolicyHistoryItem,
  PolicyBundle,
  CreatePolicyResponse,
  ActivatePolicyResponse,
  ResetPolicyResponse,
  StatusResponse,
} from "@beadhub/dashboard"

export type {
  WorkspacePresence,
  Claim,
  EscalationSummary,
  EscalationDetail,
  BeadIssue,
  InboxMessage,
  PendingConversation,
  ChatSession,
  StartChatResponse,
  ChatMessage,
  SessionListItem,
  SessionListResponse,
  MessageHistoryItem,
  MessageHistoryResponse,
  AdminSessionParticipant,
  AdminSessionListItem,
  AdminSessionListResponse,
  JoinSessionResponse,
  DashboardIdentity,
  DashboardConfig,
  Invariant,
  RolePlaybook,
  SelectedRole,
  ActivePolicy,
  PolicyHistoryItem,
  PolicyBundle,
  CreatePolicyResponse,
  ActivatePolicyResponse,
  ResetPolicyResponse,
  StatusResponse,
}

const API_BASE = ""
const API_KEY_STORAGE_KEY = "beadhub_api_key"

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined"
}

function extractApiKeyFromUrlFragment(): string | null {
  if (typeof window === "undefined") return null
  const raw = window.location.hash || ""
  if (!raw || raw === "#") return null

  const params = new URLSearchParams(raw.replace(/^#/, ""))
  const candidate =
    params.get("api_key") ||
    params.get("beadhub_api_key") ||
    params.get("key")
  if (!candidate) return null

  const apiKey = candidate.trim()
  if (!apiKey.startsWith("aw_sk_") || apiKey.length < 38) return null

  // Remove the key from the URL to avoid leaving it in the address bar / history.
  try {
    window.history.replaceState({}, document.title, window.location.pathname + window.location.search)
  } catch {
    // ignore
  }

  return apiKey
}

function loadStoredApiKey(): string | null {
  if (!canUseLocalStorage()) return null
  try {
    return window.localStorage.getItem(API_KEY_STORAGE_KEY)
  } catch {
    return null
  }
}

function persistApiKey(key: string | null) {
  if (!canUseLocalStorage()) return
  try {
    if (key) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, key)
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY)
    }
  } catch {
    // ignore
  }
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.body = body
  }
}

export class ApiClient implements DashboardApiClient {
  private headers: Record<string, string> = {}

  constructor() {
    const fromUrl = extractApiKeyFromUrlFragment()
    if (fromUrl) {
      this.setApiKey(fromUrl, { persist: true })
      return
    }
    const stored = loadStoredApiKey()
    if (stored) {
      this.setApiKey(stored, { persist: false })
    }
  }

  setHeaders(headers: Record<string, string>) {
    this.headers = headers
  }

  getHeaders(): Record<string, string> {
    return this.headers
  }

  setApiKey(apiKey: string | null, opts?: { persist?: boolean }) {
    const persist = opts?.persist ?? true
    if (apiKey && apiKey.trim()) {
      this.headers = {
        ...this.headers,
        Authorization: `Bearer ${apiKey.trim()}`,
      }
      if (persist) persistApiKey(apiKey.trim())
    } else {
      const next = { ...this.headers }
      delete next.Authorization
      this.headers = next
      if (persist) persistApiKey(null)
    }
  }

  private async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...this.headers,
        ...options?.headers,
      },
    })

    if (!response.ok) {
      const raw = await response.text().catch(() => "")
      let body: unknown = raw
      let detail = response.statusText || `HTTP ${response.status}`
      if (raw) {
        try {
          body = JSON.parse(raw)
        } catch {
          body = raw
        }
      }
      if (body && typeof body === "object" && "detail" in body) {
        const d = (body as { detail?: unknown }).detail
        if (typeof d === "string" && d.trim()) detail = d
      }
      throw new ApiError(response.status, detail, body)
    }

    if (response.status === 204) {
      return undefined as T
    }

    const raw = await response.text().catch(() => "")
    if (!raw) {
      return undefined as T
    }
    return JSON.parse(raw) as T
  }

  // Status
  async getStatus(filters?: {
    workspaceId?: string
    projectSlug?: string
    repo?: string
  }): Promise<StatusResponse> {
    const params = new URLSearchParams()
    if (filters?.workspaceId) params.set("workspace_id", filters.workspaceId)
    if (filters?.projectSlug) params.set("project_slug", filters.projectSlug)
    if (filters?.repo) params.set("repo", filters.repo)
    const query = params.toString()
    return this.fetch(`/v1/status${query ? `?${query}` : ""}`)
  }

  // Claims
  async listClaims(filters?: {
    projectSlug?: string
    workspaceId?: string
    limit?: number
    cursor?: string
  }): Promise<{ claims: Claim[]; has_more: boolean; next_cursor: string | null }> {
    const params = new URLSearchParams()
    if (filters?.projectSlug) params.set("project_slug", filters.projectSlug)
    if (filters?.workspaceId) params.set("workspace_id", filters.workspaceId)
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.cursor) params.set("cursor", filters.cursor)
    const query = params.toString()
    return this.fetch(`/v1/claims${query ? `?${query}` : ""}`)
  }

  // Workspaces
  async listWorkspaces(filters?: {
    projectSlug?: string
    humanName?: string
    repo?: string
    includeDeleted?: boolean
    limit?: number
    cursor?: string
  }): Promise<{ workspaces: WorkspacePresence[]; has_more: boolean; next_cursor: string | null }> {
    const params = new URLSearchParams()
    if (filters?.projectSlug) params.set("project_slug", filters.projectSlug)
    if (filters?.humanName) params.set("human_name", filters.humanName)
    if (filters?.repo) params.set("repo", filters.repo)
    if (filters?.includeDeleted) params.set("include_deleted", "true")
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.cursor) params.set("cursor", filters.cursor)
    const query = params.toString()
    return this.fetch(`/v1/workspaces${query ? `?${query}` : ""}`)
  }

  async deleteWorkspace(workspaceId: string): Promise<{
    workspace_id: string
    alias: string
    deleted_at: string
  }> {
    return this.fetch(`/v1/workspaces/${workspaceId}`, {
      method: "DELETE",
    })
  }

  async restoreWorkspace(workspaceId: string): Promise<{
    workspace_id: string
    alias: string
    restored_at: string
  }> {
    return this.fetch(`/v1/workspaces/${workspaceId}/restore`, {
      method: "POST",
    })
  }

  // Escalations
  async listEscalations(filters?: {
    workspaceId?: string
    projectSlug?: string
    repo?: string
    status?: string
    alias?: string
    limit?: number
    cursor?: string
  }): Promise<{ escalations: EscalationSummary[]; has_more: boolean; next_cursor: string | null }> {
    const params = new URLSearchParams()
    if (filters?.workspaceId) params.set("workspace_id", filters.workspaceId)
    if (filters?.projectSlug) params.set("project_slug", filters.projectSlug)
    if (filters?.repo) params.set("repo", filters.repo)
    if (filters?.status) params.set("status", filters.status)
    if (filters?.alias) params.set("alias", filters.alias)
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.cursor) params.set("cursor", filters.cursor)
    const query = params.toString()
    return this.fetch(`/v1/escalations${query ? `?${query}` : ""}`)
  }

  async getEscalation(escalationId: string): Promise<EscalationDetail> {
    return this.fetch(`/v1/escalations/${escalationId}`)
  }

  async respondToEscalation(
    escalationId: string,
    response: string,
    note?: string
  ): Promise<{
    escalation_id: string
    status: string
    response: string
    response_note: string | null
    responded_at: string
  }> {
    return this.fetch(`/v1/escalations/${escalationId}/respond`, {
      method: "POST",
      body: JSON.stringify({ response, note }),
    })
  }

  // Beads
  async getReadyIssues(
    workspaceId: string,
    filters?: { repo?: string; branch?: string }
  ): Promise<{ issues: BeadIssue[]; count: number }> {
    const params = new URLSearchParams({ workspace_id: workspaceId })
    if (filters?.repo) params.set("repo", filters.repo)
    if (filters?.branch) params.set("branch", filters.branch)
    return this.fetch(`/v1/beads/ready?${params.toString()}`)
  }

  async listBeadIssues(filters?: {
    repo?: string
    branch?: string
    status?: string
    type?: string
    assignee?: string
    createdBy?: string
    label?: string
    beadIds?: string[]
    q?: string
    limit?: number
    cursor?: string
  }): Promise<{ issues: BeadIssue[]; count: number; synced_at: string | null; has_more: boolean; next_cursor: string | null }> {
    const params = new URLSearchParams()
    if (filters?.repo) params.set("repo", filters.repo)
    if (filters?.branch) params.set("branch", filters.branch)
    if (filters?.status) params.set("status", filters.status)
    if (filters?.type) params.set("type", filters.type)
    if (filters?.assignee) params.set("assignee", filters.assignee)
    if (filters?.createdBy) params.set("created_by", filters.createdBy)
    if (filters?.label) params.set("label", filters.label)
    if (filters?.beadIds && filters.beadIds.length > 0) {
      params.set("bead_ids", filters.beadIds.join(","))
    }
    if (filters?.q) params.set("q", filters.q)
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.cursor) params.set("cursor", filters.cursor)
    const query = params.toString()
    return this.fetch(`/v1/beads/issues${query ? `?${query}` : ""}`)
  }

  async getBeadIssue(beadId: string): Promise<BeadIssue> {
    return this.fetch(`/v1/beads/issues/${beadId}`)
  }

  // Messages
  async fetchInbox(
    workspaceId: string,
    filters?: { limit?: number; unreadOnly?: boolean; cursor?: string }
  ): Promise<{ messages: InboxMessage[]; has_more: boolean; next_cursor: string | null }> {
    const params = new URLSearchParams({ workspace_id: workspaceId })
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.unreadOnly) params.set("unread_only", "true")
    if (filters?.cursor) params.set("cursor", filters.cursor)
    return this.fetch(`/v1/messages/inbox?${params.toString()}`)
  }

  async acknowledgeMessage(
    messageId: string,
    workspaceId: string
  ): Promise<{ message_id: string; acknowledged_at: string }> {
    return this.fetch(`/v1/messages/${messageId}/ack`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    })
  }

  async sendMessage(
    fromWorkspace: string,
    fromAlias: string,
    toWorkspace: string,
    subject: string,
    body: string,
    priority: "low" | "normal" | "high" = "normal"
  ): Promise<{ message_id: string; delivered_at: string }> {
    return this.fetch("/v1/messages", {
      method: "POST",
      body: JSON.stringify({
        from_workspace: fromWorkspace,
        from_alias: fromAlias,
        to_workspace: toWorkspace,
        subject,
        body,
        priority,
      }),
    })
  }

  // Health
  async health(): Promise<{ status: string; checks: Record<string, string> }> {
    return this.fetch("/health")
  }

  // Chat
  async startChat(
    fromWorkspaceId: string,
    fromAlias: string,
    toAliases: string[],
    message: string
  ): Promise<StartChatResponse> {
    return this.fetch("/v1/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        from_workspace: fromWorkspaceId,
        from_alias: fromAlias,
        to_aliases: toAliases,
        message,
      }),
    })
  }

  async listPendingChats(
    workspaceId: string
  ): Promise<{ pending: PendingConversation[]; messages_waiting: number }> {
    const params = new URLSearchParams({
      workspace_id: workspaceId,
    })
    return this.fetch(`/v1/chat/pending?${params.toString()}`)
  }

  async sendChatMessage(
    sessionId: string,
    workspaceId: string,
    alias: string,
    message: string
  ): Promise<{ message_id: string; delivered: boolean }> {
    return this.fetch(`/v1/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, alias, body: message }),
    })
  }

  // v2.1: No status parameter - sessions are persistent with no lifecycle
  async listChatSessions(
    workspaceId: string
  ): Promise<SessionListResponse> {
    const params = new URLSearchParams({
      workspace_id: workspaceId,
    })
    return this.fetch(`/v1/chat/sessions?${params.toString()}`)
  }

  async getSessionMessages(
    sessionId: string,
    workspaceId: string
  ): Promise<MessageHistoryResponse> {
    const params = new URLSearchParams({ workspace_id: workspaceId })
    return this.fetch(`/v1/chat/sessions/${sessionId}/messages?${params.toString()}`)
  }

  // Admin endpoints - for monitoring all sessions in a project
  async listAllSessions(
    workspaceId: string,
    filters?: { limit?: number; cursor?: string }
  ): Promise<AdminSessionListResponse> {
    const params = new URLSearchParams({ workspace_id: workspaceId })
    if (filters?.limit) params.set("limit", String(filters.limit))
    if (filters?.cursor) params.set("cursor", filters.cursor)
    return this.fetch(`/v1/chat/admin/sessions?${params.toString()}`)
  }

  async getSessionMessagesAdmin(
    sessionId: string,
    workspaceId: string
  ): Promise<MessageHistoryResponse> {
    const params = new URLSearchParams({ workspace_id: workspaceId })
    return this.fetch(`/v1/chat/admin/sessions/${sessionId}/messages?${params.toString()}`)
  }

  async joinSession(
    sessionId: string,
    workspaceId: string,
    alias: string
  ): Promise<JoinSessionResponse> {
    return this.fetch(`/v1/chat/admin/sessions/${sessionId}/join`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, alias }),
    })
  }

  // Dashboard config - get configured human name for OSS mode
  async getDashboardConfig(): Promise<DashboardConfig> {
    return this.fetch("/v1/dashboard/config")
  }

  // Dashboard identity - creates or retrieves dashboard workspace for human
  async getDashboardIdentity(
    humanName: string,
    alias?: string
  ): Promise<DashboardIdentity> {
    return this.fetch("/v1/dashboard/identity", {
      method: "POST",
      body: JSON.stringify({
        human_name: humanName,
        ...(alias && { alias }),
      }),
    })
  }

  // Policies
  async getActivePolicy(): Promise<ActivePolicy> {
    return this.fetch("/v1/policies/active")
  }

  async getPolicyHistory(limit?: number): Promise<{ policies: PolicyHistoryItem[] }> {
    const params = new URLSearchParams()
    if (limit) params.set("limit", String(limit))
    const query = params.toString()
    return this.fetch(`/v1/policies/history${query ? `?${query}` : ""}`)
  }

  async getPolicyById(policyId: string): Promise<ActivePolicy> {
    return this.fetch(`/v1/policies/${policyId}`)
  }

  async createPolicy(bundle: PolicyBundle, basePolicyId?: string): Promise<CreatePolicyResponse> {
    return this.fetch("/v1/policies", {
      method: "POST",
      body: JSON.stringify({
        bundle,
        ...(basePolicyId && { base_policy_id: basePolicyId }),
      }),
    })
  }

  async activatePolicy(policyId: string): Promise<ActivatePolicyResponse> {
    return this.fetch(`/v1/policies/${policyId}/activate`, {
      method: "POST",
    })
  }

  async resetPolicyToDefault(): Promise<ResetPolicyResponse> {
    return this.fetch("/v1/policies/reset", {
      method: "POST",
    })
  }
}

export const api = new ApiClient()
