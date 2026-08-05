/**
 * Trainer module routing seam (CONTRACTS.md §12.2–§12.4).
 *
 * App.tsx owns the view state and renders these components with navigation
 * callbacks + params. The trainer implementation is replaced behind these
 * prop types WITHOUT touching App.tsx — do not change the shapes here
 * without updating App.tsx in the same change.
 */

/** The five drillable sets, in display order (CONTRACTS.md §11.1). */
export type SetKey = 'oll' | 'pll' | 'coll' | 'zbll' | 'vls'

export const SET_KEYS: readonly SetKey[] = ['oll', 'pll', 'coll', 'zbll', 'vls']

/**
 * Drill modes (§12.3/§12.4): `random` = recognition + execution with the case
 * never named; `grind` = one chosen case, execution only.
 */
export type TrainerMode = 'random' | 'grind'

/** Set picker (§12.4 "Set picker"): choose a set, then random drill or casepick. */
export interface SetPickerProps {
  /** "← home" back link. */
  onBack: () => void
  /** "Random drill ▸" on a set card → trainer in random mode. */
  onRandomDrill: (set: SetKey) => void
  /** "Choose a case…" on a set card → casepick for that set. */
  onChooseCase: (set: SetKey) => void
}

/** Case picker (§12.4 "Casepick"): grid of case tiles for one set. */
export interface CasePickProps {
  set: SetKey
  /** "← sets" back link → set picker. */
  onBack: () => void
  /** Clicking a case tile → trainer in grind mode for that case. */
  onPickCase: (caseId: string) => void
}

/** Trainer screen (§12.3 random / §12.4 grind variant). */
export interface TrainerProps {
  set: SetKey
  mode: TrainerMode
  /** The case to grind — present exactly when `mode === 'grind'`. */
  caseId?: string
  /** "← sets" back link → set picker. */
  onBackToSets: () => void
}

/** Records screen (§12.5): five tabs, defaults to the last-trained set's tab. */
export interface RecordsProps {
  /** "← home" back link. */
  onBack: () => void
}

// ---------------------------------------------------------------------------
// Trainer API payloads (CONTRACTS.md §11.3–§11.4) — mirrored 1:1.
// ---------------------------------------------------------------------------

/**
 * §11.3 preview payload — the LL pattern as seen from above: `u` = the nine
 * U-face facelets row-major, plus the top row of each side face (left→right
 * as viewed from that face). Values are face letters for recognition-relevant
 * stickers, else `"x"` (rendered dim).
 */
export interface TrainerPreview {
  u: string[]
  f: string[]
  r: string[]
  b: string[]
  l: string[]
}

/** One group inside a set (GET /api/trainer/sets). */
export interface TrainerGroup {
  key: string
  name: string
  count: number
}

/** One drillable set (GET /api/trainer/sets). */
export interface TrainerSet {
  key: SetKey
  name: string
  count: number
  description: string
  groups: TrainerGroup[]
}

/** One case (GET /api/trainer/cases). */
export interface TrainerCase {
  id: string
  name: string
  group: string
  preview: TrainerPreview
}

/**
 * GET /api/trainer/scramble. `solution` is the inverse of `scramble` and
 * drives the ghost CubeView playback. In random mode `name`/`preview` MUST NOT
 * be rendered at all — the case is never identified (§11.4 / design ⚠️ #2).
 */
export interface TrainerScramble {
  set: SetKey
  case_id: string
  name: string
  group: string
  scramble: string
  solution: string
  preview: TrainerPreview
}
