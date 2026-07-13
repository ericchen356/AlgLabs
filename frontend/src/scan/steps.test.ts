/** Guided sequence data matches the §6 scan protocol table. */
import { describe, expect, it } from 'vitest'
import { SCAN_STEPS, faceLabel } from './steps'
import { COLOR_HEX } from '../cubeModel'
import type { FaceLetter } from '../types'

const COLOR_NAMES: Record<FaceLetter, string> = {
  U: 'yellow',
  R: 'orange',
  F: 'green',
  D: 'white',
  L: 'red',
  B: 'blue',
}

describe('SCAN_STEPS (§6 guided sequence)', () => {
  it('scans the six faces in the §6 order F, R, B, L, U, D', () => {
    expect(SCAN_STEPS.map((s) => s.face)).toEqual(['F', 'R', 'B', 'L', 'U', 'D'])
  })

  it('expected center color per step matches the §2.1 scheme', () => {
    for (const step of SCAN_STEPS) {
      expect(step.hex).toBe(COLOR_HEX[step.face])
      expect(step.colorName).toBe(COLOR_NAMES[step.face])
    }
  })

  it('records the §6 motions: start, then three y-turns, tilt toward, tilt away twice', () => {
    expect(SCAN_STEPS.map((s) => s.motion)).toEqual([
      'start',
      'yLeft',
      'yLeft',
      'yLeft',
      'tiltToward',
      'tiltAway2',
    ])
  })

  it('tracks the up-face per pose (yellow up for sides; B up scanning U; F up scanning D)', () => {
    for (const step of SCAN_STEPS.slice(0, 4)) expect(step.upFace).toBe('U')
    expect(SCAN_STEPS[4].upFace).toBe('B')
    expect(SCAN_STEPS[5].upFace).toBe('F')
  })

  it('faceLabel names a face with its color word', () => {
    expect(faceLabel('F')).toBe('F (green)')
    expect(faceLabel('D')).toBe('D (white)')
  })
})
