"""T2-T5: move engine, known sequences (frozen regression), commutation, parser."""

import random

import pytest

from cube.facelet import (
    SOLVED_FACELETS,
    CubieState,
    cubies_to_facelets,
    facelets_to_cubies,
    is_solved,
    multiply,
)
from cube.moves import (
    ALL_TOKENS,
    FACELET_MOVES,
    FACES,
    MOVE_TOKENS,
    TABLE,
    apply_facelet_move,
    apply_move,
    apply_moves,
    invert,
    parse_algorithm,
    random_scramble,
    random_state,
    to_notation,
)
from cube.validate import validate

# --------------------------------------------------------------------------- #
# T2: every move
# --------------------------------------------------------------------------- #


def test_tables_complete_and_are_permutations():
    assert set(TABLE) == set(MOVE_TOKENS) and len(TABLE) == 18
    for m, perm in FACELET_MOVES.items():
        assert sorted(perm) == list(range(54)), m
    for m, t in TABLE.items():
        assert sorted(t.cp) == list(range(8)), m
        assert sorted(t.ep) == list(range(12)), m
        assert sum(t.co) % 3 == 0 and sum(t.eo) % 2 == 0, m


@pytest.mark.parametrize("face", list(FACES))
def test_t2_move_group_laws_cubie(face):
    solved = CubieState.solved()
    # m . m' = identity
    assert is_solved(apply_move(apply_move(solved, face), face + "'"))
    assert is_solved(apply_move(apply_move(solved, face + "'"), face))
    # m^4 = identity
    s = solved
    for _ in range(4):
        s = apply_move(s, face)
    assert is_solved(s)
    # m2 = m . m  and  m' = m . m . m
    assert TABLE[face + "2"] == multiply(TABLE[face], TABLE[face])
    assert TABLE[face + "'"] == multiply(multiply(TABLE[face], TABLE[face]), TABLE[face])


@pytest.mark.parametrize("face", list(FACES))
def test_t2_move_group_laws_facelet(face):
    s = apply_facelet_move(face, SOLVED_FACELETS)
    assert apply_facelet_move(face + "'", s) == SOLVED_FACELETS
    s4 = SOLVED_FACELETS
    for _ in range(4):
        s4 = apply_facelet_move(face, s4)
    assert s4 == SOLVED_FACELETS
    assert apply_facelet_move(face, apply_facelet_move(face, SOLVED_FACELETS)) == (
        apply_facelet_move(face + "2", SOLVED_FACELETS)
    )


def test_quarter_turn_moves_exactly_20_stickers():
    for face in FACES:
        s = apply_facelet_move(face, SOLVED_FACELETS)
        moved = sum(1 for a, b in zip(s, SOLVED_FACELETS) if a != b)
        # 12 side stickers change face letters; the face's own 8 stickers keep
        # their letter on a solved cube, so exactly 12 letters change.
        assert moved == 12, face
        perm = FACELET_MOVES[face]
        assert sum(1 for i in range(54) if perm[i] != i) == 20, face


# --------------------------------------------------------------------------- #
# T3: known sequences
# --------------------------------------------------------------------------- #


def test_t3_sexy_move_order_six():
    state = CubieState.solved()
    for i in range(6):
        state = apply_moves(state, "R U R' U'")
        assert is_solved(state) == (i == 5)


def test_t3_hperm_preserves_first_two_layers():
    # H-perm via slices: must leave everything but the U-layer edges alone.
    state = apply_moves(CubieState.solved(), "M2 U M2 U2 M2 U M2")
    assert state.cp == list(range(8)) and state.co == [0] * 8
    assert state.ep[4:] == list(range(4, 12)) and state.eo == [0] * 12
    assert state.ep[:4] != [0, 1, 2, 3]
    # H perm swaps opposite edge pairs: UR<->UL and UF<->UB.
    assert state.ep[:4] == [2, 3, 0, 1]


