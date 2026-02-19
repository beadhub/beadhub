// Shared API types + interface used by @beadhub/dashboard pages.
//
// Consumers provide a concrete client object via <ApiProvider client={...} />.
// That client should satisfy the ApiClient interface (structural typing).

export interface WorkspacePresence {
  workspace_id: string
  alias: string
  program: string | null
  model: string | null
  project_id: string | null
  project_slug: string | null
  repo: string | null
  branch: string | null
  member_email: string | null
  human_name: string | null
  role: string | null
  status: string
  last_seen: string
  deleted_at: string | null
}

export interface Claim {
  bead_id: string
  workspace_id: string
  alias: string
  human_name: string | null
  claimed_at: string
  claimant_count?: number
  project_id: string
  title: string | null
}

export interface EscalationSummary {
  escalation_id: string
  alias: string
  subject: string
  status: string
  created_at: string
  expires_at: string | null
}

export interface EscalationDetail {
  escalation_id: string
  workspace_id: string
  alias: string
  member_email: string | null
  subject: string
  situation: string
  options: string[] | null
  status: string
  response: string | null
  response_note: string | null
  created_at: string
  responded_at: string | null
  expires_at: string | null
}

export interface BeadIssue {
  bead_id: string
  project_id: string
  repo: string
  branch: string
  title: string
  description?: string | null
  status: string
  priority: number
  type: string
  assignee: string | null
  created_by?: string | null
  labels: string[]
  blocked_by: Array<{ repo: string; branch: string; bead_id: string }>
  parent_id: { repo: string; branch: string; bead_id: string } | null
  created_at?: string | null
  updated_at?: string | null
}

export interface InboxMessage {
  message_id: string
  from_workspace: string
  from_alias: string
  subject: string
  body: string
  priority: string
  thread_id: string | null
  read: boolean
  created_at: string
}

export interface PendingConversation {
  session_id: string
  participants: string[]
  last_message: string
  last_from: string
  unread_count: number
  last_activity: string
}

export interface ChatSession {
  session_id: string
  status: string
  initiator_alias: string
  target_alias: string
  target_workspace: string
  expires_at: string
  sse_url: string
}

export interface StartChatResponse {
  session_id: string
  message_id: string
  participants: Array<{ workspace_id: string; alias: string }>
  sse_url: string
}

export interface ChatMessage {
  message_id: string
  from_alias: string
  from?: string
  body: string
  timestamp: string
  sender_leaving?: boolean
}

export interface SessionListItem {
  session_id: string
  initiator_agent: string
  target_agent: string
  created_at: string
}

export interface SessionListResponse {
  sessions: SessionListItem[]
}

export interface MessageHistoryItem {
  message_id: string
  from_agent: string
  body: string
  created_at: string
}

export interface MessageHistoryResponse {
  session_id: string
  messages: MessageHistoryItem[]
}

export interface AdminSessionParticipant {
  workspace_id: string
  alias: string
}

export interface AdminSessionListItem {
  session_id: string
  participants: AdminSessionParticipant[]
  last_message?: string
  last_from?: string
  last_activity?: string
  message_count: number
}

export interface AdminSessionListResponse {
  sessions: AdminSessionListItem[]
  has_more: boolean
  next_cursor: string | null
}

export interface JoinSessionResponse {
  session_id: string
  workspace_id: string
  alias: string
  joined_at: string
}

export interface DashboardIdentity {
  workspace_id: string
  alias: string
  human_name: string
  project_id: string
  created: boolean
}

export interface DashboardConfig {
  human_name: string
}

export interface Invariant {
  id: string
  title: string
  body_md: string
}

export interface RolePlaybook {
  title: string
  playbook_md: string
}

export interface SelectedRole {
  role: string
  title: string
  playbook_md: string
}

export interface ActivePolicy {
  policy_id: string
  project_id: string
  version: number
  updated_at: string
  invariants: Invariant[]
  roles: Record<string, RolePlaybook>
  selected_role: SelectedRole | null
  adapters: Record<string, unknown>
}

export interface PolicyHistoryItem {
  policy_id: string
  version: number
  created_at: string
  created_by_workspace_id: string | null
  is_active: boolean
}

export interface PolicyBundle {
  invariants: Invariant[]
  roles: Record<string, RolePlaybook>
  adapters: Record<string, unknown>
}

export interface CreatePolicyResponse {
  policy_id: string
  project_id: string
  version: number
  created: boolean
}

export interface ActivatePolicyResponse {
  activated: boolean
  active_policy_id: string
}

export interface ResetPolicyResponse {
  reset: boolean
  active_policy_id: string
  version: number
}

