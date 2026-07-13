"""T12 + T13: FastAPI endpoints (§8, §10) via fastapi.testclient."""

import base64
import json
import struct
import zlib

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import app
from cube.facelet import CubieState, cubies_to_facelets, facelets_to_cubies, is_solved
from cube.moves import MOVE_TOKENS, apply_moves
from cube.validate import validate

client = TestClient(app)

SOLVED = cubies_to_facelets(CubieState.solved())

#: Contract color scheme (§2.1) as RGB; white rendered slightly off-white
#: (250) so the quality layer never mistakes synthetic stickers for glare.
STICKER_RGB = {
    "U": (255, 213, 0),
    "R": (255, 88, 0),
    "F": (0, 155, 72),
    "D": (250, 250, 250),
    "L": (183, 18, 52),
    "B": (0, 70, 173),
}


def _lab(letter: str) -> list[float]:
    """OpenCV 8-bit Lab of a sticker color (single-pixel conversion)."""
    r, g, b = STICKER_RGB[letter]
    px = np.uint8([[[b, g, r]]])
    return [float(v) for v in cv2.cvtColor(px, cv2.COLOR_BGR2Lab)[0, 0]]


def _faces_payload(facelets: str) -> dict[str, list[list[float]]]:
    """§8 /classify body for a facelet string: 6 tight Lab clusters."""
    faces: dict[str, list[list[float]]] = {}
    for face_index, face in enumerate("URFDLB"):
        samples = []
        for i in range(9):
            L, a, b = _lab(facelets[face_index * 9 + i])
            jitter = ((face_index * 9 + i) % 3) - 1  # deterministic +-1
            samples.append([L + jitter, a + jitter * 0.5, b - jitter * 0.5])
        faces[face] = samples
    return faces


# --------------------------------------------------------------------------- #
# T12 — /api/solve and /api/scramble
# --------------------------------------------------------------------------- #


def test_solve_happy_path_known_scramble():
    facelets = cubies_to_facelets(apply_moves(CubieState.solved(), "R U R' U' F2 L'"))
    response = client.post("/api/solve", json={"facelets": facelets})
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {"valid", "facelets", "total_moves", "stages"}
    assert body["valid"] is True
    assert body["facelets"] == facelets
    assert [s["id"] for s in body["stages"]] == ["cross", "f2l", "oll", "pll"]
    assert [s["label"] for s in body["stages"]] == ["Cross", "F2L", "OLL", "PLL"]

    flat: list[str] = []
    for stage in body["stages"]:
        assert set(stage) == {"id", "label", "steps"}
        for step in stage["steps"]:
            assert set(step) == {
                "label", "case", "moves", "notation", "move_offset",
                "skipped", "highlight",
            }
            assert step["move_offset"] == len(flat)
            assert all(m in MOVE_TOKENS for m in step["moves"])
            for h in step["highlight"]:
                assert set(h) == {"type", "piece"}
                assert h["type"] in ("edge", "corner")
            flat.extend(step["moves"])
    assert body["total_moves"] == len(flat)
    assert is_solved(apply_moves(facelets_to_cubies(facelets), flat))


def test_solve_invalid_cube_400_with_section5_codes():
    # Twisted URF corner on an otherwise solved cube.
    twisted = list(SOLVED)
    twisted[8], twisted[9], twisted[20] = "R", "F", "U"
    response = client.post("/api/solve", json={"facelets": "".join(twisted)})
    assert response.status_code == 400
    body = response.json()
    assert body["valid"] is False
    assert [e["code"] for e in body["errors"]] == ["corner_twist"]
    assert set(body["errors"][0]) == {"code", "message", "facelets", "suspect_faces"}

    response = client.post("/api/solve", json={"facelets": "U" * 54})
    assert response.status_code == 400
    assert [e["code"] for e in response.json()["errors"]] == ["bad_counts"]

    response = client.post("/api/solve", json={"facelets": "UUF"})
    assert response.status_code == 400
    assert [e["code"] for e in response.json()["errors"]] == ["bad_length"]


