/**
 * Scanner — guided six-face webcam scan (CONTRACTS.md §6 + §9.5).
 *
 * For each SCAN_STEPS step (F → R → B → L → U → D) the UI shows the motion
 * instruction and a pose diagram, watches the guide box, and auto-captures
 * once the last 8 frames are stable and the center cell matches the expected
 * color family (manual capture and per-face photo upload always work too —
 * the whole flow is usable with no camera at all). Each capture goes through
 * POST /api/scan-face; after all six faces POST /api/classify and show the
 * review net; when valid, POST /api/solve and hand off via onSolved exactly
 * like the other App entry paths. The video is never mirrored — mirroring
 * would flip the sticker grid and break the §6 row-major key property.
 */

import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import type {
  ClassifyResponse,
  FaceLetter,
  SolveResponse,
  ValidationError,
} from './types'
import { COLOR_HEX, FACE_ORDER } from './cubeModel'
import * as api from './api'
import { SCAN_STEPS, faceLabel } from './scan/steps'
import { StabilityTracker, hueMatchesFace, type RGB } from './scan/stability'
import PoseCube from './scan/PoseCube'
import BootingNotice from './backendStatus'
import './Scanner.css'

/** Guide-box side as a fraction of min(video width, height). */
const GUIDE_FRACTION = 0.78
/** §6: the cropped face image must be at least 270×270. */
const CAPTURE_MIN = 270
const CAPTURE_MAX = 480
/** Grace period after a face advances before auto-capture may fire (ms). */
const ARM_DELAY_MS = 1200
/** Hidden sampling canvas side: 3 cells × 10 px. */
const SAMPLE_SIDE = 30
/** Review: pulse cells whose classify confidence is below this. */
const LOW_CONFIDENCE = 0.35

interface FaceSamples {
  lab: number[][]
  rgb: number[][]
}

type SamplesByFace = Partial<Record<FaceLetter, FaceSamples>>

type Phase = 'scan' | 'classifying' | 'review'

interface ScannerProps {
  onSolved: (facelets: string, solve: SolveResponse) => void
  onManualEntry?: () => void
  onBack: () => void
}

/** Same unfolded-net layout as manual entry (3-cell block row/col per face). */
const NET_BLOCK: Record<FaceLetter, { row: number; col: number }> = {
  U: { row: 0, col: 1 },
  L: { row: 1, col: 0 },
  F: { row: 1, col: 1 },
  R: { row: 1, col: 2 },
  B: { row: 1, col: 3 },
  D: { row: 2, col: 1 },
}

// ---------------------------------------------------------------------------
// Canvas helpers
// ---------------------------------------------------------------------------

/** Guide-box region in video source coordinates (centered square, §9.5). */
function guideRegion(video: HTMLVideoElement): { sx: number; sy: number; s: number } {
  const s = Math.min(video.videoWidth, video.videoHeight) * GUIDE_FRACTION
  return { sx: (video.videoWidth - s) / 2, sy: (video.videoHeight - s) / 2, s }
}

/** Crop a square source region into a ≥270px square canvas (§6). */
function cropSquare(
  source: CanvasImageSource,
  sx: number,
  sy: number,
  s: number,
): HTMLCanvasElement {
  const side = Math.round(Math.min(CAPTURE_MAX, Math.max(CAPTURE_MIN, s)))
  const canvas = document.createElement('canvas')
  canvas.width = side
  canvas.height = side
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 2D unavailable')
  ctx.drawImage(source, sx, sy, s, s, 0, 0, side, side)
  return canvas
}

/** Average the central patch of each of the 9 cells of the sampling canvas. */
function sampleCells(ctx: CanvasRenderingContext2D): RGB[] {
  const data = ctx.getImageData(0, 0, SAMPLE_SIDE, SAMPLE_SIDE).data
  const cells: RGB[] = []
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      let sr = 0
      let sg = 0
      let sb = 0
      let n = 0
      for (let y = r * 10 + 3; y < r * 10 + 7; y++) {
        for (let x = c * 10 + 3; x < c * 10 + 7; x++) {
          const i = (y * SAMPLE_SIDE + x) * 4
          sr += data[i]
          sg += data[i + 1]
          sb += data[i + 2]
          n++
        }
      }
      cells.push([sr / n, sg / n, sb / n])
    }
  }
  return cells
}

