import { describe, it, expect, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { ApiProvider } from "@beadhub/dashboard"
import { StatusPage } from "@beadhub/dashboard/pages"
import type { ApiClient, StatusResponse, WorkspacePresence } from "@beadhub/dashboard"

// Suppress SSE fetch errors in test output
vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no SSE in tests")))

function makeStatus(
  agents: StatusResponse["agents"] = []
): StatusResponse {
  return {
    workspace: { project_slug: "test-project", workspace_count: agents.length },
    agents,
    claims: [],
    escalations_pending: 0,
    timestamp: new Date().toISOString(),
  }
}

function makeWorkspace(overrides: Partial<WorkspacePresence> = {}): WorkspacePresence {
  return {
    workspace_id: "ws-1",
    alias: "kate",
    program: "claude-code",
    model: null,
    project_id: "proj-1",
    project_slug: "test-project",
    repo: "github.com/beadhub/beadhub",
    branch: "kate",
    member_email: null,
    human_name: "Juan Reyero",
    role: "frontend",
    status: "active",
    last_seen: new Date().toISOString(),
    deleted_at: null,
    ...overrides,
  }
}

function makeMockApi(
  status: StatusResponse,
  workspaces: WorkspacePresence[]
): ApiClient {
  return {
    getHeaders: () => ({}),
    getStatus: vi.fn().mockResolvedValue(status),
    listWorkspaces: vi.fn().mockResolvedValue({
      workspaces,
      has_more: false,
      next_cursor: null,
    }),
    // Stubs for unused methods
    listClaims: vi.fn(),
    deleteWorkspace: vi.fn(),
    restoreWorkspace: vi.fn(),
    listEscalations: vi.fn(),
    getEscalation: vi.fn(),
    respondToEscalation: vi.fn(),
    listBeadIssues: vi.fn(),
    getBeadIssue: vi.fn(),
    fetchInbox: vi.fn(),
    acknowledgeMessage: vi.fn(),
    sendMessage: vi.fn(),
    startChat: vi.fn(),
    listPendingChats: vi.fn(),
    sendChatMessage: vi.fn(),
    listChatSessions: vi.fn(),
    getSessionMessages: vi.fn(),
    listAllSessions: vi.fn(),
    getSessionMessagesAdmin: vi.fn(),
    joinSession: vi.fn(),
    getDashboardConfig: vi.fn(),
    getDashboardIdentity: vi.fn(),
    getActivePolicy: vi.fn(),
    getPolicyHistory: vi.fn(),
    getPolicyById: vi.fn(),
    createPolicy: vi.fn(),
    activatePolicy: vi.fn(),
    resetPolicyToDefault: vi.fn(),
  } as ApiClient
}

function renderStatusPage(api: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={api}>
        <MemoryRouter>
          <StatusPage />
        </MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>
  )
}

describe("StatusPage workspace cards", () => {
  it("shows human_name when available", async () => {
    const ws = makeWorkspace({ human_name: "Juan Reyero" })
    const agent = {
      workspace_id: ws.workspace_id,
      alias: ws.alias,
      member: null,
      program: ws.program,
      role: ws.role,
      status: ws.status,
      current_issue: null,
      last_seen: ws.last_seen,
    }
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("Juan Reyero")).toBeInTheDocument()
    })
  })

  it("shows repo:branch format", async () => {
    const ws = makeWorkspace({
      repo: "github.com/beadhub/beadhub",
      branch: "kate",
    })
    const agent = {
      workspace_id: ws.workspace_id,
      alias: ws.alias,
      member: null,
      program: ws.program,
      role: ws.role,
      status: ws.status,
      current_issue: null,
      last_seen: ws.last_seen,
    }
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(
        screen.getAllByText((_, el) =>
          el?.textContent === "github.com/beadhub/beadhub:kate"
        ).length
      ).toBeGreaterThanOrEqual(1)
    })
  })

  it("omits human_name when not set", async () => {
    const ws = makeWorkspace({ human_name: null })
    const agent = {
      workspace_id: ws.workspace_id,
      alias: ws.alias,
      member: null,
      program: ws.program,
      role: ws.role,
      status: ws.status,
      current_issue: null,
      last_seen: ws.last_seen,
    }
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("kate")).toBeInTheDocument()
    })
    expect(screen.queryByText("Juan Reyero")).not.toBeInTheDocument()
  })
})
