/**
 * Pose facelet strings for the scan-step pose cube (CONTRACTS.md §6 + §12
 * design handoff, Scan screen).
 *
 * The instruction card shows a small REAL CubeView of a solved cube
 * re-oriented so the face currently being scanned points toward the camera
 * (CubeView's front, +z). CubeView paints any 54-char facelet string without
 * validation, so each pose is just "solved, whole-cube rotated": every face
 * shows one uniform letter. The strings are derived here from the §6 scan
 * protocol motions and locked by unit tests (poses.test.ts) against
 * hand-derived expectations and the SCAN_STEPS up-face data.
 *
 * Whole-cube rotations from the home pose (yellow up, green front):
 *   F: identity · R: y · B: y² · L: y³ (y = like U: F→L, keeps yellow up)
 *   U: x' (tilt toward you: yellow to camera, blue up)
 *   D: x  (net tilt away: white to camera, green up)
 */

import type { FaceLetter } from '../types'
import { FACE_NORMAL, FACE_ORDER } from '../cubeModel'
import type { ScanMotion } from './steps'

type Vec3 = readonly [number, number, number]

/**
 * One 90° whole-cube rotation step, same handedness as cubeModel's
 * rotateVecOnce: x is the speedcubing x (like R: F→U), y is the speedcubing
 * y (like U: F→L).
 */
const rotX = ([x, y, z]: Vec3): Vec3 => [x, z, -y]
const rotY = ([x, y, z]: Vec3): Vec3 => [-z, y, x]

/** Whole-cube rotation (as normal-vector steps) from home to each scan pose. */
const POSE_ROTATION: Record<FaceLetter, readonly ((v: Vec3) => Vec3)[]> = {
  F: [],
  R: [rotY],
  B: [rotY, rotY],
  L: [rotY, rotY, rotY],
  U: [rotX, rotX, rotX], // x' as three x steps
  D: [rotX],
}

function samePos(a: Vec3, b: Vec3): boolean {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2]
}

/**
 * Facelet string of a solved cube under a whole-cube rotation: face m shows
 * the (uniform) letter of the home face whose normal the rotation carries
 * onto m's normal.
 */
function poseFacelets(rotation: readonly ((v: Vec3) => Vec3)[]): string {
  let out = ''
  for (const m of FACE_ORDER) {
    const shown = FACE_ORDER.find((f) =>
      samePos(
        rotation.reduce<Vec3>((v, rot) => rot(v), FACE_NORMAL[f]),
        FACE_NORMAL[m],
      ),
    )
    if (!shown) throw new Error(`Pose rotation is not a cube rotation (face ${m})`) // unreachable
    out += shown.repeat(9)
  }
  return out
}

/**
 * Scanned face → 54-char facelet string putting that face toward the camera
 * (yellow stays up for the four side poses, per the §6 protocol).
 */
export const POSE_FACELETS: Record<FaceLetter, string> = Object.fromEntries(
  (Object.entries(POSE_ROTATION) as [FaceLetter, readonly ((v: Vec3) => Vec3)[]][]).map(
    ([face, rotation]) => [face, poseFacelets(rotation)],
  ),
) as Record<FaceLetter, string>

/** Short caption naming the motion that reaches a step's pose. */
export const MOTION_CAPTION: Record<ScanMotion, string> = {
  start: 'hold: yellow up · green to camera',
  yLeft: 'motion: turn 90° to the left',
  tiltToward: 'motion: turn left once more, then tilt toward you',
  tiltAway2: 'motion: tilt away from you, twice',
}
