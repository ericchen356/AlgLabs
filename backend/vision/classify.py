"""Sticker colour classification over all 54 Lab samples (CONTRACTS.md §6).

Pipeline:

1. k-means with k=6 over the 54 Lab samples (deterministic: seeded OpenCV
   RNG + multiple k-means++ restarts).
2. Label the 6 clusters using the 6 face-centre samples (sample index 4 of
   each face). Two centres falling in the same cluster is a hard,
   structured error naming the faces to re-scan.
3. Enforce exactly 9 stickers per colour with an optimal assignment
   (``scipy.optimize.linear_sum_assignment``) on the 54x54 matrix of
   squared Lab distances, each colour's cluster centroid repeated 9 times.
4. Per-sticker confidence = normalised margin between the assigned colour's
   centroid distance and the closest competing centroid distance; entries
   below :data:`AMBIGUITY_THRESHOLD` are reported as ambiguous.
5. A centre sticker whose final assignment differs from its own face letter
   is a hard error (the scan frame cannot be trusted — re-scan).

Validation of the assembled facelet string (§5) is wired in the API layer,
not here.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

#: Face order used to assemble the 54-char facelet string (CONTRACTS.md §2).
FACE_ORDER = "URFDLB"

#: Confidence below which a sticker is reported as ambiguous.
AMBIGUITY_THRESHOLD = 0.15

#: Largest sample magnitude that survives the float32 cast fed to cv2.kmeans.
_MAX_SAMPLE_MAGNITUDE = float(np.finfo(np.float32).max)

_KMEANS_SEED = 20260711
_KMEANS_ATTEMPTS = 10
_KMEANS_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-4)


class ClassifyError(Exception):
    """Structured classification failure that requires a re-scan.

    Attributes:
        code: machine-readable failure code (``indistinct_centers`` or
            ``center_mismatch``).
        message: user-facing explanation.
        faces: face letters whose scans are implicated and should be redone.
    """

    def __init__(self, code: str, message: str, faces: Sequence[str]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.faces = sorted(set(faces))

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "suspect_faces": self.faces}


def _validate_input(faces: Mapping[str, Sequence[Sequence[float]]]) -> None:
    missing = [f for f in FACE_ORDER if f not in faces]
    if missing:
        raise ValueError(f"Missing face sample sets: {missing}")
    for face in FACE_ORDER:
        samples = faces[face]
        if len(samples) != 9:
            raise ValueError(f"Face {face}: expected 9 Lab samples, got {len(samples)}")
        for sample in samples:
            if len(sample) != 3:
                raise ValueError(f"Face {face}: each sample must be [L, a, b]")
            for value in sample:
                if not math.isfinite(value) or abs(value) > _MAX_SAMPLE_MAGNITUDE:
                    raise ValueError(
                        f"Face {face}: sample values must be finite numbers "
                        f"(got {value!r})"
                    )


def _kmeans6(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic k-means k=6: (labels[54], centroids[6, 3])."""
    cv2.setRNGSeed(_KMEANS_SEED)
    _, labels, centroids = cv2.kmeans(
        samples.astype(np.float32),
        6,
        None,
        _KMEANS_CRITERIA,
        _KMEANS_ATTEMPTS,
        cv2.KMEANS_PP_CENTERS,
    )
    return labels.ravel().astype(int), centroids.astype(np.float64)


def classify_faces(faces: Mapping[str, Sequence[Sequence[float]]]) -> dict[str, Any]:
    """Classify all 54 stickers from their per-face Lab samples.

    Args:
        faces: ``{face_letter: [[L, a, b]] * 9}`` for all 6 faces, samples in
            row-major scan order (OpenCV 8-bit Lab).

    Returns:
        Dict with keys ``facelets``, ``colors``, ``confidence`` and
        ``ambiguous`` — the §8 /classify response minus ``valid``/``errors``.

    Raises:
        ClassifyError: on indistinct face centres or a centre sticker whose
            final colour differs from its own face.
        ValueError: on malformed input.
    """
    _validate_input(faces)

    # Global sample index of face f, cell i is FACE_ORDER.index(f) * 9 + i.
    samples = np.array(
        [faces[face][i] for face in FACE_ORDER for i in range(9)], dtype=np.float64
    )
    labels, centroids = _kmeans6(samples)

    # Label clusters by the 6 face-centre samples (cell index 4 of each face).
    cluster_of_face = {
        face: int(labels[face_index * 9 + 4])
        for face_index, face in enumerate(FACE_ORDER)
    }
    faces_by_cluster: dict[int, list[str]] = defaultdict(list)
    for face, cluster in cluster_of_face.items():
        faces_by_cluster[cluster].append(face)
    collisions = [group for group in faces_by_cluster.values() if len(group) > 1]
    if collisions:
        implicated = [face for group in collisions for face in group]
        raise ClassifyError(
            code="indistinct_centers",
            message=(
                "The centre stickers of faces "
                + ", ".join(sorted(implicated))
                + " look like the same colour. Check the lighting and "
                "re-scan those faces."
            ),
            faces=implicated,
        )
    letter_of_cluster = {cluster: face for face, cluster in cluster_of_face.items()}

    # Squared Lab distance of each sticker to each colour's centroid,
    # expanded to a 54x54 cost matrix (each colour owns exactly 9 slots).
    deltas = samples[:, None, :] - centroids[None, :, :]
    sq_dist = np.einsum("ijk,ijk->ij", deltas, deltas)  # 54 x 6
    cost = np.repeat(sq_dist, 9, axis=1)  # 54 x 54; column j -> cluster j // 9
    rows, cols = linear_sum_assignment(cost)
    assigned_cluster = np.empty(54, dtype=int)
    assigned_cluster[rows] = cols // 9

    # Confidence: margin between the assigned colour's distance and the
    # nearest competing colour's distance, normalised to [0, 1].
    dist = np.sqrt(sq_dist)
    confidences: list[float] = []
    for i in range(54):
        own = dist[i, assigned_cluster[i]]
        others = np.delete(dist[i], assigned_cluster[i])
        nearest_other = float(others.min())
        if nearest_other <= 1e-9:
            confidence = 0.0
        else:
            confidence = float(np.clip((nearest_other - own) / nearest_other, 0.0, 1.0))
        confidences.append(round(confidence, 4))

    colors: dict[str, list[str]] = {}
    confidence_out: dict[str, list[float]] = {}
    ambiguous: list[dict[str, Any]] = []
    for face_index, face in enumerate(FACE_ORDER):
        letters: list[str] = []
        face_conf: list[float] = []
        for i in range(9):
            g = face_index * 9 + i
            letters.append(letter_of_cluster[int(assigned_cluster[g])])
            face_conf.append(confidences[g])
            if confidences[g] < AMBIGUITY_THRESHOLD:
                ambiguous.append({"face": face, "index": i, "margin": confidences[g]})
        colors[face] = letters
        confidence_out[face] = face_conf

    mismatched = [face for face in FACE_ORDER if colors[face][4] != face]
    if mismatched:
        raise ClassifyError(
            code="center_mismatch",
            message=(
                "The centre sticker of face "
                + ", ".join(mismatched)
                + " classified as a different colour than expected. "
                "Make sure the cube is held yellow-up / green-front and "
                "re-scan those faces."
            ),
            faces=mismatched,
        )

    facelets = "".join("".join(colors[face]) for face in FACE_ORDER)
    return {
        "facelets": facelets,
        "colors": colors,
        "confidence": confidence_out,
        "ambiguous": ambiguous,
    }
