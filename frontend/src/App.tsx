import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ApiProvider } from "@beadhub/dashboard"
import { TooltipProvider } from "@beadhub/dashboard/components/ui"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Layout } from "@/components/Layout"
import { GettingStartedPage } from "@/pages/GettingStartedPage"
import {
  StatusPage,
  WorkspacesPage,
  EscalationsPage,
  IssuesPage,
  MessagesPage,
  ClaimsPage,
  ChatPage,
  PoliciesPage,
} from "@beadhub/dashboard/pages"
import { api } from "@/lib/api"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60000,
      retry: 1,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={api}>
        <ErrorBoundary>
          <TooltipProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<Layout />}>
                  <Route index element={<StatusPage />} />
                  <Route path="getting-started" element={<GettingStartedPage />} />
                  <Route path="workspaces" element={<WorkspacesPage />} />
                  <Route path="escalations" element={<EscalationsPage />} />
                  <Route path="tasks" element={<IssuesPage />} />
                  <Route path="claims" element={<ClaimsPage />} />
                  <Route path="messages" element={<MessagesPage />} />
                  <Route path="chat" element={<ChatPage />} />
                  <Route path="policies" element={<PoliciesPage />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </TooltipProvider>
        </ErrorBoundary>
      </ApiProvider>
    </QueryClientProvider>
  )
}

export default App
