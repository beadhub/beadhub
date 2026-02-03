import { createContext, type ReactNode } from 'react'

/**
 * Generic API context for dashboard pages.
 *
 * The dashboard package doesn't define specific API methods - each app
 * (standalone, embedded) provides its own API client with its own types.
 *
 * Recommended typing pattern:
 *
 * ```ts
 * import type { ApiClient } from '@beadhub/dashboard'
 * const api = useApi<ApiClient>()
 * ```
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const ApiContext = createContext<any>(null)

interface ApiProviderProps<T> {
  client: T
  children: ReactNode
}

export function ApiProvider<T>({ client, children }: ApiProviderProps<T>) {
  return (
    <ApiContext.Provider value={client}>
      {children}
    </ApiContext.Provider>
  )
}
