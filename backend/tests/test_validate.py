"""T6: validation — solved OK, targeted single mutations, random scrambles valid."""

import random

import pytest

from cube.facelet import SOLVED_FACELETS, CubieState, cubies_to_facelets
from cube.moves import apply_moves, random_state
from cube.validate import permutation_parity, validate


def _codes(result):
    return [e.code for e in result.errors]


def test_solved_is_valid():
    result = validate(SOLVED_FACELETS)
    assert result.valid and result.errors == []
    assert result.to_dict() == {"valid": True, "errors": []}


def test_random_legal_scrambles_always_valid():
    rng = random.Random(1234)
    for _ in range(100):
        facelets = cubies_to_facelets(random_state(rng))
        result = validate(facelets)
        assert result.valid, (facelets, _codes(result))


def test_scrambled_then_validated_known_sequence():
    state = apply_moves(CubieState.solved(), "R U R' U' F2 L' B2 D M2 r x' U'")
    assert validate(cubies_to_facelets(state)).valid


# ---- targeted single mutations: exactly the right error code ---------------


def test_twisted_corner_yields_corner_twist():
    # Twist URF clockwise: its stickers (U9,R1,F3)=(U,R,F) become (F,U,R).
    s = list(SOLVED_FACELETS)
    s[8], s[9], s[20] = "F", "U", "R"
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["corner_twist"]
    err = result.errors[0]
    assert set(err.facelets) == {8, 9, 20}
    assert set(err.suspect_faces) == {"U", "R", "F"}
    assert err.message


def test_flipped_edge_yields_edge_flip():
    # Flip the UF edge: swap its two stickers (U8 idx 7, F2 idx 19).
    s = list(SOLVED_FACELETS)
    s[7], s[19] = s[19], s[7]
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["edge_flip"]
    err = result.errors[0]
    assert set(err.facelets) == {7, 19}
    assert set(err.suspect_faces) == {"U", "F"}


def test_swapped_edges_yield_permutation_parity():
    # Physically swap the UR and UF edge cubies (a single 2-swap = odd edge
    # permutation with even corner permutation).
    s = list(SOLVED_FACELETS)
    s[5], s[10] = "U", "F"  # UR slot now holds the UF cubie
    s[7], s[19] = "U", "R"  # UF slot now holds the UR cubie
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["permutation_parity"]
    err = result.errors[0]
    assert {5, 10, 7, 19} <= set(err.facelets)
    assert {"U", "R", "F"} <= set(err.suspect_faces)


def test_recolored_sticker_yields_bad_counts():
    s = list(SOLVED_FACELETS)
    s[0] = "R"  # U1 painted orange: U appears 8 times, R appears 10 times
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["bad_counts"]
    err = result.errors[0]
    assert set(err.suspect_faces) == {"U", "R"}
    assert 0 in err.facelets  # the over-represented letter's stickers


def test_swapped_centers_yield_bad_centers():
    s = list(SOLVED_FACELETS)
    s[4], s[13] = s[13], s[4]  # swap U and R centers
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["bad_centers"]
    err = result.errors[0]
    assert set(err.facelets) == {4, 13}
    assert set(err.suspect_faces) == {"U", "R"}


def test_unrecognized_piece_yields_unrecognized_pieces():
    # Corner URF becomes (U,R,R) and edge UR becomes (U,F): counts stay 9-9
    # but neither is a real cubie / the UF edge is duplicated.
    s = list(SOLVED_FACELETS)
    s[20] = "R"  # F3 -> R
    s[10] = "F"  # R2 -> F
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["unrecognized_pieces"]
    err = result.errors[0]
    assert {8, 9, 20} <= set(err.facelets)


def test_duplicate_pieces_yield_unrecognized_pieces():
    # Turn UF,UB,DF,DB into UF,UF,DB,DB: every pair is a real cubie but two
    # cubies appear twice (letter counts are unchanged).
    s = list(SOLVED_FACELETS)
    s[1], s[46] = "U", "F"  # UB slot now shows a second UF edge
    s[28], s[25] = "D", "B"  # DF slot now shows a second DB edge
    result = validate("".join(s))
    assert not result.valid
    assert _codes(result) == ["unrecognized_pieces"]
    err = result.errors[0]
    assert {1, 46, 7, 19, 28, 25, 34, 52} <= set(err.facelets)


def test_bad_length_and_characters():
    result = validate("UUU")
    assert not result.valid and _codes(result) == ["bad_length"]

    s = list(SOLVED_FACELETS)
    s[3] = "X"
    result = validate("".join(s))
    assert not result.valid and _codes(result) == ["bad_characters"]
    assert result.errors[0].facelets == [3]


def test_multiple_law_violations_all_reported():
    # Twist a corner AND flip an edge: both codes must be reported.
    s = list(SOLVED_FACELETS)
    s[8], s[9], s[20] = "F", "U", "R"  # twist URF
    s[7], s[19] = s[19], s[7]  # flip UF
    result = validate("".join(s))
    assert not result.valid
    assert set(_codes(result)) == {"corner_twist", "edge_flip"}


def test_permutation_parity_helper():
    assert permutation_parity([0, 1, 2, 3]) == 0
    assert permutation_parity([1, 0, 2, 3]) == 1
    assert permutation_parity([1, 2, 0]) == 0  # 3-cycle is even
    assert permutation_parity([3, 0, 1, 2]) == 1  # 4-cycle is odd


def test_error_dict_shape():
    s = list(SOLVED_FACELETS)
    s[7], s[19] = s[19], s[7]
    result = validate("".join(s))
    d = result.to_dict()
    assert d["valid"] is False
    err = d["errors"][0]
    assert set(err) == {"code", "message", "facelets", "suspect_faces"}
    assert isinstance(err["message"], str) and err["message"]
