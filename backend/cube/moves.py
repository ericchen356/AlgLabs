"""Move engine: facelet permutations, derived cubie tables, algorithm parser.

Per CONTRACTS.md section 4:

* The 18 face turns are defined FIRST as 54-element facelet permutations,
  derived from geometry below (every quarter-turn cycle is written out
  explicitly with a comment naming the facelets involved).
* Cubie tables are DERIVED, never hand-typed:
  ``TABLE[m] = facelets_to_cubies(apply_facelet_move(m, SOLVED_FACELETS))``.
* ``parse_algorithm`` accepts the full token set (face turns, rotations
  x/y/z, slices M/E/S, wide moves) and returns only the 18 face-turn tokens,
  using rotation-relabel rewriting (section 4.3).

Facelet index cheat sheet (global indices; local k = index - face offset):
U face 0..8 (row 0 adjacent B), R 9..17, F 18..26, D 27..35 (row 0 adjacent F),
L 36..44, B 45..53 — side faces viewed straight on with U at the top.
"""

from __future__ import annotations

import random
import re

from .facelet import (
    CubieState,
    SOLVED_FACELETS,
    cubies_to_facelets,
    facelets_to_cubies,
    is_solved,
    multiply,
)

# --------------------------------------------------------------------------- #
# 4.1 Facelet permutations (source of truth)
#
# Each move is given as a list of 4-cycles (a, b, c, d) meaning the sticker at
# global index a moves to b, b to c, c to d, and d back to a, for one
# CLOCKWISE quarter turn as viewed looking at that face from outside.
#
# Every face's own stickers cycle corners (0,2,8,6) and edges (1,5,7,3) in
# local indices, because a clockwise turn in the face's own viewing frame
# sends top-left -> top-right -> bottom-right -> bottom-left.
# --------------------------------------------------------------------------- #

