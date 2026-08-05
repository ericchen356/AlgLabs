/**
 * Trainer screen (CONTRACTS.md §12.3 random mode / §12.4 grind variant).
 *
 * Random: idle → recognition → execution → idle. The case is never named, and
 * neither is its PB (no header chip, no time in the stage caption) — an exact
 * best time would narrow down which case you are looking at. Cube stage:
 * hidden "?" during idle + recognition;
 * during execution a ghost (real CubeView) plays the CURRENT scramble's
 * solution, tween-scaled so the playback lasts the PB total. Stopping the
 * timer immediately fetches the next scramble and re-arms, so the user just
 * keeps going; the splits of the finished solve stay on screen until the next
 * solve starts.
 *
 * Grind: idle → armed → execution → idle for ONE case; header shows the case
 * name + preview openly; a single EXEC split; the cube stage shows the case
 * state while idle and the ghost (scaled to PB exec) during execution. The
 * scramble is fetched ONCE per case — the case never changes, so neither does
 * its setup — and stopping the timer re-arms for the next rep.
 *
 * Advance = Space (ignored while an input is focused) or tapping the big
 * timer panel; while the solve timer runs, ANY key stops it. Live timers tick
 * per animation frame, formatted (ms/1000).toFixed(2).
 */

import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import CubeView, { type CubeViewHandle } from '../CubeView'
import { applyMovesToFacelets, solvedFacelets } from '../cubeModel'
import { parseSequence } from '../notation'
import { fetchScramble } from './api'
import {
  fmtMs,
  initialMachine,
  isRunning,
  justFinished,
  liveSplits,
  pushSession,
  stepMachine,
  type SessionEntry,
  type TrainerInput,
  type TrainerMachine,
} from './machine'
import {
  applyGrindResult,
  applyRandomResult,
  loadRecords,
  saveLastSet,
  saveRecords,
  type RecordsState,
} from './records'
import { appendSolve, loadSolves, saveSolves, type SolvesState } from './solves'
import PreviewGrid from './PreviewGrid'
import type { TrainerProps, TrainerScramble } from './types'
import BootingNotice from '../backendStatus'
import '../Trainer.css'

/** Hint copy per phase — describes the hold/release mechanic (§12.3 / §12.4). */
const HINTS = {
  random: {
    idle: 'hold SPACE (or press the timer) to recognize, release to start solving',
    armed: '', // unreachable in random mode
    recognition: 'recognizing… release to start solving',
    execution: 'solving… hit any key the instant you finish',
  },
  grind: {
    idle: 'hold SPACE (or the timer), then release to start the timer',
    armed: 'release to start…',
    recognition: '', // unreachable in grind mode
    execution: 'solving… hit any key the instant you finish',
  },
} as const

/** Idle hint right after a solve — the drill has already re-armed itself. */
const FINISHED_HINTS = {
  random: 'logged ✓ · next scramble ready · hold SPACE to go again',
  grind: 'logged ✓ · hold SPACE for the next rep',
} as const

