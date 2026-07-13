/**
 * CubeView — plain three.js cube renderer inside a React component (§9.3).
 *
 * Rendering is driven by the LOGICAL model in cubeModel.ts (integer grid
 * positions + exact 90° sticker-normal rotations). Animations tween a pivot
 * Object3D, then every affected transform is snapped back from the logical
 * model — float rotations are never accumulated, so the view cannot drift.
 *
 * Imperative API (via ref):
 *   setState(facelets)            — rebuild from a facelet string, instantly
 *   playMove(move, durationMs)    — animate one move; rejects while animating
 *   setHighlights(descriptors)    — emissive pulse on the named pieces (§9.4)
 *   reset()                       — back to the last setState facelets
 */

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { Highlight } from './types'
import { AXIS_INDEX, parseMove, type Move } from './notation'
import {
  applyMoveToModel,
  buildCubies,
  COLOR_HEX,
  FACE_NORMAL,
  findCubieIndexByPiece,
  solvedFacelets,
  type Cubie,
} from './cubeModel'

export interface CubeViewHandle {
  setState(facelets: string): void
  playMove(move: Move | string, durationMs?: number): Promise<void>
  setHighlights(descriptors: Highlight[]): void
  reset(): void
}

interface CubeViewProps {
  className?: string
}

const CUBIE_SIZE = 0.94
const STICKER_SIZE = 0.8
const STICKER_OFFSET = CUBIE_SIZE / 2 + 0.006

interface ActiveAnimation {
  pivot: THREE.Group
  groups: THREE.Group[]
  move: Move
  axis: Move['axis']
  /** Total signed rotation angle (radians) about the +axis. */
  angle: number
  start: number
  duration: number
  resolve: () => void
}

interface Internals {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  controls: OrbitControls
  boxGeometry: THREE.BoxGeometry
  stickerGeometry: THREE.PlaneGeometry
  boxMaterial: THREE.MeshStandardMaterial
  model: Cubie[]
  lastSetFacelets: string
  groups: THREE.Group[]
  /** Per-group sticker materials, for highlight pulsing. */
  stickerMaterials: THREE.MeshStandardMaterial[][]
  highlightDescriptors: Highlight[]
  highlightedIndices: Set<number>
  anim: ActiveAnimation | null
  observer: ResizeObserver
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

/** Signed pivot angle for a move: −90° right-handed per clockwise quarter. */
function moveAngle(move: Move): number {
  return (-Math.PI / 2) * move.quarterTurns * move.layer
}

function setAxisRotation(obj: THREE.Object3D, axis: Move['axis'], angle: number): void {
  obj.rotation.set(0, 0, 0)
  obj.rotation[axis] = angle
}

/** Rebuild one cubie group's transform + sticker meshes from the logical model. */
function syncGroup(int: Internals, i: number): void {
  const group = int.groups[i]
  const cubie = int.model[i]
  group.position.set(cubie.position[0], cubie.position[1], cubie.position[2])
  group.quaternion.identity()
  group.rotation.set(0, 0, 0)
  // remove old sticker meshes (keep the base box, child 0)
  const old = group.children.filter((c) => c.userData.isSticker)
  for (const mesh of old) {
    group.remove(mesh)
    const m = mesh as THREE.Mesh
    ;(m.material as THREE.Material).dispose()
  }
  const mats: THREE.MeshStandardMaterial[] = []
  for (const [face, color] of Object.entries(cubie.stickers)) {
    const normal = FACE_NORMAL[face as keyof typeof FACE_NORMAL]
    const material = new THREE.MeshStandardMaterial({
      color: COLOR_HEX[color],
      roughness: 0.35,
      metalness: 0.0,
    })
    const sticker = new THREE.Mesh(int.stickerGeometry, material)
    sticker.userData.isSticker = true
    const n = new THREE.Vector3(normal[0], normal[1], normal[2])
    sticker.position.copy(n).multiplyScalar(STICKER_OFFSET)
    sticker.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n)
    group.add(sticker)
    mats.push(material)
  }
  int.stickerMaterials[i] = mats
}

function syncAllGroups(int: Internals): void {
  for (let i = 0; i < int.groups.length; i++) syncGroup(int, i)
}

/** Re-resolve highlight descriptors to cubie indices on the current model. */
function refreshHighlights(int: Internals): void {
  const indices = int.highlightDescriptors
    .map((d) => findCubieIndexByPiece(int.model, d.piece))
    .filter((i) => i >= 0)
  int.highlightedIndices = new Set(indices)
}

/** Snap-complete the active animation: apply the move logically and resync. */
function completeAnimation(int: Internals): void {
  const anim = int.anim
  if (!anim) return
  int.anim = null
  for (const g of anim.groups) int.scene.attach(g)
  int.scene.remove(anim.pivot)
  int.model = applyMoveToModel(int.model, anim.move)
  syncAllGroups(int)
  refreshHighlights(int)
  anim.resolve()
}

