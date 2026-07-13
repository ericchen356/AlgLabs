/** Pose cube facelet strings match the §6 scan protocol poses. */
import { describe, expect, it } from 'vitest'
import { MOTION_CAPTION, POSE_FACELETS } from './poses'
import { SCAN_STEPS } from './steps'
import { FACE_ORDER, solvedFacelets } from './../cubeModel'
import type { FaceLetter } from '../types'

/** Letters of one face's 9-sticker block (§2 face order U R F D L B). */
function faceBlock(facelets: string, face: FaceLetter): string {
  const offset = FACE_ORDER.indexOf(face) * 9
  return facelets.slice(offset, offset + 9)
}

describe('POSE_FACELETS (§6 pose cube states)', () => {
  it('every pose is a whole-cube rotation of solved: 54 chars, uniform faces, 9 per letter', () => {
    for (const step of SCAN_STEPS) {
      const s = POSE_FACELETS[step.face]
      expect(s).toMatch(/^[URFDLB]{54}$/)
      const seen = new Set<string>()
      for (const face of FACE_ORDER) {
        const block = faceBlock(s, face)
        expect(block).toBe(block[0].repeat(9)) // uniform face
        seen.add(block[0])
      }
      expect(seen.size).toBe(6) // all six letters present once each
    }
  })

  it('the scanned face points toward the camera (CubeView front, F block)', () => {
    for (const step of SCAN_STEPS) {
      expect(faceBlock(POSE_FACELETS[step.face], 'F')).toBe(step.face.repeat(9))
    }
  })

  it('the up face (U block) matches each step pose from steps.ts', () => {
    for (const step of SCAN_STEPS) {
      expect(faceBlock(POSE_FACELETS[step.face], 'U')).toBe(step.upFace.repeat(9))
    }
  })

  it('yellow stays up for the four side poses (F R B L)', () => {
    for (const face of ['F', 'R', 'B', 'L'] as const) {
      expect(faceBlock(POSE_FACELETS[face], 'U')).toBe('U'.repeat(9))
    }
  })

  it('matches the hand-derived strings for home, y, x′ and x poses', () => {
    // F scan = home = solved.
    expect(POSE_FACELETS.F).toBe(solvedFacelets)
    // R scan = y: R to front, B to right, L to back, F to left.
    expect(POSE_FACELETS.R).toBe(
      'U'.repeat(9) + 'B'.repeat(9) + 'R'.repeat(9) + 'D'.repeat(9) + 'F'.repeat(9) + 'L'.repeat(9),
    )
    // U scan = x': yellow to camera, blue up, white behind.
    expect(POSE_FACELETS.U).toBe(
      'B'.repeat(9) + 'R'.repeat(9) + 'U'.repeat(9) + 'F'.repeat(9) + 'L'.repeat(9) + 'D'.repeat(9),
    )
    // D scan = x: white to camera, green up, yellow behind.
    expect(POSE_FACELETS.D).toBe(
      'F'.repeat(9) + 'R'.repeat(9) + 'D'.repeat(9) + 'B'.repeat(9) + 'L'.repeat(9) + 'U'.repeat(9),
    )
  })

  it('names a motion caption for every scan step', () => {
    for (const step of SCAN_STEPS) {
      expect(MOTION_CAPTION[step.motion]).toBeTruthy()
    }
  })
})