_QUARTER_CYCLES: dict[str, list[tuple[int, int, int, int]]] = {
    # U (viewed from above, B at top). Top layer rotates front -> left.
    "U": [
        (0, 2, 8, 6),  # U1 -> U3 -> U9 -> U7 (U face corners)
        (1, 5, 7, 3),  # U2 -> U6 -> U8 -> U4 (U face edges)
        # Side rows: F top row -> L top row -> B top row -> R top row -> F.
        # Rows stay left-to-right aligned (e.g. UF edge's F sticker F2 lands
        # on the L face at L2 when the UF edge moves to the UL slot).
        (18, 36, 45, 9),  # F1 -> L1 -> B1 -> R1
        (19, 37, 46, 10),  # F2 -> L2 -> B2 -> R2
        (20, 38, 47, 11),  # F3 -> L3 -> B3 -> R3
    ],
    # D (viewed from below, F at top). Bottom layer rotates front -> right.
    "D": [
        (27, 29, 35, 33),  # D1 -> D3 -> D9 -> D7 (D face corners)
        (28, 32, 34, 30),  # D2 -> D6 -> D8 -> D4 (D face edges)
        # Side rows: F bottom row -> R bottom row -> B bottom row -> L bottom.
        # (DF edge's F sticker F8 lands on R8 when DF moves to the DR slot.)
        (24, 15, 51, 42),  # F7 -> R7 -> B7 -> L7
        (25, 16, 52, 43),  # F8 -> R8 -> B8 -> L8
        (26, 17, 53, 44),  # F9 -> R9 -> B9 -> L9
    ],
    # R (viewed from the right, U at top). Right layer rotates front -> up.
    "R": [
        (9, 11, 17, 15),  # R1 -> R3 -> R9 -> R7 (R face corners)
        (10, 14, 16, 12),  # R2 -> R6 -> R8 -> R4 (R face edges)
        # F right column -> U right column -> B left column (inverted) ->
        # D right column (inverted) -> F right column.
        # Chain checks (corner slots named): F3 is URF's F sticker; URF->UBR,
        # front->up, so F3 -> U3. U3 is UBR's U; UBR->DRB, up->back, so
        # U3 -> B7 (B's left column is adjacent to R since B is viewed from
        # behind). B7 is DRB's B; DRB->DFR, back->down, so B7 -> D3. D3 is
        # DFR's D; DFR->URF, down->front, so D3 -> F3. Edge chain: FR edge's
        # F sticker F6 -> U6 -> B4 -> D6 -> F6.
        (20, 2, 51, 29),  # F3 -> U3 -> B7 -> D3
        (23, 5, 48, 32),  # F6 -> U6 -> B4 -> D6
        (26, 8, 45, 35),  # F9 -> U9 -> B1 -> D9
    ],
    # L (viewed from the left, U at top). Left layer rotates up -> front.
    "L": [
        (36, 38, 44, 42),  # L1 -> L3 -> L9 -> L7 (L face corners)
        (37, 41, 43, 39),  # L2 -> L6 -> L8 -> L4 (L face edges)
        # U left column -> F left column -> D left column -> B right column
        # (inverted) -> U left column.
        # e.g. UL edge's U sticker U4 faces front after L: it lands on F4;
        # the DBL corner's D sticker D7 rotates to face back, landing on B3
        # (B's right column is adjacent to L).
        (0, 18, 27, 53),  # U1 -> F1 -> D1 -> B9
        (3, 21, 30, 50),  # U4 -> F4 -> D4 -> B6
        (6, 24, 33, 47),  # U7 -> F7 -> D7 -> B3
    ],
    # F (viewed from the front, U at top). Front layer rotates up -> right.
    "F": [
        (18, 20, 26, 24),  # F1 -> F3 -> F9 -> F7 (F face corners)
        (19, 23, 25, 21),  # F2 -> F6 -> F8 -> F4 (F face edges)
        # U bottom row -> R left column -> D top row (inverted) ->
        # L right column (inverted) -> U bottom row.
        # Chain checks: U7 is UFL's U sticker; UFL->URF, up->right, so
        # U7 -> R1. R1 is URF's R; URF->DFR, right->down, so R1 -> D3. D3 is
        # DFR's D; DFR->DLF, down->left, so D3 -> L9. L9 is DLF's L;
        # DLF->UFL, left->up, so L9 -> U7. Edge chain: UF edge's U sticker
        # U8 -> R4 -> D2 -> L6 -> U8.
        (6, 9, 29, 44),  # U7 -> R1 -> D3 -> L9
        (7, 12, 28, 41),  # U8 -> R4 -> D2 -> L6
        (8, 15, 27, 38),  # U9 -> R7 -> D1 -> L3
    ],
    # B (viewed from behind, U at top). Back layer rotates up -> left (in the
    # cube's frame; that is clockwise as seen from behind).
    "B": [
        (45, 47, 53, 51),  # B1 -> B3 -> B9 -> B7 (B face corners)
        (46, 50, 52, 48),  # B2 -> B6 -> B8 -> B4 (B face edges)
        # U top row -> L left column (inverted) -> D bottom row -> R right
        # column (inverted) -> U top row.
        # e.g. UB edge's U sticker U2 faces left after B: it lands on L4;
        # the ULB corner's U sticker U1 lands on L7 (DBL slot's L facelet).
        (0, 42, 35, 11),  # U1 -> L7 -> D9 -> R3
        (1, 39, 34, 14),  # U2 -> L4 -> D8 -> R6
        (2, 36, 33, 17),  # U3 -> L1 -> D7 -> R9
    ],
}

FACES = "URFDLB"
MOVE_TOKENS: tuple[str, ...] = tuple(
    f + suffix for f in FACES for suffix in ("", "'", "2")
)


def _perm_from_cycles(cycles: list[tuple[int, int, int, int]]) -> list[int]:
    """Build ``src`` array: result[i] = s[src[i]] for one application."""
    src = list(range(54))
    for cycle in cycles:
        # a -> b means position b is filled from position a.
        for i in range(4):
            src[cycle[(i + 1) % 4]] = cycle[i]
    return src


def _compose_perm(p: list[int], q: list[int]) -> list[int]:
    """Permutation applying p then q (both as src arrays)."""
    return [p[q[i]] for i in range(54)]


