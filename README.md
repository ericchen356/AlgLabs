# AlgLabs

A cube scanner, solver, and speedcubing trainer on the web.

Built by [Eric Chen](https://ericzxchen.com). Source: [github.com/ericchen356/AlgLabs](https://github.com/ericchen356/AlgLabs).

Two apps in one:

- **Solve a cube.** Read a real Rubik's Cube with your webcam (or paint the colors in by
  hand), then watch an animated 3D walkthrough solve it step by step with the CFOP method:
  Cross, then F2L, then OLL, then PLL.
- **Train algorithms.** Drill any of five last-layer sets against a timer and track how fast
  you are on each individual case:
  - **OLL** (Orientation of the Last Layer)
  - **PLL** (Permutation of the Last Layer)
  - **COLL** (Corners of the Last Layer)
  - **ZBLL** (Zborowski-Bruchem Last Layer)
  - **VLS** (Valk Last Slot)

## Training

Every drill gives you a scrambled cube that is one case from the set you picked, and it
times you in two halves:

- **Recognition** runs while you figure out which case you are looking at.
- **Execution** runs while your hands do the algorithm.

They are worth timing separately because you fix them in different ways. Slow recognition
means you need to learn the case's shape. Slow execution means you need to drill the fingers.
A single combined time cannot tell you which one to work on.

A few things build on that:

- **Ghost cube.** Your personal best for the current case replays next to your live attempt,
  so you race your own fastest solve instead of a number.
- **Local records.** Everything is saved in your browser (`localStorage`), per case: best
  recognition, best execution, best total, and how many reps you have done. There is no
  account and nothing is uploaded, so your records stay on whatever browser you trained on.
- **Two modes per set.** Random drill hides the case until you finish, so you cannot skip the
  recognition half, and each scramble is genuinely different rather than the same setup moves
  every time. Grind lets you pick one case from a visual browser and rep it with an
  execution-only timer.

## Solving without a camera

You do not need a webcam. On **Solve a cube**, pick **Enter colors by hand** and paste this
54-character string to load a scrambled cube:

```
LRBRUULBDRFDFRBUDUULBUFLRBFDURDDBBFRFUFDLLLFFLDDRBLBRU
```

That is what you get by applying this scramble to a solved cube:

```
F L2 U B F2 U2 F U' L R B' U2 R B L2 D R B F' R2
```

It solves in 51 moves and runs the full method end to end, including an OLL 2 (Zamboni) and a
PLL Ua. You can also click stickers on the unfolded net to enter your own cube, or hit **Demo
scramble** to have one rolled for you.

## Stack

- **Backend.** Python 3.12, FastAPI, OpenCV, NumPy, SciPy. Cube math on a validated cubie
  model, a hybrid CFOP solver (search for Cross and F2L, machine-verified 57-case and 21-case
  tables for OLL and PLL), CIELAB k-means color classification for the scanner, and the
  trainer engine, which enumerates the case sets mathematically (57 / 21 / 42 / 493 / 216) and
  computes scrambles that are replayed and verified before being served.
- **Frontend.** React, TypeScript, Vite, Three.js. The webcam scan flow, the animated 3D
  walkthrough, and the trainer UI.

## Run

```bash
# backend (from repo root), http://127.0.0.1:8010
cd backend && uv sync && uv run uvicorn app:app --port 8010

# frontend (second terminal), http://localhost:5173, proxies /api to the backend
cd frontend && npm install && npm run dev
```

## Test

```bash
cd backend && uv run pytest   # cube core, solver, vision, API, trainer engine
cd frontend && npm run test   # notation, cube model, scan logic, trainer machines/records
```

## Docs

[docs/CONTRACTS.md](docs/CONTRACTS.md) covers the engineering conventions: the facelet/cubie
model, the scan protocol, API schemas, trainer case math (§11), the UI spec (§12), and the
property-test suite that enforces all of it.
