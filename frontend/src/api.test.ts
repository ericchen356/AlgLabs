/**
 * api.classify error handling (§6/§8): a 400 from /api/classify carries the
 * structured ClassifyError payload (code/message/suspect_faces) and must
 * surface as an ApiValidationError, not a generic HTTP failure — the re-scan
 * guidance has to reach the UI.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiValidationError, classify } from './api'
import type { FaceLetter } from './types'

const FACES = Object.fromEntries(
  (['U', 'R', 'F', 'D', 'L', 'B'] as FaceLetter[]).map((f) => [
    f,
    Array.from({ length: 9 }, () => [50, 0, 0]),
  ]),
) as Record<FaceLetter, number[][]>

function stubFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ status, json: async () => body })),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('classify', () => {
  it('throws ApiValidationError with the structured 400 body', async () => {
    stubFetch(400, {
      valid: false,
      errors: [
        {
          code: 'indistinct_centers',
          message:
            'The centre stickers of faces L, R look like the same colour — re-scan those faces.',
          suspect_faces: ['L', 'R'],
        },
      ],
    })
    const err = await classify(FACES).then(
      () => null,
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiValidationError)
    const verr = err as ApiValidationError
    expect(verr.errors).toHaveLength(1)
    expect(verr.errors[0].code).toBe('indistinct_centers')
    expect(verr.errors[0].suspect_faces).toEqual(['L', 'R'])
    expect(verr.message).toContain('re-scan those faces')
  })

  it('throws ApiValidationError even when a 400 body has no errors array', async () => {
    stubFetch(400, { valid: false })
    await expect(classify(FACES)).rejects.toBeInstanceOf(ApiValidationError)
  })

  it('returns the body on 200', async () => {
    const body = {
      facelets: 'U'.repeat(54),
      colors: {},
      confidence: {},
      ambiguous: [],
      valid: false,
      errors: [],
    }
    stubFetch(200, body)
    await expect(classify(FACES)).resolves.toEqual(body)
  })

  it('throws a generic error on non-400 failures', async () => {
    stubFetch(500, { detail: 'boom' })
    await expect(classify(FACES)).rejects.toThrow('/api/classify failed (HTTP 500)')
  })
})
