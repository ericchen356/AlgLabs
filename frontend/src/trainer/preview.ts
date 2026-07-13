/**
 * Pure mapping from the §11.3 preview payload to the classic above-view
 * diagram: a 5×5 grid whose middle 3×3 is the U face and whose edge strips
 * are the top rows of the four side faces, each placed as SEEN FROM ABOVE.
 *
 * The payload lists each side's top row left→right AS VIEWED FROM THAT FACE
 * (§11.3), so strips whose viewing direction opposes the above-view axis flip:
 *
 *  - B top row: B1 sits at grid (1,1,-1) — the back-RIGHT cubie — so the top
 *    strip drawn left→right is b[2] b[1] b[0].
 *  - R top row: R1 sits at (1,1,1) — the front-right cubie — so the right
 *    column drawn top→bottom (back→front) is r[2] r[1] r[0].
 *  - L and F line up with the above-view axes and stay in payload order.
 *
 * (Grid positions per cubeModel.stickerPosition / CONTRACTS §2 — the mapping
 * is cross-checked against the cube model in preview.test.ts.)
 */

import type { FaceLetter } from '../types'
import type { TrainerPreview } from './types'

/**
 * One cell of the 5×5 diagram: a face letter (muted sticker palette), `'x'`
 * (recognition-irrelevant, rendered dim), or null (the four empty corners).
 */
export type PreviewCell = FaceLetter | 'x' | null

/** Rows top→bottom, cells left→right, as seen from above the cube. */
export function previewGrid(p: TrainerPreview): PreviewCell[][] {
  const cell = (v: string): PreviewCell => (v === 'x' ? 'x' : (v as FaceLetter))
  const rows: PreviewCell[][] = [[null, cell(p.b[2]), cell(p.b[1]), cell(p.b[0]), null]]
  for (let r = 0; r < 3; r++) {
    rows.push([
      cell(p.l[r]),
      cell(p.u[r * 3]),
      cell(p.u[r * 3 + 1]),
      cell(p.u[r * 3 + 2]),
      cell(p.r[2 - r]),
    ])
  }
  rows.push([null, cell(p.f[0]), cell(p.f[1]), cell(p.f[2]), null])
  return rows
}
