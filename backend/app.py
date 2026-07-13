"""CubeSight FastAPI application — all routes under /api (CONTRACTS.md §8).

Endpoints:

* ``POST /api/solve``     — CFOP walkthrough for a facelet string.
* ``GET  /api/scramble``  — 25-move random scramble + resulting facelets.
* ``POST /api/scan-face`` — sample the 9 sticker patches of one face image.
* ``POST /api/classify``  — 54 Lab samples -> facelet string + §5 validation.
"""

from __future__ import annotations

import random
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cube.facelet import CubieState, cubies_to_facelets
from cube.moves import apply_moves, random_scramble
from cube.validate import validate
from solver import cfop
from vision.classify import ClassifyError, classify_faces
from vision.quality import assess_face
from vision.sampling import SamplingError, sample_face

app = FastAPI(title="CubeSight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class SolveRequest(BaseModel):
    facelets: str


class ScanFaceRequest(BaseModel):
    face: str = Field(pattern="^[URFDLB]$")
    image: str


class ClassifyRequest(BaseModel):
    faces: dict[str, list[list[float]]]


def _error_response(status: int, errors: list[dict[str, Any]]) -> JSONResponse:
    return JSONResponse(status_code=status, content={"valid": False, "errors": errors})


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@app.post("/api/solve")
def solve(body: SolveRequest) -> Any:
    """CFOP solution per §8; 400 with §5 error dicts on an invalid cube."""
    try:
        return cfop.solve(body.facelets)
    except cfop.CubeInvalidError as exc:
        return _error_response(400, exc.errors)


@app.get("/api/scramble")
def scramble() -> dict[str, str]:
    """A fresh 25-move random scramble and the facelets it produces."""
    notation = random_scramble(random.Random(), n_moves=25)
    state = apply_moves(CubieState.solved(), notation)
    return {"facelets": cubies_to_facelets(state), "scramble": notation}


@app.post("/api/scan-face")
def scan_face(body: ScanFaceRequest) -> Any:
    """Sample one face image: 9 Lab/RGB patch means + a quality report."""
    try:
        samples = sample_face(body.image)
    except SamplingError as exc:
        return _error_response(
            400, [{"code": "bad_image", "message": exc.message, "suspect_faces": [body.face]}]
        )
    return {
        "face": body.face,
        "samples_lab": samples.samples_lab,
        "samples_rgb": samples.samples_rgb,
        "quality": assess_face(samples),
    }


@app.post("/api/classify")
def classify(body: ClassifyRequest) -> Any:
    """Classify all 54 stickers, then §5-validate the assembled string.

    Classification failures (indistinct/mismatched centers) are 400s with the
    structured ClassifyError payload; a §5-invalid but classifiable cube is a
    200 with ``valid: false`` and the §5 errors alongside the classification.
    """
    try:
        result = classify_faces(body.faces)
    except ClassifyError as exc:
        return _error_response(400, [exc.to_dict()])
    except ValueError as exc:
        return _error_response(
            400, [{"code": "bad_samples", "message": str(exc), "suspect_faces": []}]
        )
    validation = validate(result["facelets"])
    return {
        **result,
        "valid": validation.valid,
        "errors": [e.to_dict() for e in validation.errors],
    }


# --------------------------------------------------------------------------- #
# Trainer routes (CONTRACTS.md §11.4) — appended; existing routes unchanged.
# --------------------------------------------------------------------------- #

from fastapi import Query  # noqa: E402  (trainer addition)

from solver import trainer  # noqa: E402  (trainer addition)


@app.get("/api/trainer/sets")
def trainer_sets() -> Any:
    """The five drillable sets with counts, descriptions and groups."""
    return trainer.sets_payload()


@app.get("/api/trainer/cases")
def trainer_cases(
    set_key: str = Query(alias="set"),
    group: str | None = Query(default=None),
) -> Any:
    """All cases of one set (optionally one group) with §11.3 previews."""
    try:
        return trainer.cases_payload(set_key, group=group)
    except trainer.TrainerError as exc:
        return _error_response(400, [exc.to_dict()])


@app.get("/api/trainer/scramble")
def trainer_scramble(
    set_key: str = Query(alias="set"),
    case_id: str | None = Query(default=None),
    seed: int | None = Query(default=None),
) -> Any:
    """A fresh case-targeted scramble (§11.2); ``seed`` is for tests only."""
    try:
        return trainer.scramble_payload(set_key, case_id=case_id, seed=seed)
    except trainer.TrainerError as exc:
        return _error_response(400, [exc.to_dict()])
