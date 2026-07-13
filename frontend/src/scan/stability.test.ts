/** Stability window math (§9.5): ring-buffer variance + steady-duration logic. */
import { describe, expect, it } from 'vitest'
import {
  StabilityTracker,
  hueMatchesFace,
  maxCellVariance,
  rgbToHsv,
  type RGB,
  type StabilityStatus,
} from './stability'
import { COLOR_HEX, FACE_ORDER } from '../cubeModel'

const CFG = { windowSize: 8, varianceThreshold: 100, steadyMs: 400 }

/** 9 identical gray cells of value v. */
const frame = (v: number): RGB[] => Array.from({ length: 9 }, () => [v, v, v] as const)

const hexToRgb = (hex: string): RGB => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
]

describe('StabilityTracker', () => {
  it('a steady stream becomes stable only once the window fills', () => {
    const t = new StabilityTracker(CFG)
    for (let i = 0; i < 7; i++) {
      const s = t.push(frame(120), i * 100)
      expect(s.windowFull).toBe(false)
      expect(s.steady).toBe(false)
    }
    const s = t.push(frame(120), 700)
    expect(s.windowFull).toBe(true)
    expect(s.steady).toBe(true)
    expect(s.maxVariance).toBe(0)
    expect(s.shouldCapture).toBe(false) // steady just began
  })

  it('fires shouldCapture only after steadyMs of continuous steadiness', () => {
    const t = new StabilityTracker(CFG)
    let s: StabilityStatus | undefined
    for (let i = 0; i < 8; i++) s = t.push(frame(120), i * 100) // steady at t=700
    expect(s?.steadyForMs).toBe(0)
    expect(t.push(frame(120), 1000).shouldCapture).toBe(false) // 300 ms steady
    const fired = t.push(frame(120), 1100) // 400 ms steady
    expect(fired.steadyForMs).toBe(400)
    expect(fired.shouldCapture).toBe(true)
  })

  it('a spike resets steadiness until it leaves the window', () => {
    const t = new StabilityTracker(CFG)
    for (let i = 0; i < 12; i++) t.push(frame(120), i * 100)
    const spike = t.push(frame(220), 1200)
    expect(spike.steady).toBe(false)
    expect(spike.steadyForMs).toBe(0)
    // The spike frame stays inside the 8-frame window for 7 more pushes.
    for (let i = 0; i < 7; i++) {
      expect(t.push(frame(120), 1300 + i * 100).steady).toBe(false)
    }
    const recovered = t.push(frame(120), 2000)
    expect(recovered.steady).toBe(true)
    expect(recovered.steadyForMs).toBe(0) // duration restarted from scratch
    expect(recovered.shouldCapture).toBe(false)
  })

  it('variance exactly at the threshold is NOT steady (strict less-than)', () => {
    // Alternating 0/20 over 8 frames: per-channel variance = ((20-0)/2)^2 = 100.
    const t = new StabilityTracker(CFG)
    let s: StabilityStatus | undefined
    for (let i = 0; i < 8; i++) s = t.push(frame(i % 2 === 0 ? 0 : 20), i * 100)
    expect(s?.maxVariance).toBeCloseTo(100, 6)
    expect(s?.steady).toBe(false)
  })

  it('variance just below the threshold is steady', () => {
    // Alternating 0/18: variance = 81 < 100.
    const t = new StabilityTracker(CFG)
    let s: StabilityStatus | undefined
    for (let i = 0; i < 8; i++) s = t.push(frame(i % 2 === 0 ? 0 : 18), i * 100)
    expect(s?.maxVariance).toBeCloseTo(81, 6)
    expect(s?.steady).toBe(true)
  })

  it('reset clears the window and the steady duration', () => {
    const t = new StabilityTracker(CFG)
    for (let i = 0; i < 20; i++) t.push(frame(120), i * 100)
    t.reset()
    const s = t.push(frame(120), 5000)
    expect(s.windowFull).toBe(false)
    expect(s.steady).toBe(false)
  })
})

describe('maxCellVariance', () => {
  it('is zero for identical frames and empty input', () => {
    expect(maxCellVariance([])).toBe(0)
    expect(maxCellVariance([frame(80), frame(80), frame(80)])).toBe(0)
  })

  it('tracks the single worst channel of the worst cell', () => {
    // Only cell 6's blue channel alternates 0/30 → variance 225.
    const mk = (b: number): RGB[] =>
      frame(50).map((c, i) => (i === 6 ? ([50, 50, b] as const) : c))
    expect(maxCellVariance([mk(0), mk(30), mk(0), mk(30)])).toBeCloseTo(225, 6)
  })
})

describe('hueMatchesFace (cheap §9.5 center-color gate)', () => {
  it('each §2.1 color matches its own face', () => {
    for (const face of FACE_ORDER) {
      expect(hueMatchesFace(hexToRgb(COLOR_HEX[face]), face)).toBe(true)
    }
  })

  it('rejects the tricky neighbors', () => {
    expect(hueMatchesFace(hexToRgb(COLOR_HEX.L), 'R')).toBe(false) // red is not orange
    expect(hueMatchesFace(hexToRgb(COLOR_HEX.R), 'L')).toBe(false) // orange is not red
    expect(hueMatchesFace(hexToRgb(COLOR_HEX.U), 'D')).toBe(false) // yellow is not white
    expect(hueMatchesFace(hexToRgb(COLOR_HEX.F), 'B')).toBe(false) // green is not blue
    expect(hueMatchesFace(hexToRgb(COLOR_HEX.D), 'U')).toBe(false) // white is not yellow
  })

  it('rgbToHsv basics', () => {
    expect(rgbToHsv([0, 0, 0])).toEqual({ h: 0, s: 0, v: 0 })
    const white = rgbToHsv([255, 255, 255])
    expect(white.s).toBe(0)
    expect(white.v).toBe(1)
    expect(rgbToHsv([255, 0, 0]).h).toBeCloseTo(0, 6)
    expect(rgbToHsv([0, 255, 0]).h).toBeCloseTo(120, 6)
    expect(rgbToHsv([0, 0, 255]).h).toBeCloseTo(240, 6)
  })
})
