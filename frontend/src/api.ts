/**
 * Typed fetch wrappers for the AlgLabs API (§8), base path /api, plus a
 * MOCK mode so the walkthrough is demoable without the backend.
 *
 * Mock mode activates when:
 *  - the app is built/served with VITE_MOCK=1, or
 *  - `enableMockMode()` is called (the UI does this when fetch fails).
 *
 * In mock mode /api/scramble returns a fixed short scramble and /api/solve
 * only answers for that exact scramble (the fixture is computed from the
 * logical cube model at load, so it is valid by construction).
 */

import type {
  ClassifyResponse,
  FaceLetter,
  Highlight,
  ScanFaceResponse,
  ScrambleResponse,
  SolveErrorResponse,
  SolveResponse,
  Stage,
  Step,
  ValidationError,
} from './types'
import { applyMovesToFacelets, solvedFacelets } from './cubeModel'
import { invertSequence, moveToString, parseSequence } from './notation'

/**
 * API base path. Defaults to the same-origin `/api` (the dev server proxies
 * it to 127.0.0.1:8010). On a split deploy the frontend and the API live on
 * different hosts, so set `VITE_API_BASE` to the API origin at build time,
 * e.g. `https://alglabs-api.onrender.com/api`.
 */
const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '/api'

/** The backend rejected the cube as invalid (§5). */
export class ApiValidationError extends Error {
  readonly errors: ValidationError[]
  constructor(errors: ValidationError[]) {
    super(errors.map((e) => e.message).join(' — ') || 'Invalid cube')
    this.name = 'ApiValidationError'
    this.errors = errors
  }
}

/** The backend could not be reached (network failure / not running). */
export class ApiUnavailableError extends Error {
  constructor(message = 'Backend unreachable') {
    super(message)
    this.name = 'ApiUnavailableError'
  }
}

let mockMode: boolean = import.meta.env.VITE_MOCK === '1'

export function isMockMode(): boolean {
  return mockMode
}

export function enableMockMode(): void {
  mockMode = true
}

// ---------------------------------------------------------------------------
// Mock fixture — computed once from the logical model, valid by construction.
// ---------------------------------------------------------------------------

const MOCK_SCRAMBLE = "R U R' U' F2 D L' B"

const CROSS_HIGHLIGHT: Highlight[] = [
  { type: 'edge', piece: 'DR' },
  { type: 'edge', piece: 'DF' },
  { type: 'edge', piece: 'DL' },
  { type: 'edge', piece: 'DB' },
]

const LL_HIGHLIGHT: Highlight[] = [
  { type: 'corner', piece: 'URF' },
  { type: 'corner', piece: 'UFL' },
  { type: 'corner', piece: 'ULB' },
  { type: 'corner', piece: 'UBR' },
  { type: 'edge', piece: 'UR' },
  { type: 'edge', piece: 'UF' },
  { type: 'edge', piece: 'UL' },
  { type: 'edge', piece: 'UB' },
]

const F2L_PAIRS: { slot: string; corner: string; edge: string }[] = [
  { slot: 'FR', corner: 'DFR', edge: 'FR' },
  { slot: 'FL', corner: 'DLF', edge: 'FL' },
  { slot: 'BL', corner: 'DBL', edge: 'BL' },
  { slot: 'BR', corner: 'DRB', edge: 'BR' },
]

interface MockFixture {
  scramble: ScrambleResponse
  solve: SolveResponse
}

