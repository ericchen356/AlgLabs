/**
 * Guided scan sequence data (CONTRACTS.md §6).
 *
 * The user holds the cube yellow-up, green-front ("home") and shows faces to
 * the camera in the fixed order F → R → B → L → U → D. Each step records the
 * face letter the camera should be seeing, its color, which face points UP in
 * that pose (for the diagram), and the plain-language motion that gets there
 * from the previous step. The §6 key property (camera cells row-major =
 * facelet indices 1..9) depends on this exact protocol — do not reorder.
 */

import type { FaceLetter } from '../types'
import { COLOR_HEX } from '../cubeModel'

/** The cube motion performed to arrive at a step (drives the diagram arrow). */
export type ScanMotion = 'start' | 'yLeft' | 'tiltToward' | 'tiltAway2'

export interface ScanStep {
  /** Face the camera should be seeing during this step. */
  face: FaceLetter
  /** Its color word (§2.1). */
  colorName: string
  /** Its color hex (§2.1). */
  hex: string
  /** Which face of the cube points UP in this pose (for the diagram). */
  upFace: FaceLetter
  motion: ScanMotion
  /** Plain-language instruction to get here from the previous step. */
  instruction: string
}

export const SCAN_STEPS: readonly ScanStep[] = [
  {
    face: 'F',
    colorName: 'green',
    hex: COLOR_HEX.F,
    upFace: 'U',
    motion: 'start',
    instruction: 'Hold the cube with yellow on top and green facing the camera.',
  },
  {
    face: 'R',
    colorName: 'orange',
    hex: COLOR_HEX.R,
    upFace: 'U',
    motion: 'yLeft',
    instruction: 'Turn the whole cube 90° to the left, keeping yellow on top.',
  },
  {
    face: 'B',
    colorName: 'blue',
    hex: COLOR_HEX.B,
    upFace: 'U',
    motion: 'yLeft',
    instruction: 'Turn the whole cube 90° to the left again, keeping yellow on top.',
  },
  {
    face: 'L',
    colorName: 'red',
    hex: COLOR_HEX.L,
    upFace: 'U',
    motion: 'yLeft',
    instruction: 'Turn the whole cube 90° to the left again, keeping yellow on top.',
  },
  {
    face: 'U',
    colorName: 'yellow',
    hex: COLOR_HEX.U,
    upFace: 'B',
    motion: 'tiltToward',
    instruction:
      'Turn 90° to the left once more (green faces you again), then tilt the cube toward you so yellow faces the camera.',
  },
  {
    face: 'D',
    colorName: 'white',
    hex: COLOR_HEX.D,
    upFace: 'F',
    motion: 'tiltAway2',
    instruction: 'Tilt the cube away from you twice so white faces the camera.',
  },
]

/** "F (green)" style label used across the scanner UI. */
export function faceLabel(face: FaceLetter): string {
  const step = SCAN_STEPS.find((s) => s.face === face)
  return step ? `${step.face} (${step.colorName})` : face
}
