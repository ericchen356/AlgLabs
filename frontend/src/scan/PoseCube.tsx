/**
 * PoseCube — the scan instruction card's pose diagram (design handoff §3 +
 * ⚠️ note 1): a small REAL Three.js CubeView showing a solved cube
 * re-oriented so the face being scanned points toward the camera, plus a
 * caption naming the motion that reaches the pose. Replaces the old
 * FaceDiagram SVG.
 */

import { useEffect, useRef } from 'react'
import CubeView, { type CubeViewHandle } from '../CubeView'
import { MOTION_CAPTION, POSE_FACELETS } from './poses'
import type { ScanStep } from './steps'

export default function PoseCube({ step }: { step: ScanStep }) {
  const cubeRef = useRef<CubeViewHandle>(null)

  useEffect(() => {
    cubeRef.current?.setState(POSE_FACELETS[step.face])
  }, [step.face])

  return (
    <div className="pose-cube" role="img" aria-label={`Camera should see the ${step.colorName} face`}>
      <div className="pose-cube-stage">
        <CubeView ref={cubeRef} className="pose-cube-view" />
      </div>
      <div className="pose-caption">{MOTION_CAPTION[step.motion]}</div>
    </div>
  )
}
