import { useState, useEffect, useMemo } from "react"
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Moon,
  Sun,
  Activity,
  Users,
  AlertTriangle,
  ListTodo,
  MessageSquare,
  MessageCircle,
  Menu,
  X,
  GitBranch,
  Shield,
} from "lucide-react"
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@beadhub/dashboard/components/ui"
import { FilterBar } from "@/components/FilterBar"
import { ScopeBanner } from "@/components/ScopeBanner"
import { useStore, cn } from "@beadhub/dashboard"
import { ApiError, api } from "@/lib/api"

const navItems = [
  // Overview
  { path: "/", label: "Status", icon: Activity, group: "overview" },
  // Coordination (most used)
  { path: "/tasks", label: "Tasks", icon: ListTodo, group: "coordination" },
  { path: "/claims", label: "Claims", icon: GitBranch, group: "coordination" },
  // Communication
  { path: "/messages", label: "Mail", icon: MessageSquare, group: "communication" },
  { path: "/chat", label: "Chat", icon: MessageCircle, group: "communication" },
  // Admin (seldom used)
  { path: "/workspaces", label: "Workspaces", icon: Users, group: "admin" },
  { path: "/escalations", label: "Escalations", icon: AlertTriangle, group: "admin" },
  { path: "/policies", label: "Policies", icon: Shield, group: "admin" },
]

