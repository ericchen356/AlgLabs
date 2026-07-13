/**
 * Move notation for the 18 face-turn tokens (CONTRACTS.md §4 / §9).
 *
 * Only the 18 face turns exist here — the backend rewrites rotations, wide
 * and slice moves before they ever reach the frontend.
 *
 * Conventions:
 * - axes: +x = R, +y = U, +z = F (§9.2)
 * - `layer` selects the turned slice along the axis: +1 (U/R/F) or -1 (D/L/B)
 * - `quarterTurns` is clockwise-positive **as viewed looking at that face
 *   from outside the cube**: 1 = 90° cw, -1 = 90° ccw (a `'` token), 2 = 180°.
 */

import type { FaceLetter } from './types'

export type Axis = 'x' | 'y' | 'z'

export interface Move {
  face: FaceLetter
  axis: Axis
  layer: -1 | 1
  quarterTurns: 1 | -1 | 2
}

/** Geometry of each face: rotation axis and the coordinate of its layer. */
const FACE_GEOMETRY: Record<FaceLetter, { axis: Axis; layer: -1 | 1 }> = {
  U: { axis: 'y', layer: 1 },
  D: { axis: 'y', layer: -1 },
  R: { axis: 'x', layer: 1 },
  L: { axis: 'x', layer: -1 },
  F: { axis: 'z', layer: 1 },
  B: { axis: 'z', layer: -1 },
}

/** Index of an axis into an [x, y, z] tuple. */
export const AXIS_INDEX: Record<Axis, 0 | 1 | 2> = { x: 0, y: 1, z: 2 }

const TOKEN_RE = /^([URFDLB])(['2]?)$/

/** All 18 valid tokens, for reference and tests. */
export const ALL_TOKENS: readonly string[] = (
  ['U', 'D', 'L', 'R', 'F', 'B'] as const
).flatMap((f) => [f, `${f}'`, `${f}2`])

/**
 * Parse one of the 18 tokens (e.g. "R", "U'", "F2").
 * Throws on anything else.
 */
export function parseMove(token: string): Move {
  const m = TOKEN_RE.exec(token)
  if (!m) throw new Error(`Invalid move token: ${JSON.stringify(token)}`)
  const face = m[1] as FaceLetter
  const suffix = m[2]
  const quarterTurns: 1 | -1 | 2 = suffix === "'" ? -1 : suffix === '2' ? 2 : 1
  const { axis, layer } = FACE_GEOMETRY[face]
  return { face, axis, layer, quarterTurns }
}

/** Parse a whitespace-separated sequence of tokens. Throws on garbage. */
export function parseSequence(s: string): Move[] {
  return s
    .split(/\s+/)
    .filter((t) => t.length > 0)
    .map(parseMove)
}

/** Serialize a Move back to its token. */
export function moveToString(move: Move): string {
  const suffix = move.quarterTurns === 2 ? '2' : move.quarterTurns === -1 ? "'" : ''
  return move.face + suffix
}

/** Serialize a sequence of moves to notation. */
export function sequenceToString(moves: readonly Move[]): string {
  return moves.map(moveToString).join(' ')
}

/** Inverse of a single move (R -> R', R2 -> R2). */
export function invertMove(move: Move): Move {
  const quarterTurns: 1 | -1 | 2 =
    move.quarterTurns === 2 ? 2 : move.quarterTurns === 1 ? -1 : 1
  return { ...move, quarterTurns }
}

/** Inverse of a sequence: reversed order, each move inverted. */
export function invertSequence(moves: readonly Move[]): Move[] {
  return [...moves].reverse().map(invertMove)
}
