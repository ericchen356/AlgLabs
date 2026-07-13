/**
 * TypeScript mirrors of the AlgLabs API schemas (docs/CONTRACTS.md §8).
 *
 * Facelet strings are 54 chars, face order U,R,F,D,L,B, 9 stickers per face,
 * characters are face letters (U R F D L B), never color names.
 */

/** The six face letters, doubling as color letters (§2). */
export type FaceLetter = 'U' | 'R' | 'F' | 'D' | 'L' | 'B'

/** A piece to glow during a step; `piece` names the cubie by its SOLVED slot. */
export interface Highlight {
  type: 'edge' | 'corner'
  piece: string
}

/** One walkthrough step (a labelled burst of moves). */
export interface Step {
  /** Human label, e.g. "F2L pair 2 (BR slot)". */
  label: string
  /** Case name, e.g. "OLL 27 — Sune" or "PLL T"; null when not applicable. */
  case: string | null
  /** Face turns only — always among the 18 tokens. */
  moves: string[]
  /** The same moves as a single space-separated string. */
  notation: string
  /** Index of this step's first move in the flat, whole-solve move list. */
  move_offset: number
  skipped: boolean
  highlight: Highlight[]
}

export type StageId = 'cross' | 'f2l' | 'oll' | 'pll'

export interface Stage {
  id: StageId
  label: string
  steps: Step[]
}

/** 200 response of POST /api/solve. */
export interface SolveResponse {
  valid: true
  facelets: string
  total_moves: number
  stages: Stage[]
}

/** One §5 validation error entry. */
export interface ValidationError {
  code: string
  message: string
  /**
   * Implicated 0-based global facelet indices. Absent on /api/classify 400
   * entries (indistinct_centers / center_mismatch), which only name faces.
   */
  facelets?: number[]
  /** Faces containing the implicated facelets. */
  suspect_faces: string[]
}

/** 400 response of POST /api/solve (invalid cube). */
export interface SolveErrorResponse {
  valid: false
  errors: ValidationError[]
}

/** Response of GET /api/scramble. */
export interface ScrambleResponse {
  facelets: string
  scramble: string
}

/** Response of POST /api/scan-face. */
export interface ScanFaceResponse {
  face: FaceLetter
  /** 9 × [L, a, b] in row-major cell order (§6). */
  samples_lab: number[][]
  /** 9 × [r, g, b]. */
  samples_rgb: number[][]
  quality: {
    ok: boolean
    noisy_cells: number[]
    message: string
  }
}

/** Response of POST /api/classify. */
export interface ClassifyResponse {
  facelets: string
  colors: Record<FaceLetter, string[]>
  confidence: Record<FaceLetter, number[]>
  ambiguous: { face: FaceLetter; index: number; margin: number }[]
  valid: boolean
  errors: ValidationError[]
}
