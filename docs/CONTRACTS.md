# AlgLabs — Engineering Contracts

This is the **authoritative conventions document** for the CFOP Cube Scanner. Every module
(backend cube core, solver, vision, API, frontend) MUST follow these conventions exactly.
Where two modules meet, this document is the interface. Property tests listed in §10 enforce it.

---

## 1. Repo layout

```
AlgLabs/
├─ docs/CONTRACTS.md          # this file
├─ backend/
│  ├─ pyproject.toml          # uv-managed; run everything via `uv run ...` in backend/
│  ├─ app.py                  # FastAPI app: all routes under /api
│  ├─ cube/
│  │  ├─ facelet.py           # facelet string <-> cubie model, constants
│  │  ├─ moves.py             # 18 moves, algorithm parser/rewriter, apply/multiply
│  │  └─ validate.py          # counts + orientation + parity checks with face blame
│  ├─ vision/
│  │  ├─ sampling.py          # 9 patch colors from a cropped face image
│  │  ├─ classify.py          # Lab + k-means(6) + label-by-centers + 9-per-color assignment
│  │  └─ quality.py           # confidence / separability metrics
│  ├─ solver/
│  │  ├─ cross.py             # BFS cross (D-layer edges)
│  │  ├─ f2l.py               # per-slot IDA* insert with PDB heuristics
│  │  ├─ oll.py               # recognition table built at import from data/oll.json
│  │  ├─ pll.py               # recognition table built at import from data/pll.json
│  │  ├─ cfop.py              # orchestrates stages, builds the /solve response
│  │  └─ data/{oll.json,pll.json}
│  └─ tests/                  # pytest; all property tests in §10
└─ frontend/                  # Vite + React + TS + three
   └─ src/
      ├─ types.ts             # mirrors §8 API schemas
      ├─ api.ts               # fetch wrappers, base path /api
      ├─ notation.ts          # move string -> {axis, layer, quarterTurns}
      ├─ cubeModel.ts         # facelet string -> 26 cubie descriptors (§9.2)
      ├─ CubeView.tsx         # three.js cube + animated moves
      ├─ Scanner.tsx          # webcam, grid overlay, stability, guided 6-face flow
      ├─ Walkthrough.tsx      # stage/step UI + playback controls
      └─ App.tsx              # scan | manual entry | demo scramble -> walkthrough
```

---

## 2. Facelet representation

54-character string, 9 stickers per face, face order **U, R, F, D, L, B**.
Global index offsets: `U=0, R=9, F=18, D=27, L=36, B=45`. Facelet `U1..U9` = index `0..8`, etc.

Each face is written **as viewed looking directly at that face**, rows top→bottom, each row
left→right, with these viewing orientations:

- **U**: viewed from above, with the **B edge at the top** (row U1 U2 U3 is adjacent to B).
- **D**: viewed from below the cube's front, with the **F edge at the top** (row D1 D2 D3 is adjacent to F).
- **F, R, B, L**: viewed straight on from outside, with **U at the top**.

Characters are **face letters** (`U R F D L B`), not color names. The center sticker of each
face is always its own letter in a valid string (index 4 within the face).

Solved string:
```
UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB
```

### 2.1 Color scheme (UI/scanning only — the solver never sees colors)

The user holds the cube **YELLOW on top, GREEN facing them** for both scanning and the
walkthrough render. Letters map to colors:

| Face | U | R | F | D | L | B |
|------|---|---|---|---|---|---|
| Color | Yellow | Orange | Green | White | Red | Blue |
| Hex | `#FFD500` | `#FF5800` | `#009B48` | `#FFFFFF` | `#B71234` | `#0046AD` |

The CFOP cross is the **white cross = the D layer**. This is why yellow is up: the cross is
solved on the bottom, matching how the user holds the cube.

---

## 3. Cubie model

```python
@dataclass
class CubieState:
    cp: list[int]  # corner_perm[8]  — cp[slot] = which corner CUBIE occupies this SLOT
    co: list[int]  # corner_ori[8]   — 0,1,2
    ep: list[int]  # edge_perm[12]   — ep[slot] = which edge cubie occupies this slot
    eo: list[int]  # edge_ori[12]    — 0,1
```

Corner order: `URF=0, UFL=1, ULB=2, UBR=3, DFR=4, DLF=5, DBL=6, DRB=7`
Edge order:   `UR=0, UF=1, UL=2, UB=3, DR=4, DF=5, DL=6, DB=7, FR=8, FL=9, BL=10, BR=11`

Solved: `cp=[0..7], co=[0]*8, ep=[0..11], eo=[0]*12`.