export default function Trainer({ set, mode, caseId, onBackToSets }: TrainerProps) {
  const [scr, setScr] = useState<TrainerScramble | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [machine, setMachine] = useState<TrainerMachine>(() => initialMachine(mode))
  const [now, setNow] = useState(0)
  const [records, setRecords] = useState<RecordsState>(() => loadRecords())
  const [solves, setSolves] = useState<SolvesState>(() => loadSolves())
  const [session, setSession] = useState<SessionEntry[]>([])
  const [lastWasPB, setLastWasPB] = useState(false)

  const cubeRef = useRef<CubeViewHandle | null>(null)
  /** Bumping this cancels any in-flight ghost playback loop. */
  const ghostRun = useRef(0)

  // Remember the last-trained set for the Records default tab (§12.5).
  useEffect(() => {
    saveLastSet(set)
  }, [set])

  const loadScramble = useCallback(async () => {
    setScr(null)
    setError(null)
    try {
      setScr(await fetchScramble(set, mode === 'grind' ? caseId : undefined))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [set, mode, caseId])

  // Full reset + first scramble whenever the drill target changes.
  useEffect(() => {
    setMachine(initialMachine(mode))
    setSession([])
    setLastWasPB(false)
    void loadScramble()
  }, [mode, loadScramble])

  const phase = machine.phase
  const running = isRunning(machine)

  // The current case's record; PB = total in random mode, exec in grind.
  const rec = scr ? records[set]?.[scr.case_id] : undefined
  const pbMs = mode === 'random' ? rec?.total : rec?.exec

  const scrambledFacelets = useMemo(
    () => (scr ? applyMovesToFacelets(solvedFacelets, parseSequence(scr.scramble)) : null),
    [scr],
  )
  const solutionMoves = useMemo(() => (scr ? parseSequence(scr.solution) : []), [scr])

  // ---- step: press (`down`) / release (`up`) drive the phase machine -----

  const step = useCallback(
    (input: TrainerInput) => {
      if (!scr) return // no scramble yet (loading / error)
      const ts = performance.now()
      const { state, event } = stepMachine(machine, input, ts)
      if (event === 'none') return
      setMachine(state)
      setNow(ts)
      if (event === 'finish') {
        ghostRun.current++ // stop the ghost
        const update =
          mode === 'random'
            ? applyRandomResult(records, set, scr.case_id, state.recogMs, state.execMs)
            : applyGrindResult(records, set, scr.case_id, state.execMs)
        setRecords(update.records)
        saveRecords(update.records)
        setLastWasPB(update.isPB)
        // Log the solve itself (§12.6). Random solves carry their recognition
        // split; grind reps have none, which is what marks them as grind.
        const history = appendSolve(solves, set, scr.case_id, {
          ...(mode === 'random' && { recog: state.recogMs }),
          exec: state.execMs,
          at: Date.now(),
        })
        setSolves(history)
        saveSolves(history)
        setSession((s) =>
          pushSession(s, {
            ms: mode === 'random' ? state.recogMs + state.execMs : state.execMs,
            isPB: update.isPB,
          }),
        )
        // The machine already re-armed itself to `idle`. Random mode needs a
        // new draw for the next solve; grind keeps the one case (and so its one
        // scramble) it was chosen to drill.
        if (mode === 'random') void loadScramble()
      }
    },
    [scr, machine, mode, records, solves, set, loadScramble],
  )

  // Latest `step` in a ref so the window listeners (registered once) never go
  // stale between renders.
  const stepRef = useRef(step)
  stepRef.current = step

  // The live phase for the key handler, which is registered once.
  const phaseRef = useRef(phase)
  phaseRef.current = phase

  // Space press/release drives the machine — ignored while an input is focused
  // (§12.3). Holding Space auto-repeats keydown; `e.repeat` filters that so a
  // hold is exactly one `down` and one `up`. While the solve timer runs, ANY
  // key stops it (stackmat convention: whichever hand lands first wins) — only
  // Space produces the `up` edge, so a non-Space stop leaves no stray release.
  useEffect(() => {
    const inField = (t: EventTarget | null): boolean => {
      const el = t as HTMLElement | null
      return (
        !!el &&
        (el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.tagName === 'SELECT' ||
          el.isContentEditable)
      )
    }
    const isSpace = (e: KeyboardEvent) => e.code === 'Space' || e.key === ' '
    /** Bare modifiers can't stop a solve — the palm resting on Shift shouldn't. */
    const isBareModifier = (e: KeyboardEvent) =>
      e.key === 'Shift' ||
      e.key === 'Control' ||
      e.key === 'Alt' ||
      e.key === 'Meta' ||
      e.key === 'CapsLock'
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || inField(e.target)) return
      if (!isSpace(e)) {
        // Any other key is a stop, and only a stop. Chords (⌘R, ⌘L, …) stay
        // browser shortcuts.
        const stops =
          phaseRef.current === 'execution' &&
          !isBareModifier(e) &&
          !e.metaKey &&
          !e.ctrlKey &&
          !e.altKey
        if (!stops) return
      }
      e.preventDefault()
      stepRef.current('down')
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (!isSpace(e) || inField(e.target)) return
      e.preventDefault()
      stepRef.current('up')
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])

  // Pointer press/release on the timer panel mirror Space. Track that the
  // gesture started on the panel and complete it on a window `pointerup`, so a
  // release that drifts off the button (or ends anywhere on screen) still fires.
  const pointerActive = useRef(false)
  const onPanelPointerDown = useCallback((e: ReactPointerEvent) => {
    e.preventDefault() // avoid the synthetic click / focus scroll
    pointerActive.current = true
    stepRef.current('down')
  }, [])
  useEffect(() => {
    const onPointerUp = () => {
      if (!pointerActive.current) return
      pointerActive.current = false
      stepRef.current('up')
    }
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
    return () => {
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
    }
  }, [])

  // rAF loop drives the live readouts while a timer runs.
  useEffect(() => {
    if (!running) return
    let raf = requestAnimationFrame(function tick() {
      setNow(performance.now())
      raf = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(raf)
  }, [running])

  // ---- cube stage --------------------------------------------------------

  const ghostAvailable = pbMs !== undefined && solutionMoves.length > 0
  const ghostActive = phase === 'execution' && ghostAvailable
  // The CubeView stays MOUNTED the whole time (mounting it mid-session would
  // let React StrictMode's simulated remount rebuild its internals to solved
  // right after an imperative setState) — visibility is pure CSS. Random mode
  // shows it only for the ghost; grind also shows the case state while idle
  // (§12.4).
  const showCube =
    mode === 'grind' ? scrambledFacelets !== null : ghostActive && scrambledFacelets !== null

  // Grind idle: show the case state so the user can check their setup.
  useEffect(() => {
    if (mode !== 'grind' || phase !== 'idle' || !scrambledFacelets) return
    cubeRef.current?.setState(scrambledFacelets)
  }, [mode, phase, scrambledFacelets])

  // Execution: play the CURRENT scramble's solution, per-move tweens scaled
  // so the whole playback lasts ≈ the PB (total in random, exec in grind).
  useEffect(() => {
    if (!ghostActive || !scrambledFacelets || pbMs === undefined) return
    let cancelled = false
    const run = ++ghostRun.current
    const cube = cubeRef.current
    if (!cube) return
    cube.setState(scrambledFacelets)
    const perMove = Math.max(1, pbMs / solutionMoves.length)
    void (async () => {
      for (const move of solutionMoves) {
        if (cancelled || ghostRun.current !== run) return
        const handle = cubeRef.current
        if (!handle) return
        try {
          await handle.playMove(move, perMove)
        } catch {
          return // unmounted or superseded mid-move
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [ghostActive, scrambledFacelets, solutionMoves, pbMs])

  // ---- derived display ----------------------------------------------------

  const splits = liveSplits(machine, now)
  // Idle-holding-the-last-result: splits stay frozen on screen, marks stay
  // ticked, and the newest session chip pops.
  const finished = justFinished(machine)
  const hint = finished ? FINISHED_HINTS[mode] : HINTS[mode][phase]
  const recogMark = phase === 'recognition' ? '●' : phase === 'execution' || finished ? '✓' : ''
  const execMark = phase === 'execution' ? '●' : finished ? '✓' : ''
  const bigMs = mode === 'random' ? splits.total : splits.exec
  const bigColor = mode === 'random' && phase === 'recognition' ? 'recog' : 'exec'

  // Random mode must not print the PB anywhere: the case is hidden, and its
  // exact best time would narrow down which case it is. Grind names the case
  // openly, so the number is free to show there.
  const caption =
    mode === 'random'
      ? 'your best solve plays here as a ghost · beat it'
      : phase === 'idle'
        ? 'the case, scrambled · check your setup'
        : ghostAvailable && pbMs !== undefined
          ? `plays your ${fmtMs(pbMs)}s solve · beat it`
          : 'set a PB and the ghost appears here'

  return (
    <div className="screen trainer">
      <div className="tr-head">
        <button className="back-link" onClick={onBackToSets}>
          ← sets
        </button>
        <span className="tr-chip">{mode === 'grind' ? 'grinding' : set.toUpperCase()}</span>
        {mode === 'grind' && scr ? (
          <span className={`tr-case revealed${lastWasPB && finished ? ' pop' : ''}`}>
            {scr.name}
            <PreviewGrid preview={scr.preview} className="tr-head-preview" />
          </span>
        ) : (
          <span className="tr-case hidden-case">case hidden · recognize it</span>
        )}
        <span className="tr-scramble">
          {error ? '' : scr ? scr.scramble : 'fetching scramble…'}
        </span>
        {mode === 'grind' && (
          <span className="tr-pb-chip">
            {pbMs !== undefined ? `PB ${fmtMs(pbMs)}` : 'no PB yet'}
          </span>
        )}
      </div>

      {error && (
        <div className="failure">
          {error}{' '}
          <button className="btn" onClick={() => void loadScramble()}>
            Retry
          </button>
        </div>
      )}

      <BootingNotice compact />

      <div className="tr-body">
        <div className="tr-stage-col">
          <div className="tr-stage">
            <CubeView ref={cubeRef} className={`tr-cube${showCube ? '' : ' off'}`} />
            {ghostActive && <span className="tr-ghost-badge">Ghost ▸ PB</span>}
            {!showCube && (
              <div className="tr-stage-hidden">
                <div className="tr-stage-q">{scr ? '?' : '…'}</div>
                {mode === 'random' && scr && (
                  <div className="tr-stage-sub">
                    cube hidden during
                    <br />
                    recognition
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="tr-stage-caption">{caption}</div>
        </div>

        <div className="tr-timer-col">
          <div className="tr-splits">
            {mode === 'random' && (
              <div className={`tr-split${phase === 'recognition' ? ' active recog' : ''}`}>
                <span>RECOG {recogMark}</span>
                <b>{fmtMs(splits.recog)}</b>
              </div>
            )}
            <div className={`tr-split${phase === 'execution' ? ' active exec' : ''}`}>
              <span>EXEC {execMark}</span>
              <b>{fmtMs(splits.exec)}</b>
            </div>
          </div>

          <button
            type="button"
            className={`tr-panel${machine.phase === 'armed' ? ' armed' : ''}`}
            onPointerDown={onPanelPointerDown}
          >
            <span className={`tr-total ${bigColor}${running ? ' running' : ''}`}>
              {fmtMs(bigMs)}
              <span className="tr-total-unit">s</span>
            </span>
            <span className="tr-panel-sub">
              {mode === 'random' ? 'recognition + execution' : 'execution only'}
            </span>
          </button>

          <div className="tr-hint">{hint}</div>

          <div className="tr-session">
            <span className="tr-session-label">session:</span>
            {session.map((a, i) => (
              <span
                key={session.length - i}
                className={`tr-session-chip${a.isPB ? ' pb' : ''}${i === 0 && finished ? ' pop' : ''}`}
              >
                {fmtMs(a.ms)}
              </span>
            ))}
            {session.length === 0 && <span className="tr-session-empty">no solves yet</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
