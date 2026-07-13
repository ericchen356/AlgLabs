# AlgLabs — CFOP trainer & scanner

Two apps in one, wrapped in a warm "Paper Toy" design:

- **Solve a cube** — scan a Rubik's Cube with your webcam (or paint the net by hand, or roll
  a demo scramble), and watch an animated 3D walkthrough that solves it step-by-step with
  the CFOP method (Cross → F2L → OLL → PLL).
- **Train algorithms** — drill **OLL · PLL · COLL · ZBLL · VLS** with split
  recognition/execution timing, a ghost cube of your personal best to race, and persistent
  per-case records. Two modes per set: **random drill** (the case stays hidden until you
  finish — every draw is a structurally different scramble, so you can't memorize your way
  around recognition) and **grind** (pick one case from the visual case browser and rep it
  with an execution-only timer).

## Stack

- **Backend** — Python 3.12, FastAPI, OpenCV, NumPy, SciPy. Cube math (validated cubie
  model), the hybrid CFOP solver (search-based Cross/F2L, machine-verified 57/21-case
  OLL/PLL tables), CIELAB k-means color classification, and the trainer engine
  (mathematically enumerated case classes — 57/21/42/493/216 — with computed, replay-verified
  scrambles).
- **Frontend** — React + TypeScript + Vite + Three.js. Webcam scan UX, the animated 3D
  walkthrough, and the trainer UI. Records persist in `localStorage`.

## Run

```bash
# backend (from repo root) — http://127.0.0.1:8010
cd backend && uv sync && uv run uvicorn app:app --port 8010

# frontend (second terminal) — http://localhost:5173, proxies /api to the backend
cd frontend && npm install && npm run dev
```

## Test

```bash
cd backend && uv run pytest          # cube core, solver, vision, API, trainer engine
cd frontend && npm run test          # notation, cube model, scan logic, trainer machines/records
```

## Docs

- [docs/CONTRACTS.md](docs/CONTRACTS.md) — engineering conventions: facelet/cubie model,
  scan protocol, API schemas, trainer case math (§11), Paper Toy UI spec (§12), and the
  property-test suite that enforces it all.