def _build_facelet_moves() -> dict[str, list[int]]:
    moves: dict[str, list[int]] = {}
    for face, cycles in _QUARTER_CYCLES.items():
        quarter = _perm_from_cycles(cycles)
        half = _compose_perm(quarter, quarter)
        inverse = _compose_perm(half, quarter)  # three quarter turns
        moves[face] = quarter
        moves[face + "2"] = half
        moves[face + "'"] = inverse
    return moves


#: token -> src permutation array (result[i] = s[perm[i]]).
FACELET_MOVES: dict[str, list[int]] = _build_facelet_moves()


def apply_facelet_move(move: str, facelets: str) -> str:
    """Apply one of the 18 face-turn tokens to a facelet string."""
    perm = FACELET_MOVES[move]
    return "".join(facelets[perm[i]] for i in range(54))


# --------------------------------------------------------------------------- #
# 4.2 Cubie tables: DERIVED from the facelet permutations, never hand-typed.
# Because e . m = m, the cubie state of "move applied to solved" IS the
# move's composition table.
# --------------------------------------------------------------------------- #

TABLE: dict[str, CubieState] = {
    m: facelets_to_cubies(apply_facelet_move(m, SOLVED_FACELETS)) for m in MOVE_TOKENS
}


def apply_move(state: CubieState, move: str) -> CubieState:
    """Apply one face-turn token: ``state . TABLE[move]``."""
    return multiply(state, TABLE[move])


def apply_moves(state: CubieState, moves: "str | list[str] | tuple[str, ...]") -> CubieState:
    """Apply a move sequence (left-to-right fold).

    ``moves`` may be a notation string (parsed with :func:`parse_algorithm`,
    so rotations/slices/wide moves are accepted) or an iterable of face-turn
    tokens.
    """
    if isinstance(moves, str):
        moves = parse_algorithm(moves)
    for m in moves:
        state = apply_move(state, m)
    return state


# --------------------------------------------------------------------------- #
# 4.3 Algorithm parser / rewriter
# --------------------------------------------------------------------------- #

#: Rotation relabel maps: after rotation r, logical face f refers to the
#: physical face _ROT_MAPS[r][f] (of the pre-rotation frame).
#: x rotates the whole cube like R (F goes up), y like U (R comes to front),
#: z like F (L comes to the top).
_ROT_MAPS: dict[str, dict[str, str]] = {
    "x": {"U": "F", "F": "D", "D": "B", "B": "U", "R": "R", "L": "L"},
    "y": {"F": "R", "R": "B", "B": "L", "L": "F", "U": "U", "D": "D"},
    "z": {"U": "L", "L": "D", "D": "R", "R": "U", "F": "F", "B": "B"},
}

#: Expansion of every token base into commuting primitives (face turn or
#: rotation, each with a quarter-turn count). Rotations are listed last so
#: the face-turn parts are read in the pre-rotation logical frame.
#:
#: Wide moves: turning two layers = turning the OPPOSITE face + rotating the
#: whole cube, e.g. r = L . x (the x rotation turns everything in the R
#: direction; the L face turn puts the left layer back... equivalently both
#: descriptions turn exactly the R and middle layers).
#: Slices are derived from the wide/outer identities: M = l . L' = R x' L',
#: i.e. M ~ (L', R, x'); E = d . D' = (U, D', y'); S = f . F' = (F', B, z).
#: (M follows the L direction, E follows D, S follows F.)
_EXPANSION: dict[str, list[tuple[str, int]]] = {
    # 18 face turns
    **{f: [(f, 1)] for f in FACES},
    # rotations
    "x": [("x", 1)],
    "y": [("y", 1)],
    "z": [("z", 1)],
    # wide moves (Xw and lowercase aliases): opposite face + rotation
    "Rw": [("L", 1), ("x", 1)],
    "r": [("L", 1), ("x", 1)],
    "Lw": [("R", 1), ("x", 3)],
    "l": [("R", 1), ("x", 3)],
    "Uw": [("D", 1), ("y", 1)],
    "u": [("D", 1), ("y", 1)],
    "Dw": [("U", 1), ("y", 3)],
    "d": [("U", 1), ("y", 3)],
    "Fw": [("B", 1), ("z", 1)],
    "f": [("B", 1), ("z", 1)],
    "Bw": [("F", 1), ("z", 3)],
    "b": [("F", 1), ("z", 3)],
    # slices
    "M": [("L", 3), ("R", 1), ("x", 3)],
    "E": [("U", 1), ("D", 3), ("y", 3)],
    "S": [("F", 3), ("B", 1), ("z", 1)],
}

