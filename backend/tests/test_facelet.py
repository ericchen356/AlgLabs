"""T1: facelet <-> cubie round-trip, plus converter/composition unit tests."""

import random

import pytest

from cube.facelet import (
    CENTER_INDICES,
    CORNER_COLOR,
    CORNER_FACELET,
    EDGE_COLOR,
    EDGE_FACELET,
    FACE_OFFSET,
    FACE_ORDER,
    InvalidCubeError,
    SOLVED_FACELETS,
    CubieState,
    cubies_to_facelets,
    facelets_to_cubies,
    is_solved,
    multiply,
)
from cube.moves import random_state


def test_constants_shape():
    assert len(SOLVED_FACELETS) == 54
    assert SOLVED_FACELETS == "U" * 9 + "R" * 9 + "F" * 9 + "D" * 9 + "L" * 9 + "B" * 9
    assert [FACE_OFFSET[f] for f in FACE_ORDER] == [0, 9, 18, 27, 36, 45]
    assert CENTER_INDICES == (4, 13, 22, 31, 40, 49)
    assert len(CORNER_FACELET) == len(CORNER_COLOR) == 8
    assert len(EDGE_FACELET) == len(EDGE_COLOR) == 12
    # Every non-center facelet index appears exactly once across the tables.
    used = [i for triple in CORNER_FACELET for i in triple]
    used += [i for pair in EDGE_FACELET for i in pair]
    assert len(used) == 48 and len(set(used)) == 48
    assert set(used) | set(CENTER_INDICES) == set(range(54))


def test_solved_round_trip():
    state = facelets_to_cubies(SOLVED_FACELETS)
    assert state == CubieState.solved()
    assert is_solved(state)
    assert cubies_to_facelets(state) == SOLVED_FACELETS


def test_t1_random_round_trip_500():
    rng = random.Random(20260711)
    for _ in range(500):
        state = random_state(rng)
        facelets = cubies_to_facelets(state)
        assert facelets_to_cubies(facelets) == state


def test_unrecognizable_corner_raises_structured_error():
    # Make URF = (U, R, R): no such corner exists.
    s = list(SOLVED_FACELETS)
    s[20] = "R"  # F3, URF's F sticker
    with pytest.raises(InvalidCubeError) as exc_info:
        facelets_to_cubies("".join(s))
    err = exc_info.value
    assert err.code == "unrecognized_pieces"
    assert set(err.facelets) >= {8, 9, 20}
    assert set(err.suspect_faces) >= {"U", "R", "F"}


def test_unrecognizable_edge_raises_structured_error():
    # Make UF = (U, U): an edge cannot have two identical stickers.
    s = list(SOLVED_FACELETS)
    s[19] = "U"  # F2, UF's F sticker
    with pytest.raises(InvalidCubeError) as exc_info:
        facelets_to_cubies("".join(s))
    err = exc_info.value
    assert err.code == "unrecognized_pieces"
    assert set(err.facelets) >= {7, 19}


def test_corner_without_ud_sticker_raises():
    # Make URF = (F, R, F): no U/D sticker at all.
    s = list(SOLVED_FACELETS)
    s[8] = "F"  # U9
    with pytest.raises(InvalidCubeError):
        facelets_to_cubies("".join(s))


def test_multiply_identity_and_associativity():
    rng = random.Random(99)
    e = CubieState.solved()
    for _ in range(20):
        a, b, c = random_state(rng), random_state(rng), random_state(rng)
        assert multiply(a, e) == a
        assert multiply(e, a) == a
        assert multiply(multiply(a, b), c) == multiply(a, multiply(b, c))


def test_is_solved_negative():
    rng = random.Random(5)
    state = random_state(rng)
    # A 30-move random state is essentially never solved with this seed.
    assert not is_solved(state)
