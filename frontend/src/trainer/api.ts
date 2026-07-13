/**
 * Fetch wrappers for the trainer endpoints (CONTRACTS.md §11.4), base path
 * /api/trainer. Kept separate from the global src/api.ts on purpose — the
 * trainer is its own module (§12.2) — but reuses its error classes so the
 * shell's failure copy stays consistent.
 *
 * Sets and per-set case lists are cached per session: they are immutable for
 * a given backend build (case ids are stable across releases, §11.1), and
 * ZBLL's 493 cases must load once and filter client-side (§12.4).
 */

import { ApiUnavailableError } from '../api'
import type { SetKey, TrainerCase, TrainerScramble, TrainerSet } from './types'

const BASE = '/api/trainer'

interface TrainerErrorBody {
  valid: false
  errors: { code: string; message: string }[]
}

function isErrorBody(body: unknown): body is TrainerErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    (body as { valid?: unknown }).valid === false &&
    Array.isArray((body as { errors?: unknown }).errors)
  )
}

async function get<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`)
  } catch {
    throw new ApiUnavailableError()
  }
  let body: unknown
  try {
    body = await res.json()
  } catch {
    throw new Error(`Unexpected non-JSON response from /trainer${path} (HTTP ${res.status})`)
  }
  if (isErrorBody(body)) {
    throw new Error(body.errors.map((e) => e.message).join(' — ') || 'Trainer request rejected')
  }
  if (!res.ok) throw new Error(`${BASE}${path} failed (HTTP ${res.status})`)
  return body as T
}

let setsCache: TrainerSet[] | null = null

/** GET /api/trainer/sets — the five sets in oll/pll/coll/zbll/vls order. */
export async function fetchSets(): Promise<TrainerSet[]> {
  if (setsCache) return setsCache
  const { sets } = await get<{ sets: TrainerSet[] }>('/sets')
  setsCache = sets
  return sets
}

const casesCache = new Map<SetKey, TrainerCase[]>()

/**
 * GET /api/trainer/cases?set=… — ALL cases of a set (no server-side group
 * filter; grouping is client-side per §12.4). Cached after the first load.
 */
export async function fetchCases(set: SetKey): Promise<TrainerCase[]> {
  const hit = casesCache.get(set)
  if (hit) return hit
  const { cases } = await get<{ set: string; cases: TrainerCase[] }>(
    `/cases?set=${encodeURIComponent(set)}`,
  )
  casesCache.set(set, cases)
  return cases
}

/**
 * GET /api/trainer/scramble?set=…[&case_id=…] — a fresh draw every call
 * (free params re-drawn per §11.2, so one case yields many scrambles).
 */
export async function fetchScramble(set: SetKey, caseId?: string): Promise<TrainerScramble> {
  const query = caseId ? `?set=${set}&case_id=${encodeURIComponent(caseId)}` : `?set=${set}`
  return get<TrainerScramble>(`/scramble${query}`)
}