_TOKEN_RE = re.compile(r"^([URFDLB]w?|[urfdlb]|[MES]|[xyz])(2|')?$")

#: Every token accepted by parse_algorithm (for tests / callers).
ALL_TOKENS: tuple[str, ...] = tuple(
    base + suffix for base in _EXPANSION for suffix in ("", "'", "2")
)

_SUFFIX_TURNS = {None: 1, "": 1, "2": 2, "'": 3}
_TURNS_SUFFIX = {1: "", 2: "2", 3: "'"}


def _split_token(token: str) -> tuple[str, int]:
    m = _TOKEN_RE.match(token)
    if m is None:
        raise ValueError(f"Unrecognized move token: {token!r}")
    return m.group(1), _SUFFIX_TURNS[m.group(2)]


def parse_algorithm(s: str) -> list[str]:
    """Parse an algorithm string into a list of the 18 face-turn tokens.

    Rotations (x/y/z) are handled by relabel tracking: they update a
    logical->physical face map applied to all subsequent tokens; no rotation
    is ever emitted (the cubie model has fixed centers). Wide and slice moves
    rewrite to outer face turns plus rotations via _EXPANSION.

    Raises ``ValueError`` on any unrecognized token.
    """
    frame = {f: f for f in FACES}  # logical face -> physical face
    out: list[str] = []
    for token in s.split():
        base, turns = _split_token(token)
        for kind, base_turns in _EXPANSION[base]:
            n = (base_turns * turns) % 4
            if n == 0:
                continue
            if kind in _ROT_MAPS:
                rot = _ROT_MAPS[kind]
                for _ in range(n):
                    frame = {f: frame[rot[f]] for f in frame}
            else:
                out.append(frame[kind] + _TURNS_SUFFIX[n])
    return out


def invert(alg: "str | list[str]") -> "str | list[str]":
    """Invert an algorithm (any supported tokens), purely syntactically.

    Accepts a notation string or token list and returns the same type.
    ``parse_algorithm(a + ' ' + invert(a))`` always acts as the identity.
    """
    tokens = alg.split() if isinstance(alg, str) else list(alg)
    inverted: list[str] = []
    for token in reversed(tokens):
        base, turns = _split_token(token)
        inverted.append(base + _TURNS_SUFFIX[(-turns) % 4])
    return " ".join(inverted) if isinstance(alg, str) else inverted


def to_notation(moves: "list[str] | tuple[str, ...]") -> str:
    """Join a token list back into a notation string."""
    return " ".join(moves)


# --------------------------------------------------------------------------- #
# Random states / scrambles (for other modules' tests and /api/scramble)
# --------------------------------------------------------------------------- #


def _random_tokens(rng: random.Random, n: int) -> list[str]:
    """n random face-turn tokens with no two consecutive turns of one face."""
    tokens: list[str] = []
    prev_face: str | None = None
    for _ in range(n):
        face = rng.choice([f for f in FACES if f != prev_face])
        tokens.append(face + rng.choice(("", "'", "2")))
        prev_face = face
    return tokens


def random_scramble(rng: random.Random, n_moves: int = 25) -> str:
    """A random scramble notation string of ``n_moves`` face turns."""
    return to_notation(_random_tokens(rng, n_moves))


def random_state(rng: random.Random, n_moves: int = 30) -> CubieState:
    """A random reachable cube state (~``n_moves`` random moves from solved)."""
    return apply_moves(CubieState.solved(), _random_tokens(rng, n_moves))


__all__ = [
    "FACES",
    "MOVE_TOKENS",
    "ALL_TOKENS",
    "FACELET_MOVES",
    "TABLE",
    "apply_facelet_move",
    "apply_move",
    "apply_moves",
    "parse_algorithm",
    "invert",
    "to_notation",
    "random_scramble",
    "random_state",
    "cubies_to_facelets",
    "facelets_to_cubies",
    "is_solved",
]