export function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const {
    darkMode,
    toggleDarkMode,
    dashboardIdentity,
    setDashboardIdentity,
    setIdentityLoading,
    setIdentityError,
  } = useStore()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [authRequired, setAuthRequired] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState("")

  // Fetch dashboard config (human_name from env var)
  const { data: configData, isLoading: configLoading, error: configError } = useQuery({
    queryKey: ["dashboard-config"],
    queryFn: () => api.getDashboardConfig(),
    staleTime: Infinity,
    enabled: !authRequired,
  })

  // Fetch workspaces (used for nav badges and first-run onboarding redirects)
  const { data: workspacesData, isLoading: workspacesLoading, error: workspacesError } = useQuery({
    queryKey: ["workspaces-for-identity"],
    queryFn: () => api.listWorkspaces(),
    staleTime: Infinity,
    enabled: !authRequired,
  })

  const humanName = configData?.human_name || "admin"
  const hasNoWorkspaces = workspacesData && workspacesData.workspaces.length === 0

  // Fetch dashboard identity when we have config (project scope is derived server-side from auth)
  const { data: identityData, isLoading: identityLoading, error: identityError } = useQuery({
    queryKey: ["dashboard-identity", humanName],
    queryFn: () => api.getDashboardIdentity(humanName),
    enabled: !!configData && !dashboardIdentity && !authRequired,
    staleTime: Infinity,
  })

  // Badge counts for navigation
  const workspaces = workspacesData?.workspaces || []
  const workspaceIds = useMemo(
    () => workspaces.map((ws) => ws.workspace_id),
    [workspaces]
  )

  const { data: statusData } = useQuery({
    queryKey: ["nav-status"],
    queryFn: () => api.getStatus(),
    refetchInterval: 30000,
  })

  // Fetch unread messages from all workspaces
  const { data: allInboxData } = useQuery({
    queryKey: ["nav-inbox-unread-all", workspaceIds.join(",")],
    queryFn: async () => {
      if (workspaces.length === 0) return { unreadCount: 0 }
      const results = await Promise.all(
        workspaces.map(async (ws) => {
          try {
            const inbox = await api.fetchInbox(ws.workspace_id, { unreadOnly: true, limit: 100 })
            return inbox.messages.length
          } catch (err) {
            console.error(`Failed to fetch inbox for ${ws.workspace_id}:`, err)
            return 0
          }
        })
      )
      return { unreadCount: results.reduce((sum, count) => sum + count, 0) }
    },
    enabled: workspaces.length > 0,
    refetchInterval: 30000,
  })

  // Fetch pending chats from all workspaces
  const { data: allPendingChatsData } = useQuery({
    queryKey: ["nav-pending-chats-all", workspaceIds.join(",")],
    queryFn: async () => {
      if (workspaces.length === 0) return { pendingCount: 0 }
      const results = await Promise.all(
        workspaces.map(async (ws) => {
          try {
            const pending = await api.listPendingChats(ws.workspace_id)
            return pending.messages_waiting
          } catch (err) {
            console.error(`Failed to fetch pending chats for ${ws.workspace_id}:`, err)
            return 0
          }
        })
      )
      return { pendingCount: results.reduce((sum, count) => sum + count, 0) }
    },
    enabled: workspaces.length > 0,
    refetchInterval: 30000,
  })

  // Compute badge counts (memoized to prevent unnecessary re-renders)
  const badgeCounts: Record<string, number> = useMemo(() => ({
    "/escalations": statusData?.escalations_pending ?? 0,
    "/messages": allInboxData?.unreadCount ?? 0,
    "/chat": allPendingChatsData?.pendingCount ?? 0,
  }), [statusData?.escalations_pending, allInboxData?.unreadCount, allPendingChatsData?.pendingCount])

  // Track loading state and errors
  useEffect(() => {
    const isLoading = configLoading || workspacesLoading || identityLoading
    setIdentityLoading(isLoading)

    const isAuthError = (err: unknown) => err instanceof ApiError && err.status === 401
    if (isAuthError(configError) || isAuthError(workspacesError) || isAuthError(identityError)) {
      setAuthRequired(true)
      setIdentityError("Authentication required. Enter a project API key (aw_sk_...) to use the dashboard.")
      setIdentityLoading(false)
      return
    }

    if (configError) {
      setIdentityError(`Failed to load config: ${(configError as Error).message}`)
    } else if (workspacesError) {
      setIdentityError(`Failed to load workspaces: ${(workspacesError as Error).message}`)
    } else if (hasNoWorkspaces) {
      setIdentityError("No workspaces available. Register a workspace to enable messaging.")
      setIdentityLoading(false)
    } else if (identityError) {
      setIdentityError(`Failed to initialize identity: ${(identityError as Error).message}`)
    } else if (!isLoading && !dashboardIdentity && !identityData) {
      // Still loading or waiting for data
    } else {
      setIdentityError(null)
    }
  }, [
    configLoading,
    workspacesLoading,
    identityLoading,
    configError,
    workspacesError,
    identityError,
    hasNoWorkspaces,
    authRequired,
    dashboardIdentity,
    identityData,
    setAuthRequired,
    setIdentityLoading,
    setIdentityError,
  ])

  // Store identity when fetched
  useEffect(() => {
    if (identityData && !dashboardIdentity) {
      setDashboardIdentity(identityData)
      setIdentityLoading(false)
      setIdentityError(null)
    }
  }, [identityData, dashboardIdentity, setDashboardIdentity, setIdentityLoading, setIdentityError])

  const handleSaveApiKey = () => {
    api.setApiKey(apiKeyInput, { persist: true })
    setAuthRequired(false)
    setApiKeyInput("")
    setDashboardIdentity(null)
    queryClient.invalidateQueries()
  }

  const handleClearApiKey = () => {
    api.setApiKey(null, { persist: true })
    setAuthRequired(true)
    setDashboardIdentity(null)
    queryClient.invalidateQueries()
  }

  const isGettingStartedPath =
    location.pathname === "/getting-started" || location.pathname === "/getting-started/"

  useEffect(() => {
    if (authRequired) return
    if (workspacesLoading) return
    if (!workspacesData) return

    const workspaceCount = workspacesData.workspaces.length
    if (workspaceCount === 0) {
      if (!isGettingStartedPath) {
        navigate("/getting-started", { replace: true })
      }
      return
    }

    if (isGettingStartedPath) {
      navigate("/", { replace: true })
    }
  }, [authRequired, isGettingStartedPath, navigate, workspacesData, workspacesLoading])

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar - Desktop */}
      <aside className="hidden md:flex md:w-48 md:flex-col md:fixed md:inset-y-0 border-r bg-background">
        {/* Logo */}
        <div className="flex h-14 items-center gap-2 px-4 border-b">
          <Link to="/" className="flex items-center gap-2">
            <svg viewBox="0 0 100 100" className="h-5 w-5 text-primary" aria-hidden="true"><circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="10"/><circle cx="50" cy="50" r="12" fill="currentColor"/></svg>
            <span className="font-semibold tracking-tight">BeadHub</span>
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4">
          {navItems.map(({ path, label, icon: Icon, group }, index) => {
            const prevItem = navItems[index - 1]
            const showSeparator = index > 0 && group !== prevItem?.group
            const badgeCount = badgeCounts[path] ?? 0
            return (
              <div key={path}>
                {showSeparator && <div className="my-2 mx-1 border-t border-border" />}
                <Link
                  to={path}
                  aria-label={badgeCount > 0 ? `${label} (${badgeCount} unread)` : label}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm transition-colors rounded-md",
                    location.pathname === path
                      ? "bg-primary/10 text-primary font-medium border-l-2 border-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="flex-1">{label}</span>
                  {badgeCount > 0 && (
                    <span className="min-w-5 h-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center" aria-hidden="true">
                      {badgeCount > 99 ? "99+" : badgeCount}
                    </span>
                  )}
                </Link>
              </div>
            )
          })}
        </nav>

        {/* Theme Toggle */}
        <div className="p-4 border-t">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleDarkMode}
            className="w-full justify-start gap-2"
          >
            {darkMode ? (
              <>
                <Sun className="h-4 w-4" />
                Light mode
              </>
            ) : (
              <>
                <Moon className="h-4 w-4" />
                Dark mode
              </>
            )}
          </Button>
        </div>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar - Mobile */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-48 flex-col border-r bg-background transition-transform md:hidden",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Logo + Close */}
        <div className="flex h-14 items-center justify-between px-4 border-b">
          <Link to="/" className="flex items-center gap-2" onClick={() => setSidebarOpen(false)}>
            <svg viewBox="0 0 100 100" className="h-5 w-5 text-primary" aria-hidden="true"><circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="10"/><circle cx="50" cy="50" r="12" fill="currentColor"/></svg>
            <span className="font-semibold tracking-tight">BeadHub</span>
          </Link>
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4">
          {navItems.map(({ path, label, icon: Icon, group }, index) => {
            const prevItem = navItems[index - 1]
            const showSeparator = index > 0 && group !== prevItem?.group
            const badgeCount = badgeCounts[path] ?? 0
            return (
              <div key={path}>
                {showSeparator && <div className="my-2 mx-1 border-t border-border" />}
                <Link
                  to={path}
                  onClick={() => setSidebarOpen(false)}
                  aria-label={badgeCount > 0 ? `${label} (${badgeCount} unread)` : label}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm transition-colors rounded-md",
                    location.pathname === path
                      ? "bg-primary/10 text-primary font-medium border-l-2 border-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="flex-1">{label}</span>
                  {badgeCount > 0 && (
                    <span className="min-w-5 h-5 px-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium flex items-center justify-center" aria-hidden="true">
                      {badgeCount > 99 ? "99+" : badgeCount}
                    </span>
                  )}
                </Link>
              </div>
            )
          })}
        </nav>

        {/* Theme Toggle */}
        <div className="p-4 border-t">
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleDarkMode}
            className="w-full justify-start gap-2"
          >
            {darkMode ? (
              <>
                <Sun className="h-4 w-4" />
                Light mode
              </>
            ) : (
              <>
                <Moon className="h-4 w-4" />
                Dark mode
              </>
            )}
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 md:ml-48">
        {/* Mobile Header */}
        <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/95 backdrop-blur px-4 md:hidden">
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
            <Menu className="h-5 w-5" />
          </Button>
          <span className="font-semibold">BeadHub</span>
        </header>

        {/* Filter Bar */}
        {!isGettingStartedPath && (
          <div className="h-14 flex items-center border-b bg-background px-4">
            <FilterBar />
          </div>
        )}

        {/* Scope Banner - shows current filter context prominently */}
        {!isGettingStartedPath && <ScopeBanner />}

        {authRequired && !isGettingStartedPath && (
          <div className="border-b bg-background px-4 py-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Authentication required</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>
                  Enter a project API key (<span className="font-mono text-xs text-foreground">aw_sk_...</span>) to use the
                  dashboard. Generate one with <span className="font-mono text-xs text-foreground">bdh :init</span>.
                  To avoid manual copy/paste, run <span className="font-mono text-xs text-foreground">bdh :dashboard</span>{" "}
                  (stores the key in this browser).
                </p>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <Input
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder="aw_sk_..."
                    className="font-mono text-xs"
                  />
                  <div className="flex gap-2">
                    <Button type="button" onClick={handleSaveApiKey} disabled={!apiKeyInput.trim()}>
                      Save key
                    </Button>
                    <Button type="button" variant="outline" onClick={handleClearApiKey}>
                      Clear key
                    </Button>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button type="button" onClick={() => window.location.reload()}>
                    Refresh
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Page Content */}
        <main className="px-4 py-6 w-full max-w-6xl min-w-0">
          <Outlet />
        </main>

        {/* Footer */}
        <footer className="border-t py-4">
          <div className="px-4 text-xs text-muted-foreground">
            <span className="opacity-60">BeadHub OSS</span>
            <span className="mx-2 opacity-30">·</span>
            <span className="opacity-60">Agent Coordination</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
