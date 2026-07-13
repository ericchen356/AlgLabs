"""Cube validation with face blame (CONTRACTS.md section 5).

Checks a facelet string in order:

1. length / alphabet / exact-9 letter counts
2. centers distinct and canonical (``bad_centers``)
3. every corner/edge is a real cubie, each exactly once (``unrecognized_pieces``)
4. corner orientation sum (``corner_twist``)
5. edge orientation sum (``edge_flip``)
6. corner vs edge permutation parity (``permutation_parity``)

Each error carries the offending facelet indices and the suspect faces so the
UI can point the user at what to re-scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .facelet import (
    CENTER_INDICES,
    CORNER_FACELET,
    EDGE_FACELET,
    FACE_ORDER,
    InvalidCubeError,
    N_CORNERS,
    N_EDGES,
    faces_of_indices,
    facelets_to_cubies,
)


@dataclass
class ValidationError:
    """One validation failure, with facelet indices and face blame."""

    code: str
    message: str
    facelets: list[int] = field(default_factory=list)
    suspect_faces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "facelets": list(self.facelets),
            "suspect_faces": list(self.suspect_faces),
        }


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "errors": [e.to_dict() for e in self.errors]}


_ALPHABET = set("URFDLB")


def permutation_parity(perm: list[int]) -> int:
    """Parity of a permutation: 0 = even, 1 = odd (counted by inversions)."""
    inversions = 0
    n = len(perm)
    for i in range(n):
        for j in range(i + 1, n):
            if perm[i] > perm[j]:
                inversions += 1
    return inversions % 2


def _corner_facelets(slots: list[int]) -> list[int]:
    out: list[int] = []
    for s in slots:
        out.extend(CORNER_FACELET[s])
    return sorted(out)


def _edge_facelets(slots: list[int]) -> list[int]:
    out: list[int] = []
    for s in slots:
        out.extend(EDGE_FACELET[s])
    return sorted(out)


def validate(facelets: str) -> ValidationResult:
    """Validate a facelet string per CONTRACTS.md section 5."""
    errors: list[ValidationError] = []

    # ---- 1. Length / alphabet / counts -----------------------------------
    if len(facelets) != 54:
        errors.append(
            ValidationError(
                code="bad_length",
                message=(
                    f"A cube description needs exactly 54 stickers; "
                    f"this one has {len(facelets)}."
                ),
            )
        )
        return ValidationResult(False, errors)

    bad_chars = [i for i, ch in enumerate(facelets) if ch not in _ALPHABET]
    if bad_chars:
        errors.append(
            ValidationError(
                code="bad_characters",
                message=(
                    "Stickers must be one of the letters U, R, F, D, L, B; "
                    "some stickers use other characters."
                ),
                facelets=bad_chars,
            )
        )
        return ValidationResult(False, errors)

    counts = {f: facelets.count(f) for f in FACE_ORDER}
    wrong = {f: c for f, c in counts.items() if c != 9}
    if wrong:
        over = [f for f, c in wrong.items() if c > 9]
        indices = sorted(i for i, ch in enumerate(facelets) if ch in over)
        detail = ", ".join(f"{f}: {c}" for f, c in wrong.items())
        errors.append(
            ValidationError(
                code="bad_counts",
                message=(
                    f"Each color must appear exactly 9 times, but got {detail}. "
                    "A sticker was probably misread — re-scan the affected faces."
                ),
                facelets=indices,
                suspect_faces=[f for f in FACE_ORDER if f in wrong],
            )
        )
        return ValidationResult(False, errors)

    # ---- 2. Centers -------------------------------------------------------
    centers = [facelets[i] for i in CENTER_INDICES]
    bad_center_idx = [
        CENTER_INDICES[k] for k, f in enumerate(FACE_ORDER) if centers[k] != f
    ]
    if len(set(centers)) != 6 or bad_center_idx:
        involved = sorted(
            {facelets[i] for i in bad_center_idx}
            | {FACE_ORDER[CENTER_INDICES.index(i)] for i in bad_center_idx}
        )
        errors.append(
            ValidationError(
                code="bad_centers",
                message=(
                    "The face centers are not in the expected orientation. "
                    "Hold the cube yellow on top with green facing you and "
                    "re-scan in the guided order."
                ),
                facelets=bad_center_idx or list(CENTER_INDICES),
                suspect_faces=involved or list(FACE_ORDER),
            )
        )
        return ValidationResult(False, errors)

    # ---- 3. Real pieces, each exactly once --------------------------------
    try:
        state = facelets_to_cubies(facelets)
    except InvalidCubeError as exc:
        errors.append(
            ValidationError(
                code="unrecognized_pieces",
                message=exc.message,
                facelets=list(exc.facelets),
                suspect_faces=list(exc.suspect_faces),
            )
        )
        return ValidationResult(False, errors)

    dup_corner_slots = [
        s for s in range(N_CORNERS) if state.cp.count(state.cp[s]) != 1
    ]
    dup_edge_slots = [s for s in range(N_EDGES) if state.ep.count(state.ep[s]) != 1]
    if dup_corner_slots or dup_edge_slots:
        indices = _corner_facelets(dup_corner_slots) + _edge_facelets(dup_edge_slots)
        errors.append(
            ValidationError(
                code="unrecognized_pieces",
                message=(
                    "Some pieces appear more than once (and others are missing). "
                    "A face was probably scanned twice or misread."
                ),
                facelets=sorted(indices),
                suspect_faces=faces_of_indices(indices),
            )
        )
        return ValidationResult(False, errors)

    # ---- 4-6. Orientation and parity laws ---------------------------------
    if sum(state.co) % 3 != 0:
        twisted = [s for s in range(N_CORNERS) if state.co[s] != 0]
        indices = _corner_facelets(twisted)
        errors.append(
            ValidationError(
                code="corner_twist",
                message=(
                    "A corner is twisted: this coloring cannot be reached by "
                    "turning the faces. Check the highlighted corner stickers."
                ),
                facelets=indices,
                suspect_faces=faces_of_indices(indices),
            )
        )

    if sum(state.eo) % 2 != 0:
        flipped = [s for s in range(N_EDGES) if state.eo[s] != 0]
        indices = _edge_facelets(flipped)
        errors.append(
            ValidationError(
                code="edge_flip",
                message=(
                    "An edge is flipped: this coloring cannot be reached by "
                    "turning the faces. Check the highlighted edge stickers."
                ),
                facelets=indices,
                suspect_faces=faces_of_indices(indices),
            )
        )

    if permutation_parity(state.cp) != permutation_parity(state.ep):
        misplaced_corners = [s for s in range(N_CORNERS) if state.cp[s] != s]
        misplaced_edges = [s for s in range(N_EDGES) if state.ep[s] != s]
        indices = _corner_facelets(misplaced_corners) + _edge_facelets(misplaced_edges)
        errors.append(
            ValidationError(
                code="permutation_parity",
                message=(
                    "Two pieces are swapped: this arrangement cannot be reached "
                    "by turning the faces. Two stickers were likely mixed up "
                    "during entry — check the highlighted pieces."
                ),
                facelets=sorted(indices),
                suspect_faces=faces_of_indices(indices),
            )
        )

    return ValidationResult(not errors, errors)


__all__ = ["ValidationError", "ValidationResult", "permutation_parity", "validate"]
