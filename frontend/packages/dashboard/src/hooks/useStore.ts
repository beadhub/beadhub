import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { DashboardIdentity } from "../lib/api"
import type { SSEEvent } from "./useSSE"

export type { DashboardIdentity }

const MAX_EVENTS = 100
export const STORAGE_KEY = "beadhub-dashboard-storage"

interface DashboardState {
  // API routing ('' for standalone, '/api' for embedded)
  apiBasePath: string
  setApiBasePath: (path: string) => void

  // Dashboard identity (for sending messages)
  dashboardIdentity: DashboardIdentity | null
  setDashboardIdentity: (identity: DashboardIdentity | null) => void
  identityLoading: boolean
  setIdentityLoading: (loading: boolean) => void
  identityError: string | null
  setIdentityError: (error: string | null) => void

  // Theme
  darkMode: boolean
  toggleDarkMode: () => void

  // Filters
  repoFilter: string | null
  setRepoFilter: (repo: string | null) => void
  ownerFilter: string | null
  setOwnerFilter: (owner: string | null) => void
  createdByFilter: string | null
  setCreatedByFilter: (createdBy: string | null) => void
  clearFilters: () => void

  // Events (persisted across navigation)
  events: SSEEvent[]
  addEvent: (event: SSEEvent) => void
  clearEvents: () => void
}

export const useStore = create<DashboardState>()(
  persist(
    (set) => ({
      apiBasePath: "",
      setApiBasePath: (path) => set({ apiBasePath: path }),

      dashboardIdentity: null,
      setDashboardIdentity: (identity) => set({ dashboardIdentity: identity }),
      identityLoading: true,
      setIdentityLoading: (loading) => set({ identityLoading: loading }),
      identityError: null,
      setIdentityError: (error) => set({ identityError: error }),

      darkMode: false,
      toggleDarkMode: () =>
        set((state) => {
          const newDarkMode = !state.darkMode
          if (newDarkMode) {
            document.documentElement.classList.add("dark")
          } else {
            document.documentElement.classList.remove("dark")
          }
          return { darkMode: newDarkMode }
        }),

      repoFilter: null,
      setRepoFilter: (repo) => set({ repoFilter: repo }),
      ownerFilter: null,
      setOwnerFilter: (owner) => set({ ownerFilter: owner }),
      createdByFilter: null,
      setCreatedByFilter: (createdBy) => set({ createdByFilter: createdBy }),
      clearFilters: () =>
        set({
          repoFilter: null,
          ownerFilter: null,
          createdByFilter: null,
        }),

      // Events
      events: [],
      addEvent: (event) =>
        set((state) => ({
          events: [event, ...state.events].slice(0, MAX_EVENTS),
        })),
      clearEvents: () => set({ events: [] }),
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({ darkMode: state.darkMode }),
      onRehydrateStorage: () => (state) => {
        if (state?.darkMode) {
          document.documentElement.classList.add("dark")
        } else {
          document.documentElement.classList.remove("dark")
        }
      },
    }
  )
)
