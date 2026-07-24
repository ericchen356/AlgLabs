/**
 * AlgLabs "Paper Toy" app shell (CONTRACTS.md §9.1 + §12.2): persistent
 * header, Home mode-select, solve landing (scan / manual / demo scramble all
 * converging on POST /api/solve -> Walkthrough), and the trainer views
 * (setpick / casepick / trainer / records) rendered from src/trainer.
 */

import { useEffect, useMemo, useState } from 'react'
import type { FaceLetter, SolveResponse, ValidationError } from './types'
import { COLOR_HEX, FACE_ORDER, solvedFacelets } from './cubeModel'
import * as api from './api'
import './App.css'
import Scanner from './Scanner'
import Walkthrough from './Walkthrough'
import { CasePick, Records, SetPicker, Trainer } from './trainer'
import type { SetKey, TrainerMode } from './trainer'

type View =
  | { kind: 'home' }
  | { kind: 'solve' }
  | { kind: 'scan' }
  | { kind: 'manual' }
  | { kind: 'walk'; solve: SolveResponse; facelets: string }
  | { kind: 'setpick' }
  | { kind: 'casepick'; set: SetKey }
  | { kind: 'trainer'; set: SetKey; mode: TrainerMode; caseId?: string }
  | { kind: 'records' }

const CENTER_INDICES: readonly number[] = [4, 13, 22, 31, 40, 49]

/** Grid-block (row, col) of each face in the unfolded net, in 3-cell units. */
const NET_BLOCK: Record<FaceLetter, { row: number; col: number }> = {
  U: { row: 0, col: 1 },
  L: { row: 1, col: 0 },
  F: { row: 1, col: 1 },
  R: { row: 1, col: 2 },
  B: { row: 1, col: 3 },
  D: { row: 2, col: 1 },
}

const FACE_NAMES: Record<FaceLetter, string> = {
  U: 'Up (yellow)',
  R: 'Right (orange)',
  F: 'Front (green)',
  D: 'Down (white)',
  L: 'Left (red)',
  B: 'Back (blue)',
}

/**
 * §5-style local checks (length / charset / counts / centers) for a facelet
 * string. Returns human-readable problems (empty = passes the local checks;
 * the backend still runs the full validation).
 */
function localChecks(s: string): string[] {
  const problems: string[] = []
  if (s.length !== 54) {
    problems.push(`Must be exactly 54 characters (got ${s.length}).`)
    return problems
  }
  if (!/^[URFDLB]+$/.test(s)) {
    problems.push('Only the letters U, R, F, D, L, B are allowed.')
    return problems
  }
  const counts = new Map<string, number>()
  for (const ch of s) counts.set(ch, (counts.get(ch) ?? 0) + 1)
  for (const face of FACE_ORDER) {
    const n = counts.get(face) ?? 0
    if (n !== 9) problems.push(`Letter ${face} appears ${n} times (needs exactly 9).`)
  }
  for (let i = 0; i < 6; i++) {
    if (s[CENTER_INDICES[i]] !== FACE_ORDER[i]) {
      problems.push(
        `Center stickers are fixed: the ${FACE_ORDER[i]} center must be ${FACE_ORDER[i]}.`,
      )
      break
    }
  }
  return problems
}