### 3.1 Facelet positions of each slot (0-based global indices)

These are the standard Kociemba tables. They are the reference; the geometry tests in §10
must pass against them.

```python
CORNER_FACELET = [  # (U/D facelet first, then clockwise around the corner)
    (8,  9, 20),   # URF: U9 R1 F3
    (6, 18, 38),   # UFL: U7 F1 L3
    (0, 36, 47),   # ULB: U1 L1 B3
    (2, 45, 11),   # UBR: U3 B1 R3
    (29, 26, 15),  # DFR: D3 F9 R7
    (27, 44, 24),  # DLF: D1 L9 F7
    (33, 53, 42),  # DBL: D7 B9 L7
    (35, 17, 51),  # DRB: D9 R9 B7
]
EDGE_FACELET = [
    (5, 10),   # UR: U6 R2
    (7, 19),   # UF: U8 F2
    (3, 37),   # UL: U4 L2
    (1, 46),   # UB: U2 B2
    (32, 16),  # DR: D6 R8
    (28, 25),  # DF: D2 F8
    (30, 43),  # DL: D4 L8
    (34, 52),  # DB: D8 B8
    (23, 12),  # FR: F6 R4
    (21, 41),  # FL: F4 L6
    (50, 39),  # BL: B6 L4
    (48, 14),  # BR: B4 R6
]
CORNER_COLOR = ["URF","UFL","ULB","UBR","DFR","DLF","DBL","DRB"]  # letter i of entry s = color at CORNER_FACELET[s][i] when solved
EDGE_COLOR   = ["UR","UF","UL","UB","DR","DF","DL","DB","FR","FL","BL","BR"]
```

### 3.2 Orientation convention (Kociemba standard)

- **Corner** in slot `s` holding cubie `c`: `co[s] = o` where `o ∈ {0,1,2}` is the index such
  that the cubie's **U/D-colored sticker** sits at facelet position `CORNER_FACELET[s][o]`.
  (`o=0` ⇔ the U/D sticker is on the U/D face.)
- **Edge** in slot `s` holding cubie `e`: `eo[s] = 0` if the sticker at
  `EDGE_FACELET[s][0]` is the cubie's **first-listed color** (per `EDGE_COLOR[e]`), else `1`.

`facelets_to_cubies` must raise a structured error (not crash) on unrecognizable pieces
(a sticker triple/pair that is no real cubie) — validation reports it per §5.

### 3.3 State composition

Applying transformation `b` after state/transformation `a` (both as CubieState):

```
(a·b).cp[i] = a.cp[b.cp[i]]        (a·b).co[i] = (a.co[b.cp[i]] + b.co[i]) mod 3
(a·b).ep[i] = a.ep[b.ep[i]]        (a·b).eo[i] = (a.eo[b.ep[i]] + b.eo[i]) mod 2
```

`apply_move(s, m) = s · TABLE[m]`. Applying a move sequence = left-to-right fold.

---

## 4. Move engine

### 4.1 Source of truth: facelet permutations

Implement the 18 face turns (`U U' U2 D D' D2 L L' L2 R R' R2 F F' F2 B B' B2`) **first as
54-element facelet permutations**, derived from geometry (each quarter turn cycles the face's
8 non-center stickers plus 12 side stickers; e.g. a clockwise U sends F's top row to L's top
row). All turns are **clockwise as viewed looking at that face from outside**.

### 4.2 Cubie tables are DERIVED, never hand-typed

```
TABLE[m] = facelets_to_cubies(apply_facelet_move(m, SOLVED_FACELETS))
```

Because `e · m = m`, the cubie state produced by applying a move to the solved cube IS that
move's composition table. This removes an entire class of transcription bugs; the converter
and the facelet permutations cross-validate each other (§10 test T4).

### 4.3 Algorithm parser / rewriter

`parse_algorithm(s: str) -> list[str]` returns **only the 18 face-turn tokens**.
Accepted input tokens: `U D L R F B` (+ `'`/`2`), rotations `x y z`, slices `M E S`,
wide moves `Uw/u, Dw/d, Lw/l, Rw/r, Fw/f, Bw/b` (+ `'`/`2`).

Rotations are handled by **relabel tracking**: an `x/y/z` token updates a logical→physical
face mapping applied to all subsequent tokens (no rotation is ever emitted — the cubie model
has fixed centers). Wide and slice moves rewrite to an outer face turn plus a rotation, e.g.
`r ≡ L` followed by an `x` relabel (`r = L·x`), `M ≡ x'·L'·R`... derive the rest; the tests
pin the behavior:

