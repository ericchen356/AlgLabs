"""Facelet-string <-> cubie-model conversion and core cube constants.

Conventions per docs/CONTRACTS.md (sections 2 and 3):

* A cube state is a 54-character string of face letters, 9 stickers per face,
  face order U, R, F, D, L, B (global offsets U=0, R=9, F=18, D=27, L=36, B=45).
* Each face is written as viewed looking directly at that face, rows top to
  bottom, each row left to right, with U viewed with B at the top, D viewed
  with F at the top, and F/R/B/L viewed with U at the top.
* The cubie model (CubieState) uses the standard Kociemba slot ordering and
  orientation conventions (section 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Constants (CONTRACTS.md section 2 / 3.1)
# --------------------------------------------------------------------------- #

FACE_ORDER: tuple[str, ...] = ("U", "R", "F", "D", "L", "B")

#: Global facelet index offset of each face's first sticker.
FACE_OFFSET: dict[str, int] = {"U": 0, "R": 9, "F": 18, "D": 27, "L": 36, "B": 45}

#: Global indices of the 6 center stickers, in face order U, R, F, D, L, B.
CENTER_INDICES: tuple[int, ...] = (4, 13, 22, 31, 40, 49)

SOLVED_FACELETS: str = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"

#: Color scheme (UI/scanning only; the solver never sees colors).
#: The user holds the cube yellow on top, green facing them.
COLOR_NAME: dict[str, str] = {
    "U": "yellow",
    "R": "orange",
    "F": "green",
    "D": "white",
    "L": "red",
    "B": "blue",
}
COLOR_HEX: dict[str, str] = {
    "U": "#FFD500",
    "R": "#FF5800",
    "F": "#009B48",
    "D": "#FFFFFF",
    "L": "#B71234",
    "B": "#0046AD",
}

#: Facelet positions of each corner slot (U/D facelet first, then clockwise).
CORNER_FACELET: list[tuple[int, int, int]] = [
    (8, 9, 20),  # URF: U9 R1 F3
    (6, 18, 38),  # UFL: U7 F1 L3
    (0, 36, 47),  # ULB: U1 L1 B3
    (2, 45, 11),  # UBR: U3 B1 R3
    (29, 26, 15),  # DFR: D3 F9 R7
    (27, 44, 24),  # DLF: D1 L9 F7
    (33, 53, 42),  # DBL: D7 B9 L7
    (35, 17, 51),  # DRB: D9 R9 B7
]

#: Facelet positions of each edge slot.
EDGE_FACELET: list[tuple[int, int]] = [
    (5, 10),  # UR: U6 R2
    (7, 19),  # UF: U8 F2
    (3, 37),  # UL: U4 L2
    (1, 46),  # UB: U2 B2
    (32, 16),  # DR: D6 R8
    (28, 25),  # DF: D2 F8
    (30, 43),  # DL: D4 L8
    (34, 52),  # DB: D8 B8
    (23, 12),  # FR: F6 R4
    (21, 41),  # FL: F4 L6
    (50, 39),  # BL: B6 L4
    (48, 14),  # BR: B4 R6
]

#: Letter i of entry s = color at CORNER_FACELET[s][i] when solved.
CORNER_COLOR: list[str] = ["URF", "UFL", "ULB", "UBR", "DFR", "DLF", "DBL", "DRB"]
EDGE_COLOR: list[str] = ["UR", "UF", "UL", "UB", "DR", "DF", "DL", "DB", "FR", "FL", "BL", "BR"]

N_CORNERS = 8
N_EDGES = 12


# --------------------------------------------------------------------------- #
# Cubie model
# --------------------------------------------------------------------------- #


@dataclass
class CubieState:
    """Permutation + orientation cube state (Kociemba convention, section 3).

    ``cp[slot]`` / ``ep[slot]`` name which cubie occupies the slot;
    ``co[slot]`` in {0,1,2} and ``eo[slot]`` in {0,1} give its orientation.
    """

    cp: list[int] = field(default_factory=lambda: list(range(N_CORNERS)))
    co: list[int] = field(default_factory=lambda: [0] * N_CORNERS)
    ep: list[int] = field(default_factory=lambda: list(range(N_EDGES)))
    eo: list[int] = field(default_factory=lambda: [0] * N_EDGES)

    @classmethod
    def solved(cls) -> "CubieState":
        return cls()

    def copy(self) -> "CubieState":
        return CubieState(list(self.cp), list(self.co), list(self.ep), list(self.eo))


class InvalidCubeError(ValueError):
    """A facelet string contains pieces that are no real cubie.

    Structured so validation (section 5) can report it: ``code`` is always
    ``"unrecognized_pieces"``, ``facelets`` holds the offending global sticker
    indices and ``suspect_faces`` the face letters containing them.
    """

    code = "unrecognized_pieces"

    def __init__(self, message: str, facelets: list[int], suspect_faces: list[str]):
        super().__init__(message)
        self.message = message
        self.facelets = facelets
        self.suspect_faces = suspect_faces


def faces_of_indices(indices: list[int] | tuple[int, ...]) -> list[str]:
    """Face letters (in U,R,F,D,L,B order) containing the given global indices."""
    present = {FACE_ORDER[i // 9] for i in indices}
    return [f for f in FACE_ORDER if f in present]


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #


def facelets_to_cubies(facelets: str) -> CubieState:
    """Convert a 54-char facelet string to a :class:`CubieState`.

    Raises :class:`InvalidCubeError` (listing every offending facelet index)
    when any corner triple or edge pair is not a real cubie. Duplicate pieces
    are NOT detected here; validation (section 5) handles them.
    """
    if len(facelets) != 54:
        raise InvalidCubeError(
            f"Facelet string must be 54 characters, got {len(facelets)}.", [], []
        )

    state = CubieState()
    bad_indices: list[int] = []

    for slot in range(N_CORNERS):
        idxs = CORNER_FACELET[slot]
        stickers = tuple(facelets[i] for i in idxs)
        # The U/D-colored sticker fixes the orientation index (section 3.2).
        ori = next((o for o in range(3) if stickers[o] in ("U", "D")), None)
        found = False
        if ori is not None:
            c1 = stickers[(ori + 1) % 3]
            c2 = stickers[(ori + 2) % 3]
            for cubie, name in enumerate(CORNER_COLOR):
                if name[0] == stickers[ori] and name[1] == c1 and name[2] == c2:
                    state.cp[slot] = cubie
                    state.co[slot] = ori
                    found = True
                    break
        if not found:
            bad_indices.extend(idxs)

    for slot in range(N_EDGES):
        idxs = EDGE_FACELET[slot]
        pair = facelets[idxs[0]] + facelets[idxs[1]]
        found = False
        for cubie, name in enumerate(EDGE_COLOR):
            if pair == name:
                state.ep[slot] = cubie
                state.eo[slot] = 0
                found = True
                break
            if pair == name[::-1]:
                state.ep[slot] = cubie
                state.eo[slot] = 1
                found = True
                break
        if not found:
            bad_indices.extend(idxs)

    if bad_indices:
        raise InvalidCubeError(
            "Some sticker combinations do not form a real cube piece "
            "(check the highlighted stickers).",
            sorted(bad_indices),
            faces_of_indices(bad_indices),
        )
    return state


def cubies_to_facelets(state: CubieState) -> str:
    """Convert a :class:`CubieState` back to its 54-char facelet string."""
    out = [""] * 54
    for face, offset in FACE_OFFSET.items():
        out[offset + 4] = face  # centers are fixed
    for slot in range(N_CORNERS):
        cubie, ori = state.cp[slot], state.co[slot]
        for i in range(3):
            out[CORNER_FACELET[slot][(i + ori) % 3]] = CORNER_COLOR[cubie][i]
    for slot in range(N_EDGES):
        cubie, ori = state.ep[slot], state.eo[slot]
        for i in range(2):
            out[EDGE_FACELET[slot][(i + ori) % 2]] = EDGE_COLOR[cubie][i]
    return "".join(out)


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def multiply(a: CubieState, b: CubieState) -> CubieState:
    """Compose: apply transformation ``b`` after state/transformation ``a``.

    Per CONTRACTS.md section 3.3:
    ``(a.b).cp[i] = a.cp[b.cp[i]]``, ``(a.b).co[i] = (a.co[b.cp[i]] + b.co[i]) % 3``
    (and likewise for edges mod 2).
    """
    return CubieState(
        cp=[a.cp[b.cp[i]] for i in range(N_CORNERS)],
        co=[(a.co[b.cp[i]] + b.co[i]) % 3 for i in range(N_CORNERS)],
        ep=[a.ep[b.ep[i]] for i in range(N_EDGES)],
        eo=[(a.eo[b.ep[i]] + b.eo[i]) % 2 for i in range(N_EDGES)],
    )


def is_solved(state: CubieState) -> bool:
    """True iff the state is the identity (solved) state."""
    return (
        state.cp == list(range(N_CORNERS))
        and state.co == [0] * N_CORNERS
        and state.ep == list(range(N_EDGES))
        and state.eo == [0] * N_EDGES
    )