def test_scramble_returns_valid_solvable_cube():
    response = client.get("/api/scramble")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"facelets", "scramble"}
    tokens = body["scramble"].split()
    assert len(tokens) == 25
    assert all(t in MOVE_TOKENS for t in tokens)
    assert len(body["facelets"]) == 54
    assert validate(body["facelets"]).valid
    # The scramble string reproduces the facelets.
    assert (
        cubies_to_facelets(apply_moves(CubieState.solved(), body["scramble"]))
        == body["facelets"]
    )
    # And /api/solve solves it.
    solve = client.post("/api/solve", json={"facelets": body["facelets"]})
    assert solve.status_code == 200
    assert solve.json()["valid"] is True


# --------------------------------------------------------------------------- #
# /api/scan-face
# --------------------------------------------------------------------------- #

_SCAN_LETTERS = ["F", "U", "R", "D", "L", "B", "F", "U", "R"]


def _face_image_base64(letters=_SCAN_LETTERS, size=270) -> str:
    """A clean synthetic 3x3 face image (PNG, base64)."""
    image = np.zeros((size, size, 3), dtype=np.uint8)
    cell = size // 3
    for row in range(3):
        for col in range(3):
            r, g, b = STICKER_RGB[letters[row * 3 + col]]
            image[row * cell : (row + 1) * cell, col * cell : (col + 1) * cell] = (
                b, g, r,
            )
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def test_scan_face_happy_path():
    payload = {"face": "F", "image": _face_image_base64()}
    response = client.post("/api/scan-face", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"face", "samples_lab", "samples_rgb", "quality"}
    assert body["face"] == "F"
    assert len(body["samples_lab"]) == 9 and len(body["samples_rgb"]) == 9
    for i, letter in enumerate(_SCAN_LETTERS):
        assert all(len(sample) == 3 for sample in (body["samples_lab"][i], body["samples_rgb"][i]))
        expected = STICKER_RGB[letter]
        assert all(
            abs(got - want) <= 3.0
            for got, want in zip(body["samples_rgb"][i], expected)
        ), f"cell {i}: {body['samples_rgb'][i]} != {expected}"
    assert body["quality"] == {
        "ok": True,
        "noisy_cells": [],
        "message": "Face captured cleanly.",
    }


def test_scan_face_accepts_data_url():
    payload = {"face": "U", "image": "data:image/png;base64," + _face_image_base64()}
    response = client.post("/api/scan-face", json=payload)
    assert response.status_code == 200
    assert response.json()["face"] == "U"


@pytest.mark.parametrize("image", ["", "!!!", "data:image/png;base64,AAAA"])
def test_scan_face_undecodable_image_is_structured_400(image):
    response = client.post("/api/scan-face", json={"face": "F", "image": image})
    assert response.status_code == 400
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "bad_image"
    assert body["errors"][0]["message"]


def test_scan_face_oversized_image_header_is_structured_400():
    """A tiny PNG whose header claims 65500x65500 pixels: cv2.imdecode raises
    (CV_IO_MAX_IMAGE_PIXELS) instead of returning None — still a 400."""
    ok, buffer = cv2.imencode(".png", np.zeros((1, 1, 3), dtype=np.uint8))
    assert ok
    png = bytearray(buffer.tobytes())
    struct.pack_into(">II", png, 16, 65500, 65500)  # IHDR width/height
    struct.pack_into(">I", png, 29, zlib.crc32(bytes(png[12:29])))  # IHDR CRC
    image = base64.b64encode(bytes(png)).decode("ascii")
    response = client.post("/api/scan-face", json={"face": "F", "image": image})
    assert response.status_code == 400
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "bad_image"


