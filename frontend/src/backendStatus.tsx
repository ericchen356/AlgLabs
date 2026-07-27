/**
 * Cold-start UI for the API.
 *
 * The backend is hosted on a free tier that idles its instance out after a
 * quiet spell, so the first request from a new visitor can take tens of
 * seconds while the server boots. Without a signal that reads as *waiting on
 * the server* rather than *the app is broken*, a capture button stuck on
 * "Reading…" is indistinguishable from a hang — so every screen that talks to
 * the API surfaces this instead.
 */

import { useBackendBooting } from './backendBooting'
import './backendStatus.css'

/**
 * Inline "the server is waking up" note. Renders nothing while the API is
 * warm, so callers can drop it in unconditionally.
 */
export default function BootingNotice({ compact = false }: { compact?: boolean }) {
  const booting = useBackendBooting()
  if (!booting) return null
  return (
    <p className={`booting-notice${compact ? ' compact' : ''}`} role="status">
      <span className="booting-dots" aria-hidden>
        <span />
        <span />
        <span />
      </span>
      Waking the server up. It sleeps when nobody is using it, so this first request can take
      up to a minute. Everything is quick afterwards.
    </p>
  )
}

/** Header-sized version of the same signal. */
export function BootingBadge() {
  const booting = useBackendBooting()
  if (!booting) return null
  return (
    <span className="booting-badge" role="status">
      <span className="booting-dots" aria-hidden>
        <span />
        <span />
        <span />
      </span>
      waking the server…
    </span>
  )
}