const CubeView = forwardRef<CubeViewHandle, CubeViewProps>(function CubeView(
  { className },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const intRef = useRef<Internals | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
    // Initial view shows U/F/R — how the user holds the cube (§9.3).
    camera.position.set(4.1, 3.7, 5.1)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    container.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.enablePan = false
    controls.minDistance = 4.5
    controls.maxDistance = 14

    scene.add(new THREE.AmbientLight(0xffffff, 1.7))
    const key = new THREE.DirectionalLight(0xffffff, 1.3)
    key.position.set(5, 8, 6)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 0.5)
    fill.position.set(-5, -3, -6)
    scene.add(fill)

    const boxGeometry = new THREE.BoxGeometry(CUBIE_SIZE, CUBIE_SIZE, CUBIE_SIZE)
    const stickerGeometry = new THREE.PlaneGeometry(STICKER_SIZE, STICKER_SIZE)
    const boxMaterial = new THREE.MeshStandardMaterial({
      color: 0x14161c,
      roughness: 0.6,
      metalness: 0.1,
    })

    const model = buildCubies(solvedFacelets)
    const groups: THREE.Group[] = model.map(() => {
      const g = new THREE.Group()
      g.add(new THREE.Mesh(boxGeometry, boxMaterial))
      scene.add(g)
      return g
    })

    const applySize = () => {
      const w = Math.max(1, container.clientWidth)
      const h = Math.max(1, container.clientHeight)
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(applySize)
    observer.observe(container)
    // Size once synchronously too: ResizeObserver delivery is suspended in
    // hidden/background tabs, which would leave the canvas at its default
    // 600×300 attribute size until the tab becomes visible.
    applySize()

    const int: Internals = {
      scene,
      camera,
      renderer,
      controls,
      boxGeometry,
      stickerGeometry,
      boxMaterial,
      model,
      lastSetFacelets: solvedFacelets,
      groups,
      stickerMaterials: model.map(() => []),
      highlightDescriptors: [],
      highlightedIndices: new Set(),
      anim: null,
      observer,
    }
    intRef.current = int
    syncAllGroups(int)

    renderer.setAnimationLoop((time: number) => {
      const anim = int.anim
      if (anim) {
        const t = Math.min(1, (time - anim.start) / anim.duration)
        setAxisRotation(anim.pivot, anim.axis, anim.angle * easeInOutCubic(t))
        if (t >= 1) completeAnimation(int)
      }
      // Emissive pulse on highlighted pieces.
      const pulse = 0.25 + 0.3 * (Math.sin(time / 180) + 1) * 0.5
      for (let i = 0; i < int.groups.length; i++) {
        const hl = int.highlightedIndices.has(i)
        for (const mat of int.stickerMaterials[i]) {
          if (hl) {
            mat.emissive.copy(mat.color).multiplyScalar(pulse)
          } else if (mat.emissive.r !== 0 || mat.emissive.g !== 0 || mat.emissive.b !== 0) {
            mat.emissive.setRGB(0, 0, 0)
          }
        }
      }
      controls.update()
      renderer.render(scene, camera)
    })

    return () => {
      intRef.current = null
      renderer.setAnimationLoop(null)
      observer.disconnect()
      controls.dispose()
      boxGeometry.dispose()
      stickerGeometry.dispose()
      boxMaterial.dispose()
      for (const mats of int.stickerMaterials) for (const m of mats) m.dispose()
      renderer.dispose()
      container.removeChild(renderer.domElement)
    }
  }, [])

  useImperativeHandle(
    ref,
    (): CubeViewHandle => ({
      setState(facelets: string): void {
        const int = intRef.current
        if (!int) return
        completeAnimation(int)
        int.model = buildCubies(facelets)
        int.lastSetFacelets = facelets
        syncAllGroups(int)
        refreshHighlights(int)
      },

      playMove(move: Move | string, durationMs = 350): Promise<void> {
        const int = intRef.current
        if (!int) return Promise.reject(new Error('CubeView is not mounted'))
        if (int.anim) return Promise.reject(new Error('CubeView is already animating'))
        const m = typeof move === 'string' ? parseMove(move) : move
        if (durationMs <= 0) {
          int.model = applyMoveToModel(int.model, m)
          syncAllGroups(int)
          refreshHighlights(int)
          return Promise.resolve()
        }
        return new Promise<void>((resolve) => {
          const axisIdx = AXIS_INDEX[m.axis]
          const pivot = new THREE.Group()
          int.scene.add(pivot)
          int.scene.updateMatrixWorld(true)
          const layerGroups: THREE.Group[] = []
          for (let i = 0; i < int.model.length; i++) {
            if (int.model[i].position[axisIdx] === m.layer) {
              pivot.attach(int.groups[i])
              layerGroups.push(int.groups[i])
            }
          }
          int.anim = {
            pivot,
            groups: layerGroups,
            move: m,
            axis: m.axis,
            angle: moveAngle(m),
            start: performance.now(),
            duration: durationMs,
            resolve,
          }
        })
      },

      setHighlights(descriptors: Highlight[]): void {
        const int = intRef.current
        if (!int) return
        int.highlightDescriptors = descriptors
        refreshHighlights(int)
      },

      reset(): void {
        const int = intRef.current
        if (!int) return
        completeAnimation(int)
        int.model = buildCubies(int.lastSetFacelets)
        syncAllGroups(int)
        refreshHighlights(int)
      },
    }),
    [],
  )

  return <div ref={containerRef} className={className ?? 'cube-view'} />
})

export default CubeView
