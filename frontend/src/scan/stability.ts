/**
 * Client-side stability detection for the scanner (CONTRACTS.md §9.5) —
 * pure math, no DOM, so it is unit-testable under vitest's node environment.
 *
 * Each animation frame the scanner samples the 9 cell centers of the guide
 * box and pushes them here. The tracker keeps the last `windowSize` frames;
 * the stream is "steady" once the window is full and the max per-cell,
 * per-channel RGB variance is strictly below `varianceThreshold`. After
 * `steadyMs` of continuous steadiness the tracker reports `shouldCapture`.
 */

import type { FaceLetter } from '../types'

/** One sampled cell color, 0–255 per channel. */
export type RGB = readonly [number, number, number]

export interface StabilityConfig {
  /** Number of most-recent frames considered (§9.5: 8). */
  windowSize: number
  /** Steady when max per-cell channel variance is strictly below this. */
  varianceThreshold: number
  /** Continuous steady time (ms) required before auto-capture. */
  steadyMs: number
}

export const DEFAULT_STABILITY: StabilityConfig = {
  windowSize: 8,
  varianceThreshold: 120,
  steadyMs: 400,
}

export interface StabilityStatus {
  /** True once `windowSize` frames have been seen since the last reset. */
  windowFull: boolean
  /** Max per-cell per-channel variance over the window (Infinity until full). */
  maxVariance: number
  /** Window full and variance below the threshold. */
  steady: boolean
  /** How long (ms) the stream has been continuously steady. */
  steadyForMs: number
  /** steady for at least `steadyMs` — fire the auto-capture. */
  shouldCapture: boolean
}

/**
 * Max population variance of any single channel of any cell across frames.
 * All frames must have the same cell count.
 */
export function maxCellVariance(frames: readonly (readonly RGB[])[]): number {
  if (frames.length === 0) return 0
  const n = frames.length
  const cells = frames[0].length
  let worst = 0
  for (let cell = 0; cell < cells; cell++) {
    for (let ch = 0; ch < 3; ch++) {
      let sum = 0
      let sumSq = 0
      for (let f = 0; f < n; f++) {
        const v = frames[f][cell][ch]
        sum += v
        sumSq += v * v
      }
      const mean = sum / n
      const variance = sumSq / n - mean * mean
      if (variance > worst) worst = variance
    }
  }
  return worst
}

/** Ring buffer of recent frames + steady-duration bookkeeping. */
export class StabilityTracker {
  private readonly config: StabilityConfig
  private frames: (readonly RGB[])[] = []
  private steadySince: number | null = null

  constructor(config: StabilityConfig = DEFAULT_STABILITY) {
    this.config = config
  }

  /** Forget everything (call when the target face changes). */
  reset(): void {
    this.frames = []
    this.steadySince = null
  }

  /** Feed one frame of cell samples; `nowMs` is a monotonic timestamp. */
  push(cells: readonly RGB[], nowMs: number): StabilityStatus {
    this.frames.push(cells.map((c) => [c[0], c[1], c[2]] as const))
    if (this.frames.length > this.config.windowSize) this.frames.shift()

    const windowFull = this.frames.length >= this.config.windowSize
    const maxVariance = windowFull ? maxCellVariance(this.frames) : Number.POSITIVE_INFINITY
    const steady = windowFull && maxVariance < this.config.varianceThreshold

    if (!steady) {
      this.steadySince = null
    } else if (this.steadySince === null) {
      this.steadySince = nowMs
    }
    const steadyForMs = this.steadySince === null ? 0 : nowMs - this.steadySince

    return {
      windowFull,
      maxVariance,
      steady,
      steadyForMs,
      shouldCapture: steady && steadyForMs >= this.config.steadyMs,
    }
  }
}

// ---------------------------------------------------------------------------
// Cheap expected-color check for the center cell (§9.5). This only gates the
// AUTO-capture — the manual capture button never consults it — so the ranges
// are deliberately loose. If it proves brittle in real lighting, loosening or
// removing the gate is safe (auto-capture would just fire on any steady view).
// ---------------------------------------------------------------------------

/** RGB (0–255) → HSV with h in degrees [0, 360) and s, v in [0, 1]. */
export function rgbToHsv([r, g, b]: RGB): { h: number; s: number; v: number } {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const delta = max - min
  let h = 0
  if (delta > 0) {
    if (max === rn) h = 60 * (((gn - bn) / delta + 6) % 6)
    else if (max === gn) h = 60 * ((bn - rn) / delta + 2)
    else h = 60 * ((rn - gn) / delta + 4)
  }
  return { h, s: max === 0 ? 0 : delta / max, v: max }
}

/**
 * Does this color roughly belong to the given face's color family (§2.1)?
 * Loose hue-band check; white is the low-saturation family.
 */
export function hueMatchesFace(rgb: RGB, face: FaceLetter): boolean {
  const { h, s, v } = rgbToHsv(rgb)
  switch (face) {
    case 'D': // white
      return s < 0.35 && v > 0.4
    case 'U': // yellow
      return s >= 0.25 && h >= 35 && h <= 80
    case 'R': // orange
      return s >= 0.35 && h >= 8 && h <= 45
    case 'F': // green
      return s >= 0.2 && h >= 70 && h <= 180
    case 'L': // red
      return s >= 0.35 && (h <= 18 || h >= 335)
    case 'B': // blue
      return s >= 0.2 && h >= 180 && h <= 270
  }
}
