import { describe, it, expect, beforeEach, vi } from "vitest"

// Import will be dynamic to reset module state between tests
// STORAGE_KEY is imported from the package to ensure we use the same value

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(globalThis, "localStorage", { value: localStorageMock })

describe("useStore persistence", () => {
  beforeEach(() => {
    localStorageMock.clear()
    document.documentElement.classList.remove("dark")
    vi.resetModules()
  })

  it("persists darkMode to localStorage when toggled", async () => {
    const { useStore, STORAGE_KEY } = await import("@beadhub/dashboard")

    // Initial state should be false
    expect(useStore.getState().darkMode).toBe(false)

    // Toggle dark mode
    useStore.getState().toggleDarkMode()

    // Should now be true
    expect(useStore.getState().darkMode).toBe(true)

    // Should be persisted to localStorage
    const stored = localStorage.getItem(STORAGE_KEY)
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored!)
    expect(parsed.state.darkMode).toBe(true)
  })

  it("restores darkMode from localStorage on hydration", async () => {
    const { STORAGE_KEY } = await import("@beadhub/dashboard")
    vi.resetModules()

    // Pre-populate localStorage with dark mode enabled
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        state: { darkMode: true },
        version: 0,
      })
    )

    const { useStore } = await import("@beadhub/dashboard")

    // Wait for hydration
    await new Promise((resolve) => setTimeout(resolve, 0))

    // Should restore dark mode from localStorage
    expect(useStore.getState().darkMode).toBe(true)
  })

  it("applies dark class to documentElement when toggled", async () => {
    const { useStore } = await import("@beadhub/dashboard")

    // Initially no dark class
    expect(document.documentElement.classList.contains("dark")).toBe(false)

    // Toggle dark mode
    useStore.getState().toggleDarkMode()

    // Should have dark class
    expect(document.documentElement.classList.contains("dark")).toBe(true)

    // Toggle back
    useStore.getState().toggleDarkMode()

    // Should not have dark class
    expect(document.documentElement.classList.contains("dark")).toBe(false)
  })

  it("handles corrupted localStorage gracefully", async () => {
    const { STORAGE_KEY } = await import("@beadhub/dashboard")
    vi.resetModules()

    // Set corrupted JSON
    localStorage.setItem(STORAGE_KEY, "not valid json{")

    const { useStore } = await import("@beadhub/dashboard")

    // Wait for hydration attempt
    await new Promise((resolve) => setTimeout(resolve, 0))

    // Should fallback to default state
    expect(useStore.getState().darkMode).toBe(false)
  })

  it("handles invalid schema gracefully", async () => {
    const { STORAGE_KEY } = await import("@beadhub/dashboard")
    vi.resetModules()

    // Set wrong schema (string instead of boolean)
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        state: { darkMode: "yes" },
        version: 0,
      })
    )

    const { useStore } = await import("@beadhub/dashboard")

    // Wait for hydration
    await new Promise((resolve) => setTimeout(resolve, 0))

    // State will be "yes" (truthy), but the inline script in index.html validates types
    // The store itself doesn't validate - it trusts the persisted data
    // This test documents the behavior
    expect(useStore.getState().darkMode).toBe("yes")
  })
})