function loadImageFile(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Could not decode the image'))
    }
    img.src = url
  })
}

function errorMessage(err: unknown): string {
  if (err instanceof api.ApiUnavailableError) {
    return 'Backend unreachable — scanning needs the API server running.'
  }
  return err instanceof Error ? err.message : String(err)
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

/**
 * Guide overlay per the Paper Toy design: a #ffffff22 3×3 grid over the
 * §9.5 guide box plus yellow corner brackets (green while steady).
 */
function GuideOverlay({ steady }: { steady: boolean }) {
  return (
    <div className={`scan-guide${steady ? ' steady' : ''}`} aria-hidden>
      <div className="scan-grid" />
      <span className="scan-bracket tl" />
      <span className="scan-bracket tr" />
      <span className="scan-bracket bl" />
      <span className="scan-bracket br" />
    </div>
  )
}

function MiniGrid({ rgb }: { rgb: number[][] }) {
  return (
    <div className="mini-grid" aria-hidden>
      {rgb.map((c, i) => (
        <span key={i} style={{ background: `rgb(${c[0]}, ${c[1]}, ${c[2]})` }} />
      ))}
    </div>
  )
}

function ValidationErrorList({ errors }: { errors: ValidationError[] }) {
  return (
    <div className="validation-errors">
      {errors.map((e, i) => (
        <div key={i} className="validation-error">
          <span className="error-code">{e.code}</span>
          <span>{e.message}</span>
          {e.suspect_faces.length > 0 && (
            <span className="suspect-faces">
              Check face{e.suspect_faces.length > 1 ? 's' : ''}: {e.suspect_faces.join(', ')}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Scanner
// ---------------------------------------------------------------------------

export default function Scanner({ onSolved, onManualEntry, onBack }: ScannerProps) {
  const [phase, setPhase] = useState<Phase>('scan')
  const [stepIndex, setStepIndex] = useState(0)
  const [samples, setSamples] = useState<SamplesByFace>({})
  const [lastCapture, setLastCapture] = useState<{ face: FaceLetter; rgb: number[][] } | null>(
    null,
  )
  const [scanBusy, setScanBusy] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [classifyResult, setClassifyResult] = useState<ClassifyResponse | null>(null)
  const [classifyError, setClassifyError] = useState<string | null>(null)
  const [classifyErrors, setClassifyErrors] = useState<ValidationError[] | null>(null)
  const [solveBusy, setSolveBusy] = useState(false)
  const [solveErrors, setSolveErrors] = useState<ValidationError[] | null>(null)

  const [cameraState, setCameraState] = useState<'starting' | 'ready' | 'error'>('starting')
  const [cameraMessage, setCameraMessage] = useState('')
  const [steady, setSteady] = useState(false)
  const [steadyPct, setSteadyPct] = useState(0)
  const [hueOk, setHueOk] = useState(true)

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const trackerRef = useRef<StabilityTracker | null>(null)
  trackerRef.current ??= new StabilityTracker()
  const tracker = trackerRef.current
  const samplesRef = useRef<SamplesByFace>(samples)
  const capturingRef = useRef(false)
  const armedAtRef = useRef(0)
  const faceRef = useRef<FaceLetter>('F')

  const scanning = phase === 'scan'
  const currentStep = SCAN_STEPS[stepIndex]
  faceRef.current = currentStep.face

  const rearm = useCallback(() => {
    tracker.reset()
    armedAtRef.current = performance.now()
  }, [tracker])

  // ------------------------------------------------------------------ camera
  useEffect(() => {
    if (!scanning) return
    let cancelled = false
    let stream: MediaStream | null = null
    // Captured now: on cleanup the ref may already point at a different (or
    // unmounted) element, and this effect owns *this* element's srcObject.
    const video = videoRef.current
    setCameraState('starting')

    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setCameraState('error')
        setCameraMessage('This browser has no camera support.')
        return
      }
      try {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { ideal: 'environment' },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          })
        } catch {
          // Constraints too strict for this device — degrade gracefully.
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        }
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        if (video) {
          video.srcObject = stream
          await video.play().catch(() => {})
        }
        if (!cancelled) {
          armedAtRef.current = performance.now()
          setCameraState('ready')
        }
      } catch (err) {
        if (cancelled) return
        const name = err instanceof DOMException ? err.name : ''
        setCameraState('error')
        setCameraMessage(
          name === 'NotAllowedError'
            ? 'Camera permission was denied.'
            : name === 'NotFoundError'
              ? 'No camera was found.'
              : 'The camera could not be started.',
        )
      }
    }

    void start()
    return () => {
      cancelled = true
      stream?.getTracks().forEach((t) => t.stop())
      if (video) video.srcObject = null
    }
  }, [scanning])

  // ---------------------------------------------------------------- captures

  const runClassify = useCallback(async (all: SamplesByFace) => {
    const faces = {} as Record<FaceLetter, number[][]>
    for (const f of FACE_ORDER) {
      const s = all[f]
      if (!s) return
      faces[f] = s.lab
    }
    setPhase('classifying')
    setClassifyError(null)
    setClassifyErrors(null)
    setSolveErrors(null)
    try {
      setClassifyResult(await api.classify(faces))
    } catch (err) {
      setClassifyResult(null)
      // A 400 carries structured re-scan guidance (§6) — keep it structured.
      if (err instanceof api.ApiValidationError) setClassifyErrors(err.errors)
      else setClassifyError(errorMessage(err))
    }
    setPhase('review')
  }, [])

  /** Store a face's samples, then advance to the next missing face (§6 order). */
  const acceptFace = useCallback(
    (face: FaceLetter, lab: number[][], rgb: number[][]) => {
      const next: SamplesByFace = { ...samplesRef.current, [face]: { lab, rgb } }
      samplesRef.current = next
      setSamples(next)
      setLastCapture({ face, rgb })
      rearm()
      const missing = SCAN_STEPS.findIndex((st) => !next[st.face])
      if (missing === -1) void runClassify(next)
      else setStepIndex(missing)
    },
    [rearm, runClassify],
  )

  const submitFace = useCallback(
    async (face: FaceLetter, canvas: HTMLCanvasElement) => {
      setScanBusy(true)
      setScanError(null)
      try {
        const res = await api.scanFace(face, canvas.toDataURL('image/jpeg', 0.9))
        if (!res.quality.ok) {
          setScanError(
            res.quality.message ||
              'That capture was too noisy — hold the cube steady and try again.',
          )
          rearm()
          return
        }
        acceptFace(face, res.samples_lab, res.samples_rgb)
      } catch (err) {
        setScanError(errorMessage(err))
        rearm()
      } finally {
        setScanBusy(false)
      }
    },
    [acceptFace, rearm],
  )

  const captureFromVideo = useCallback(async () => {
    const video = videoRef.current
    if (!video || video.readyState < 2 || !video.videoWidth || capturingRef.current) return
    capturingRef.current = true
    try {
      const { sx, sy, s } = guideRegion(video)
      await submitFace(faceRef.current, cropSquare(video, sx, sy, s))
    } finally {
      capturingRef.current = false
    }
  }, [submitFace])

  const onUpload = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      e.target.value = ''
      if (!file || capturingRef.current) return
      capturingRef.current = true
      // Snapshot the face BEFORE awaiting the decode — the user can change
      // the current step (e.g. "Re-take this face") while it is in flight.
      const face = faceRef.current
      try {
        const img = await loadImageFile(file)
        const m = Math.min(img.naturalWidth, img.naturalHeight)
        const canvas = cropSquare(img, (img.naturalWidth - m) / 2, (img.naturalHeight - m) / 2, m)
        await submitFace(face, canvas)
      } catch {
        setScanError('Could not read that image file.')
      } finally {
        capturingRef.current = false
      }
    },
    [submitFace],
  )

  /** Drop a face's samples and jump back into the flow for just that face. */
  const retakeFace = useCallback(
    (face: FaceLetter) => {
      const next = { ...samplesRef.current }
      delete next[face]
      samplesRef.current = next
      setSamples(next)
      setLastCapture(null)
      setClassifyResult(null)
      setClassifyError(null)
      setClassifyErrors(null)
      setScanError(null)
      setSolveErrors(null)
      setStepIndex(SCAN_STEPS.findIndex((st) => st.face === face))
      setPhase('scan')
      rearm()
    },
    [rearm],
  )

  // --------------------------------------------------- per-frame stability
  useEffect(() => {
    if (!scanning || cameraState !== 'ready') return
    const canvas = document.createElement('canvas')
    canvas.width = SAMPLE_SIDE
    canvas.height = SAMPLE_SIDE
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return

    let raf = 0
    let lastSteady = false
    let lastPct = -1
    let lastHueOk = true
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const video = videoRef.current
      if (!video || video.readyState < 2 || !video.videoWidth) return
      const { sx, sy, s } = guideRegion(video)
      ctx.drawImage(video, sx, sy, s, s, 0, 0, SAMPLE_SIDE, SAMPLE_SIDE)
      const cells = sampleCells(ctx)
      const now = performance.now()
      const status = tracker.push(cells, now)
      const centerOk = hueMatchesFace(cells[4], faceRef.current)
      const isSteady = status.steady && centerOk
      if (isSteady !== lastSteady) {
        lastSteady = isSteady
        setSteady(isSteady)
      }
      if (centerOk !== lastHueOk) {
        lastHueOk = centerOk
        setHueOk(centerOk)
      }
      const pct = isSteady
        ? Math.round(Math.min(1, status.steadyForMs / 400) * 20) / 20
        : 0
      if (pct !== lastPct) {
        lastPct = pct
        setSteadyPct(pct)
      }
      if (
        status.shouldCapture &&
        centerOk &&
        now - armedAtRef.current > ARM_DELAY_MS &&
        !capturingRef.current
      ) {
        void captureFromVideo()
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [scanning, cameraState, tracker, captureFromVideo])

  // ------------------------------------------------------------------- solve
  const solveIt = useCallback(async () => {
    const res = classifyResult
    if (!res || !res.valid) return
    setSolveBusy(true)
    setSolveErrors(null)
    try {
      const solve = await api.solve(res.facelets)
      onSolved(res.facelets, solve)
    } catch (err) {
      if (err instanceof api.ApiValidationError) setSolveErrors(err.errors)
      else setClassifyError(errorMessage(err))
    } finally {
      setSolveBusy(false)
    }
  }, [classifyResult, onSolved])

  // ------------------------------------------------------------------ render

  const chips = (
    <div className="face-chips">
      {SCAN_STEPS.map((st, i) => (
        <div
          key={st.face}
          className={`face-chip${samples[st.face] ? ' done' : ''}${
            scanning && i === stepIndex ? ' current' : ''
          }`}
          title={faceLabel(st.face)}
        >
          <span className="chip-swatch" style={{ background: st.hex }} />
          <span>{st.face}</span>
          {samples[st.face] && <span className="chip-check">✓</span>}
        </div>
      ))}
    </div>
  )

  // Back link shares the title row with the h2 (design handoff: one inline
  // flex row, exactly like manual entry / setpick / records).
  const backLink = (
    <button className="back-link" onClick={onBack}>
      ← back
    </button>
  )

  if (phase === 'classifying') {
    return (
      <div className="scanner">
        <div className="screen-title-row">
          {backLink}
          <h2>Scan with camera</h2>
        </div>
        {chips}
        <p className="hint">Reading the colors of all 54 stickers…</p>
        <BootingNotice />
      </div>
    )
  }

  if (phase === 'review') {
    return (
      <ReviewScreen
        backLink={backLink}
        chips={chips}
        result={classifyResult}
        classifyError={classifyError}
        classifyErrors={classifyErrors}
        solveBusy={solveBusy}
        solveErrors={solveErrors}
        onRetryClassify={() => void runClassify(samplesRef.current)}
        onRetake={retakeFace}
        onSolve={() => void solveIt()}
      />
    )
  }

  // phase === 'scan'
  const statusLine = scanBusy
    ? 'reading colors…'
    : steady
      ? 'steady — capturing…'
      : cameraState === 'ready'
        ? hueOk
          ? `hold the ${currentStep.colorName} face steady inside the frame`
          : `looking for the ${currentStep.colorName} center…`
        : ''

  // Green progress bar under the frame: captured faces out of 6, plus the
  // current face's steadiness creeping toward its next sixth.
  const doneCount = SCAN_STEPS.reduce((n, st) => n + (samples[st.face] ? 1 : 0), 0)
  const progressPct = Math.min(100, ((doneCount + steadyPct) / 6) * 100)

  return (
    <div className="scanner">
      <div className="screen-title-row">
        {backLink}
        <h2>Scan with camera</h2>
      </div>
      {chips}

      <div className="scan-body">
        <div className="scan-video-col">
          <div className="scan-video-wrap">
            {/* NOT mirrored on purpose — mirroring would flip the sticker grid. */}
            <video ref={videoRef} playsInline muted />
            {cameraState === 'ready' && <GuideOverlay steady={steady} />}
            {cameraState === 'ready' && <div className="scan-caption">{statusLine}</div>}
            {cameraState === 'starting' && (
              <div className="scan-video-placeholder">Starting camera…</div>
            )}
            {cameraState === 'error' && (
              <div className="scan-video-placeholder camera-error">
                <strong>Camera unavailable</strong>
                <span>{cameraMessage}</span>
                <span>
                  You can still scan by uploading a photo of each face, or enter the colors
                  manually.
                </span>
                {onManualEntry && (
                  <button className="btn" onClick={onManualEntry}>
                    Enter colors manually
                  </button>
                )}
              </div>
            )}
          </div>
          <div className="scan-progress" aria-hidden>
            <div className="scan-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
        </div>

        <div className="scan-side">
          <div className="scan-instruction">
            <div className="scan-face-now">
              <span className="face-dot" style={{ background: currentStep.hex }} />
              <span>
                Face {stepIndex + 1} of 6 — {currentStep.colorName} ({currentStep.face})
              </span>
            </div>
            <p className="hint">{currentStep.instruction}</p>
            <PoseCube step={currentStep} />
          </div>

          <div className="scan-actions">
            <button
              className="btn primary capture-btn"
              onClick={() => void captureFromVideo()}
              disabled={cameraState !== 'ready' || scanBusy}
            >
              {scanBusy ? 'Reading…' : 'Capture now'}
            </button>
            <label className={`btn upload-btn${scanBusy ? ' disabled' : ''}`}>
              Upload
              <input
                type="file"
                accept="image/*"
                onChange={(e) => void onUpload(e)}
                disabled={scanBusy}
              />
            </label>
          </div>

          <BootingNotice compact />

          {lastCapture && (
            <div className="last-capture">
              <MiniGrid rgb={lastCapture.rgb} />
              <div className="last-capture-info">
                <span>Captured {faceLabel(lastCapture.face)}</span>
                <button className="btn" onClick={() => retakeFace(lastCapture.face)}>
                  Re-take this face
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {scanError && <div className="failure">{scanError}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Review screen
// ---------------------------------------------------------------------------

interface ReviewScreenProps {
  backLink: React.ReactNode
  chips: React.ReactNode
  result: ClassifyResponse | null
  classifyError: string | null
  /** Structured 400 errors from /api/classify (§6 re-scan guidance). */
  classifyErrors: ValidationError[] | null
  solveBusy: boolean
  solveErrors: ValidationError[] | null
  onRetryClassify: () => void
  onRetake: (face: FaceLetter) => void
  onSolve: () => void
}

function RescanRow({
  suspects,
  onRetake,
}: {
  suspects: Set<string>
  onRetake: (face: FaceLetter) => void
}) {
  return (
    <div className="rescan-row">
      {SCAN_STEPS.map((st) => (
        <button
          key={st.face}
          className={`btn rescan-btn${suspects.has(st.face) ? ' suspect' : ''}`}
          onClick={() => onRetake(st.face)}
        >
          <span className="chip-swatch" style={{ background: st.hex }} />
          Re-scan {st.colorName}
        </button>
      ))}
    </div>
  )
}

function ReviewScreen({
  backLink,
  chips,
  result,
  classifyError,
  classifyErrors,
  solveBusy,
  solveErrors,
  onRetryClassify,
  onRetake,
  onSolve,
}: ReviewScreenProps) {
  if (!result) {
    // Classification failed outright. A structured 400 is deterministic for
    // the same samples, so the way out is re-scanning the implicated faces —
    // retrying only helps for transient (network/server) failures.
    const suspects = new Set<string>()
    for (const e of classifyErrors ?? []) for (const f of e.suspect_faces) suspects.add(f)
    return (
      <div className="scanner">
        <div className="screen-title-row">
          {backLink}
          <h2>Review your scan</h2>
        </div>
        {chips}
        {classifyErrors && <ValidationErrorList errors={classifyErrors} />}
        {classifyError && <div className="failure">{classifyError}</div>}
        <RescanRow suspects={suspects} onRetake={onRetake} />
        {!classifyErrors && (
          <div className="scan-actions">
            <button className="btn primary" onClick={onRetryClassify}>
              Retry classification
            </button>
          </div>
        )}
      </div>
    )
  }

  // Cells to pulse: backend-flagged ambiguous + anything low-confidence.
  const warn = new Set<string>(result.ambiguous.map((a) => `${a.face}${a.index}`))
  for (const f of FACE_ORDER) {
    result.confidence[f]?.forEach((conf, k) => {
      if (conf < LOW_CONFIDENCE) warn.add(`${f}${k}`)
    })
  }

  // Faces implicated by validation errors or ambiguity get highlighted buttons.
  const suspects = new Set<string>()
  for (const e of result.errors) for (const f of e.suspect_faces) suspects.add(f)
  for (const a of result.ambiguous) suspects.add(a.face)

  const netCells = []
  for (let f = 0; f < 6; f++) {
    const face = FACE_ORDER[f]
    const block = NET_BLOCK[face]
    const letters = result.colors[face] ?? []
    for (let k = 0; k < 9; k++) {
      const letter = (letters[k] ?? face) as FaceLetter
      const conf = result.confidence[face]?.[k]
      netCells.push(
        <div
          key={`${face}${k}`}
          className={`net-cell readonly${warn.has(`${face}${k}`) ? ' warn' : ''}`}
          style={{
            gridRow: block.row * 3 + Math.floor(k / 3) + 1,
            gridColumn: block.col * 3 + (k % 3) + 1,
            background: COLOR_HEX[letter],
          }}
          title={`${face}${k + 1} → ${letter}${
            conf !== undefined ? ` (confidence ${conf.toFixed(2)})` : ''
          }`}
        />,
      )
    }
  }

  return (
    <div className="scanner">
      <div className="screen-title-row">
        {backLink}
        <h2>Review your scan</h2>
      </div>
      {chips}
      <p className="hint">
        Every sticker as AlgLabs read it. Pulsing cells were ambiguous or low-confidence —
        re-scan their face if they look wrong.
      </p>

      <div className="net-grid review-net">{netCells}</div>

      {result.valid ? (
        <div className="local-ok">The cube is valid — ready to solve.</div>
      ) : (
        <ValidationErrorList errors={result.errors} />
      )}
      {solveErrors && <ValidationErrorList errors={solveErrors} />}
      {classifyError && <div className="failure">{classifyError}</div>}

      <RescanRow suspects={suspects} onRetake={onRetake} />

      {result.valid && (
        <button className="btn-ink solve-btn" onClick={onSolve} disabled={solveBusy}>
          {solveBusy ? 'Solving…' : 'All six faces read — Solve it ▸'}
        </button>
      )}
      <BootingNotice compact />
    </div>
  )
}
