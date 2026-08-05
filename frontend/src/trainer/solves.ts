/**
 * Solve history (CONTRACTS.md §12.6): every solve ever timed, persisted at
 * localStorage["alglabs.solves.v1"] shaped `{[setKey]: {[caseId]: Solve[]}}`,
 * oldest first.
 *
 * This is a SEPARATE key from the records store on purpose. Records hold the
 * personal bests the trainer reads on every scramble; history is a much larger,
 * append-only log that only the Records screen reads. Keeping them apart means
 * a corrupt or over-quota history can never take the PBs down with it.
 *
 * A solve always has an execution split — the one figure comparable across both
 * modes (§12.5: grind updates exec only). `recog` is present exactly for random
 * solves, so `recog === undefined` identifies a grind rep, and the totals stats
 * are computed over the random solves alone rather than mixing the two.
 *
 * Pure functions over the state, unit-tested per T18; persistence is the same
 * thin, injectable-storage layer the records store uses and touches ONLY our
 * own key.
 */

import { SET_KEYS, type SetKey } from './types'

export const SOLVES_KEY = 'alglabs.solves.v1'

/**
 * Per-case history cap. At ~40 bytes of JSON per solve this keeps even a
 * fully-drilled ZBLL history far inside the ~5MB localStorage budget. Oldest
 * solves fall off first; the stats then describe the retained window.
 */
export const MAX_SOLVES_PER_CASE = 500

export interface Solve {
  /** Recognition split (ms). Absent for grind reps, which never time recognition. */
  recog?: number
  /** Execution split (ms). Always present. */
  exec: number
  /** Wall-clock time the solve ended (epoch ms). */
  at: number
}

export type SetSolves = Record<string, Solve[]>
export type SolvesState = Partial<Record<SetKey, SetSolves>>

/** A solve's headline time: total for random solves, exec for grind reps. */
export function solveMs(s: Solve): number {
  return s.recog === undefined ? s.exec : s.recog + s.exec
}

/**
 * Append one solve, keeping chronological order and the newest
 * MAX_SOLVES_PER_CASE entries.
 */
export function appendSolve(
  state: SolvesState,
  set: SetKey,
  caseId: string,
  solve: Solve,
): SolvesState {
  const prev = state[set]?.[caseId] ?? []
  const next = [...prev, solve].slice(-MAX_SOLVES_PER_CASE)
  return { ...state, [set]: { ...state[set], [caseId]: next } }
}

export interface CaseStats {
  /** Solves in the retained history (may be less than the record's lifetime n). */
  n: number
  avgExec: number
  bestExec: number
  /** Random solves only — the ones that timed recognition. */
  nRandom: number
  avgRecog?: number
  avgTotal?: number
  bestTotal?: number
}

const mean = (xs: readonly number[]): number => xs.reduce((a, b) => a + b, 0) / xs.length

/** Aggregate one case's history; `null` for a case with no solves logged. */
export function caseStats(solves: readonly Solve[]): CaseStats | null {
  if (solves.length === 0) return null
  const execs = solves.map((s) => s.exec)
  const randoms = solves.filter((s): s is Solve & { recog: number } => s.recog !== undefined)
  const totals = randoms.map((s) => s.recog + s.exec)
  return {
    n: solves.length,
    avgExec: mean(execs),
    bestExec: Math.min(...execs),
    nRandom: randoms.length,
    ...(randoms.length > 0 && {
      avgRecog: mean(randoms.map((s) => s.recog)),
      avgTotal: mean(totals),
      bestTotal: Math.min(...totals),
    }),
  }
}

// ---------------------------------------------------------------------------
// Persistence — only getItem/setItem on our own key.
// ---------------------------------------------------------------------------

export type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

function defaultStorage(): StorageLike | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isSolve(v: unknown): v is Solve {
  if (!isPlainObject(v)) return false
  return (
    typeof v.exec === 'number' &&
    typeof v.at === 'number' &&
    (v.recog === undefined || typeof v.recog === 'number')
  )
}

/**
 * Load the history; malformed / missing data degrades to `{}`, and any
 * malformed ENTRY (unknown set key, non-array case, solve without numeric
 * exec/at) is dropped so the stats never see junk shapes.
 */
export function loadSolves(storage: StorageLike | null = defaultStorage()): SolvesState {
  if (!storage) return {}
  try {
    const raw = storage.getItem(SOLVES_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!isPlainObject(parsed)) return {}
    const state: SolvesState = {}
    for (const set of SET_KEYS) {
      const cases = parsed[set]
      if (!isPlainObject(cases)) continue
      const clean: SetSolves = {}
      for (const [caseId, list] of Object.entries(cases)) {
        if (Array.isArray(list)) clean[caseId] = list.filter(isSolve).slice(-MAX_SOLVES_PER_CASE)
      }
      state[set] = clean
    }
    return state
  } catch {
    return {}
  }
}

export function saveSolves(
  solves: SolvesState,
  storage: StorageLike | null = defaultStorage(),
): void {
  try {
    storage?.setItem(SOLVES_KEY, JSON.stringify(solves))
  } catch {
    // Quota / privacy-mode failures are non-fatal: the session keeps working
    // and the PBs, which live under their own key, are untouched.
  }
}
