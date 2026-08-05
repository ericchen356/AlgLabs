/** T18 — solve history store (§12.6): append, stats, load/save validation. */
import { describe, expect, it } from 'vitest'
import {
  appendSolve,
  caseStats,
  loadSolves,
  MAX_SOLVES_PER_CASE,
  saveSolves,
  SOLVES_KEY,
  solveMs,
  type Solve,
  type SolvesState,
  type StorageLike,
} from './solves'

/** In-memory storage double: only getItem/setItem, like the real thing. */
function fakeStorage(seed: Record<string, string> = {}): StorageLike & { data: typeof seed } {
  const data = { ...seed }
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v
    },
  }
}

const random = (recog: number, exec: number, at = 0): Solve => ({ recog, exec, at })
const grind = (exec: number, at = 0): Solve => ({ exec, at })

describe('appendSolve', () => {
  it('appends chronologically and nests under set → case', () => {
    let s: SolvesState = {}
    s = appendSolve(s, 'pll', 't-perm', random(1000, 2000, 10))
    s = appendSolve(s, 'pll', 't-perm', grind(1800, 20))
    s = appendSolve(s, 'pll', 'y-perm', grind(3000, 30))
    expect(s.pll?.['t-perm']).toEqual([random(1000, 2000, 10), grind(1800, 20)])
    expect(s.pll?.['y-perm']).toEqual([grind(3000, 30)])
  })

  it('does not mutate the previous state', () => {
    const before: SolvesState = { pll: { 't-perm': [grind(1000)] } }
    const after = appendSolve(before, 'pll', 't-perm', grind(2000))
    expect(before.pll?.['t-perm']).toHaveLength(1)
    expect(after.pll?.['t-perm']).toHaveLength(2)
  })

  it('keeps the newest MAX_SOLVES_PER_CASE, dropping the oldest', () => {
    let s: SolvesState = {}
    for (let i = 0; i < MAX_SOLVES_PER_CASE + 5; i++) {
      s = appendSolve(s, 'oll', 'oll-1', grind(i, i))
    }
    const list = s.oll?.['oll-1'] ?? []
    expect(list).toHaveLength(MAX_SOLVES_PER_CASE)
    expect(list[0].exec).toBe(5) // the first five fell off
    expect(list[list.length - 1].exec).toBe(MAX_SOLVES_PER_CASE + 4)
  })
})

describe('solveMs (headline time: total for random, exec for grind)', () => {
  it('sums the splits of a random solve', () => {
    expect(solveMs(random(1200, 2300))).toBe(3500)
  })

  it('uses execution alone for a grind rep', () => {
    expect(solveMs(grind(2300))).toBe(2300)
  })
})

describe('caseStats', () => {
  it('is null for a case with no history', () => {
    expect(caseStats([])).toBeNull()
  })

  it('averages execution across BOTH modes, totals across random only', () => {
    const stats = caseStats([random(1000, 2000), grind(3000), random(2000, 4000)])
    expect(stats).not.toBeNull()
    expect(stats?.n).toBe(3)
    expect(stats?.avgExec).toBe(3000) // (2000 + 3000 + 4000) / 3
    expect(stats?.bestExec).toBe(2000)
    expect(stats?.nRandom).toBe(2)
    expect(stats?.avgRecog).toBe(1500) // (1000 + 2000) / 2
    expect(stats?.avgTotal).toBe(4500) // (3000 + 6000) / 2
    expect(stats?.bestTotal).toBe(3000)
  })

  it('omits the recognition/total stats when every solve is a grind rep', () => {
    const stats = caseStats([grind(2000), grind(3000)])
    expect(stats?.avgExec).toBe(2500)
    expect(stats?.bestExec).toBe(2000)
    expect(stats?.nRandom).toBe(0)
    expect(stats?.avgRecog).toBeUndefined()
    expect(stats?.avgTotal).toBeUndefined()
    expect(stats?.bestTotal).toBeUndefined()
  })
})

describe('persistence', () => {
  it('round-trips through storage', () => {
    const store = fakeStorage()
    const state = appendSolve({}, 'pll', 't-perm', random(1000, 2000, 42))
    saveSolves(state, store)
    expect(loadSolves(store)).toEqual(state)
  })

  it('returns {} with no storage, no key, or unparseable JSON', () => {
    expect(loadSolves(null)).toEqual({})
    expect(loadSolves(fakeStorage())).toEqual({})
    expect(loadSolves(fakeStorage({ [SOLVES_KEY]: '{oops' }))).toEqual({})
    expect(loadSolves(fakeStorage({ [SOLVES_KEY]: '[1,2]' }))).toEqual({})
  })

  it('drops malformed entries instead of failing the whole load', () => {
    const raw = JSON.stringify({
      pll: {
        good: [{ exec: 2000, at: 1 }, { recog: 1000, exec: 2000, at: 2 }, { exec: 'nope', at: 3 }],
        alsoBad: 'not an array',
      },
      notASet: { x: [{ exec: 1, at: 1 }] },
    })
    const loaded = loadSolves(fakeStorage({ [SOLVES_KEY]: raw }))
    expect(loaded.pll?.good).toEqual([grind(2000, 1), random(1000, 2000, 2)])
    expect(loaded.pll?.alsoBad).toBeUndefined()
    expect(loaded).not.toHaveProperty('notASet')
  })

  it('trims an over-long stored history on load', () => {
    const long = Array.from({ length: MAX_SOLVES_PER_CASE + 3 }, (_, i) => ({ exec: i, at: i }))
    const loaded = loadSolves(fakeStorage({ [SOLVES_KEY]: JSON.stringify({ oll: { a: long } }) }))
    expect(loaded.oll?.a).toHaveLength(MAX_SOLVES_PER_CASE)
    expect(loaded.oll?.a[0].exec).toBe(3)
  })

  it('survives a storage that throws (quota / privacy mode)', () => {
    const throwing: StorageLike = {
      getItem: () => {
        throw new Error('denied')
      },
      setItem: () => {
        throw new Error('quota')
      },
    }
    expect(loadSolves(throwing)).toEqual({})
    expect(() => saveSolves({ pll: { a: [grind(1)] } }, throwing)).not.toThrow()
  })
})
