/**
 * Records screen (CONTRACTS.md §12.5 + handoff README §8): five set tabs
 * (default = last-trained set), a 5-column grid (Case · Recog · Exec · Best ·
 * n) over every case of the set, "—" for missing values (untrained cases and
 * the recog/total of grind-only cases), the fastest total in the set
 * highlighted green. ZBLL's 493 rows are grouped by OCLL family with
 * collapsible sections so the table stays usable.
 */

import { useEffect, useMemo, useState } from 'react'
import { fetchCases } from './api'
import { fmtMs } from './machine'
import { loadLastSet, loadRecords, type CaseRecord } from './records'
import { SET_KEYS, type RecordsProps, type SetKey, type TrainerCase } from './types'
import '../Trainer.css'

interface RowProps {
  c: TrainerCase
  rec: CaseRecord | undefined
  isBest: boolean
}

function RecordRow({ c, rec, isBest }: RowProps) {
  return (
    <div className="rec-row">
      <span className="rec-case">
        <span className="rec-dot" aria-hidden />
        {c.name}
      </span>
      <span className="rec-num">{rec?.recog !== undefined ? fmtMs(rec.recog) : '—'}</span>
      <span className="rec-num">{rec ? fmtMs(rec.exec) : '—'}</span>
      <span className={`rec-num rec-best${isBest ? ' top' : ''}`}>
        {rec?.total !== undefined ? fmtMs(rec.total) : '—'}
      </span>
      <span className="rec-num">{rec?.n ?? 0}</span>
    </div>
  )
}

export default function Records({ onBack }: RecordsProps) {
  const [tab, setTab] = useState<SetKey>(() => loadLastSet() ?? 'oll')
  const [cases, setCases] = useState<TrainerCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  /** Open ZBLL family sections (all collapsed initially). */
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())

  const records = useMemo(() => loadRecords(), [])
  const setRecords = records[tab] ?? {}

  useEffect(() => {
    let alive = true
    setCases(null)
    setError(null)
    setOpen(new Set())
    fetchCases(tab).then(
      (cs) => {
        if (alive) setCases(cs)
      },
      (err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      },
    )
    return () => {
      alive = false
    }
  }, [tab])

  // Fastest total in the set — its row's Best cell is highlighted green.
  let bestTotal = Infinity
  for (const rec of Object.values(setRecords)) {
    if (rec.total !== undefined && rec.total < bestTotal) bestTotal = rec.total
  }

  /** ZBLL: cases grouped by OCLL family, in server order (§12.5). */
  const families = useMemo(() => {
    if (!cases || tab !== 'zbll') return null
    const byGroup = new Map<string, TrainerCase[]>()
    for (const c of cases) {
      const list = byGroup.get(c.group)
      if (list) list.push(c)
      else byGroup.set(c.group, [c])
    }
    return [...byGroup.entries()]
  }, [cases, tab])

  const isBest = (rec: CaseRecord | undefined) =>
    rec?.total !== undefined && rec.total === bestTotal

  const trainedCount = (list: TrainerCase[]) =>
    list.reduce((n, c) => n + (setRecords[c.id] ? 1 : 0), 0)

  return (
    <div className="screen records">
      <div className="rec-head">
        <button className="back-link" onClick={onBack}>
          ← home
        </button>
        <h2 className="screen-title big">Personal bests</h2>
        <div className="rec-tabs">
          {SET_KEYS.map((key) => (
            <button
              key={key}
              className={`rec-tab${key === tab ? ' active' : ''}`}
              onClick={() => setTab(key)}
            >
              {key.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="failure">{error}</div>}
      {!error && !cases && <div className="tr-loading">loading cases…</div>}

      {cases && (
        <div className="rec-card">
          <div className="rec-row rec-header-row">
            <span>Case</span>
            <span className="rec-num">Recog</span>
            <span className="rec-num">Exec</span>
            <span className="rec-num">Best</span>
            <span className="rec-num">n</span>
          </div>

          {families
            ? families.map(([family, list]) => {
                const opened = open.has(family)
                return (
                  <div key={family} className="rec-family">
                    <button
                      className="rec-family-head"
                      onClick={() =>
                        setOpen((prev) => {
                          const next = new Set(prev)
                          if (opened) next.delete(family)
                          else next.add(family)
                          return next
                        })
                      }
                    >
                      <span className="rec-family-arrow">{opened ? '▾' : '▸'}</span>
                      <span className="rec-family-name">{family}</span>
                      <span className="rec-family-count">
                        {list.length} cases · {trainedCount(list)} trained
                      </span>
                    </button>
                    {opened &&
                      list.map((c) => (
                        <RecordRow
                          key={c.id}
                          c={c}
                          rec={setRecords[c.id]}
                          isBest={isBest(setRecords[c.id])}
                        />
                      ))}
                  </div>
                )
              })
            : cases.map((c) => (
                <RecordRow
                  key={c.id}
                  c={c}
                  rec={setRecords[c.id]}
                  isBest={isBest(setRecords[c.id])}
                />
              ))}
        </div>
      )}

      <p className="rec-footnote">
        Times persist in this browser. Train a case to set its first record; a green best means
        it&apos;s your fastest in the set.
      </p>
    </div>
  )
}
