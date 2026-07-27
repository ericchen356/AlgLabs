/**
 * Set picker (CONTRACTS.md §12.4 + handoff README §6, restyled to 5 sets):
 * one card per set from GET /api/trainer/sets — icon tile, name, count +
 * description, and two actions: "Random drill ▸" (ink pill → trainer random
 * mode) and "Choose a case…" (outline pill → casepick).
 */

import { useEffect, useState } from 'react'
import { fetchSets } from './api'
import type { SetKey, SetPickerProps, TrainerSet } from './types'
import BootingNotice from '../backendStatus'
import '../Trainer.css'

/** CSS icon tiles (no image assets): tile color class + glyph per set. */
const SET_ICONS: Record<SetKey, { className: string; glyph: string }> = {
  oll: { className: 'ink', glyph: '▦' },
  pll: { className: 'blue', glyph: '▦' },
  coll: { className: 'red', glyph: 'C' },
  zbll: { className: 'green', glyph: 'Z' },
  vls: { className: 'yellow', glyph: 'V' },
}

/** What each acronym stands for, spelled out on the set cards. */
const SET_FULL_NAMES: Record<SetKey, string> = {
  oll: 'Orientation of the Last Layer',
  pll: 'Permutation of the Last Layer',
  coll: 'Corners of the Last Layer',
  zbll: 'Zborowski-Bruchem Last Layer',
  vls: 'Valk Last Slot',
}

const TILTS = ['tilt-a', 'tilt-b', 'tilt-c', 'tilt-d'] as const

export default function SetPicker({ onBack, onRandomDrill, onChooseCase }: SetPickerProps) {
  const [sets, setSets] = useState<TrainerSet[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let alive = true
    setError(null)
    fetchSets().then(
      (s) => {
        if (alive) setSets(s)
      },
      (err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      },
    )
    return () => {
      alive = false
    }
  }, [retry])

  return (
    <div className="screen">
      <div className="screen-title-row">
        <button className="back-link" onClick={onBack}>
          ← home
        </button>
        <h2 className="screen-title big">Choose what to drill</h2>
      </div>
      <p className="hint">
        Each set gives you a random scramble from one of its cases. Time your recognition,
        then your execution, or pick a single case and grind it.
      </p>

      {error && (
        <div className="failure">
          {error}{' '}
          <button className="btn" onClick={() => setRetry((n) => n + 1)}>
            Retry
          </button>
        </div>
      )}
      {!error && !sets && <div className="tr-loading">loading sets…</div>}
      <BootingNotice />

      {sets && (
        <div className="set-grid">
          {sets.map((s, i) => {
            const icon = SET_ICONS[s.key]
            return (
              <div key={s.key} className={`set-card ${TILTS[i % TILTS.length]}`}>
                <div className="set-card-top">
                  <span className={`set-icon ${icon.className}`} aria-hidden>
                    {icon.glyph}
                  </span>
                  <span className="set-card-text">
                    <span className="set-name">{s.name}</span>
                    <span className="set-fullname">{SET_FULL_NAMES[s.key]}</span>
                    <span className="set-sub">
                      {s.count} cases · {s.description}
                    </span>
                  </span>
                </div>
                <div className="set-actions">
                  <button className="set-drill" onClick={() => onRandomDrill(s.key)}>
                    Random drill ▸
                  </button>
                  <button className="set-choose" onClick={() => onChooseCase(s.key)}>
                    Choose a case…
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
