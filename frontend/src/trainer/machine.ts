/**
 * Trainer phase machines as PURE reducers (CONTRACTS.md §12.3/§12.4, tested
 * per T18 without a DOM).
 *
 * Hold-based ("StackMat"-style) interaction — a single key (Space) or a
 * pointer press on the timer panel drives everything via press (`down`) and
 * release (`up`) edges:
 *
 *   random: idle --down--> recognition --up--> execution --down--> idle
 *           You HOLD the key to recognize (recognition runs while held) and
 *           RELEASE to start solving; press again to stop.
 *
 *   grind:  idle --down--> armed --up--> execution --down--> idle
 *           Hold to arm (nothing runs), release to start the timer; press to stop.
 *
 * The stop press returns straight to `idle` — the drill re-arms itself, so the
 * next solve needs no extra keypress. The frozen splits SURVIVE that return
 * (they are only cleared when the next solve actually starts), which is what
 * keeps the just-finished time on screen while the trainer waits.
 *
 * Only recognition ends on the RELEASE edge; every other transition fires on
 * PRESS and ignores the matching release, so one physical press-release never
 * advances two steps unintentionally (the release after the "stop" press lands
 * harmlessly in `idle`, which ignores releases).
 *
 * Timestamps are passed in (`performance.now()` in the app, fake numbers in
 * tests); the reducer freezes each split when the phase it times ends. Live
 * readouts are derived by `liveSplits(state, now)`.
 */

import type { TrainerMode } from './types'

export type TrainerPhase = 'idle' | 'armed' | 'recognition' | 'execution'

/** A press (`down`) or release (`up`) of Space / the timer panel. */
export type TrainerInput = 'down' | 'up'

export interface TrainerMachine {
  mode: TrainerMode
  phase: TrainerPhase
  /** Timestamp the RUNNING split started at; null unless a timer is running. */
  phaseStart: number | null
  /** Frozen recognition split (ms). Always 0 in grind mode. */
  recogMs: number
  /** Frozen execution split (ms). */
  execMs: number
}

/** What a step did — the component maps these to side effects. */
export type StepEvent = 'none' | 'startRecognition' | 'arm' | 'startExecution' | 'finish'

/**
 * True when the machine is sitting in `idle` holding the splits of the solve
 * that just ended (as opposed to a fresh, never-solved idle).
 */
export function justFinished(m: TrainerMachine): boolean {
  return m.phase === 'idle' && m.execMs > 0
}

export function initialMachine(mode: TrainerMode): TrainerMachine {
  return { mode, phase: 'idle', phaseStart: null, recogMs: 0, execMs: 0 }
}

export interface StepResult {
  state: TrainerMachine
  event: StepEvent
}

const noop = (m: TrainerMachine): StepResult => ({ state: m, event: 'none' })

/**
 * Advance the machine on a press/release edge (§12.3/§12.4 phase machines).
 * Unhandled (phase, input) pairs are no-ops so stray edges — the release that
 * follows a "stop"/"next" press, an auto-repeat, a keyup with no keydown — do
 * nothing.
 */
export function stepMachine(m: TrainerMachine, input: TrainerInput, now: number): StepResult {
  switch (m.phase) {
    case 'idle':
      if (input !== 'down') return noop(m)
      return m.mode === 'random'
        ? {
            state: { ...m, phase: 'recognition', phaseStart: now, recogMs: 0, execMs: 0 },
            event: 'startRecognition',
          }
        : {
            // grind: hold arms the timer without starting it (§12.4).
            state: { ...m, phase: 'armed', phaseStart: null, recogMs: 0, execMs: 0 },
            event: 'arm',
          }

    case 'armed':
      // grind only: release starts execution.
      if (input !== 'up') return noop(m)
      return {
        state: { ...m, phase: 'execution', phaseStart: now },
        event: 'startExecution',
      }

    case 'recognition':
      // random only: release freezes recognition and starts execution.
      if (input !== 'up') return noop(m)
      return {
        state: { ...m, phase: 'execution', recogMs: now - (m.phaseStart ?? now), phaseStart: now },
        event: 'startExecution',
      }

    case 'execution':
      // press stops the solve and re-arms immediately; the frozen splits stay
      // on the machine so the finished time keeps showing until the next solve.
      if (input !== 'down') return noop(m)
      return {
        state: { ...m, phase: 'idle', execMs: now - (m.phaseStart ?? now), phaseStart: null },
        event: 'finish',
      }
  }
}

export interface Splits {
  recog: number
  exec: number
  total: number
}

/** Live/frozen splits at time `now` — running split ticks, others are frozen. */
export function liveSplits(m: TrainerMachine, now: number): Splits {
  const recog = m.phase === 'recognition' ? now - (m.phaseStart ?? now) : m.recogMs
  const exec = m.phase === 'execution' ? now - (m.phaseStart ?? now) : m.execMs
  return { recog, exec, total: recog + exec }
}

/** True while a timer is live (big panel blinks, rAF loop runs). `armed` is not running. */
export function isRunning(m: TrainerMachine): boolean {
  return m.phase === 'recognition' || m.phase === 'execution'
}

/** The mandated timer format: seconds with two decimals (§12.3). */
export function fmtMs(ms: number): string {
  return (ms / 1000).toFixed(2)
}

/** Session strip entry: total ms in random mode, exec ms in grind mode. */
export interface SessionEntry {
  ms: number
  isPB: boolean
}

/** Push onto the session strip, newest first, keeping the last 6 (§12.3). */
export function pushSession(
  session: readonly SessionEntry[],
  entry: SessionEntry,
): SessionEntry[] {
  return [entry, ...session].slice(0, 6)
}
