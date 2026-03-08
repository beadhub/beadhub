import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ApiProvider } from "../../packages/dashboard/src/providers/ApiProvider"
import { useStore } from "../../packages/dashboard/src/hooks/useStore"
import { SendMessageDialog } from "../../packages/dashboard/src/components/SendMessageDialog"
import type { ApiClient, DashboardIdentity } from "../../packages/dashboard/src/lib/api"

const dashboardIdentity: DashboardIdentity = {
  workspace_id: "sender-1",
  alias: "grace",
  human_name: "Grace Hopper",
  project_id: "proj-1",
  created: true,
}

function renderDialog(api: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={api}>
        <SendMessageDialog
          open
          onOpenChange={vi.fn()}
          targetWorkspaceId="target-1"
          targetAlias="target"
        />
      </ApiProvider>
    </QueryClientProvider>
  )
}

function makeApi(sendMessage: ApiClient["sendMessage"]): ApiClient {
  return {
    sendMessage,
  } as ApiClient
}

function makeStatusError(status: number, message: string) {
  return Object.assign(new Error(message), { status })
}

describe("SendMessageDialog", () => {
  beforeEach(async () => {
    await act(async () => {
      useStore.setState({
        dashboardIdentity,
        identityLoading: false,
        identityError: null,
      })
    })
  })

  afterEach(async () => {
    await act(async () => {
      useStore.setState({
        dashboardIdentity: null,
        identityLoading: true,
        identityError: null,
      })
    })
  })

  it("retries transient network failures before succeeding", async () => {
    const sendMessage = vi
      .fn<ApiClient["sendMessage"]>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        message_id: "msg-1",
        delivered_at: new Date().toISOString(),
      })

    const user = userEvent.setup()
    renderDialog(makeApi(sendMessage))

    await user.type(screen.getByPlaceholderText("Enter your message..."), "Hello")
    await user.click(screen.getByRole("button", { name: "Send" }))

    expect(sendMessage).toHaveBeenCalledTimes(1)

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByText("Message sent successfully!")).toBeInTheDocument()
  })

  it("retries 5xx responses before succeeding", async () => {
    const sendMessage = vi
      .fn<ApiClient["sendMessage"]>()
      .mockRejectedValueOnce(makeStatusError(503, "Service unavailable"))
      .mockResolvedValueOnce({
        message_id: "msg-2",
        delivered_at: new Date().toISOString(),
      })

    const user = userEvent.setup()
    renderDialog(makeApi(sendMessage))

    await user.type(screen.getByPlaceholderText("Enter your message..."), "Hello")
    await user.click(screen.getByRole("button", { name: "Send" }))

    expect(sendMessage).toHaveBeenCalledTimes(1)

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByText("Message sent successfully!")).toBeInTheDocument()
  })

  it("does not retry 4xx responses", async () => {
    const sendMessage = vi
      .fn<ApiClient["sendMessage"]>()
      .mockRejectedValueOnce(makeStatusError(401, "Unauthorized"))

    const user = userEvent.setup()
    renderDialog(makeApi(sendMessage))

    await user.type(screen.getByPlaceholderText("Enter your message..."), "Hello")
    await user.click(screen.getByRole("button", { name: "Send" }))

    await waitFor(() => {
      expect(screen.getByText("Unauthorized")).toBeInTheDocument()
    })
    expect(sendMessage).toHaveBeenCalledTimes(1)

    await new Promise((resolve) => {
      setTimeout(resolve, 800)
    })

    expect(sendMessage).toHaveBeenCalledTimes(1)
  })
})