export interface StatusResponse {
  workspace: {
    workspace_id?: string
    project_slug?: string
    repo?: string
    workspace_count?: number
    scope?: string
  }
  agents: Array<{
    workspace_id: string
    alias: string
    member: string | null
    human_name: string | null
    program: string | null
    role: string | null
    status: string
    current_branch: string | null
    canonical_origin: string | null
    timezone: string | null
    current_issue: string | null
    last_seen: string
  }>
  claims: Claim[]
  conflicts: Array<{
    bead_id: string
    claimants: Array<{
      alias: string
      human_name: string | null
      workspace_id: string
    }>
  }>
  escalations_pending: number
  timestamp: string
}

export interface ApiClient {
  // Auth (used by SSE streaming)
  getHeaders(): Record<string, string>

  // Status
  getStatus(filters?: {
    workspaceId?: string
    projectSlug?: string
    repo?: string
  }): Promise<StatusResponse>

  // Claims
  listClaims(filters?: {
    projectSlug?: string
    workspaceId?: string
    limit?: number
    cursor?: string
  }): Promise<{ claims: Claim[]; has_more: boolean; next_cursor: string | null }>

  // Workspaces
  listWorkspaces(filters?: {
    projectSlug?: string
    humanName?: string
    repo?: string
    includeDeleted?: boolean
    limit?: number
    cursor?: string
  }): Promise<{
    workspaces: WorkspacePresence[]
    has_more: boolean
    next_cursor: string | null
  }>
  deleteWorkspace(workspaceId: string): Promise<{
    workspace_id: string
    alias: string
    deleted_at: string
  }>
  restoreWorkspace(workspaceId: string): Promise<{
    workspace_id: string
    alias: string
    restored_at: string
  }>

  // Escalations
  listEscalations(filters?: {
    workspaceId?: string
    projectSlug?: string
    repo?: string
    status?: string
    alias?: string
    limit?: number
    cursor?: string
  }): Promise<{
    escalations: EscalationSummary[]
    has_more: boolean
    next_cursor: string | null
  }>
  getEscalation(escalationId: string): Promise<EscalationDetail>
  respondToEscalation(
    escalationId: string,
    response: string,
    note?: string
  ): Promise<{
    escalation_id: string
    status: string
    response: string
    response_note: string | null
    responded_at: string
  }>

  // Beads issues
  listBeadIssues(filters?: {
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
  }): Promise<{ issues: BeadIssue[]; count: number; synced_at: string | null; has_more: boolean; next_cursor: string | null }>
  getBeadIssue(beadId: string): Promise<BeadIssue>

  // Messages
  fetchInbox(
    workspaceId: string,
    filters?: { limit?: number; unreadOnly?: boolean; cursor?: string }
  ): Promise<{ messages: InboxMessage[]; has_more: boolean; next_cursor: string | null }>
  acknowledgeMessage(
    messageId: string,
    workspaceId: string
  ): Promise<{ message_id: string; acknowledged_at: string }>
  sendMessage(
    fromWorkspace: string,
    fromAlias: string,
    toWorkspace: string,
    subject: string,
    body: string,
    priority?: 'low' | 'normal' | 'high'
  ): Promise<{ message_id: string; delivered_at: string }>

  // Chat
  startChat(
    fromWorkspaceId: string,
    fromAlias: string,
    toAliases: string[],
    message: string
  ): Promise<StartChatResponse>
  listPendingChats(
    workspaceId: string
  ): Promise<{ pending: PendingConversation[]; messages_waiting: number }>
  sendChatMessage(
    sessionId: string,
    workspaceId: string,
    alias: string,
    message: string
  ): Promise<{ message_id: string; delivered: boolean }>

  listChatSessions(workspaceId: string): Promise<SessionListResponse>
  getSessionMessages(
    sessionId: string,
    workspaceId: string
  ): Promise<MessageHistoryResponse>

  // Chat admin (project-wide monitoring)
  listAllSessions(
    workspaceId: string,
    filters?: { limit?: number; cursor?: string }
  ): Promise<AdminSessionListResponse>
  getSessionMessagesAdmin(
    sessionId: string,
    workspaceId: string
  ): Promise<MessageHistoryResponse>
  joinSession(
    sessionId: string,
    workspaceId: string,
    alias: string
  ): Promise<JoinSessionResponse>

  // OSS dashboard identity (humans-as-workspaces)
  getDashboardConfig(): Promise<DashboardConfig>
  getDashboardIdentity(
    humanName: string,
    alias?: string
  ): Promise<DashboardIdentity>

  // Policies
  getActivePolicy(): Promise<ActivePolicy>
  getPolicyHistory(limit?: number): Promise<{ policies: PolicyHistoryItem[] }>
  getPolicyById(policyId: string): Promise<ActivePolicy>
  createPolicy(bundle: PolicyBundle, basePolicyId?: string): Promise<CreatePolicyResponse>
  activatePolicy(policyId: string): Promise<ActivatePolicyResponse>
  resetPolicyToDefault(): Promise<ResetPolicyResponse>
}
