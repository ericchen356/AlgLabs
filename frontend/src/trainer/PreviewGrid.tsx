/**
 * Mini 2D case preview (§12.4): the §11.3 payload rendered as a 5×5-ish grid
 * — 3×3 U face with the four 1×3 side strips, empty corners. `x` cells are
 * dim; letters use the muted sticker palette variables from index.css.
 * Cell size is themable via the `--pv-cell` custom property.
 */

import { memo } from 'react'
import { previewGrid } from './preview'
import type { TrainerPreview } from './types'

interface PreviewGridProps {
  preview: TrainerPreview
  className?: string
}

const PreviewGrid = memo(function PreviewGrid({ preview, className }: PreviewGridProps) {
  const grid = previewGrid(preview)
  return (
    <span className={className ? `preview-grid ${className}` : 'preview-grid'} aria-hidden>
      {grid.flatMap((row, r) =>
        row.map((cell, c) => (
          <span
            key={r * 5 + c}
            className={cell === null ? 'pv-corner' : `pv-cell pv-${cell}`}
          />
        )),
      )}
    </span>
  )
})

export default PreviewGrid
