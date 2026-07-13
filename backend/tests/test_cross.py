"""T7: cross solver — 300 random scrambles, optimal, <= 8 moves (§10)."""

import random

import pytest

from cube.facelet import CubieState
from cube.moves import MOVE_TOKENS, apply_moves, random_scramble
from solver.cross import (
    CROSS_EDGES,
    cross_distance,
    is_cross_solved,
    solve_cross,
)


def _cross_ok(state: CubieState) -> bool:
    return all(state.ep[s] == s and state.eo[s] == 0 for s in CROSS_EDGES)


def test_solved_state_needs_no_moves():
    state = CubieState.solved()
    assert solve_cross(state) == []
    assert cross_distance(state) == 0


def test_single_move_crosses():
    # One D-face turn keeps cross edges in the D layer permuted: distance 1.
    for move in ("D", "D'", "D2"):
        state = apply_moves(CubieState.solved(), [move])
        assert cross_distance(state) == 1
        sol = solve_cross(state)
        assert len(sol) == 1
        assert _cross_ok(apply_moves(state, sol))


def test_cross_ignores_non_cross_pieces():
    # The sexy move scrambles U-layer pieces and the FR pair but leaves the
    # cross edges alone: the cross is still "solved".
    state = apply_moves(CubieState.solved(), "R U R' U'")
    assert cross_distance(state) == 0
    assert solve_cross(state) == []


def test_t7_300_random_scrambles():
    rng = random.Random(0xC705)
    for _ in range(300):
        scramble = random_scramble(rng)
        state = apply_moves(CubieState.solved(), scramble)

        moves = solve_cross(state)

        # Only the 18 face-turn tokens.
        assert all(m in MOVE_TOKENS for m in moves), (scramble, moves)
        # Always <= 8 moves (cross God's number).
        assert len(moves) <= 8, (scramble, moves)
        # Optimal: length equals the BFS distance.
        assert len(moves) == cross_distance(state), (scramble, moves)
        # Applying it solves all 4 cross edges (nothing else is required).
        after = apply_moves(state, moves)
        assert _cross_ok(after), (scramble, moves)
        assert is_cross_solved(after)


def test_distance_is_a_metric_step():
    # Each move changes the distance by at most 1 (consistency of the table).
    rng = random.Random(7)
    for _ in range(50):
        state = apply_moves(CubieState.solved(), random_scramble(rng, 10))
        d = cross_distance(state)
        for move in MOVE_TOKENS:
            d2 = cross_distance(apply_moves(state, [move]))
            assert abs(d2 - d) <= 1


def test_invalid_state_rejected():
    state = CubieState.solved()
    state.ep[4], state.ep[5] = 5, 5  # duplicate cubie: no valid abstraction
    with pytest.raises(ValueError):
        cross_distance(state)
