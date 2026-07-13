/**
 * Walkthrough — stage/step UI + playback controls over a SolveResponse (§9).
 *
 * Flattens stages -> steps -> moves. Forward/backward single moves animate;
 * any jump (step navigation, clicking a step) instantly rebuilds the cube
 * from the initial facelets plus the move prefix — never by replaying floats.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { SolveResponse, Stage, Step } from './types'
import { invertMove, parseMove } from './notation'
import { applyMovesToFacelets } from './cubeModel'
import CubeView, { type CubeViewHandle } from './CubeView'
import './Walkthrough.css'

interface WalkthroughProps {
  solve: SolveResponse
  /** The scanned/entered facelet string the solve starts from. */
  initialFacelets: string
  onExit?: () => void
}

interface StepInfo {
  stage: Stage
  step: Step
  /** Flat-move index of this step's first move. */
  start: number
  /** Flat-move index one past this step's last move. */
  end: number
}

const BASE_MOVE_MS = 420
const SPEEDS_MIN = 0.25
const SPEEDS_MAX = 3

function flatten(solve: SolveResponse): { steps: StepInfo[]; moves: string[] } {
  const steps: StepInfo[] = []
  const moves: string[] = []
  for (const stage of solve.stages) {
    for (const step of stage.steps) {
      const start = moves.length
      moves.push(...step.moves)
      steps.push({ stage, step, start, end: moves.length })
    }
  }
  return { steps, moves }
}

