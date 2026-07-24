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

## Deploy (split: Vercel + Render, both free tiers)

The frontend is a static bundle; the backend needs OpenCV/SciPy and is too large for a
serverless function, so it runs as a small always-addressable web service instead. Both
halves are described by checked-in config - there is nothing to configure by hand beyond
two values.

**1. Backend on Render.** New → Blueprint → point it at this repo. `render.yaml` builds
`backend/requirements.txt` and starts `uvicorn app:app`; the free plan needs no card. Note
the resulting URL, e.g. `https://alglabs-api.onrender.com`.

**2. Frontend on Vercel.** Import the repo. `vercel.json` at the root already sets the
build (`frontend/`, Vite, SPA fallback). Add one Environment Variable before the first
build:

```
VITE_API_BASE = https://alglabs-api.onrender.com/api
```

**3. Lock down CORS.** Back on Render, set `ALGLABS_ALLOWED_ORIGINS` to your Vercel URL
(comma-separated if you keep preview domains), replacing the `*` default.

Free-tier caveats worth knowing:

- Render idles the instance after ~15 minutes without traffic, and the next request pays a
  cold start of roughly half a minute. Two things absorb that: the app pings `/api/health` on
  mount so the wake-up overlaps with the home screen, and any request outstanding for more
  than 1.5s raises a "waking the server up" flag (header badge plus an inline note on the
  scan, trainer, manual-entry and demo screens) so the wait never reads as a hang.
- Requests give up after 90s. If the API is genuinely unreachable the UI drops into mock
  mode, which only solves one built-in demo scramble and cannot scan. If scanning
  "disappears" in production, check the API before anything else.
- Webcam capture needs a secure context; both hosts serve HTTPS, so this is already fine.
- `POST /api/scan-face` sends a base64 JPEG frame. Render does not cap request bodies the
  way serverless platforms do, so full-resolution frames are safe here.

## Docs

- [docs/CONTRACTS.md](docs/CONTRACTS.md) — engineering conventions: facelet/cubie model,
  scan protocol, API schemas, trainer case math (§11), Paper Toy UI spec (§12), and the
  property-test suite that enforces it all.
