/**
 * Logical cube model: facelet string <-> 26 cubie descriptors (CONTRACTS.md §9.2).
 *
 * Grid axes: +x = R, +y = U, +z = F. Cubies live at integer grid positions
 * (x, y, z) ∈ {-1, 0, 1}³ minus the origin. Every rotation here is an exact
 * logical 90° step on integers — no floats, so the model can never drift.
 */

import type { FaceLetter } from './types'
import { AXIS_INDEX, parseMove, type Move } from './notation'

export type Vec3 = readonly [number, number, number]

/**
 * One cubie: integer grid position plus a stickers map from the face the
 * sticker currently points at (its outward normal) to its color letter.
 */
export interface Cubie {
  position: Vec3
  stickers: Partial<Record<FaceLetter, FaceLetter>>
}

/** Face order in the facelet string, with global index offsets (§2). */
export const FACE_ORDER: readonly FaceLetter[] = ['U', 'R', 'F', 'D', 'L', 'B']

/**
 * Letter -> UI hex color: the muted "Paper Toy" sticker palette (§12.2 +
 * design handoff tokens). D-white (#FBF8F1) stays visible on the cream
 * canvas thanks to the existing gap/border rendering around stickers.
 */
export const COLOR_HEX: Record<FaceLetter, string> = {
  U: '#F0C64A', // yellow
  R: '#E8703A', // orange
  F: '#4E9E6B', // green
  D: '#FBF8F1', // white
  L: '#C1495B', // red
  B: '#3E6BA8', // blue
}

export const solvedFacelets: string =
  'UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB'

/** Outward unit normal of each face. */
export const FACE_NORMAL: Record<FaceLetter, Vec3> = {
  U: [0, 1, 0],
  D: [0, -1, 0],
  R: [1, 0, 0],
  L: [-1, 0, 0],
  F: [0, 0, 1],
  B: [0, 0, -1],
}

const NORMAL_TO_FACE = new Map<string, FaceLetter>(
  (Object.entries(FACE_NORMAL) as [FaceLetter, Vec3][]).map(([f, v]) => [
    v.join(','),
    f,
  ]),
)

function vecToFace(v: Vec3): FaceLetter {
  const f = NORMAL_TO_FACE.get(v.join(','))
  if (!f) throw new Error(`Not a face normal: ${v.join(',')}`)
  return f
}

/**
 * Grid position of sticker k (0-based, row-major per the §2 viewing
 * orientations) on a given face — the §9.2 table verbatim.
 */
export function stickerPosition(face: FaceLetter, k: number): Vec3 {
  const row = Math.floor(k / 3)
  const col = k % 3
  switch (face) {
    case 'U':
      return [col - 1, 1, row - 1]
    case 'D':
      return [col - 1, -1, 1 - row]
    case 'F':
      return [col - 1, 1 - row, 1]
    case 'B':
      return [1 - col, 1 - row, -1]
    case 'R':
      return [1, 1 - row, 1 - col]
    case 'L':
      return [-1, 1 - row, col - 1]
  }
}

interface FaceletGeometry {
  /** Grid position of the cubie carrying this facelet. */
  position: Vec3
  /** The face this facelet points at (its outward normal). */
  normal: FaceLetter
}

/** Precomputed geometry of all 54 global facelet indices. */
export const FACELET_GEOMETRY: readonly FaceletGeometry[] = FACE_ORDER.flatMap(
  (face) =>
    Array.from({ length: 9 }, (_, k) => ({
      position: stickerPosition(face, k),
      normal: face,
    })),
)

function posKey(p: Vec3): string {
  return `${p[0]},${p[1]},${p[2]}`
}

const LETTER_RE = /^[URFDLB]{54}$/

/**
 * Build the 26-cubie model from a facelet string.
 *
 * The returned array order is stable (fixed grid enumeration), and — because
 * `applyMoveToModel` preserves array order — index i always names the same
 * physical piece across moves.
 */
