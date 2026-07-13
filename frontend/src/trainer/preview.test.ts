/** T18 — preview-grid mapping from the §11.3 payload to the above-view diagram. */
import { describe, expect, it } from 'vitest'
import type { FaceLetter } from '../types'
import { applyMovesToFacelets, buildCubies, solvedFacelets, type Cubie, type Vec3 } from '../cubeModel'
import { parseSequence } from '../notation'
import { previewGrid } from './preview'
import type { TrainerPreview } from './types'

/** Build a §11.3 payload from a facelet string (§2 offsets: U=0 R=9 F=18 L=36 B=45). */
function stripsFromFacelets(s: string): TrainerPreview {
  return {
    u: [...s.slice(0, 9)],
    r: [...s.slice(9, 12)],
    f: [...s.slice(18, 21)],
    l: [...s.slice(36, 39)],
    b: [...s.slice(45, 48)],
  }
}

function stickerAt(cubies: readonly Cubie[], pos: Vec3, face: FaceLetter): FaceLetter {
  const c = cubies.find(
    (c) => c.position[0] === pos[0] && c.position[1] === pos[1] && c.position[2] === pos[2],
  )
  const letter = c?.stickers[face]
  if (!letter) throw new Error(`no ${face} sticker at ${pos.join(',')}`)
  return letter
}

describe('previewGrid geometry (5×5 above-view)', () => {
  it('lays out the solved payload with empty corners and correct strips', () => {
    const grid = previewGrid(stripsFromFacelets(solvedFacelets))
    expect(grid).toEqual([
      [null, 'B', 'B', 'B', null],
      ['L', 'U', 'U', 'U', 'R'],
      ['L', 'U', 'U', 'U', 'R'],
      ['L', 'U', 'U', 'U', 'R'],
      [null, 'F', 'F', 'F', null],
    ])
  })

  it('passes "x" (recognition-irrelevant) cells through for OLL-style payloads', () => {
    // OLL 27 (Sune)-like orientation diagram.
    const p: TrainerPreview = {
      u: ['x', 'x', 'U', 'U', 'U', 'U', 'U', 'x', 'x'],
      f: ['x', 'x', 'U'],
      r: ['U', 'x', 'x'],
      b: ['x', 'x', 'U'],
      l: ['U', 'x', 'x'],
    }
    const grid = previewGrid(p)
    expect(grid[0]).toEqual([null, 'U', 'x', 'x', null]) // top strip = b reversed
    expect(grid[1]).toEqual(['U', 'x', 'x', 'U', 'x']) // right col row 1 = r[2]
    expect(grid[4]).toEqual([null, 'x', 'x', 'U', null]) // bottom strip = f in order
    expect(grid.flat().filter((c) => c === 'x')).toHaveLength(12)
  })

  /**
   * Cross-check against the cube model (§2/§9.2 geometry): every cell of the
   * grid must equal the sticker of the cubie physically at that above-view
   * position — U cells face U, and each strip cell faces its side. This pins
   * the left↔right flips of the B and R strips to the real geometry instead
   * of to hand-written expectations.
   */
  it('matches the physical above-view of a scrambled cube', () => {
    const facelets = applyMovesToFacelets(
      solvedFacelets,
      parseSequence("R U R' U' F2 B L D' R2 U"),
    )
    const cubies = buildCubies(facelets)
    const grid = previewGrid(stripsFromFacelets(facelets))

    // Above-view axes: grid col → x = col - 2, grid row → z = row - 2.
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 3; c++) {
        expect(grid[r + 1][c + 1]).toBe(stickerAt(cubies, [c - 1, 1, r - 1], 'U'))
      }
    }
    for (let c = 0; c < 3; c++) {
      expect(grid[0][c + 1]).toBe(stickerAt(cubies, [c - 1, 1, -1], 'B')) // top strip
      expect(grid[4][c + 1]).toBe(stickerAt(cubies, [c - 1, 1, 1], 'F')) // bottom strip
    }
    for (let r = 0; r < 3; r++) {
      expect(grid[r + 1][0]).toBe(stickerAt(cubies, [-1, 1, r - 1], 'L')) // left strip
      expect(grid[r + 1][4]).toBe(stickerAt(cubies, [1, 1, r - 1], 'R')) // right strip
    }

    // And the four corners stay empty.
    for (const [r, c] of [
      [0, 0],
      [0, 4],
      [4, 0],
      [4, 4],
    ]) {
      expect(grid[r][c]).toBeNull()
    }
  })
})