def test_scan_face_rejects_bad_face_letter():
    response = client.post(
        "/api/scan-face", json={"face": "X", "image": _face_image_base64()}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# T13 — /api/classify with synthetic Lab samples
# --------------------------------------------------------------------------- #


def test_classify_scrambled_cube_exact_letters():
    facelets = cubies_to_facelets(
        apply_moves(CubieState.solved(), "R U R' U' F2 L' B D2 R U'")
    )
    response = client.post("/api/classify", json={"faces": _faces_payload(facelets)})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "facelets", "colors", "confidence", "ambiguous", "valid", "errors",
    }
    assert body["facelets"] == facelets
    assert body["valid"] is True and body["errors"] == []
    assert body["ambiguous"] == []
    for face_index, face in enumerate("URFDLB"):
        assert body["colors"][face] == list(facelets[face_index * 9 : face_index * 9 + 9])
        assert len(body["confidence"][face]) == 9
        assert all(0.3 < c <= 1.0 for c in body["confidence"][face])
    # Exactly 9 stickers of each color.
    for letter in "URFDLB":
        assert body["facelets"].count(letter) == 9


def test_classify_flags_ambiguous_midpoint_sample():
    faces = _faces_payload(SOLVED)
    green = np.array(_lab("F"))
    blue = np.array(_lab("B"))
    faces["F"][0] = [float(v) for v in (green + blue) / 2.0]  # non-center cell
    response = client.post("/api/classify", json={"faces": faces})
    assert response.status_code == 200
    body = response.json()
    flagged = [(a["face"], a["index"]) for a in body["ambiguous"]]
    assert ("F", 0) in flagged
    margin = next(a["margin"] for a in body["ambiguous"] if (a["face"], a["index"]) == ("F", 0))
    assert margin < 0.15
    assert margin == body["confidence"]["F"][0]
    # The 9-per-color constraint still pins the sticker to its own face color,
    # so the assembled cube is the solved one and remains valid.
    for letter in "URFDLB":
        assert body["facelets"].count(letter) == 9
    assert body["facelets"] == SOLVED
    assert body["valid"] is True


def test_classify_invalid_but_classifiable_cube_valid_false():
    """Two stickers swapped between faces: clean classification, §5 errors."""
    swapped = list(SOLVED)
    swapped[9], swapped[18] = swapped[18], swapped[9]  # R1 <-> F1
    swapped = "".join(swapped)
    response = client.post("/api/classify", json={"faces": _faces_payload(swapped)})
    assert response.status_code == 200
    body = response.json()
    assert body["facelets"] == swapped
    assert body["colors"]["R"][0] == "F" and body["colors"]["F"][0] == "R"
    assert body["valid"] is False
    assert body["errors"], "section-5 errors must be surfaced"
    section5_codes = {
        "bad_length", "bad_characters", "bad_counts", "bad_centers",
        "unrecognized_pieces", "corner_twist", "edge_flip", "permutation_parity",
    }
    assert all(e["code"] in section5_codes for e in body["errors"])
    assert all(
        set(e) == {"code", "message", "facelets", "suspect_faces"}
        for e in body["errors"]
    )
    # Classification results are still fully present alongside the errors.
    assert set(body["confidence"]) == set("URFDLB")


def test_classify_indistinct_centers_is_structured_400():
    faces = _faces_payload(SOLVED)
    faces["U"][4] = _lab("D")  # yellow face scanned with a white-looking center
    response = client.post("/api/classify", json={"faces": faces})
    assert response.status_code == 400
    body = response.json()
    assert body["valid"] is False
    error = body["errors"][0]
    assert error["code"] == "indistinct_centers"
    assert set(error["suspect_faces"]) == {"U", "D"}


def test_classify_malformed_input_is_structured_400():
    faces = _faces_payload(SOLVED)
    faces["B"] = faces["B"][:5]  # only 5 samples for one face
    response = client.post("/api/classify", json={"faces": faces})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "bad_samples"

    response = client.post("/api/classify", json={"faces": {"U": [[0, 0, 0]] * 9}})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "bad_samples"


@pytest.mark.parametrize("bad", [1e308, float("nan"), float("inf"), float("-inf")])
def test_classify_nonfinite_samples_are_structured_400(bad):
    """Values that overflow the float32 cast (or NaN/Infinity tokens, which
    Python's json parser accepts) must be a 400 bad_samples, not a kmeans 500."""
    faces = _faces_payload(SOLVED)
    faces["U"][0][0] = bad
    response = client.post(
        "/api/classify",
        content=json.dumps({"faces": faces}),  # allow_nan: emits NaN/Infinity
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "bad_samples"
