/**
 * Records screen (CONTRACTS.md §12.5 bests + §12.6 history + handoff README
 * §8): five set tabs (default = last-trained set), a 6-column grid (Case ·
 * Recog · Exec · Best · Avg · n) over every case of the set, "—" for missing
 * values (untrained cases and the recog/total of grind-only cases), the fastest
 * total in the set highlighted green. ZBLL's 493 rows are grouped by OCLL
 * family with collapsible sections so the table stays usable.
 *
 * Any case with logged solves expands to its full history: a stat strip, a
 * sparkline of execution over time, and every individual solve newest first.
 * Cases trained before history logging existed still show their bests, with a
 * note in place of the (absent) solve list.
 */

import { useEffect, useMemo, useState } from 'react'
import { fetchCases } from './api'
import { fmtMs } from './machine'
import { loadLastSet, loadRecords, type CaseRecord } from './records'
import { caseStats, loadSolves, solveMs, type CaseStats, type Solve } from './solves'
import { SET_KEYS, type RecordsProps, type SetKey, type TrainerCase } from './types'
import '../Trainer.css'

/**
 * Execution over time, oldest → newest. Flat when every solve is identical.
 *
 * The viewBox is stretched to the container (`preserveAspectRatio="none"`), so
 * every mark has to be shape-independent of that scaling: strokes opt out via
 * `vector-effect`, and the fastest solve is flagged with a full-height vertical
 * tick rather than a dot, which non-uniform scaling would squash into an oval.
 */
function Sparkline({ solves }: { solves: readonly Solve[] }) {
  const execs = solves.map((s) => s.exec)
  const lo = Math.min(...execs)
  const hi = Math.max(...execs)
  const span = hi - lo || 1
  // Inset horizontally so the fastest-solve tick stays clear of the frame when
  // the PB is the first or the last solve, which is the common case.
  const x = (i: number) => 2 + (i / (execs.length - 1)) * 96
  // Inverted: the FASTEST time sits at the top, so an improving trend rises.
  const y = (ms: number) => 2 + ((ms - lo) / span) * 20
  const points = execs.map((ms, i) => `${x(i).toFixed(2)},${y(ms).toFixed(2)}`).join(' ')
  const bestX = x(execs.indexOf(lo))
  return (
    <svg
      className="rec-spark"
      viewBox="0 0 100 24"
      preserveAspectRatio="none"
      role="img"
      aria-label={`execution trend over ${execs.length} solves, fastest ${fmtMs(lo)}s`}
    >
      <path
        className="rec-spark-area"
        d={`M${x(0)},24 ${points} L${x(execs.length - 1)},24 Z`}
      />
      <line
        className="rec-spark-best"
        x1={bestX}
        y1="0"
        x2={bestX}
        y2="24"
        vectorEffect="non-scaling-stroke"
      />
      <polyline className="rec-spark-line" points={points} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'pb' }) {
  return (
    <div className={`rec-stat${tone ? ` ${tone}` : ''}`}>
      <span className="rec-stat-label">{label}</span>
      <b className="rec-stat-value">{value}</b>
    </div>
  )
}

/** The expanded history panel for one case. */
function CaseHistory({ solves, stats }: { solves: readonly Solve[]; stats: CaseStats }) {
  const bestExecAt = solves.reduce((b, s, i) => (s.exec < solves[b].exec ? i : b), 0)
  return (
    <div className="rec-detail">
      <div className="rec-stats">
        <Stat label="logged" value={String(stats.n)} />
        <Stat label="avg exec" value={`${fmtMs(stats.avgExec)}s`} />
        <Stat label="best exec" value={`${fmtMs(stats.bestExec)}s`} tone="pb" />
        {stats.avgRecog !== undefined && (
          <Stat label="avg recog" value={`${fmtMs(stats.avgRecog)}s`} />
        )}
        {stats.avgTotal !== undefined && (
          <Stat label="avg total" value={`${fmtMs(stats.avgTotal)}s`} />
        )}
        {stats.bestTotal !== undefined && (
          <Stat label="best total" value={`${fmtMs(stats.bestTotal)}s`} tone="pb" />
        )}
      </div>

      {solves.length > 2 && (
        <figure className="rec-spark-wrap">
          <Sparkline solves={solves} />
          <figcaption className="rec-spark-cap">
            <span>execution, oldest → newest (up is faster)</span>
            <span className="rec-spark-key">fastest</span>
          </figcaption>
        </figure>
      )}

      <ol className="rec-solves">
        {solves
          .map((s, i) => ({ s, i }))
          .reverse()
          .map(({ s, i }) => (
            <li key={`${s.at}-${i}`} className={`rec-solve${i === bestExecAt ? ' best' : ''}`}>
              <span className="rec-solve-i">#{i + 1}</span>
              <span className="rec-solve-ms">{fmtMs(solveMs(s))}</span>
              <span className="rec-solve-meta">
                {s.recog === undefined
                  ? 'grind · exec only'
                  : `recog ${fmtMs(s.recog)} + exec ${fmtMs(s.exec)}`}
              </span>
              <span className="rec-solve-at">{new Date(s.at).toLocaleDateString()}</span>
            </li>
          ))}
      </ol>
    </div>
  )
}