# Frozen regression: "R U R' U' F2 L'" applied to solved.
#
# Hand-verified stickers (geometric reasoning, tracking one sticker forward
# through each move; facelet names are 1-based within a face, indices global):
#
# * URF's U sticker 'U' (U9, idx 8):
#     R  : URF corner -> UBR, sticker up->back            -> B1 (45)
#     U  : B top row -> R top row (aligned)               -> R1 (9)
#     R' : R face turns ccw, top-left -> bottom-left      -> R7 (15)
#     U' : untouched (R7 is not in the top layer)
#     F2 : R7 is DFR's R sticker; DFR -> DLF -> UFL, so right->down->left
#          (R left column -> D top row -> L right column) -> L3 (38)
#     L' : L face ccw, top-right -> top-left              -> L1 (36)
#   => result[36] == 'U'
# * ULB's U sticker 'U' (U1, idx 0):
#     U  : U face cw, U1 -> U3 (2);  R' : U3 -> F3 (20) (R cw sends F3->U3);
#     U' : F top row -> R top row, F3 -> R3 (11);  F2, L': untouched.
#   => result[11] == 'U'
# * DLF's L sticker 'L' (L9, idx 44): untouched by R/U; F2 sends L right
#   column L9 -> U7 -> R1 (44 -> 6 -> 9); L' does not touch the R face.
#   => result[9] == 'L'
# * DLF's D sticker 'D' (D1, idx 27): untouched until F2: D top row
#   D1 -> L3 -> U9 (27 -> 38 -> 8); L' touches U left column (0,3,6) only.
#   => result[8] == 'D'
# * UFL's F sticker 'F' (F1, idx 18): U sends F top row to L (18 -> 36), U'
#   sends it straight back (36 -> 18); F2 spins the F face, F1 -> F3 -> F9;
#   L' touches only F's left column.
#   => result[26] == 'F'
# * UBR's B sticker 'B' (B1, idx 45): R sends B left column to D right column
#   (B1 -> D9, 45 -> 35); R' undoes it (back to 45); U' sends B top row to
#   L top row (45 -> 36); L' spins L face ccw, L1 -> L7 (36 -> 42).
#   => result[42] == 'B'
# * The DB edge (D8 idx 34, B8 idx 52) is touched by none of R, U, F, L:
#   result[34] == 'D', result[52] == 'B'. All six centers keep their letter.
FROZEN_SCRAMBLE = "R U R' U' F2 L'"
FROZEN_RESULT = "FULUUFDDDLRULRRLRRFFFDFFDFFBUUBDDRDDUBRLLLBLLBRRBBUBBU"


def test_t3_frozen_regression_hand_checks():
    s = SOLVED_FACELETS
    for m in FROZEN_SCRAMBLE.split():
        s = apply_facelet_move(m, s)
    # The hand-derived stickers above:
    assert s[36] == "U"
    assert s[11] == "U"
    assert s[9] == "L"
    assert s[8] == "D"
    assert s[26] == "F"
    assert s[42] == "B"
    assert s[34] == "D" and s[52] == "B"
    for center, letter in zip((4, 13, 22, 31, 40, 49), "URFDLB"):
        assert s[center] == letter
    assert s == FROZEN_RESULT


def test_t3_frozen_regression_cubie_path():
    state = apply_moves(CubieState.solved(), FROZEN_SCRAMBLE)
    assert cubies_to_facelets(state) == FROZEN_RESULT
    # And it undoes cleanly.
    assert is_solved(apply_moves(state, invert(FROZEN_SCRAMBLE)))


# --------------------------------------------------------------------------- #
# T4: cubie/facelet commutation
# --------------------------------------------------------------------------- #


def test_t4_commutation_all_moves_100_random_states():
    rng = random.Random(424242)
    for _ in range(100):
        state = random_state(rng)
        facelets = cubies_to_facelets(state)
        for m in MOVE_TOKENS:
            assert cubies_to_facelets(apply_move(state, m)) == apply_facelet_move(
                m, facelets
            ), m


# --------------------------------------------------------------------------- #
# T5: parser / rewriter
# --------------------------------------------------------------------------- #


def _effect(alg: str) -> CubieState:
    return apply_moves(CubieState.solved(), alg)


