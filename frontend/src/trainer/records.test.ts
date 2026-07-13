/** T18 — records store (§12.5 schema + §12.4 grind-mode update rules). */
import { describe, expect, it } from 'vitest'
import {
  applyGrindResult,
  applyRandomResult,
  LAST_SET_KEY,
  loadLastSet,
  loadRecords,
  RECORDS_KEY,
  saveLastSet,
  saveRecords,
  type RecordsState,
  type StorageLike,
} from './records'

/** In-memory Storage stand-in (vitest runs in node, no DOM). */
function fakeStorage(initial: Record<string, string> = {}): StorageLike & {
  data: Map<string, string>
} {
  const data = new Map(Object.entries(initial))
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v)
    },
  }
}

describe('applyRandomResult (§12.3 step 3: independent minima + n)', () => {
  it('creates a full record on the first attempt, flagged PB', () => {
    const { records, record, isPB } = applyRandomResult({}, 'oll', 'oll-27', 2000, 3000)
    expect(record).toEqual({ recog: 2000, exec: 3000, total: 5000, n: 1 })
    expect(isPB).toBe(true)
    expect(records.oll?.['oll-27']).toEqual(record)
  })

  it('updates recog / exec / total INDEPENDENTLY', () => {
    const first = applyRandomResult({}, 'oll', 'oll-27', 2000, 3000).records
    // Better recog, worse exec, equal total: only recog improves.
    const { record, isPB } = applyRandomResult(first, 'oll', 'oll-27', 1000, 4000)
    expect(record).toEqual({ recog: 1000, exec: 3000, total: 5000, n: 2 })
    expect(isPB).toBe(false) // 5000 is not strictly better than 5000
  })

  it('flags a PB exactly when the total strictly improves', () => {
    const first = applyRandomResult({}, 'pll', 'pll-T', 1500, 2500).records
    const better = applyRandomResult(first, 'pll', 'pll-T', 1000, 2500)
    expect(better.isPB).toBe(true)
    expect(better.record.total).toBe(3500)
    const worse = applyRandomResult(better.records, 'pll', 'pll-T', 2000, 3000)
    expect(worse.isPB).toBe(false)
    expect(worse.record).toEqual({ recog: 1000, exec: 2500, total: 3500, n: 3 })
  })

  it('grants the first total on a grind-only case a PB and keeps its exec best', () => {
    const grindOnly = applyGrindResult({}, 'coll', 'coll-T-3', 1800).records
    const { record, isPB } = applyRandomResult(grindOnly, 'coll', 'coll-T-3', 2000, 2200)
    expect(isPB).toBe(true) // no previous total
    expect(record).toEqual({ recog: 2000, exec: 1800, total: 4200, n: 2 })
  })

  it('does not mutate its input', () => {
    const before: RecordsState = { oll: { 'oll-1': { recog: 1, exec: 2, total: 3, n: 1 } } }
    const frozen = JSON.stringify(before)
    applyRandomResult(before, 'oll', 'oll-1', 10, 20)
    applyGrindResult(before, 'oll', 'oll-1', 10)
    expect(JSON.stringify(before)).toBe(frozen)
  })
})

describe('applyGrindResult (§12.4: exec best + n ONLY)', () => {
  it('creates an exec-only record (no recog/total) on the first grind', () => {
    const { record, isPB } = applyGrindResult({}, 'zbll', 'zbll-Pi-17', 2100)
    expect(record).toEqual({ exec: 2100, n: 1 })
    expect('recog' in record).toBe(false)
    expect('total' in record).toBe(false)
    expect(isPB).toBe(true)
  })

  it('never touches recog/total bests set by random mode', () => {
    const seeded = applyRandomResult({}, 'oll', 'oll-27', 2000, 3000).records
    const { record, isPB } = applyGrindResult(seeded, 'oll', 'oll-27', 1000)
    expect(record).toEqual({ recog: 2000, exec: 1000, total: 5000, n: 2 })
    expect(isPB).toBe(true) // exec strictly improved
  })

  it('flags a PB exactly when the exec best strictly improves', () => {
    const first = applyGrindResult({}, 'vls', 'vls-eo2-11', 1500).records
    expect(applyGrindResult(first, 'vls', 'vls-eo2-11', 1500).isPB).toBe(false)
    const better = applyGrindResult(first, 'vls', 'vls-eo2-11', 1400)
    expect(better.isPB).toBe(true)
    expect(better.record).toEqual({ exec: 1400, n: 2 })
  })

  it('leaves other cases and other sets untouched', () => {
    const seeded = applyRandomResult({}, 'oll', 'oll-1', 1, 2).records
    const { records } = applyGrindResult(seeded, 'pll', 'pll-T', 500)
    expect(records.oll?.['oll-1']).toEqual({ recog: 1, exec: 2, total: 3, n: 1 })
    expect(records.pll?.['pll-T']).toEqual({ exec: 500, n: 1 })
  })
})