function buildMockFixture(): MockFixture {
  const scrambleMoves = parseSequence(MOCK_SCRAMBLE)
  const facelets = applyMovesToFacelets(solvedFacelets, scrambleMoves)
  const solution = invertSequence(scrambleMoves).map(moveToString)

  // Distribute the 8 solution moves across demo stages: 2 cross, 4 F2L
  // (one per slot), 1 OLL, 1 PLL. The stage semantics are cosmetic — this
  // fixture only demonstrates the walkthrough UI — but the moves genuinely
  // solve the fixture scramble.
  let offset = 0
  const takeStep = (
    label: string,
    caseName: string | null,
    n: number,
    highlight: Highlight[],
  ): Step => {
    const moves = solution.slice(offset, offset + n)
    const step: Step = {
      label,
      case: caseName,
      moves,
      notation: moves.join(' '),
      move_offset: offset,
      skipped: false,
      highlight,
    }
    offset += n
    return step
  }

  const stages: Stage[] = [
    { id: 'cross', label: 'Cross', steps: [takeStep('Cross', null, 2, CROSS_HIGHLIGHT)] },
    {
      id: 'f2l',
      label: 'F2L',
      steps: F2L_PAIRS.map((p, i) =>
        takeStep(`F2L pair ${i + 1} (${p.slot} slot)`, null, 1, [
          { type: 'corner', piece: p.corner },
          { type: 'edge', piece: p.edge },
        ]),
      ),
    },
    {
      id: 'oll',
      label: 'OLL',
      steps: [takeStep('OLL — demo case', 'OLL (demo)', 1, LL_HIGHLIGHT)],
    },
    {
      id: 'pll',
      label: 'PLL',
      steps: [takeStep('PLL — demo case', 'PLL (demo)', 1, LL_HIGHLIGHT)],
    },
  ]

  return {
    scramble: { facelets, scramble: MOCK_SCRAMBLE },
    solve: {
      valid: true,
      facelets,
      total_moves: solution.length,
      stages,
    },
  }
}

let mockFixture: MockFixture | null = null

function getMockFixture(): MockFixture {
  mockFixture ??= buildMockFixture()
  return mockFixture
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch {
    throw new ApiUnavailableError()
  }
  let body: T
  try {
    body = (await res.json()) as T
  } catch {
    throw new Error(`Unexpected non-JSON response from ${path} (HTTP ${res.status})`)
  }
  return { status: res.status, body }
}

function postInit(payload: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/**
 * GET /api/health, fire-and-forget. Free API hosts idle their instance out
 * after inactivity and take tens of seconds to boot; pinging on app mount
 * overlaps that wake-up with the user reading the home screen instead of
 * with their first solve. Never throws.
 */
export function wake(): void {
  if (mockMode) return
  void fetch(`${BASE}/health`).catch(() => undefined)
}

/** POST /api/solve. Throws ApiValidationError on an invalid cube (400). */
export async function solve(facelets: string): Promise<SolveResponse> {
  if (mockMode) {
    const fixture = getMockFixture()
    if (facelets === fixture.scramble.facelets) return fixture.solve
    throw new ApiUnavailableError(
      'Mock mode can only solve the built-in demo scramble — start the backend to solve arbitrary cubes.',
    )
  }
  const { status, body } = await request<SolveResponse | SolveErrorResponse>(
    '/solve',
    postInit({ facelets }),
  )
  if (status === 400 || (body as SolveErrorResponse).valid === false) {
    throw new ApiValidationError((body as SolveErrorResponse).errors ?? [])
  }
  if (status !== 200) throw new Error(`/api/solve failed (HTTP ${status})`)
  return body as SolveResponse
}

/** GET /api/scramble. */
export async function scramble(): Promise<ScrambleResponse> {
  if (mockMode) return getMockFixture().scramble
  const { status, body } = await request<ScrambleResponse>('/scramble')
  if (status !== 200) throw new Error(`/api/scramble failed (HTTP ${status})`)
  return body
}

/** POST /api/scan-face. Not available in mock mode. */
export async function scanFace(face: FaceLetter, image: string): Promise<ScanFaceResponse> {
  if (mockMode) throw new ApiUnavailableError('Scanning requires the backend.')
  const { status, body } = await request<ScanFaceResponse>(
    '/scan-face',
    postInit({ face, image }),
  )
  if (status !== 200) throw new Error(`/api/scan-face failed (HTTP ${status})`)
  return body
}

/**
 * POST /api/classify. Not available in mock mode. Throws ApiValidationError
 * on a 400 (indistinct_centers / center_mismatch / bad_samples, §6) so the
 * structured re-scan guidance reaches the UI.
 */
export async function classify(
  faces: Record<FaceLetter, number[][]>,
): Promise<ClassifyResponse> {
  if (mockMode) throw new ApiUnavailableError('Classification requires the backend.')
  const { status, body } = await request<ClassifyResponse | SolveErrorResponse>(
    '/classify',
    postInit({ faces }),
  )
  if (status === 400) {
    throw new ApiValidationError((body as SolveErrorResponse).errors ?? [])
  }
  if (status !== 200) throw new Error(`/api/classify failed (HTTP ${status})`)
  return body as ClassifyResponse
}
