/**
 * Case picker (CONTRACTS.md §12.4 "Casepick"): back link "← sets", title
 * "{Set} — pick a case to grind", a group tab row (ink-filled when active),
 * then a responsive grid of case tiles — mini 2D preview, case name, and a
 * PB chip when a record exists. Tiles tilt ±1deg alternately; clicking one
 * starts grind mode. The whole set (ZBLL: 493 cases) is fetched ONCE and
 * filtered client-side; tiles are memoized so tab switches stay fast.
 */

import { memo, useEffect, useMemo, useState } from 'react'
import { fetchCases, fetchSets } from './api'
import { fmtMs } from './machine'
import { loadRecords } from './records'
import PreviewGrid from './PreviewGrid'
import type { CasePickProps, TrainerCase } from './types'
import '../Trainer.css'

interface CaseTileProps {
  c: TrainerCase
  /** Best time to show on the PB chip (total when known, else exec), or undefined. */
  pbMs: number | undefined
  tilt: 'tilt-a' | 'tilt-b'
  onPick: (caseId: string) => void
}

const CaseTile = memo(function CaseTile({ c, pbMs, tilt, onPick }: CaseTileProps) {
  return (
    <button className={`case-tile ${tilt}`} onClick={() => onPick(c.id)}>
      <PreviewGrid preview={c.preview} />
      <span className="case-tile-name">{c.name}</span>
      {pbMs !== undefined && <span className="case-pb">PB {fmtMs(pbMs)}</span>}
    </button>
  )
})

export default function CasePick({ set, onBack, onPickCase }: CasePickProps) {
  const [cases, setCases] = useState<TrainerCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [group, setGroup] = useState<string | null>(null)
  // Group key -> human label (§11.1: e.g. vls "eo3" -> "UF+UB flipped"),
  // served by /api/trainer/sets. Falls back to the raw key while loading.
  const [groupNames, setGroupNames] = useState<Record<string, string>>({})

  const records = useMemo(() => loadRecords()[set] ?? {}, [set])

  useEffect(() => {
    let alive = true
    setCases(null)
    setGroup(null)
    setError(null)
    fetchCases(set).then(
      (cs) => {
        if (!alive) return
        setCases(cs)
        setGroup(cs[0]?.group ?? null)
      },
      (err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      },
    )
    fetchSets().then(
      (sets) => {
        if (!alive) return
        const entry = sets.find((s) => s.key === set)
        if (entry) {
          setGroupNames(Object.fromEntries(entry.groups.map((g) => [g.key, g.name])))
        }
      },
      () => undefined, // tabs degrade to raw keys; fetchCases already surfaces errors
    )
    return () => {
      alive = false
    }
  }, [set])

  /** Group keys in server (canonical-signature) order. */
  const groups = useMemo(() => (cases ? [...new Set(cases.map((c) => c.group))] : []), [cases])

  const visible = useMemo(() => {
    if (!cases) return []
    if (groups.length <= 1 || group === null) return cases
    return cases.filter((c) => c.group === group)
  }, [cases, groups, group])

  return (
    <div className="screen">
      <div className="screen-title-row">
        <button className="back-link" onClick={onBack}>
          ← sets
        </button>
        <h2 className="screen-title big">{set.toUpperCase()} — pick a case to grind</h2>
      </div>

      {error && <div className="failure">{error}</div>}
      {!error && !cases && <div className="tr-loading">loading cases…</div>}

      {cases && groups.length > 1 && (
        <div className="group-tabs">
          {groups.map((g) => (
            <button
              key={g}
              className={`group-tab${g === group ? ' active' : ''}`}
              onClick={() => setGroup(g)}
            >
              {groupNames[g] ?? g}
            </button>
          ))}
        </div>
      )}

      {cases && (
        <div className="case-grid">
          {visible.map((c, i) => {
            const rec = records[c.id]
            return (
              <CaseTile
                key={c.id}
                c={c}
                pbMs={rec ? rec.total ?? rec.exec : undefined}
                tilt={i % 2 === 0 ? 'tilt-a' : 'tilt-b'}
                onPick={onPickCase}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