- `parse_algorithm("x U x'")` acts identically to `F`
- `parse_algorithm("y F y'")` acts identically to `R`
- `parse_algorithm("z U z'")` acts identically to `L`
- `parse_algorithm("r U r'")` acts identically to `L F L'`
- `parse_algorithm("M2 U M2 U2 M2 U M2")` (H-perm) applied to solved leaves the first two
  layers solved and permutes only U-layer edges
- for every supported token `t`: `parse(t + " " + inverse(t))` acts as identity

`invert(alg)` and `to_notation(list) -> str` round-trip.

---

## 5. Validation (`cube/validate.py`)

Given a facelet string, in order:

1. Length 54, alphabet {U,R,F,D,L,B}, each letter appears **exactly 9** times.
2. The 6 centers (indices 4, 13, 22, 31, 40, 49) are 6 **distinct** letters. (They also must
   equal U,R,F,D,L,B respectively — the scan protocol guarantees the canonical frame; if not,
   report `bad_centers`.)
3. Every corner triple / edge pair matches a real cubie (via §3.1 tables), each cubie found
   exactly once. Failure code: `unrecognized_pieces`, with the offending facelet indices.
4. `sum(co) % 3 == 0` — code `corner_twist`.
5. `sum(eo) % 2 == 0` — code `edge_flip`.
6. `permutation_parity(cp) == permutation_parity(ep)` — code `permutation_parity`.

Return `ValidationResult(valid, errors=[{code, message, facelets:[indices], suspect_faces:[letters]}])`.
`suspect_faces` = faces containing the implicated facelet indices (for counts: the
over/under-represented letters' faces; for parity/orientation: all faces touched by the
offending pieces). Friendly `message` strings — they are shown to the user.

---

## 6. Scan protocol (frontend ↔ vision ↔ assembly)

Hold: **yellow up, green front** ("home"). Camera sees one full face inside a square guide.
Scan order and cube motions (UI shows a diagram per step):