export function buildCubies(facelets: string): Cubie[] {
  if (!LETTER_RE.test(facelets)) {
    throw new Error(
      `Facelet string must be 54 characters over {U,R,F,D,L,B} (got ${facelets.length} chars)`,
    )
  }
  const cubies: Cubie[] = []
  const byPos = new Map<string, Cubie>()
  for (const x of [-1, 0, 1]) {
    for (const y of [-1, 0, 1]) {
      for (const z of [-1, 0, 1]) {
        if (x === 0 && y === 0 && z === 0) continue
        const cubie: Cubie = { position: [x, y, z], stickers: {} }
        cubies.push(cubie)
        byPos.set(posKey(cubie.position), cubie)
      }
    }
  }
  for (let i = 0; i < 54; i++) {
    const { position, normal } = FACELET_GEOMETRY[i]
    const cubie = byPos.get(posKey(position))
    if (!cubie) throw new Error(`No cubie at ${posKey(position)}`) // unreachable
    cubie.stickers[normal] = facelets[i] as FaceLetter
  }
  return cubies
}

/** Serialize a cubie model back to its 54-char facelet string. */
export function modelToFacelets(cubies: readonly Cubie[]): string {
  const byPos = new Map<string, Cubie>()
  for (const c of cubies) byPos.set(posKey(c.position), c)
  let out = ''
  for (let i = 0; i < 54; i++) {
    const { position, normal } = FACELET_GEOMETRY[i]
    const cubie = byPos.get(posKey(position))
    const letter = cubie?.stickers[normal]
    if (!letter) {
      throw new Error(`Missing sticker facing ${normal} at ${posKey(position)}`)
    }
    out += letter
  }
  return out
}

/**
 * Rotate a vector one 90° step about the given axis, in the direction that is
 * clockwise when looking at the axis' POSITIVE face from outside the cube
 * (i.e. −90° right-handed about the +axis). Integer-exact.
 */
function rotateVecOnce(v: Vec3, axis: Move['axis']): Vec3 {
  const [x, y, z] = v
  switch (axis) {
    case 'x':
      return [x, z, -y] // R clockwise: F -> U
    case 'y':
      return [-z, y, x] // U clockwise: F -> L
    case 'z':
      return [y, -x, z] // F clockwise: U -> R
  }
}

function rotateVec(v: Vec3, axis: Move['axis'], steps: number): Vec3 {
  const n = ((steps % 4) + 4) % 4
  let out = v
  for (let i = 0; i < n; i++) out = rotateVecOnce(out, axis)
  return out
}

/**
 * Number of positive-face-clockwise quarter steps a move performs.
 * A clockwise turn of a negative-layer face (D/L/B) is the opposite spin
 * about the axis, hence the multiplication by `layer`.
 */
function moveSteps(move: Move): number {
  return move.quarterTurns * move.layer
}

/** Rotate one cubie by a move: exact 90° steps on position and normals. */
export function rotateCubie(cubie: Cubie, move: Move): Cubie {
  const steps = moveSteps(move)
  const position = rotateVec(cubie.position, move.axis, steps)
  const stickers: Cubie['stickers'] = {}
  for (const [dir, color] of Object.entries(cubie.stickers) as [
    FaceLetter,
    FaceLetter,
  ][]) {
    stickers[vecToFace(rotateVec(FACE_NORMAL[dir], move.axis, steps))] = color
  }
  return { position, stickers }
}

/**
 * Apply one move to the model, returning a new array (same order, so cubie
 * identity by index is preserved). Untouched cubies are shared, not copied.
 */
export function applyMoveToModel(
  cubies: readonly Cubie[],
  move: Move | string,
): Cubie[] {
  const m = typeof move === 'string' ? parseMove(move) : move
  const axisIdx = AXIS_INDEX[m.axis]
  return cubies.map((c) => (c.position[axisIdx] === m.layer ? rotateCubie(c, m) : c))
}

/** Fold a move sequence over a facelet string. */
export function applyMovesToFacelets(
  facelets: string,
  moves: readonly (Move | string)[],
): string {
  let model = buildCubies(facelets)
  for (const m of moves) model = applyMoveToModel(model, m)
  return modelToFacelets(model)
}

/**
 * Piece finder (§9.4): a highlight descriptor names a cubie by its SOLVED
 * slot (e.g. corner "DFR"), which identifies it by its sticker color SET
 * {color(D), color(F), color(R)}. Since colors are face letters, that set is
 * exactly the letters of the slot name. Returns the model index of the cubie
 * whose sticker colors match, or -1 if none (invalid descriptor).
 */
export function findCubieIndexByPiece(
  cubies: readonly Cubie[],
  piece: string,
): number {
  const target = [...piece].sort().join('')
  return cubies.findIndex((c) => {
    const colors = Object.values(c.stickers)
    return colors.length === piece.length && [...colors].sort().join('') === target
  })
}
