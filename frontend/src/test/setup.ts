import "@testing-library/jest-dom"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// Ensure localStorage is available for zustand persist middleware.
// Node.js v22 has a built-in localStorage that may not fully work in jsdom.
if (typeof globalThis.localStorage === "undefined" || typeof globalThis.localStorage?.setItem !== "function") {
  const store: Record<string, string> = {}
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => { store[key] = value },
      removeItem: (key: string) => { delete store[key] },
      clear: () => { Object.keys(store).forEach(k => delete store[k]) },
      get length() { return Object.keys(store).length },
      key: (i: number) => Object.keys(store)[i] ?? null,
    },
    configurable: true,
  })
}

afterEach(() => {
  cleanup()
})
