/**
 * Records store (CONTRACTS.md §12.5): per-case personal bests persisted at
 * localStorage["alglabs.records.v1"], shaped
 * `{[setKey]: {[caseId]: {recog, exec, total, n}}}` where each best field is
 * the independent minimum ever seen. `recog`/`total` may be ABSENT for cases
 * only ever trained in grind mode (§12.4: grind updates exec/n only).
 *
 * The update rules are pure functions over the state (unit-tested per T18);
 * persistence is a thin layer that touches ONLY our own keys — never clears
 * or enumerates foreign localStorage keys — and takes an injectable storage
 * so the tests run without a DOM.
 */

import { SET_KEYS, type SetKey } from './types'

export const RECORDS_KEY = 'alglabs.records.v1'
export const LAST_SET_KEY = 'alglabs.lastset.v1'

// Pre-rebrand keys (app was "CubeSight"): read as a fallback so records made
// before the rename survive. Written back under the new keys on the next save.
const LEGACY_RECORDS_KEY = 'cubesight.records.v1'
const LEGACY_LAST_SET_KEY = 'cubesight.lastset.v1'

/** One case's bests. `recog`/`total` are absent while the case is grind-only. */
export interface CaseRecord {
  recog?: number
  exec: number
  total?: number
  n: number
}

export type SetRecords = Record<string, CaseRecord>
export type RecordsState = Partial<Record<SetKey, SetRecords>>

export interface RecordUpdate {
  records: RecordsState
  /** The case's record after the update. */
  record: CaseRecord
  /** Whether this attempt set a new PB (total in random mode, exec in grind). */
  isPB: boolean
}

/** min() where the previous best may not exist yet. */
function minDefined(prev: number | undefined, next: number): number {
  return prev === undefined ? next : Math.min(prev, next)
}

function withRecord(
  records: RecordsState,
  set: SetKey,
  caseId: string,
  record: CaseRecord,
): RecordsState {
  return { ...records, [set]: { ...records[set], [caseId]: record } }
}

/**
 * Random-mode result (§12.3 step 3): update best-recog, best-exec and
 * best-total INDEPENDENTLY, increment n. PB = new best total (also true for
 * the first total ever, including on a previously grind-only case).
 */
export function applyRandomResult(
  records: RecordsState,
  set: SetKey,
  caseId: string,
  recogMs: number,
  execMs: number,
): RecordUpdate {
  const prev = records[set]?.[caseId]
  const total = recogMs + execMs
  const isPB = prev?.total === undefined || total < prev.total
  const record: CaseRecord = {
    recog: minDefined(prev?.recog, recogMs),
    exec: minDefined(prev?.exec, execMs),
    total: minDefined(prev?.total, total),
    n: (prev?.n ?? 0) + 1,
  }
  return { records: withRecord(records, set, caseId, record), record, isPB }
}

/**
 * Grind-mode result (§12.4): update ONLY best-exec and n — recog/total bests
 * are set only by random mode. PB = new best exec.
 */
export function applyGrindResult(
  records: RecordsState,
  set: SetKey,
  caseId: string,
  execMs: number,
): RecordUpdate {
  const prev = records[set]?.[caseId]
  const isPB = prev?.exec === undefined || execMs < prev.exec
  const record: CaseRecord = {
    ...prev,
    exec: minDefined(prev?.exec, execMs),
    n: (prev?.n ?? 0) + 1,
  }
  return { records: withRecord(records, set, caseId, record), record, isPB }
}

// ---------------------------------------------------------------------------
// Persistence — only getItem/setItem on our own keys.
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

function isCaseRecord(v: unknown): v is CaseRecord {
  if (!isPlainObject(v)) return false
  return (
    typeof v.exec === 'number' &&
    typeof v.n === 'number' &&
    (v.recog === undefined || typeof v.recog === 'number') &&
    (v.total === undefined || typeof v.total === 'number')
  )
}

/**
 * Load the records state; malformed / missing data degrades to `{}` and any
 * malformed ENTRY (unknown set key, non-object set, case record without
 * numeric exec/n) is dropped so the update functions never see junk shapes.
 */
export function loadRecords(storage: StorageLike | null = defaultStorage()): RecordsState {
  if (!storage) return {}
  try {
    const raw = storage.getItem(RECORDS_KEY) ?? storage.getItem(LEGACY_RECORDS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!isPlainObject(parsed)) return {}
    const state: RecordsState = {}
    for (const set of SET_KEYS) {
      const cases = parsed[set]
      if (!isPlainObject(cases)) continue
      const clean: SetRecords = {}
      for (const [caseId, record] of Object.entries(cases)) {
        if (isCaseRecord(record)) clean[caseId] = record
      }
      state[set] = clean
    }
    return state
  } catch {
    return {}
  }
}

export function saveRecords(
  records: RecordsState,
  storage: StorageLike | null = defaultStorage(),
): void {
  try {
    storage?.setItem(RECORDS_KEY, JSON.stringify(records))
  } catch {
    // Quota / privacy-mode failures are non-fatal: the session keeps working.
  }
}

/** The last-trained set, for the Records default tab (§12.5). */
export function loadLastSet(storage: StorageLike | null = defaultStorage()): SetKey | null {
  try {
    const raw = storage?.getItem(LAST_SET_KEY) ?? storage?.getItem(LEGACY_LAST_SET_KEY)
    return raw !== null && raw !== undefined && (SET_KEYS as readonly string[]).includes(raw)
      ? (raw as SetKey)
      : null
  } catch {
    return null
  }
}

export function saveLastSet(set: SetKey, storage: StorageLike | null = defaultStorage()): void {
  try {
    storage?.setItem(LAST_SET_KEY, set)
  } catch {
    // Non-fatal, as above.
  }
}