function ValidationErrors({ errors }: { errors: ValidationError[] }) {
  return (
    <div className="validation-errors">
      {errors.map((e, i) => (
        <div key={i} className="validation-error">
          <span className="error-code">{e.code}</span>
          <span>{e.message}</span>
          {e.suspect_faces.length > 0 && (
            <span className="suspect-faces">
              Check face{e.suspect_faces.length > 1 ? 's' : ''}: {e.suspect_faces.join(', ')}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

interface ManualEntryProps {
  onSolved: (facelets: string, solve: SolveResponse) => void
  onBack: () => void
}

function ManualEntry({ onSolved, onBack }: ManualEntryProps) {
  const [cells, setCells] = useState<FaceLetter[]>(() => [...solvedFacelets] as FaceLetter[])
  const [brush, setBrush] = useState<FaceLetter>('U')
  const [pasted, setPasted] = useState('')
  const [busy, setBusy] = useState(false)
  const [apiErrors, setApiErrors] = useState<ValidationError[] | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const facelets = cells.join('')
  const netProblems = useMemo(() => localChecks(facelets), [facelets])
  const pasteProblems = useMemo(
    () => (pasted.trim().length === 0 ? null : localChecks(pasted.trim().toUpperCase())),
    [pasted],
  )

  const paintCell = (index: number) => {
    if (CENTER_INDICES.includes(index)) return
    setApiErrors(null)
    setCells((prev) => {
      const next = [...prev]
      next[index] = brush
      return next
    })
  }

  const applyPasted = () => {
    const s = pasted.trim().toUpperCase()
    if (localChecks(s).length === 0) {
      setApiErrors(null)
      setCells([...s] as FaceLetter[])
    }
  }

  const submit = async () => {
    setBusy(true)
    setApiErrors(null)
    setFailure(null)
    try {
      const solve = await api.solve(facelets)
      onSolved(facelets, solve)
    } catch (err) {
      if (err instanceof api.ApiValidationError) {
        setApiErrors(err.errors)
      } else if (err instanceof api.ApiUnavailableError) {
        setFailure(
          err.message === 'Backend unreachable'
            ? 'Backend unreachable — start the API server, or try the demo scramble (it works offline in mock mode).'
            : err.message,
        )
      } else {
        setFailure(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setBusy(false)
    }
  }

  // 54 net cells, positioned on a 12x9 CSS grid.
  const netCells = []
  for (let f = 0; f < 6; f++) {
    const face = FACE_ORDER[f]
    const block = NET_BLOCK[face]
    for (let k = 0; k < 9; k++) {
      const index = f * 9 + k
      const row = block.row * 3 + Math.floor(k / 3) + 1
      const col = block.col * 3 + (k % 3) + 1
      const isCenter = k === 4
      netCells.push(
        <button
          key={index}
          className={`net-cell${isCenter ? ' center' : ''}`}
          style={{ gridRow: row, gridColumn: col, background: COLOR_HEX[cells[index]] }}
          title={isCenter ? `${face} center (fixed)` : `${face}${k + 1}`}
          disabled={isCenter}
          onClick={() => paintCell(index)}
        />,
      )
    }
  }

  return (
    <div className="screen manual-entry">
      <div className="screen-title-row">
        <button className="back-link" onClick={onBack}>
          ← back
        </button>
        <h2 className="screen-title">Enter colors by hand</h2>
      </div>
      <p className="hint">Pick a color, then click stickers on the net. Centers are fixed.</p>

      <div className="palette">
        {FACE_ORDER.map((face) => (
          <button
            key={face}
            className={`palette-swatch${brush === face ? ' selected' : ''}`}
            style={{ background: COLOR_HEX[face] }}
            title={FACE_NAMES[face]}
            onClick={() => setBrush(face)}
          />
        ))}
      </div>

      <div className="manual-body">
        <div className="net-grid">{netCells}</div>

        <div className="manual-side">
          <div className="paste-row">
            <input
              className="paste-input"
              placeholder="paste a 54-char facelet string…"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              spellCheck={false}
            />
            <button
              className="btn square"
              onClick={applyPasted}
              disabled={pasteProblems === null || pasteProblems.length > 0}
            >
              Apply
            </button>
          </div>
          {pasteProblems && pasteProblems.length > 0 && (
            <div className="local-problems">
              {pasteProblems.map((p, i) => (
                <div key={i}>{p}</div>
              ))}
            </div>
          )}
          {pasteProblems && pasteProblems.length === 0 && (
            <div className="local-ok">Passes local checks — apply it to the net.</div>
          )}

          {netProblems.length > 0 && (
            <div className="local-problems">
              {netProblems.map((p, i) => (
                <div key={i}>{p}</div>
              ))}
            </div>
          )}

          {apiErrors && <ValidationErrors errors={apiErrors} />}
          {failure && <div className="failure">{failure}</div>}

          <button
            className="btn-ink"
            onClick={() => void submit()}
            disabled={busy || netProblems.length > 0}
          >
            {busy ? 'Solving…' : 'Solve it ▸'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>({ kind: 'home' })
  const [demoBusy, setDemoBusy] = useState(false)
  const [demoError, setDemoError] = useState<string | null>(null)
  const [mockNotice, setMockNotice] = useState(api.isMockMode())

  // Wake an idled API instance while the user is still on the home screen.
  useEffect(() => api.wake(), [])

  const runDemo = async () => {
    setDemoBusy(true)
    setDemoError(null)
    try {
      let scr
      try {
        scr = await api.scramble()
      } catch (err) {
        if (!(err instanceof api.ApiUnavailableError)) throw err
        // Backend down: fall back to mock mode so the demo still works.
        api.enableMockMode()
        setMockNotice(true)
        scr = await api.scramble()
      }
      const solve = await api.solve(scr.facelets)
      setView({ kind: 'walk', solve, facelets: scr.facelets })
    } catch (err) {
      setDemoError(err instanceof Error ? err.message : String(err))
    } finally {
      setDemoBusy(false)
    }
  }

  const goHome = () => setView({ kind: 'home' })
  const goSolve = () => setView({ kind: 'solve' })
  const goSetpick = () => setView({ kind: 'setpick' })
  const onSolved = (facelets: string, solve: SolveResponse) =>
    setView({ kind: 'walk', solve, facelets })

  return (
    <div className="app">
      <header className="app-header">
        <button className="logo" onClick={goHome} title="Home">
          <span className="logo-mark" aria-hidden>
            <span />
            <span />
            <span />
            <span />
          </span>
          <span className="wordmark">
            CFOP <span className="accent">trainer</span>
          </span>
        </button>
        {mockNotice && <span className="mock-badge">mock mode — backend offline</span>}
        <nav className="header-nav">
          <button className="nav-pill" onClick={goSetpick}>
            Train
          </button>
          <button className="nav-pill" onClick={() => setView({ kind: 'records' })}>
            Records
          </button>
        </nav>
      </header>

      <main className="app-main">
        {view.kind === 'home' && (
          <div className="home">
            <h1 className="hero">Read a cube, or race your own hands.</h1>
            <div className="mode-grid">
              <button className="mode-card tilt-l" onClick={goSolve}>
                <span className="icon-tile lg lens-tile" aria-hidden>
                  <span className="lens-dot" />
                </span>
                <span className="mode-title">Solve a cube</span>
                <span className="mode-desc">
                  Scan with your camera, paint the net, or roll a demo — then watch the animated
                  CFOP walkthrough.
                </span>
                <span className="pill-cta">Enter ▸</span>
              </button>
              <button className="mode-card train-card tilt-r" onClick={goSetpick}>
                <span className="icon-tile lg timer-tile" aria-hidden>
                  0.00
                </span>
                <span className="mode-title">Train algorithms</span>
                <span className="mode-desc">
                  Drill OLL / PLL / COLL / ZBLL / VLS with split recognition &amp; execution
                  timing — and a ghost cube of your PB to race.
                </span>
                <span className="pill-cta">Start ▸</span>
              </button>
            </div>
          </div>
        )}

        {view.kind === 'solve' && (
          <div className="screen">
            <button className="back-link" onClick={goHome}>
              ← home
            </button>
            <h2 className="screen-title hero">How do you want to read the cube?</h2>
            <div className="solve-grid">
              <button className="entry-card" onClick={() => setView({ kind: 'scan' })}>
                <span className="icon-tile lens-tile" aria-hidden>
                  <span className="lens-dot" />
                </span>
                <span className="entry-title">Scan with camera</span>
                <span className="entry-desc">
                  Point your webcam at each face — AlgLabs reads the colors.
                </span>
              </button>
              <button className="entry-card" onClick={() => setView({ kind: 'manual' })}>
                <span className="icon-tile palette-tile" aria-hidden>
                  <span />
                  <span />
                  <span />
                </span>
                <span className="entry-title">Enter colors by hand</span>
                <span className="entry-desc">
                  Paint the stickers on an unfolded net, or paste a facelet string.
                </span>
              </button>
              <button
                className="entry-card demo"
                onClick={() => void runDemo()}
                disabled={demoBusy}
              >
                <span className="icon-tile dice-tile" aria-hidden>
                  <span />
                  <span />
                  <span />
                  <span />
                </span>
                <span className="entry-title">
                  {demoBusy ? 'Scrambling…' : 'Demo scramble'}
                </span>
                <span className="entry-desc">
                  Roll a random scramble and jump straight to the walkthrough.
                </span>
              </button>
            </div>
            {demoError && <div className="failure landing-error">{demoError}</div>}
          </div>
        )}

        {view.kind === 'scan' && (
          <div className="screen">
            <Scanner
              onSolved={onSolved}
              onManualEntry={() => setView({ kind: 'manual' })}
              onBack={goSolve}
            />
          </div>
        )}

        {view.kind === 'manual' && <ManualEntry onSolved={onSolved} onBack={goSolve} />}

        {view.kind === 'walk' && (
          <div className="walkthrough-main">
            <Walkthrough solve={view.solve} initialFacelets={view.facelets} onExit={goHome} />
          </div>
        )}

        {view.kind === 'setpick' && (
          <SetPicker
            onBack={goHome}
            onRandomDrill={(set) => setView({ kind: 'trainer', set, mode: 'random' })}
            onChooseCase={(set) => setView({ kind: 'casepick', set })}
          />
        )}

        {view.kind === 'casepick' && (
          <CasePick
            set={view.set}
            onBack={goSetpick}
            onPickCase={(caseId) =>
              setView({ kind: 'trainer', set: view.set, mode: 'grind', caseId })
            }
          />
        )}

        {view.kind === 'trainer' && (
          <Trainer
            set={view.set}
            mode={view.mode}
            caseId={view.caseId}
            onBackToSets={goSetpick}
          />
        )}

        {view.kind === 'records' && <Records onBack={goHome} />}
      </main>
    </div>
  )
}