@pytest.mark.parametrize(
    "alg,equivalent",
    [
        ("x U x'", "F"),
        ("y F y'", "R"),
        ("z U z'", "L"),
        ("r U r'", "L F L'"),
        ("Rw U Rw'", "L F L'"),  # Rw is the same token as r
        ("x x'", ""),
        ("y2 y2", ""),
        ("M M'", ""),
        ("u", "D y"),  # wide = opposite outer face + rotation
        ("f2", "B2 z2"),
        ("E'", "U' D y"),
    ],
)
def test_t5_parser_identities(alg, equivalent):
    assert _effect(alg) == _effect(equivalent)


def test_t5_parser_returns_only_face_tokens():
    tokens = parse_algorithm("x r M2 u' E S2 Bw F' y z' U2")
    assert all(t in MOVE_TOKENS for t in tokens)
    assert parse_algorithm("") == []
    assert parse_algorithm("x y z") == []  # pure rotations emit nothing


def test_t5_hperm_property_via_parser():
    tokens = parse_algorithm("M2 U M2 U2 M2 U M2")
    assert all(t in MOVE_TOKENS for t in tokens)
    state = apply_moves(CubieState.solved(), tokens)
    assert state.cp == list(range(8)) and state.co == [0] * 8
    assert state.ep[4:] == list(range(4, 12)) and state.eo == [0] * 12
    assert state.ep[:4] != [0, 1, 2, 3]


def test_t5_every_token_times_inverse_is_identity():
    # ALL_TOKENS covers faces, rotations, slices and wide moves with all
    # suffixes (72 tokens).
    assert len(ALL_TOKENS) == 72
    for t in ALL_TOKENS:
        alg = t + " " + invert(t)
        assert is_solved(_effect(alg)), alg


def test_t5_slice_rewrites():
    # With fixed centers a slice move rewrites to the two outer faces of its
    # axis (plus a rotation relabel that is never emitted): M = L' R + x'.
    assert parse_algorithm("M") == ["L'", "R"]
    assert parse_algorithm("E") == ["U", "D'"]
    assert parse_algorithm("S") == ["F'", "B"]
    assert parse_algorithm("M2") == ["L2", "R2"]
    # Slice moves have order 4.
    for slice_token in ("M", "E", "S"):
        assert is_solved(_effect(" ".join([slice_token] * 4))), slice_token
        assert is_solved(_effect(f"{slice_token}2 {slice_token}2")), slice_token


def test_t5_invert_round_trips():
    alg = "R U2 F' r M2 x y' Bw2 E S'"
    assert invert(invert(alg)) == alg
    assert _effect(alg + " " + invert(alg)) == CubieState.solved()
    tokens = parse_algorithm("R U R'")
    assert invert(tokens) == ["R", "U'", "R'"]
    assert to_notation(tokens) == "R U R'"
    assert parse_algorithm(to_notation(tokens)) == tokens


@pytest.mark.parametrize("garbage", ["Q", "R3", "UU", "2R", "xw", "Mw", "R''", "u2'"])
def test_t5_parser_rejects_garbage(garbage):
    with pytest.raises(ValueError):
        parse_algorithm("R " + garbage + " U")
    with pytest.raises(ValueError):
        invert(garbage)


# --------------------------------------------------------------------------- #
# random_state / random_scramble helpers
# --------------------------------------------------------------------------- #


def test_random_scramble_is_valid_and_seedable():
    rng = random.Random(7)
    scramble = random_scramble(rng)
    tokens = parse_algorithm(scramble)
    assert len(tokens) == 25
    state = apply_moves(CubieState.solved(), tokens)
    result = validate(cubies_to_facelets(state))
    assert result.valid
    # Deterministic under the same seed.
    assert random_scramble(random.Random(7)) == scramble


def test_random_state_valid_and_reproducible():
    a = random_state(random.Random(11))
    b = random_state(random.Random(11))
    assert a == b
    assert validate(cubies_to_facelets(a)).valid
    assert facelets_to_cubies(cubies_to_facelets(a)) == a