interface RowProps {
  c: TrainerCase
  rec: CaseRecord | undefined
  solves: readonly Solve[]
  isBest: boolean
  open: boolean
  onToggle: () => void
}

function RecordRow({ c, rec, solves, isBest, open, onToggle }: RowProps) {
  const stats = useMemo(() => caseStats(solves), [solves])
  const expandable = rec !== undefined
  return (
    <>
      <button
        type="button"
        className={`rec-row rec-row-btn${open ? ' open' : ''}`}
        onClick={onToggle}
        disabled={!expandable}
        aria-expanded={expandable ? open : undefined}
      >
        <span className="rec-case">
          <span className={`rec-arrow${expandable ? '' : ' none'}`} aria-hidden>
            {expandable ? (open ? '▾' : '▸') : ''}
          </span>
          <span className="rec-dot" aria-hidden />
          {c.name}
        </span>
        <span className="rec-num">{rec?.recog !== undefined ? fmtMs(rec.recog) : '-'}</span>
        <span className="rec-num">{rec ? fmtMs(rec.exec) : '-'}</span>
        <span className={`rec-num rec-best${isBest ? ' top' : ''}`}>
          {rec?.total !== undefined ? fmtMs(rec.total) : '-'}
        </span>
        <span className="rec-num">{stats ? fmtMs(stats.avgExec) : '-'}</span>
        <span className="rec-num">{rec?.n ?? 0}</span>
      </button>
      {open &&
        (stats ? (
          <CaseHistory solves={solves} stats={stats} />
        ) : (
          <div className="rec-detail">
            <p className="rec-empty">
              No individual times logged for this case. Its bests were set before solve history
              existed; the next solve starts the log.
            </p>
          </div>
        ))}
    </>
  )
}

export default function Records({ onBack }: RecordsProps) {
  const [tab, setTab] = useState<SetKey>(() => loadLastSet() ?? 'oll')
  const [cases, setCases] = useState<TrainerCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  /** Open ZBLL family sections (all collapsed initially). */
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())
  /** Expanded case rows, by case id. */
  const [openCases, setOpenCases] = useState<ReadonlySet<string>>(new Set())

  const records = useMemo(() => loadRecords(), [])
  const solves = useMemo(() => loadSolves(), [])
  const setRecords = records[tab] ?? {}
  const setSolves = solves[tab] ?? {}

  useEffect(() => {
    let alive = true
    setCases(null)
    setError(null)
    setOpen(new Set())
    setOpenCases(new Set())
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

  const toggleCase = (id: string) =>
    setOpenCases((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const row = (c: TrainerCase) => (
    <RecordRow
      key={c.id}
      c={c}
      rec={setRecords[c.id]}
      solves={setSolves[c.id] ?? []}
      isBest={isBest(setRecords[c.id])}
      open={openCases.has(c.id)}
      onToggle={() => toggleCase(c.id)}
    />
  )

  /** Every solve logged for the current set, for the header summary. */
  const setTotals = useMemo(() => {
    const all = Object.values(setSolves).flat()
    return { solves: all.length, cases: Object.keys(setSolves).length }
  }, [setSolves])

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

      <p className="rec-summary">
        {setTotals.solves > 0
          ? `${setTotals.solves} solve${setTotals.solves === 1 ? '' : 's'} logged across ${setTotals.cases} case${setTotals.cases === 1 ? '' : 's'} · open a row for its times`
          : 'no solves logged in this set yet'}
      </p>

      {error && <div className="failure">{error}</div>}
      {!error && !cases && <div className="tr-loading">loading cases…</div>}

      {cases && (
        <div className="rec-card">
          <div className="rec-row rec-header-row">
            <span>Case</span>
            <span className="rec-num">Recog</span>
            <span className="rec-num">Exec</span>
            <span className="rec-num">Best</span>
            <span className="rec-num">Avg</span>
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
                    {opened && list.map(row)}
                  </div>
                )
              })
            : cases.map(row)}
        </div>
      )}

      <p className="rec-footnote">
        Times persist in this browser. Train a case to set its first record; a green best means
        it&apos;s your fastest in the set. Avg is mean execution over every logged solve, the one
        split both modes time.
      </p>
    </div>
  )
}
