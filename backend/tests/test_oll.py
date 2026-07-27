"""T9: OLL build gates (215 signatures, no collisions, F2L preservation) and
runtime orientation over 200 seeded random last-layer states."""

import json
import random
from pathlib import Path

import pytest

from cube.facelet import CubieState
from cube.moves import MOVE_TOKENS, apply_moves, invert, parse_algorithm
from solver.oll import (
    AUF_TOKENS,
    N_OLL_SIGNATURES,
    OLL_TABLE,
    SOLVED_SIGNATURE,
    OllStep,
    _build_table,
    f2l_is_solved,
    ll_is_oriented,
    signature,
    solve_oll,
)

DATA_DIR = Path(__file__).parent.parent / "solver" / "data"


def _alg_pool() -> list[list[str]]:
    """Parsed OLL algs + PLL algs + U turns: every element preserves F2L."""
    pool: list[list[str]] = []
    with open(DATA_DIR / "oll.json", encoding="utf-8") as fh:
        pool += [parse_algorithm(c["alg"]) for c in json.load(fh)]
    with open(DATA_DIR / "pll.json", encoding="utf-8") as fh:
        pool += [parse_algorithm(c["alg"]) for c in json.load(fh)]
    pool += [["U"], ["U'"], ["U2"]]
    return pool


ALG_POOL = _alg_pool()


def random_ll_state(rng: random.Random) -> CubieState:
    """Random state with F2L solved: a random product of F2L-preserving algs."""
    state = CubieState.solved()
    for _ in range(rng.randint(3, 8)):
        state = apply_moves(state, rng.choice(ALG_POOL))
    return state


# --------------------------------------------------------------------------- #
# Build gates (the import-time asserts, run explicitly)
# --------------------------------------------------------------------------- #


def test_build_covers_exactly_215_nonsolved_signatures():
    table = _build_table()  # re-runs every build-time assert
    assert len(table) == N_OLL_SIGNATURES == 215
    assert SOLVED_SIGNATURE not in table
    # The 215 signatures are exactly the parity-consistent non-solved ones.
    for (co, eo) in table:
        assert sum(co) % 3 == 0 and sum(eo) % 2 == 0


def test_build_no_cross_case_collisions():
    # A signature belongs to exactly one case id; re-derive independently.
    seen: dict[tuple, int] = {}
    for sig, (case, _moves) in OLL_TABLE.items():
        assert seen.setdefault(sig, case.id) == case.id
    assert len(seen) == N_OLL_SIGNATURES


def test_every_table_entry_preserves_f2l_and_orients():
    for sig, (case, moves) in OLL_TABLE.items():
        # The setup state the entry was built from:
        s = apply_moves(CubieState.solved(), invert(moves))
        assert f2l_is_solved(s), f"case {case.id}: setup breaks F2L"
        assert signature(s) == sig, f"case {case.id}: signature mismatch"
        after = apply_moves(s, moves)
        assert ll_is_oriented(after), f"case {case.id}: moves do not orient LL"
        # Moves are pure face-turn tokens (pre-AUF U turn allowed up front).
        assert all(m in MOVE_TOKENS for m in moves), f"case {case.id}: bad tokens"
        if moves[0] in ("U", "U'", "U2"):
            assert moves[1:] == parse_algorithm(case.alg)
        else:
            assert moves == parse_algorithm(case.alg)


def test_all_57_cases_appear_in_table():
    assert {case.id for case, _ in OLL_TABLE.values()} == set(range(1, 58))


# --------------------------------------------------------------------------- #
# Runtime: 200 seeded random post-F2L states
# --------------------------------------------------------------------------- #


def test_solve_oll_orients_200_random_ll_states():
    rng = random.Random(9090)
    skips = 0
    for i in range(200):
        state = random_ll_state(rng)
        assert f2l_is_solved(state), f"generator broke F2L at iteration {i}"
        step = solve_oll(state)
        if step is None:
            skips += 1
            assert ll_is_oriented(state)
            continue
        assert isinstance(step, OllStep)
        assert 1 <= step.case_id <= 57
        assert step.label == f"OLL {step.case_id} · {step.name}"
        assert all(m in MOVE_TOKENS for m in step.moves)
        after = apply_moves(state, step.moves)
        assert ll_is_oriented(after), f"iteration {i}: OLL {step.case_id} failed"
    # Sanity: the generator must actually exercise non-skip cases.
    assert skips < 200


# --------------------------------------------------------------------------- #
# Skip paths
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_oll_skip_on_auf_only_states(k):
    state = apply_moves(CubieState.solved(), AUF_TOKENS[k])
    assert solve_oll(state) is None


def test_oll_skip_on_pure_pll_states():
    # Oriented-but-permuted last layers must be recognized as OLL skips.
    with open(DATA_DIR / "pll.json", encoding="utf-8") as fh:
        pll_cases = json.load(fh)
    for case in pll_cases:
        state = apply_moves(CubieState.solved(), invert(parse_algorithm(case["alg"])))
        assert solve_oll(state) is None, f"PLL {case['id']} state is an OLL skip"


def test_solve_oll_rejects_broken_f2l():
    state = apply_moves(CubieState.solved(), ["R"])  # breaks the FR/DFR slots
    with pytest.raises(ValueError):
        solve_oll(state)