| # | Face scanned (color) | How to get there from previous |
|---|----------------------|--------------------------------|
| 1 | F (green)  | start at home |
| 2 | R (orange) | rotate cube 90° to the left, keeping yellow up (y) |
| 3 | B (blue)   | same again (y) |
| 4 | L (red)    | same again (y) |
| 5 | U (yellow) | same again to return to home (y), then tilt the cube **toward you** (x') so yellow faces the camera |
| 6 | D (white)  | tilt **away from you** twice (x·x from the U-scan pose) so white faces the camera |

**Key property (must hold, do not break it):** with this protocol, reading the camera image's
9 cells in row-major order (top-left → bottom-right) yields exactly facelet indices 1..9 of
that face as defined in §2. No per-face reindexing is needed anywhere.

- Frontend crops the guide-box region to a square (≥ 270×270) and sends that image.
- Sampling: for each of the 9 cells, average the **middle 40%** patch; report per-patch
  BGR→Lab (OpenCV Lab, L∈[0,255]) and per-patch standard deviation.
- Classification (all 54 samples at once): k-means k=6 in Lab; label clusters by the 6 face
  **centers** (sample index 4 of each face); then enforce **exactly 9 stickers per color** via
  optimal assignment (`scipy.optimize.linear_sum_assignment` on the 54×54 cost matrix, each
  cluster center repeated 9×, cost = squared Lab distance). Confidence per sticker = margin
  between best and second-best cluster distance, normalized. A center sticker assigned to a
  different color than its own ⇒ hard error (re-scan). Ambiguous = confidence below threshold.

---

## 7. Solver contracts

The solver operates on CubieState in the canonical frame (centers fixed: U=yellow layer,
D=white layer). Output uses **only the 18 face-turn tokens**.

- **Stage `cross`**: solve the 4 D-layer edges (DR, DF, DL, DB — cubies 4,5,6,7 in slots
  4,5,6,7 with eo=0). BFS over the abstraction (positions+orientations of those 4 edges,
  ≈190k states). Must find ≤ 8 moves. One step, label `"Cross"`.
- **Stage `f2l`**: 4 steps. Slots: FR pair = corner DFR+edge FR, FL = DLF+FL, BL = DBL+BL,
  BR = DRB+BR. **Greedy order**: at each round, IDA* every unsolved slot and commit the
  shortest solution. Goal test: target pair solved AND cross AND previously solved slots
  intact. Move set: all faces **except D** (15 moves). Heuristic: max of (target-pair PDB,
  cross PDB, solved-slot pair PDBs) — pair PDB = BFS distance over (corner pos/ori × edge
  pos/ori) = 24×24 = 576 entries per slot; cross PDB = the §cross abstraction distance table.
  Precompute at import or first use; cache under `solver/cache/` (gitignored). Step labels:
  `"F2L pair 1 (FR slot)"` etc., numbered in the order actually solved.
- **Stage `oll`** (57 cases): recognition key = orientation signature
  `(co[0..3], eo[0..3])` of the U-layer slots. Build the lookup **programmatically at import**:
  for each case's algorithm `A` and each pre-AUF `k∈{0..3}`, compute the state
  `s = apply(inverse(U^k · A), solved)` — from `s`, playing `U^k A` orients the last layer —
  and map `signature(s) → (case, U^k A)`. Assert while building: `s` has its first two layers
  solved (data typo detector) and the map covers **exactly 215 non-solved signatures** with no
  cross-case collisions. Runtime: signature hit ⇒ one step, label `"OLL — <name>"`, and any
  pre-AUF U move is included at the front of the step's move list. OLL skip ⇒ omit the step
  (stage may have an empty steps list, include it with a `"skipped": true` step label "OLL skip").
- **Stage `pll`** (21 cases): recognition key = `(cp[0..3], ep[0..3])` (all LL pieces are in
  the LL after OLL). Same programmatic construction, but enumerating **both** pre-AUF `k` and
  post-AUF `j` (a state solved by `U^k A U^j` stores moves `U^k A`; the trailing `U^j` is
  recovered at runtime by the AUF computation). Assert F2L+orientation preserved by each setup
  and full coverage of **288 signatures** = 284 case signatures + the 4 AUF-only states
  (handled as "PLL skip" + AUF). Note: pre-AUF alone reaches only 84 signatures — the post-AUF
  enumeration is required for completeness. After the algorithm, compute **AUF** (`U/U'/U2/none`) and emit
  it as a final separate step labeled `"AUF"` when non-empty. Label `"PLL — <name>"`.
- **`cfop.solve(facelets) -> SolveResult`** per §8. After constructing the result, the module
  MUST verify by applying every emitted move in order to the input state and asserting the
  cube is solved (defense in depth — a solver bug can never ship an unsolved walkthrough).

### 7.1 OLL/PLL data files

`solver/data/oll.json`: `[{"id": 1..57, "name": "...", "alg": "..."}]` — 57 entries, standard
case numbering/names (e.g. 27 = "Sune", 21 = "H/Double Sune"). `solver/data/pll.json`:
21 entries, `"id"` = the letter name (`"Aa","Ab","E","F","Ga","Gb","Gc","Gd","H","Ja","Jb",
"Na","Nb","Ra","Rb","T","Ua","Ub","V","Y","Z"`). Algorithms may use rotations/wide/slice
tokens (the parser rewrites them), but must be **standard published algorithms**. The §7
build-time assertions are the correctness gate: a wrong alg fails F2L-preservation or
coverage and names the offending case id.

---

## 8. API (FastAPI, all routes under `/api`, permissive CORS)

### POST `/api/solve`  — body `{"facelets": "<54 chars>"}`

`200`:
```jsonc
{
  "valid": true,
  "facelets": "…54…",
  "total_moves": 61,
  "stages": [
    {
      "id": "cross" | "f2l" | "oll" | "pll",
      "label": "Cross" | "F2L" | "OLL" | "PLL",
      "steps": [
        {
          "label": "F2L pair 2 (BR slot)",   // human label
          "case": null | "OLL 27 — Sune" | "PLL T",
          "moves": ["R","U","R'"],            // face turns only
          "notation": "R U R'",
          "move_offset": 14,                   // index of this step's first move in the flat move list
          "skipped": false,
          "highlight": [                       // pieces to glow during this step
            {"type": "edge",   "piece": "DF"}, // piece = its SOLVED slot name (identifies the cubie by its colors)
            {"type": "corner", "piece": "DFR"}
          ]
        }
      ]
    }
  ]
}
```
Cross highlights all 4 D-edges; each F2L step its pair; OLL/PLL/AUF all 8 U-layer pieces.
`400` on invalid cube: `{"valid": false, "errors": [{code, message, facelets, suspect_faces}]}` (§5).

### GET `/api/scramble` → `{"facelets": "…", "scramble": "R U' F2 …"}` (25 random moves applied to solved; for demo/testing).

### POST `/api/scan-face` — body `{"face": "F", "image": "<base64, may be a data: URL>"}`
Image = the cropped square guide region. Returns
`{"face":"F", "samples_lab": [[L,a,b]×9], "samples_rgb": [[r,g,b]×9], "quality": {"ok": bool, "noisy_cells": [idx], "message": "..."}}` (row-major order, §6).

### POST `/api/classify` — body `{"faces": {"U": [[L,a,b]×9], "R": …, "F": …, "D": …, "L": …, "B": …}}`
Returns:
```jsonc
{
  "facelets": "…54…" ,            // assembled per §6 ordering (sample i of face X = facelet X(i+1))
  "colors": {"U": ["U","B",…×9], …},  // per-face assigned letters
  "confidence": {"U": [0.97,…×9], …},
  "ambiguous": [{"face":"F","index":4,"margin":0.08}],
  "valid": true,                   // §5 result on the assembled string
  "errors": []                     // §5 errors if invalid
}
```

---

## 9. Frontend

### 9.1 Stack & flow
Vite + React + TypeScript + `three` (plain three.js, no react-three-fiber). Dev server
proxies `/api` → `http://127.0.0.1:8010`. App flow: landing offers **Scan with camera**,
**Enter colors manually** (click-to-paint an unfolded net + facelet-string paste box), and
**Demo: random scramble** (GET /api/scramble). All three converge on POST /api/solve →
Walkthrough view (CubeView + controls).

### 9.2 Facelet → 3D mapping
Cube = 26 cubie meshes at grid positions `(x,y,z) ∈ {-1,0,1}³ \ origin`, axes:
**+x = R, +y = U, +z = F**. Sticker placement from the facelet string (0-based `k = row*3+col`
within a face, per the §2 viewing orientations):

| Face | normal | grid position of sticker k | 
|------|--------|-----------------------------|
| U | +y | `x = col-1`, `y = 1`, `z = row-1` (row 0 at back, adjacent B) |
| D | −y | `x = col-1`, `y = -1`, `z = 1-row` (row 0 at front, adjacent F) |
| F | +z | `x = col-1`, `y = 1-row`, `z = 1` |
| B | −z | `x = 1-col`, `y = 1-row`, `z = -1` |
| R | +x | `x = 1`, `y = 1-row`, `z = 1-col` |
| L | −x | `x = -1`, `y = 1-row`, `z = col-1` |

Sanity anchor: solved cube shows yellow on +y, green on +z, orange on +x, and facelet U1
(index 0) is the (-1, 1, -1) cubie's top sticker.

### 9.3 Animation (no drift, ever)
Keep a **logical model**: each cubie has integer grid coords + an exact orientation (e.g. a
quaternion snapped from a whitelist, or a face-normal→color map updated by exact 90°
rotations). To animate move `m`: attach the layer's meshes to a pivot `Object3D`, tween the
pivot (ease in-out, 90° or 180°), then on completion detach, **recompute every affected
cubie's transform from the logical model** (integers/exact rotations), and only then accept
the next move. Prev-step = apply inverse (may be instant). Jump-to-step = rebuild from the
initial facelet state + move prefix, instantly. Playback speed multiplies tween duration.
Camera: orbit controls, initial view showing U/F/R — matching how the user holds the cube.

### 9.4 Highlights
A highlight descriptor names a piece by its **solved slot** (e.g. edge "DF" = the cubie whose
sticker colors are {color(D), color(F)} = {white, green}). The frontend finds that mesh by
matching its sticker color set from the initial scanned state and glows it (emissive pulse)
while its step is current, wherever the piece currently is.

### 9.5 Scanner
getUserMedia (rear camera preferred), square guide box with 3×3 grid overlay. Client-side
stability: sample the 9 cell centers each frame; when max per-cell RGB variance over the last
8 frames < threshold, show "steady" and enable/auto-fire capture. On capture: crop guide box
→ canvas → JPEG base64 → POST /api/scan-face → paint returned `samples_rgb` onto the grid as
confirmation. Step-by-step instructions + a small 3D/2D diagram per §6 including the exact
rotation to perform. After 6 faces → /api/classify → show the full net with per-sticker
colors and confidence; ambiguous cells pulse red with a "re-scan this face" button. Then
/api/solve. Camera errors (denied/unavailable) surface a friendly message + fall back to
manual entry.

---

## 10. Master test checklist (backend `pytest`, frontend `vitest`)

Cube core:
- **T1** facelet↔cubie round-trip: solved, and 500 random move-sequence states.
- **T2** every move: `m·m'` = identity, `m⁴` = identity, `m²=m2`.
- **T3** known sequences: applying `"R U R' U'"` 6× = identity; `"F R U R' U' F'"` twice ≠ identity but 6× hmm — use: sexy-move order 6, T-perm² = identity, `(R U R' U')`... keep: sexy×6 = id; `R U2 R' U' R U' R'`... (pick verified identities: sexy×6, (U R)⁷⁰? no — sexy×6 and slice H-perm from §4.3 suffice) plus scramble regression: `"R U R' U' F2 L'"` applied to solved yields a stored expected facelet string (compute once by an independent hand-check of the facelet permutations, then freeze).
- **T4** commutation: for all 18 moves and 100 random states, `to_facelets(apply_cubie(m,s)) == apply_facelet(m, to_facelets(s))`.
- **T5** parser identities of §4.3; `invert` round-trips; rejects garbage tokens.
- **T6** validation: solved OK; each single mutation (twist one corner, flip one edge, swap two edges, recolor one sticker) yields exactly the right error code; random legal scrambles always valid.

Solver:
- **T7** cross: 300 random scrambles → cross solved, length ≤ 8, only cross edges required.
- **T8** F2L: 200 random scrambles → after cross+F2L, first two layers fully solved; earlier slots never broken between steps.
- **T9** OLL build: table covers exactly 215 signatures, no collisions, every setup preserves F2L. Runtime: 200 random scrambles → after OLL stage, all LL pieces oriented.
- **T10** PLL build: 288 signatures incl. skips; every setup preserves F2L+orientation. Runtime: 200 random scrambles → after PLL+AUF, cube **solved**.
- **T11** cfop.solve on 300 random scrambles: verifies internally, stage labels/move_offsets consistent (offsets = cumulative lengths), all moves in the 18-token set, median solution length sane (40–80).

API:
- **T12** /api/solve happy path on a known scramble string: schema-complete response; /api/solve with an invalid string → 400 with §5 codes; /api/scramble → valid facelets that /api/solve solves.
- **T13** /api/classify with synthetic Lab samples (6×9 clusters + noise) → correct 54 letters, exact-9 counts, sensible confidence; a deliberately ambiguous sample is flagged.

Vision:
- **T14** synthetic face images (draw 3×3 colored grids with cv2, add noise/gradient lighting) → sampling recovers the 9 colors; full 6-face synthetic set through classify → correct facelet string under global brightness shifts and mild white balance shifts; red/orange remain separable.

Frontend (vitest):
- **T15** notation.ts parses all 18 tokens to correct axis/layer/turns and round-trips.
- **T16** cubeModel.ts: solved string → each face's 9 stickers land on the §9.2 positions (spot-check all 6 centers + U1/F1/R1 corners); sticker count per cubie correct (8 corners×3, 12 edges×2, 6 centers×1).

---

# PART 2 — Trainer mode + "Paper Toy" redesign (2026-07-12)

The "Paper Toy" design handoff (its tokens + interactive prototype, now absorbed into §12)
supersedes the frontend's *visual* spec (§9 layout/colors) but NOT the math, API, or scan
conventions above. New product decision (user-directed): the Trainer drills **five sets —
OLL, PLL, COLL, ZBLL, VLS** (the mock's F2L / 2-look-OLL cards are replaced), and it has
**two drill modes**: *random* (recognition + execution, case hidden) and *grind* (user picks
one case, execution only — UI designed here, §12.4).

## 11. Trainer backend (`solver/trainer.py`)

### 11.1 Case model
A **case** is an equivalence class of cube states in the canonical frame (centers fixed,
F2L = bottom two layers). Classes and free parameters per set:

| set | class defined by | up to | free params when generating a state | expected count |
|---|---|---|---|---|
| `oll` | LL orientation signature (§7, existing `solver/oll.py` cases, real names) | pre/post AUF | LL permutation (parity-consistent), AUF | 57 |
| `pll` | LL permutation signature (existing `solver/pll.py`, real names) | pre/post AUF | AUF (pre & post) | 21 |
| `coll` | (cp, co) of the 4 LL corners, **all 12 edges oriented (eo=0)** | pre/post AUF | LL **edge** permutation (parity-consistent with cp), AUF | enumerate (~42 incl. the two corners-oriented "O" perm classes; exclude the fully-solved-corners class) |
| `zbll` | full (cp, co, ep) of the LL with **eo=0** | pre/post AUF | AUF only | enumerate (expect 493 non-solved classes) |
| `vls` | LL orientation pattern (co×eo = 27×8) of the **post-insert** state | nothing (pair position fixes the frame) | LL permutation of the post-insert state | 216 |

- **Enumeration is the ground truth**: canonicalize each raw state under the 16 pre/post-AUF
  combinations (U^a · s · U^b), take the lexicographic minimum signature as the class key.
  Freeze the resulting counts as constants with a comment reconciling them against the
  community numbers (57 / 21 / ~42 / 493 / 216); a mismatch is a build error, not a shrug.
- **Case ids must be STABLE across releases** (records are keyed on them): sort classes by
  canonical signature and id them `"<set>-<group>-<n>"` (e.g. `zbll-Pi-17`, `coll-T-3`,
  `vls-eo2-11`); OLL/PLL reuse existing ids (`oll-27`, `pll-T`) and real names.
- **Groups**: OLL → existing `group` field from oll.json; PLL → single group; COLL/ZBLL → the
  OCLL family of the corner-orientation part (`O, H, Pi, T, U, L, S, AS`) — for ZBLL's `O`
  group (corners oriented ⇒ the PLL subset) name cases after the PLL they equal (via
  `solver/pll.py` recognition on a representative). VLS → grouped by the 8 edge-orientation
  patterns with human labels ("all edges flipped", "UF+UB flipped", …).
- **VLS state construction**: `S_target` = F2L solved + LL orientation per case + random
  parity-consistent LL perm; the trainable state is `S = apply_moves(S_target, "R U R'")`
  (the inverse of the canonical `R U' R'` insert, i.e. the FR pair sits connected in U).

### 11.2 Scramble generation — computed, never hand-curated
`generate(set_key, case_id=None, rng)`:
1. pick the case (uniform over the set if not given), build a concrete state `S` by
   randomizing the case's free params (perm draws must respect corner/edge parity equality);
2. `solution = flat moves of cfop.solve(cubies_to_facelets(S))` (cross/F2L stages are
   empty/near-empty for LL states by construction; the internal replay-verify gate of
   §7 already guarantees correctness);
3. `scramble = invert(solution)`.

Because the free params are re-drawn every time, one case yields **many distinct scrambles**
(different underlying permutation and/or AUF ⇒ different table entries fire ⇒ genuinely
different move sequences). This satisfies the "several scrambles per case so recognition
can't be memorized" requirement without any new algorithm data. Determinism for tests via an
explicit `rng` seed.

### 11.3 Preview payload
`preview = {u: [9], f: [3], r: [3], b: [3], l: [3]}` — the LL pattern as seen from above:
`u` = U-face facelets row-major, plus the top row of each side face (left→right as viewed
from that face). Values are face letters for stickers that are **recognition-relevant** for
the set, else `"x"` (render dim):
- `oll`, `vls`: letter `U` where the facelet is U-colored, else `x` (classic OLL diagram).
- `pll`, `zbll`: actual facelet letters (all relevant).
- `coll`: corner-position facelets = actual letters; edge positions on the sides = `x`
  (edges are unconstrained); U-face edge stickers = `U` (edges oriented).
Computed from the canonical class representative (perm free params fixed to a canonical
choice so the preview is stable).

### 11.4 API (append to `app.py`, same conventions as §8)
- `GET /api/trainer/sets` → `{"sets": [{key, name, count, description, groups: [{key, name, count}]}]}`
  (order: oll, pll, coll, zbll, vls).
- `GET /api/trainer/cases?set=zbll[&group=Pi]` → `{"set": "zbll", "cases": [{id, name, group, preview}]}`.
- `GET /api/trainer/scramble?set=oll[&case_id=oll-27][&seed=123]` →
  `{set, case_id, name, group, scramble, solution, preview}`. `solution` (the inverse of the
  scramble, notation string) exists to drive the ghost cube. Unknown set/case → 400
  `{"valid": false, "errors": [{code: "unknown_set"|"unknown_case", ...}]}`. `seed` is for
  tests only.
- The random-mode client receives `name`/`preview` but MUST NOT render them until the solve
  is done (design ⚠️ #2). This is a UI rule, not a server secret.

### 11.5 Tests (T17)
For every COLL/OLL/PLL case, every VLS case, and ≥60 sampled ZBLL cases: 3 seeded draws each →
(a) applying `scramble` to solved lands **in the requested case's class** (re-canonicalize and
compare keys); (b) `solution` replays the state to solved; (c) among 4 draws of one case at
least 2 distinct scrambles exist; (d) enumeration counts equal the frozen constants; (e) ids
stable = a golden-file snapshot of `(id → canonical key)` per set; (f) endpoints: happy path
per set, unknown set/case → 400, `case_id` targeting returns that case.

## 12. Paper Toy UI (frontend)

### 12.1 Source of truth
The "Paper Toy" design handoff — tokens, typography, per-screen layout, the trainer state
machine, and the two ⚠️ rules (real Three.js `CubeView` everywhere; case hidden until done in
random mode) — is binding and captured in this §12. Fonts via **@fontsource** packages (offline-safe):
`@fontsource/bricolage-grotesque` (600–800) + `@fontsource/space-mono` (400, 700).

### 12.2 File organization
`index.css` = tokens (the `--paper/--bar/--surface/...` variables), font imports, base/reset.
`App.css` = header/shell/home/solve-landing/manual. New per-feature stylesheets:
`Scanner.css`, `Walkthrough.css`, `Trainer.css`. `cubeModel.ts`'s letter→hex map switches to
the muted sticker palette (README table; D-white keeps a visible edge on cream via the
existing gap/border rendering). Router views:
`home · solve · scan · manual · walk · setpick · casepick · trainer · records`.
Header per README (logo→home, Train→setpick, Records→records with last-trained tab).

### 12.3 Trainer screen (random mode) — per README §7 + prototype copy
Phases `idle → recognition → execution → done`; advance via Space (ignored in inputs) or
tapping the timer panel. Hidden case until done. Hint copy (verbatim from prototype):
idle "press SPACE / tap to start recognition" · recog "recognizing… SPACE / tap when you
start turning" · exec "executing… SPACE / tap the instant you finish" · done "case added to
your records ✓ — SPACE / tap for the next scramble". Cube stage: recognition = hidden
("?" + "cube hidden during recognition"); execution = ghost (real CubeView playing the
**current scramble's `solution`**, tween-scaled so the whole playback lasts the PB **total**;
caption "plays your {pb}s solve — beat it"; if no PB: "set a PB and the ghost appears here");
done = ghost stops/hides. Session strip: last 6 totals, PBs green. Timer format
`(ms/1000).toFixed(2)`.

### 12.4 Grind mode (targeted drilling) — NEW UI, designed here
- **Set picker** (README §6, restyled to 5 sets): each set card gains two actions —
  **"Random drill ▸"** (ink pill, primary → trainer random mode) and **"Choose a case…"**
  (outline pill → casepick).
- **Casepick** (`view: casepick`): back link "← sets", title "{Set} — pick a case to grind",
  a **group tab row** (pills, ink-filled when active; groups from `/api/trainer/cases`),
  then a responsive grid of **case tiles**: a mini 2D preview (the §11.3 pattern: 5×5-ish
  grid — 3×3 U face with the four 1×3 side strips around it, `x` cells dim `#E2D7BF`,
  letters in the muted sticker palette), case name (Space Mono 700 11px), and a small PB
  chip (`PB 4.21` green-tinted) when a record exists. Tiles tilt ±1deg alternately; click →
  trainer grind mode for that case. ZBLL loads once and filters client-side.
- **Trainer (grind variant)**: same layout as random with these differences — header shows
  the **case name + preview openly** (chip "grinding" in yellow `#F0C64A` instead of the set
  chip); **no RECOG pill** — a single EXEC split pill; phases `idle → execution → done`
  (Space/tap: start, stop, next scramble for the SAME case); the big timer is yellow-on-ink
  throughout; cube stage shows the **case state** on CubeView while idle (user can check
  their setup), and the ghost (scaled to PB **exec**) during execution; hint copy: idle
  "press SPACE / tap to start the timer" · exec "executing… SPACE / tap the instant you
  finish" · done "logged ✓ — SPACE / tap for a new scramble of this case". Each `done→idle`
  fetches a **fresh scramble for the same case_id** (variety per §11.2).
- **Records interplay**: grind results update **only** `exec` best and `n` (execution splits
  are comparable across modes); `recog`/`total` bests are set only by random mode. Records
  table renders "—" for missing recog/total exactly as for untrained cases.

### 12.5 Records
Per README §8 with **five tabs** (OLL/PLL/COLL/ZBLL/VLS; ZBLL table virtualized or grouped by
OCLL family with collapsible sections — 493 rows must stay usable). Persisted at
`localStorage["alglabs.records.v1"] = {[setKey]: {[caseId]: {recog, exec, total, n}}}`
(min per field independently; `recog`/`total` may be absent for grind-only cases). Also
`localStorage["alglabs.lastset.v1"]` for the Records default tab. Never clear other keys.

### 12.6 Tests (T18)
Vitest: records store (merge rules incl. grind-only exec updates, PB detection, localStorage
round-trip, never touching foreign keys); trainer state machine as a pure reducer (both
modes' phase transitions, split freezing, session strip); preview-grid mapping from the §11.3
payload. Existing T15/T16 updated for the muted palette. `npm run test` + `npm run build`
green; backend suite stays green.
