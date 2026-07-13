/** T16 — cubeModel.ts geometry per §9.2, plus logical-move identities. */
import { describe, expect, it } from 'vitest'
import {
  applyMoveToModel,
  buildCubies,
  findCubieIndexByPiece,
  modelToFacelets,
  solvedFacelets,
  type Cubie,
  type Vec3,
} from './cubeModel'
import { parseSequence } from './notation'

function cubieAt(cubies: readonly Cubie[], pos: Vec3): Cubie {
  const c = cubies.find(
    (c) => c.position[0] === pos[0] && c.position[1] === pos[1] && c.position[2] === pos[2],
  )
  if (!c) throw new Error(`no cubie at ${pos.join(',')}`)
  return c
}

describe('buildCubies on the solved string (§9.2 spot checks)', () => {
  const cubies = buildCubies(solvedFacelets)

  it('produces exactly 26 cubies', () => {
    expect(cubies).toHaveLength(26)
  })

  it('places all 6 centers at the right positions with the right colors', () => {
    const centers: [Vec3, string][] = [
      [[0, 1, 0], 'U'],
      [[1, 0, 0], 'R'],
      [[0, 0, 1], 'F'],
      [[0, -1, 0], 'D'],
      [[-1, 0, 0], 'L'],
      [[0, 0, -1], 'B'],
    ]
    for (const [pos, face] of centers) {
      const c = cubieAt(cubies, pos)
      expect(Object.entries(c.stickers)).toEqual([[face, face]])
    }
  })

  it('U1 (index 0) is the (-1,1,-1) cubie top sticker', () => {
    const c = cubieAt(cubies, [-1, 1, -1])
    expect(c.stickers.U).toBe('U')
  })

  it('F1 (index 18) sits at (-1,1,1) facing F', () => {
    const c = cubieAt(cubies, [-1, 1, 1])
    expect(c.stickers.F).toBe('F')
  })

  it('R1 (index 9) sits at (1,1,1) facing R', () => {
    const c = cubieAt(cubies, [1, 1, 1])
    expect(c.stickers.R).toBe('R')
  })

  it('has correct sticker counts: 8 corners x3, 12 edges x2, 6 centers x1', () => {
    const byCount = new Map<number, number>()
    for (const c of cubies) {
      const n = Object.keys(c.stickers).length
      byCount.set(n, (byCount.get(n) ?? 0) + 1)
      // sticker count must equal the number of non-zero coordinates
      const nonZero = c.position.filter((v) => v !== 0).length
      expect(n).toBe(nonZero)
    }
    expect(byCount.get(3)).toBe(8)
    expect(byCount.get(2)).toBe(12)
    expect(byCount.get(1)).toBe(6)
  })

  it('every sticker points outward on a face boundary', () => {
    for (const c of cubies) {
      for (const face of Object.keys(c.stickers)) {
        // e.g. a U sticker only exists on a y=1 cubie
        if (face === 'U') expect(c.position[1]).toBe(1)
        if (face === 'D') expect(c.position[1]).toBe(-1)
        if (face === 'R') expect(c.position[0]).toBe(1)
        if (face === 'L') expect(c.position[0]).toBe(-1)
        if (face === 'F') expect(c.position[2]).toBe(1)
        if (face === 'B') expect(c.position[2]).toBe(-1)
      }
    }
  })
})

describe('facelets <-> model round-trip', () => {
  it('round-trips the solved string', () => {
    expect(modelToFacelets(buildCubies(solvedFacelets))).toBe(solvedFacelets)
  })

  it('round-trips a scrambled string', () => {
    let model = buildCubies(solvedFacelets)
    for (const m of parseSequence("R U R' U' F2 D' L B2 U2 R'")) {
      model = applyMoveToModel(model, m)
    }
    const scrambled = modelToFacelets(model)
    expect(scrambled).not.toBe(solvedFacelets)
    expect(modelToFacelets(buildCubies(scrambled))).toBe(scrambled)
  })

  it('rejects strings of the wrong length or alphabet', () => {
    expect(() => buildCubies('U')).toThrow()
    expect(() => buildCubies(solvedFacelets.slice(0, 53) + 'X')).toThrow()
  })
})

describe('applyMoveToModel', () => {
  it('U applied four times is the identity on the model', () => {
    let model = buildCubies(solvedFacelets)
    // start from a non-trivial state so the check is meaningful
    model = applyMoveToModel(model, 'R')
    const before = modelToFacelets(model)
    for (let i = 0; i < 4; i++) model = applyMoveToModel(model, 'U')
    expect(modelToFacelets(model)).toBe(before)
  })

  it("R then R' restores the state", () => {
    let model = buildCubies(solvedFacelets)
    model = applyMoveToModel(model, 'F') // non-trivial start
    const before = modelToFacelets(model)
    model = applyMoveToModel(model, 'R')
    expect(modelToFacelets(model)).not.toBe(before)
    model = applyMoveToModel(model, "R'")
    expect(modelToFacelets(model)).toBe(before)
  })

  it('m2 equals m applied twice, for every face', () => {
    for (const face of ['U', 'R', 'F', 'D', 'L', 'B']) {
      const twice = applyMoveToModel(applyMoveToModel(buildCubies(solvedFacelets), face), face)
      const double = applyMoveToModel(buildCubies(solvedFacelets), `${face}2`)
      expect(modelToFacelets(double)).toBe(modelToFacelets(twice))
    }
  })

  it('U clockwise sends the F top row to L (frozen regression)', () => {
    const model = applyMoveToModel(buildCubies(solvedFacelets), 'U')
    const facelets = modelToFacelets(model)
    // L face top row (global indices 36,37,38) now shows F color
    expect(facelets.slice(36, 39)).toBe('FFF')
    // F face top row (18,19,20) now shows R color
    expect(facelets.slice(18, 21)).toBe('RRR')
  })

  it('preserves cubie identity by index', () => {
    const model = buildCubies(solvedFacelets)
    const idx = findCubieIndexByPiece(model, 'DFR')
    const after = applyMoveToModel(model, 'R')
    // same index still names the white-green-orange corner, now moved
    const colors = Object.values(after[idx].stickers).sort().join('')
    expect(colors).toBe('DFR')
  })
})

describe('findCubieIndexByPiece', () => {
  it('finds corners and edges by their solved-slot color set on scrambled states', () => {
    let model = buildCubies(solvedFacelets)
    for (const m of parseSequence("F R U R' U' F' D2 L'")) {
      model = applyMoveToModel(model, m)
    }
    const cornerIdx = findCubieIndexByPiece(model, 'DFR')
    expect(cornerIdx).toBeGreaterThanOrEqual(0)
    expect(Object.values(model[cornerIdx].stickers).sort().join('')).toBe('DFR')
    const edgeIdx = findCubieIndexByPiece(model, 'UF')
    expect(edgeIdx).toBeGreaterThanOrEqual(0)
    expect(Object.values(model[edgeIdx].stickers).sort().join('')).toBe('FU')
  })

  it('returns -1 for a nonexistent piece', () => {
    const model = buildCubies(solvedFacelets)
    expect(findCubieIndexByPiece(model, 'UD')).toBe(-1)
  })
})
