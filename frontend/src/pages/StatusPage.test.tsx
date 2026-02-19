import { afterEach, describe, it, expect, vi } from "vitest"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { ApiProvider, useStore } from "@beadhub/dashboard"
import { TooltipProvider } from "@beadhub/dashboard/components/ui"
import { StatusPage } from "@beadhub/dashboard/pages"
import type { ApiClient, StatusResponse, WorkspacePresence } from "@beadhub/dashboard"

// Suppress SSE fetch errors in test output
vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no SSE in tests")))

function makeAgent(
  overrides: Partial<StatusResponse["agents"][0]> = {}
): StatusResponse["agents"][0] {
  return {
    workspace_id: "ws-1",
    alias: "kate",
    member: null,
    human_name: null,
    program: "claude-code",
    role: "frontend",
    status: "active",
    current_branch: null,
    canonical_origin: null,
    timezone: null,
    current_issue: null,
    last_seen: new Date().toISOString(),
    ...overrides,
  }
}

function makeStatus(
  agents: StatusResponse["agents"] = []
): StatusResponse {
  return {
    workspace: { project_slug: "test-project", workspace_count: agents.length },
    agents,
    claims: [],
    conflicts: [],
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
        <TooltipProvider>
          <MemoryRouter>
            <StatusPage />
          </MemoryRouter>
        </TooltipProvider>
      </ApiProvider>
    </QueryClientProvider>
  )
}

describe("StatusPage workspace cards", () => {
  afterEach(async () => {
    await act(async () => { useStore.getState().clearFilters() })
  })

  it("shows human_name from status endpoint", async () => {
    const agent = makeAgent({ human_name: "Juan Reyero" })
    const ws = makeWorkspace({ human_name: null })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("Juan Reyero")).toBeInTheDocument()
    })
  })

  it("falls back to workspaceInfo human_name when status lacks it", async () => {
    const agent = makeAgent({ human_name: null })
    const ws = makeWorkspace({ human_name: "Juan Reyero" })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("Juan Reyero")).toBeInTheDocument()
    })
  })

  it("shows canonical_origin:current_branch from status endpoint", async () => {
    const agent = makeAgent({
      canonical_origin: "github.com/beadhub/beadhub",
      current_branch: "kate",
    })
    const ws = makeWorkspace()
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

  it("shows canonical_origin without branch when branch is null", async () => {
    const agent = makeAgent({
      canonical_origin: "github.com/beadhub/beadhub",
      current_branch: null,
    })
    const ws = makeWorkspace({ repo: null, branch: null })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(
        screen.getAllByText((_, el) =>
          el?.textContent === "github.com/beadhub/beadhub"
        ).length
      ).toBeGreaterThanOrEqual(1)
    })
    // Should not contain a colon (no branch appended)
    const repoElements = screen.getAllByText((_, el) =>
      el?.textContent === "github.com/beadhub/beadhub"
    )
    repoElements.forEach(el => {
      expect(el.textContent).not.toContain(":")
    })
  })

  it("shows timezone as tooltip on human_name", async () => {
    const agent = makeAgent({
      human_name: "Juan Reyero",
      timezone: "Europe/Madrid",
    })
    const ws = makeWorkspace()
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("Juan Reyero")).toBeInTheDocument()
    })

    // Hover over the human name to trigger tooltip
    await userEvent.hover(screen.getByText("Juan Reyero"))
    await waitFor(() => {
      expect(screen.getByRole("tooltip")).toHaveTextContent("Europe/Madrid")
    })
  })

  it("omits human_name when not set", async () => {
    const agent = makeAgent({ human_name: null })
    const ws = makeWorkspace({ human_name: null })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("kate")).toBeInTheDocument()
    })
    expect(screen.queryByText("Juan Reyero")).not.toBeInTheDocument()
  })

  it("hides human_name when ownerFilter is active", async () => {
    await act(async () => { useStore.getState().setOwnerFilter("Juan Reyero") })
    const agent = makeAgent({ human_name: "Juan Reyero" })
    const ws = makeWorkspace({ human_name: "Juan Reyero" })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(screen.getByText("kate")).toBeInTheDocument()
    })
    // human_name should be hidden because showHumanName = !ownerFilter = false
    expect(screen.queryByText("Juan Reyero")).not.toBeInTheDocument()
  })

  it("falls back to workspaceInfo repo when status lacks canonical_origin", async () => {
    const agent = makeAgent({ canonical_origin: null, current_branch: null })
    const ws = makeWorkspace({ repo: "github.com/beadhub/beadhub", branch: "main" })
    const api = makeMockApi(makeStatus([agent]), [ws])
    renderStatusPage(api)

    await waitFor(() => {
      expect(
        screen.getAllByText((_, el) =>
          el?.textContent === "github.com/beadhub/beadhub:main"
        ).length
      ).toBeGreaterThanOrEqual(1)
    })
  })
})
