/**
 * React binding for the API's cold-start flag (see `api.subscribeBooting`).
 * Lives apart from backendStatus.tsx so that file exports only components
 * (Fast Refresh requirement).
 */

import { useEffect, useState } from 'react'
import * as api from './api'

/**
 * True while a request has been outstanding long enough that the API is
 * almost certainly a cold free-tier instance booting rather than working.
 */
export function useBackendBooting(): boolean {
  const [booting, setBooting] = useState(api.isBooting())
  useEffect(() => api.subscribeBooting(setBooting), [])
  return booting
}
