/** T15 — notation.ts parses all 18 tokens correctly and round-trips. */
import { describe, expect, it } from 'vitest'
import {
  ALL_TOKENS,
  invertMove,
  invertSequence,
  moveToString,
  parseMove,
  parseSequence,
  sequenceToString,
  type Move,
} from './notation'

const EXPECTED: Record<string, Pick<Move, 'axis' | 'layer'>> = {
  U: { axis: 'y', layer: 1 },
  D: { axis: 'y', layer: -1 },
  R: { axis: 'x', layer: 1 },
  L: { axis: 'x', layer: -1 },
  F: { axis: 'z', layer: 1 },
  B: { axis: 'z', layer: -1 },
}

describe('parseMove', () => {
  it('parses all 18 tokens to the correct face/axis/layer/quarterTurns', () => {
    expect(ALL_TOKENS).toHaveLength(18)
    for (const face of Object.keys(EXPECTED)) {
      const { axis, layer } = EXPECTED[face]
      expect(parseMove(face)).toEqual({ face, axis, layer, quarterTurns: 1 })
      expect(parseMove(`${face}'`)).toEqual({ face, axis, layer, quarterTurns: -1 })
      expect(parseMove(`${face}2`)).toEqual({ face, axis, layer, quarterTurns: 2 })
    }
  })

  it('round-trips every token through moveToString', () => {
    for (const token of ALL_TOKENS) {
      expect(moveToString(parseMove(token))).toBe(token)
    }
  })

  it('rejects garbage tokens', () => {
    for (const bad of ['', 'X', 'u', "U''", 'U3', 'R2 ', "M", 'Rw', 'x', '2', "'"]) {
      expect(() => parseMove(bad), `token ${JSON.stringify(bad)}`).toThrow()
    }
  })
})

describe('sequences', () => {
  it('parses whitespace-separated sequences and serializes back', () => {
    const s = "R U R' U' F2  B'"
    const moves = parseSequence(s)
    expect(moves.map((m) => m.face)).toEqual(['R', 'U', 'R', 'U', 'F', 'B'])
    expect(sequenceToString(moves)).toBe("R U R' U' F2 B'")
  })

  it('parses the empty string to an empty sequence', () => {
    expect(parseSequence('   ')).toEqual([])
  })

  it('throws on sequences containing invalid tokens', () => {
    expect(() => parseSequence("R U Rw'")).toThrow()
  })
})

describe('inverses', () => {
  it('inverts single moves', () => {
    expect(moveToString(invertMove(parseMove('R')))).toBe("R'")
    expect(moveToString(invertMove(parseMove("R'")))).toBe('R')
    expect(moveToString(invertMove(parseMove('R2')))).toBe('R2')
  })

  it('double inversion round-trips a sequence', () => {
    const moves = parseSequence("R U2 R' F D' L2 B")
    expect(sequenceToString(invertSequence(invertSequence(moves)))).toBe(
      sequenceToString(moves),
    )
  })

  it('inverts sequences in reverse order', () => {
    expect(sequenceToString(invertSequence(parseSequence("R U R' U'")))).toBe(
      "U R U' R'",
    )
  })
})
