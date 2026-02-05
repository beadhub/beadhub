// Components
export {
  DashboardLayout,
  DashboardSidebar,
  DashboardNav,
  DashboardMobileDrawer,
  FilterBar,
  navItems,
} from './components'
export type {
  NavItem,
  DashboardLayoutProps,
  DashboardSidebarProps,
  FilterBarProps,
} from './components'

// Hooks
export { useApi, useSSE, useStore, STORAGE_KEY } from './hooks'
export type { SSEEvent, DashboardIdentity } from './hooks'

// Shared utils + types
export { cn } from './lib/utils'
export type {
  ApiClient,
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
} from './lib/api'

// Providers
export { ApiProvider, ApiContext } from './providers'

// Pages
export {
  StatusPage,
  WorkspacesPage,
  EscalationsPage,
  IssuesPage,
  ClaimsPage,
  MessagesPage,
  ChatPage,
  PoliciesPage,
} from './pages'
export type { PageProps } from './pages'
