# AlgLabs

Two apps in one:

- **Solve a cube** - read a real Rubik's Cube with your webcam (or paint the colors in by
  hand), then watch an animated 3D walkthrough solve it step by step with the CFOP method:
  Cross, then F2L, then OLL, then PLL.
- **Train algorithms** - drill the OLL, PLL, COLL, ZBLL and VLS algorithm sets against a
  timer, and build up a record of how fast you are on each individual case.

## Training

Each drill hands you a scrambled cube that is one case from the set you picked, and times
you in two halves:

- **Recognition** - the clock that runs while you work out *which* case you are looking at.
- **Execution** - the clock that runs while your hands do the algorithm.

Splitting the two matters because they improve differently: slow recognition means you need
to learn the case's shape, slow execution means you need to drill the fingers. One combined
time hides which of the two is holding you back.

A few things support that:

- **The ghost cube** replays your personal best for the current case alongside your current
  attempt, so you are racing your own fastest solve rather than an abstract number.
- **Records are saved in your browser** (`localStorage`), per case: your best recognition,
  best execution, best total, and how many times you have drilled it. Nothing is uploaded
  and there is no account, so your records live on whatever browser you trained in.
- **Two modes per set.** *Random drill* hides the case until you finish, so you cannot skip
  the recognition half, and every draw is a genuinely different scramble rather than the
  same setup moves each time. *Grind* lets you pick one case from a visual browser and rep
  it over and over with an execution-only timer.

## Solving without a camera

You do not need a webcam. On **Solve a cube**, choose **Enter colors by hand**, and paste
this 54-character string into the box to load a scrambled cube:

```
LRBRUULBDRFDFRBUDUULBUFLRBFDURDDBBFRFUFDLLLFFLDDRBLBRU
```

That is the cube you get from applying this scramble to a solved cube:

```
F L2 U B F2 U2 F U' L R B' U2 R B L2 D R B F' R2
```

It solves in 51 moves, and the walkthrough runs the full method end to end, including an
OLL 2 (Zamboni) and a PLL Ua, so it is a good way to see everything working. You can also
click stickers on the unfolded net to enter any cube of your own, or use **Demo scramble**
to have one rolled for you.

## Stack

- **Backend** - Python 3.12, FastAPI, OpenCV, NumPy, SciPy. Cube math on a validated cubie
  model, a hybrid CFOP solver (search for Cross and F2L, machine-verified 57-case and
  21-case tables for OLL and PLL), CIELAB k-means color classification for the scanner, and
  the trainer engine, which enumerates the case sets mathematically (57 / 21 / 42 / 493 /
  216) and computes scrambles that are replayed and verified before being served.
- **Frontend** - React, TypeScript, Vite, Three.js. The webcam scan flow, the animated 3D
  walkthrough, and the trainer UI.

## Run

```bash
# backend (from repo root) - http://127.0.0.1:8010
cd backend && uv sync && uv run uvicorn app:app --port 8010

# frontend (second terminal) - http://localhost:5173, proxies /api to the backend
cd frontend && npm install && npm run dev
```

## Test

```bash
cd backend && uv run pytest   # cube core, solver, vision, API, trainer engine
cd frontend && npm run test   # notation, cube model, scan logic, trainer machines/records
```

## Docs

- [docs/CONTRACTS.md](docs/CONTRACTS.md) - engineering conventions: the facelet/cubie model,
  the scan protocol, API schemas, trainer case math (§11), the UI spec (§12), and the
  property-test suite that enforces all of it.