export default function Walkthrough({ solve, initialFacelets, onExit }: WalkthroughProps) {
  const cubeRef = useRef<CubeViewHandle | null>(null)
  const { steps, moves } = useMemo(() => flatten(solve), [solve])
  const total = moves.length

  /** Number of moves currently applied to the cube (0..total). */
  const [pos, setPos] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const speedRef = useRef(speed)
  speedRef.current = speed
  const busyRef = useRef(false)
  /**
   * Bumped by every instant jump to invalidate the in-flight animated move:
   * during playback an animation is almost always in flight, so navigation
   * must interrupt it rather than be dropped. A stale stepForward/stepBack
   * continuation sees a different epoch and discards its setPos/busy release.
   */
  const epochRef = useRef(0)

  // Current step = the one containing the NEXT move to play (or the last one
  // once every move is applied). Zero-move (skipped) steps never own a move.
  const currentStepIndex = useMemo(() => {
    if (steps.length === 0) return -1
    const p = Math.min(pos, Math.max(0, total - 1))
    for (let i = 0; i < steps.length; i++) {
      if (steps[i].start <= p && p < steps[i].end) return i
    }
    return steps.length - 1
  }, [steps, pos, total])

  const current = currentStepIndex >= 0 ? steps[currentStepIndex] : null

  // Initial state.
  useEffect(() => {
    epochRef.current++
    busyRef.current = false
    cubeRef.current?.setState(initialFacelets)
    setPos(0)
    setPlaying(false)
  }, [initialFacelets, solve])

  // Highlights follow the current step.
  useEffect(() => {
    cubeRef.current?.setHighlights(current?.step.highlight ?? [])
  }, [current])

  const jumpTo = useCallback(
    (k: number) => {
      const clamped = Math.max(0, Math.min(total, k))
      // Interrupt any in-flight move: setState snap-completes the animation
      // inside CubeView, and the epoch bump makes its continuation a no-op.
      epochRef.current++
      busyRef.current = false
      setPlaying(false)
      cubeRef.current?.setState(
        applyMovesToFacelets(initialFacelets, moves.slice(0, clamped)),
      )
      setPos(clamped)
    },
    [initialFacelets, moves, total],
  )

  const stepForward = useCallback(async () => {
    if (busyRef.current || pos >= total) return
    busyRef.current = true
    const epoch = epochRef.current
    try {
      await cubeRef.current?.playMove(moves[pos], BASE_MOVE_MS / speedRef.current)
      if (epoch === epochRef.current) setPos(pos + 1)
    } catch {
      // playMove rejected (unmounted / already animating): ignore
    } finally {
      if (epoch === epochRef.current) busyRef.current = false
    }
  }, [pos, total, moves])

  const stepBack = useCallback(async () => {
    // Pause first, even mid-animation — otherwise clicks during playback
    // (when an animation is almost always in flight) would do nothing.
    setPlaying(false)
    if (busyRef.current || pos <= 0) return
    busyRef.current = true
    const epoch = epochRef.current
    try {
      const inverse = invertMove(parseMove(moves[pos - 1]))
      await cubeRef.current?.playMove(inverse, (BASE_MOVE_MS * 0.7) / speedRef.current)
      if (epoch === epochRef.current) setPos(pos - 1)
    } catch {
      // ignore
    } finally {
      if (epoch === epochRef.current) busyRef.current = false
    }
  }, [pos, moves])

  // Playback loop: each pos change while playing schedules the next move.
  useEffect(() => {
    if (!playing) return
    if (pos >= total) {
      setPlaying(false)
      return
    }
    void stepForward()
  }, [playing, pos, total, stepForward])

  const nextStep = useCallback(() => {
    if (!current) return
    jumpTo(pos < current.end ? current.end : Math.min(total, pos + 1))
  }, [current, pos, total, jumpTo])

  const prevStep = useCallback(() => {
    if (!current) return
    if (pos > current.start) {
      jumpTo(current.start)
    } else {
      // find the previous step with a smaller start
      for (let i = currentStepIndex - 1; i >= 0; i--) {
        if (steps[i].start < pos || steps[i].start < current.start) {
          jumpTo(steps[i].start)
          return
        }
      }
      jumpTo(0)
    }
  }, [current, currentStepIndex, steps, pos, jumpTo])

  const stageBadgeClass = current
    ? `walk-badge walk-stage-${current.stage.id}`
    : 'walk-badge'
  const moveCounter = `move ${Math.min(pos, total)} / ${total}`

  return (
    <div className="walkthrough">
      <div className="walk-stage">
        <CubeView ref={cubeRef} className="cube-view" />
        <span className="walk-caption">3D · {moveCounter}</span>
      </div>

      <div className="walk-panel">
        <div className="walk-panel-top">
          {onExit && (
            <button className="walk-exit" onClick={onExit}>
              ← exit
            </button>
          )}
          <span className="walk-counter">{moveCounter}</span>
        </div>

        {current && (
          <div className="walk-current">
            <span className={stageBadgeClass}>{current.stage.label}</span>
            <div className="walk-step-label">{current.step.label}</div>
            {current.step.case && <div className="walk-step-case">{current.step.case}</div>}
            <div className="walk-notation">
              {current.step.moves.length === 0 ? (
                <span className="walk-token-skip">(no moves)</span>
              ) : (
                current.step.moves.map((tok, i) => {
                  const flatIdx = current.start + i
                  const cls =
                    flatIdx === pos
                      ? 'walk-token current'
                      : flatIdx < pos
                        ? 'walk-token done'
                        : 'walk-token'
                  return (
                    <span key={i} className={cls}>
                      {tok}
                    </span>
                  )
                })
              )}
            </div>
          </div>
        )}

        <div className="walk-progress">
          <div
            className="walk-progress-fill"
            style={{ width: total > 0 ? `${(pos / total) * 100}%` : '0%' }}
          />
        </div>

        <div className="walk-transport">
          <button className="walk-tbtn" onClick={prevStep} disabled={pos <= 0} title="Previous step">
            ⏮
          </button>
          <button
            className="walk-tbtn"
            onClick={() => void stepBack()}
            disabled={pos <= 0}
            title="Previous move"
          >
            ◀
          </button>
          <button
            className="walk-tbtn walk-play"
            onClick={() => setPlaying((p) => !p)}
            disabled={total === 0 || (!playing && pos >= total)}
            title={playing ? 'Pause' : 'Play'}
          >
            {playing ? '❚❚' : '▶'}
          </button>
          <button
            className="walk-tbtn"
            onClick={() => void stepForward()}
            disabled={playing || pos >= total}
            title="Next move"
          >
            ▶
          </button>
          <button className="walk-tbtn" onClick={nextStep} disabled={pos >= total} title="Next step">
            ⏭
          </button>
        </div>

        <label className="walk-speed">
          <span>Speed {speed.toFixed(2)}×</span>
          <input
            type="range"
            min={SPEEDS_MIN}
            max={SPEEDS_MAX}
            step={0.25}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          />
        </label>

        <div className="walk-steps">
          {solve.stages.map((stage) => (
            <div key={stage.id} className="walk-stage-group">
              <div className={`walk-badge small walk-stage-${stage.id}`}>{stage.label}</div>
              {steps
                .filter((s) => s.stage === stage)
                .map((s) => {
                  const idx = steps.indexOf(s)
                  const active = idx === currentStepIndex
                  return (
                    <button
                      key={idx}
                      className={`walk-step-item${active ? ' active' : ''}${s.step.skipped ? ' skipped' : ''}`}
                      onClick={() => jumpTo(s.start)}
                    >
                      <span>{s.step.label}</span>
                      <span className="walk-step-item-notation">{s.step.notation || '—'}</span>
                    </button>
                  )
                })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
