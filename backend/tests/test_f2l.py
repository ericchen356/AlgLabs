"""T8: F2L solver — cross + F2L on 200 random scrambles (§10)."""

import random

import pytest

from cube.facelet import CubieState
from cube.moves import apply_moves, random_scramble
from solver.cross import CROSS_EDGES, solve_cross
from solver.f2l import (
    MOVES_15,
    SLOT_ORDER,
    SLOT_PAIRS,
    F2lStep,
    is_f2l_solved,
    solve_f2l,
)


def _cross_intact(state: CubieState) -> bool:
    return all(state.ep[s] == s and state.eo[s] == 0 for s in CROSS_EDGES)


def _slot_intact(state: CubieState, slot: str) -> bool:
    corner, edge = SLOT_PAIRS[slot]
    return (
        state.cp[corner] == corner
        and state.co[corner] == 0
        and state.ep[edge] == edge
        and state.eo[edge] == 0
    )


def test_solved_state_yields_four_empty_steps():
    steps = solve_f2l(CubieState.solved())
    assert [s.slot for s in steps] == list(SLOT_ORDER)  # tie-break order
    assert all(s.moves == [] for s in steps)
    assert [s.pair for s in steps] == [SLOT_PAIRS[s] for s in SLOT_ORDER]


def test_single_pair_reinsertion():
    # Pull out the FR pair only; F2L must fix it and leave the rest alone.
    state = apply_moves(CubieState.solved(), "R U R'")
    steps = solve_f2l(state)
    solved_now = [s for s in steps if s.moves]
    assert len(solved_now) == 1 and solved_now[0].slot == "FR"
    assert len(solved_now[0].moves) == 3  # optimal: undo the extraction
    after = apply_moves(state, [m for s in steps for m in s.moves])
    assert is_f2l_solved(after)


def test_requires_cross_solved():
    state = apply_moves(CubieState.solved(), "D R2 F")
    with pytest.raises(ValueError):
        solve_f2l(state)


def test_t8_200_random_scrambles():
    rng = random.Random(0xF21)
    for _ in range(200):
        scramble = random_scramble(rng)
        state = apply_moves(CubieState.solved(), scramble)
        state = apply_moves(state, solve_cross(state))
        assert _cross_intact(state)

        steps = solve_f2l(state)

        # Exactly 4 steps, one per slot, correct pair metadata.
        assert len(steps) == 4, scramble
        assert sorted(s.slot for s in steps) == sorted(SLOT_ORDER)
        for step in steps:
            assert isinstance(step, F2lStep)
            assert step.pair == SLOT_PAIRS[step.slot]
            # Only the 15 non-D face turns.
            assert all(m in MOVES_15 for m in step.moves), (scramble, step)

        # After each committed step: cross + all committed slots intact.
        committed: list[str] = []
        cur = state
        for step in steps:
            cur = apply_moves(cur, step.moves)
            committed.append(step.slot)
            assert _cross_intact(cur), (scramble, committed)
            for slot in committed:
                assert _slot_intact(cur, slot), (scramble, committed, slot)

        # After all 4: the ENTIRE first two layers are solved.
        assert is_f2l_solved(cur), scramble
        assert all(cur.cp[i] == i and cur.co[i] == 0 for i in range(4, 8))
        assert all(cur.ep[i] == i and cur.eo[i] == 0 for i in range(4, 12))


def test_greedy_commits_shortest_each_round():
    # Step lengths are produced by re-searching every remaining slot each
    # round; committing an already-solved slot (0 moves) must come first.
    state = apply_moves(CubieState.solved(), "B U B'")  # extract BR pair only
    steps = solve_f2l(state)
    # FR, FL, BL are solved (0 moves) and, being shortest, committed first.
    assert [s.slot for s in steps[:3]] == ["FR", "FL", "BL"]
    assert all(s.moves == [] for s in steps[:3])
    assert steps[3].slot == "BR" and len(steps[3].moves) == 3