describe('persistence (localStorage["alglabs.records.v1"] round-trip)', () => {
  it('round-trips through storage', () => {
    const storage = fakeStorage()
    const state = applyRandomResult({}, 'oll', 'oll-27', 2000, 3000).records
    saveRecords(state, storage)
    expect(loadRecords(storage)).toEqual(state)
  })

  it('falls back to the pre-rebrand cubesight.* keys when the new keys are absent', () => {
    const legacy = JSON.stringify({ oll: { 'oll-27': { recog: 1, exec: 2, total: 3, n: 1 } } })
    // records: legacy key read only when the new key is missing
    expect(loadRecords(fakeStorage({ 'cubesight.records.v1': legacy }))).toEqual({
      oll: { 'oll-27': { recog: 1, exec: 2, total: 3, n: 1 } },
    })
    // last-set: same fallback
    expect(loadLastSet(fakeStorage({ 'cubesight.lastset.v1': 'pll' }))).toBe('pll')
    // the new key wins when both exist
    expect(
      loadLastSet(fakeStorage({ 'alglabs.lastset.v1': 'coll', 'cubesight.lastset.v1': 'pll' })),
    ).toBe('coll')
  })

  it('degrades malformed / missing data to {}', () => {
    expect(loadRecords(fakeStorage())).toEqual({})
    expect(loadRecords(fakeStorage({ [RECORDS_KEY]: 'not json{' }))).toEqual({})
    expect(loadRecords(fakeStorage({ [RECORDS_KEY]: '[1,2]' }))).toEqual({})
    expect(loadRecords(fakeStorage({ [RECORDS_KEY]: '"nope"' }))).toEqual({})
    expect(loadRecords(null)).toEqual({})
  })

  it('drops malformed nested entries instead of letting them crash updates', () => {
    // null / junk case records and non-object sets are pruned; valid siblings survive.
    const stored = JSON.stringify({
      oll: {
        'oll-27': null, // partial/corrupt write
        'oll-1': { recog: 1, exec: 2, total: 3, n: 1 },
        'oll-2': { exec: 'fast', n: 1 }, // wrong type
        'oll-3': { n: 4 }, // missing exec
      },
      pll: null,
      f2l: [1, 2],
      'not-a-set': { 'x-1': { exec: 1, n: 1 } },
    })
    const loaded = loadRecords(fakeStorage({ [RECORDS_KEY]: stored }))
    expect(loaded).toEqual({ oll: { 'oll-1': { recog: 1, exec: 2, total: 3, n: 1 } } })
    // The scenario that used to throw: grinding a case whose stored record was null.
    const { record, isPB } = applyGrindResult(loaded, 'oll', 'oll-27', 1200)
    expect(record).toEqual({ exec: 1200, n: 1 })
    expect(isPB).toBe(true)
  })

  it('applyGrindResult tolerates a null record smuggled past the types', () => {
    const corrupt = { oll: { 'oll-27': null } } as unknown as RecordsState
    const { record, isPB } = applyGrindResult(corrupt, 'oll', 'oll-27', 900)
    expect(record).toEqual({ exec: 900, n: 1 })
    expect(isPB).toBe(true)
  })

  it('never touches foreign localStorage keys (§12.5)', () => {
    const storage = fakeStorage({ 'someone.elses.key': 'precious' })
    saveRecords(applyGrindResult({}, 'oll', 'oll-1', 100).records, storage)
    saveLastSet('zbll', storage)
    expect(storage.data.get('someone.elses.key')).toBe('precious')
    expect([...storage.data.keys()].sort()).toEqual(
      ['someone.elses.key', RECORDS_KEY, LAST_SET_KEY].sort(),
    )
  })

  it('round-trips the last-trained set and rejects junk values', () => {
    const storage = fakeStorage()
    expect(loadLastSet(storage)).toBeNull()
    saveLastSet('coll', storage)
    expect(loadLastSet(storage)).toBe('coll')
    expect(loadLastSet(fakeStorage({ [LAST_SET_KEY]: 'not-a-set' }))).toBeNull()
    expect(loadLastSet(null)).toBeNull()
  })
})
