"""T14 — vision pipeline tests (CONTRACTS.md §10).

Synthetic face images are drawn with cv2 (3x3 grids using the §2.1 hex
colours), degraded with brightness gradients, gaussian noise and mild
white-balance shifts, then pushed through the full sampling -> classify
path. All randomness is seeded.
"""

from __future__ import annotations

import base64
import random

import cv2
import numpy as np
import pytest

from vision.classify import AMBIGUITY_THRESHOLD, FACE_ORDER, ClassifyError, classify_faces
from vision.quality import assess_face, assess_quality
from vision.sampling import CANONICAL_SIZE, FaceSamples, SamplingError, sample_face

# §2.1 colour scheme.
HEX = {
    "U": "#FFD500",  # yellow
    "R": "#FF5800",  # orange
    "F": "#009B48",  # green
    "D": "#FFFFFF",  # white
    "L": "#B71234",  # red
    "B": "#0046AD",  # blue
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def hex_to_bgr(value: str) -> tuple[int, int, int]:
    r, g, b = hex_to_rgb(value)
    return b, g, r


def letter_lab(letter: str) -> list[float]:
    """OpenCV 8-bit Lab of a §2.1 face colour."""
    pixel = np.array([[hex_to_bgr(HEX[letter])]], dtype=np.uint8)
    lab = cv2.cvtColor(pixel, cv2.COLOR_BGR2Lab)[0, 0]
    return [float(v) for v in lab]


def face_image(
    letters: list[str],
    rng: np.random.Generator,
    *,
    wb_gain: tuple[float, float, float] = (1.0, 1.0, 1.0),
    gradient: tuple[float, float] = (1.0, 1.0),
    noise_sigma: float = 0.0,
    size: int = 270,
) -> np.ndarray:
    """Draw a 3x3 sticker grid (row-major) with cv2 and degrade it.

    ``wb_gain`` is a per-channel (b, g, r) gain simulating a white-balance
    shift; ``gradient`` is a horizontal brightness ramp (left, right).
    """
    img = np.zeros((size, size, 3), dtype=np.float64)
    cell = size // 3
    for i, letter in enumerate(letters):
        r0, c0 = (i // 3) * cell, (i % 3) * cell
        cv2.rectangle(
            img,
            (c0 + 4, r0 + 4),
            (c0 + cell - 5, r0 + cell - 5),
            hex_to_bgr(HEX[letter]),
            thickness=-1,
        )
    ramp = np.linspace(gradient[0], gradient[1], size)[None, :, None]
    img = img * ramp * np.array(wb_gain, dtype=np.float64)[None, None, :]
    if noise_sigma > 0:
        img = img + rng.normal(0.0, noise_sigma, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def encode_png(img: np.ndarray, *, data_url: bool = False) -> str:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}" if data_url else b64


def scrambled_arrangement(seed: int = 3) -> dict[str, list[str]]:
    """A deterministic arrangement of the 54 stickers: exactly 9 of each
    letter, with every face's centre (index 4) equal to its own letter."""
    rng = random.Random(seed)
    letters = list(FACE_ORDER) * 9
    rng.shuffle(letters)
    faces = {f: letters[i * 9 : (i + 1) * 9] for i, f in enumerate(FACE_ORDER)}
    for f in FACE_ORDER:
        if faces[f][4] == f:
            continue
        done = False
        for g in FACE_ORDER:
            for j in range(9):
                if j == 4 or faces[g][j] != f:
                    continue
                faces[g][j], faces[f][4] = faces[f][4], f
                done = True
                break
            if done:
                break
        assert done
    assert all(faces[f][4] == f for f in FACE_ORDER)
    flat = [c for f in FACE_ORDER for c in faces[f]]
    assert all(flat.count(f) == 9 for f in FACE_ORDER)
    return faces


def synth_lab_faces(
    arrangement: dict[str, list[str]],
    rng: np.random.Generator,
    noise_sigma: float = 1.5,
) -> dict[str, list[list[float]]]:
    """Lab samples straight from the §2.1 colours plus small noise."""
    return {
        f: [
            [v + float(n) for v, n in zip(letter_lab(letter), rng.normal(0, noise_sigma, 3))]
            for letter in arrangement[f]
        ]
        for f in FACE_ORDER
    }


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_sampling_recovers_solid_colors() -> None:
    letters = list("URFDLBUFR")
    rng = np.random.default_rng(0)
    img = face_image(letters, rng)  # clean: no noise, no gradient
    samples = sample_face(encode_png(img))
    assert isinstance(samples, FaceSamples)
    assert len(samples.samples_lab) == 9
    assert len(samples.samples_rgb) == 9
    assert len(samples.stddevs) == 9
    for got_rgb, got_lab, letter in zip(
        samples.samples_rgb, samples.samples_lab, letters
    ):
        expected_rgb = hex_to_rgb(HEX[letter])
        assert max(abs(g - e) for g, e in zip(got_rgb, expected_rgb)) < 4.0
        expected_lab = letter_lab(letter)
        assert max(abs(g - e) for g, e in zip(got_lab, expected_lab)) < 4.0


def test_sampling_row_major_order() -> None:
    """Cell k of the image (row-major) must be sample k."""
    letters = list("UUURRRFFF")  # rows: yellow / orange / green
    img = face_image(letters, np.random.default_rng(0))
    samples = sample_face(encode_png(img))
    for k, letter in enumerate(letters):
        expected = hex_to_rgb(HEX[letter])
        assert max(abs(g - e) for g, e in zip(samples.samples_rgb[k], expected)) < 4.0


def test_sampling_accepts_raw_base64_and_data_url() -> None:
    img = face_image(list("DDDDDDDDD"), np.random.default_rng(1))
    raw = sample_face(encode_png(img))
    via_url = sample_face(encode_png(img, data_url=True))
    assert raw.samples_lab == via_url.samples_lab
    assert raw.samples_rgb == via_url.samples_rgb


def test_sampling_resizes_nonstandard_input() -> None:
    img = face_image(list("FFFFFFFFF"), np.random.default_rng(2), size=402)
    samples = sample_face(encode_png(img))
    expected = hex_to_rgb(HEX["F"])
    for rgb in samples.samples_rgb:
        assert max(abs(g - e) for g, e in zip(rgb, expected)) < 4.0
    assert CANONICAL_SIZE == 270


def test_sampling_rejects_garbage() -> None:
    with pytest.raises(SamplingError):
        sample_face("this is !!! not base64 %%%")
    with pytest.raises(SamplingError):
        sample_face(base64.b64encode(b"not an image at all").decode("ascii"))
    with pytest.raises(SamplingError):
        sample_face("")


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


def test_quality_clean_face_ok() -> None:
    # No white (D) cell here: a synthetic #FFFFFF sticker under a >1 gain is
    # fully clipped and is legitimately indistinguishable from glare.
    rng = np.random.default_rng(4)
    img = face_image(list("FRLUBBFRL"), rng, noise_sigma=3.0, gradient=(0.93, 1.00))
    report = assess_face(sample_face(encode_png(img)))
    assert report["ok"] is True
    assert report["noisy_cells"] == []


def test_quality_flags_noisy_and_blown_cells() -> None:
    rng = np.random.default_rng(5)
    img = face_image(list("FFFFFFFFF"), rng).astype(np.float64)
    cell = 270 // 3
    # Cell 2 (row 0, col 2): heavy speckle noise -> high stddev.
    img[0:cell, 2 * cell : 3 * cell] += rng.normal(0, 80, (cell, cell, 3))
    # Cell 6 (row 2, col 0): fully blown highlight.
    img[2 * cell : 3 * cell, 0:cell] = 255.0
    img = np.clip(img, 0, 255).astype(np.uint8)
    report = assess_face(sample_face(encode_png(img)))
    assert report["ok"] is False
    assert 2 in report["noisy_cells"]
    assert 6 in report["noisy_cells"]
    assert report["message"]


def test_quality_rejects_wrong_lengths() -> None:
    with pytest.raises(ValueError):
        assess_quality([[0, 0, 0]] * 8, [0.0] * 8)


# ---------------------------------------------------------------------------
# Full pipeline: images -> sampling -> classify (T14 core)
# ---------------------------------------------------------------------------


def run_pipeline(
    arrangement: dict[str, list[str]],
    seed: int,
    wb_gains: dict[str, tuple[float, float, float]],
) -> dict:
    rng = np.random.default_rng(seed)
    lab_faces: dict[str, list[list[float]]] = {}
    for f in FACE_ORDER:
        img = face_image(
            arrangement[f],
            rng,
            wb_gain=wb_gains[f],
            gradient=(0.90, 1.10),
            noise_sigma=4.0,
        )
        samples = sample_face(encode_png(img, data_url=(f in "UF")))
        lab_faces[f] = samples.samples_lab
    return classify_faces(lab_faces)


def test_full_pipeline_recovers_scrambled_facelets() -> None:
    """6 synthetic faces with gradients, noise and per-face WB shifts must
    classify back to the exact known arrangement."""
    arrangement = scrambled_arrangement(seed=3)
    wb_gains = {  # mild per-face white-balance shifts (b, g, r gains)
        "U": (1.00, 1.00, 1.00),
        "R": (0.97, 1.00, 1.03),  # warm
        "F": (1.03, 1.00, 0.97),  # cool
        "D": (1.00, 1.02, 0.98),
        "L": (0.98, 0.98, 1.04),
        "B": (1.02, 1.01, 0.97),
    }
    result = run_pipeline(arrangement, seed=14, wb_gains=wb_gains)

    expected_facelets = "".join("".join(arrangement[f]) for f in FACE_ORDER)
    assert result["facelets"] == expected_facelets
    assert result["colors"] == arrangement
    # Exactly 9 stickers per colour by construction of the assignment.
    for letter in FACE_ORDER:
        assert result["facelets"].count(letter) == 9
    # Confidences are sane and nothing is ambiguous on a clean-ish scan.
    for f in FACE_ORDER:
        assert len(result["confidence"][f]) == 9
        assert all(0.0 <= c <= 1.0 for c in result["confidence"][f])
    assert result["ambiguous"] == []


def test_red_orange_separable_under_warm_shift() -> None:
    """Red (L) vs orange (R) must survive a warm white-balance shift plus
    the brightness gradient — the classic failure mode."""
    arrangement = scrambled_arrangement(seed=11)
    warm = (0.95, 1.00, 1.05)
    result = run_pipeline(arrangement, seed=15, wb_gains={f: warm for f in FACE_ORDER})
    for f in FACE_ORDER:
        for i, expected in enumerate(arrangement[f]):
            if expected in ("R", "L"):
                assert result["colors"][f][i] == expected, (
                    f"red/orange confusion at face {f} cell {i}: "
                    f"expected {expected}, got {result['colors'][f][i]}"
                )
    assert result["facelets"] == "".join("".join(arrangement[f]) for f in FACE_ORDER)


# ---------------------------------------------------------------------------
# Classify edge cases (direct Lab input)
# ---------------------------------------------------------------------------


def solved_arrangement() -> dict[str, list[str]]:
    return {f: [f] * 9 for f in FACE_ORDER}


def test_ambiguous_sticker_is_flagged() -> None:
    rng = np.random.default_rng(21)
    faces = synth_lab_faces(solved_arrangement(), rng)
    # Push one non-centre orange sticker halfway toward red.
    orange = np.array(letter_lab("R"))
    red = np.array(letter_lab("L"))
    faces["R"][0] = [float(v) for v in (orange + red) / 2.0]

    result = classify_faces(faces)
    flagged = {(e["face"], e["index"]) for e in result["ambiguous"]}
    assert ("R", 0) in flagged
    entry = next(e for e in result["ambiguous"] if (e["face"], e["index"]) == ("R", 0))
    assert entry["margin"] < AMBIGUITY_THRESHOLD
    assert result["confidence"]["R"][0] == entry["margin"]
    # A clean sticker on the same face stays confident.
    assert result["confidence"]["R"][1] > 0.5


def test_two_centers_in_one_cluster_raises() -> None:
    """Only 5 distinct colours (R and L identical) forces the R and L centres
    into one k-means cluster -> structured re-scan error naming both faces."""
    rng = np.random.default_rng(22)
    faces = synth_lab_faces(solved_arrangement(), rng, noise_sigma=1.0)
    # All 18 R/L samples become the exact same point: zero within-cluster
    # variance, so splitting it gains k-means nothing.
    same = letter_lab("L")
    faces["R"] = [list(same) for _ in range(9)]
    faces["L"] = [list(same) for _ in range(9)]
    # Give blue a wide bimodal spread so the 6th cluster splits it instead.
    blue = np.array(letter_lab("B"))
    faces["B"] = [
        [float(v) for v in blue + np.array([0.0, 0.0, -25.0 if i < 4 else 25.0])]
        for i in range(9)
    ]

    with pytest.raises(ClassifyError) as excinfo:
        classify_faces(faces)
    err = excinfo.value
    assert err.code == "indistinct_centers"
    assert "R" in err.faces and "L" in err.faces
    assert err.to_dict()["suspect_faces"] == err.faces


def test_center_assigned_other_color_raises() -> None:
    """A centre sticker that the 9-per-colour assignment pushes to another
    colour is a hard error naming the face."""
    rng = np.random.default_rng(23)
    faces = synth_lab_faces(solved_arrangement(), rng, noise_sigma=0.5)
    orange = np.array(letter_lab("R"))
    red = np.array(letter_lab("L"))
    # L's centre drifts 45% toward orange: still nearest the red cluster
    # (no indistinct_centers), but there are 10 red-leaning stickers for 9
    # red slots — one pure red is planted on face R — so the assignment
    # evicts the drifted centre into the orange colour.
    faces["L"][4] = [float(v) for v in red + 0.45 * (orange - red)]
    faces["R"][0] = [float(v) for v in red]

    with pytest.raises(ClassifyError) as excinfo:
        classify_faces(faces)
    err = excinfo.value
    assert err.code == "center_mismatch"
    assert "L" in err.faces


def test_classify_rejects_malformed_input() -> None:
    rng = np.random.default_rng(24)
    faces = synth_lab_faces(solved_arrangement(), rng)
    with pytest.raises(ValueError):
        classify_faces({f: faces[f] for f in "URFDL"})  # missing B
    bad = dict(faces)
    bad["U"] = bad["U"][:8]
    with pytest.raises(ValueError):
        classify_faces(bad)
