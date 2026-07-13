"""T10: PLL build gates (288 signatures incl. 4 skips, F2L+orientation
preservation) and the full OLL -> PLL -> AUF pipeline over 200 seeded states."""

import json
import random
from pathlib import Path

import pytest

from cube.facelet import CubieState, is_solved
from cube.moves import MOVE_TOKENS, apply_moves, invert, parse_algorithm
from solver.oll import AUF_TOKENS, f2l_is_solved, ll_is_oriented, solve_oll
from solver.pll import (
    N_PLL_CASE_SIGNATURES,
    N_PLL_SIGNATURES,
    PLL_IDS,
    PLL_TABLE,
    SKIP_SIGNATURES,
    PllStep,
    _build_table,
    compute_auf,
    signature,
    solve_pll,
    valid_signatures,
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


def test_build_covers_all_288_signatures_including_skips():
    table, skips = _build_table()  # re-runs every build-time assert
    assert len(table) == N_PLL_CASE_SIGNATURES == 284
    assert len(skips) == 4
    all_valid = valid_signatures()
    assert len(all_valid) == N_PLL_SIGNATURES == 288
    assert set(table) | set(skips) == all_valid
    assert not set(table) & set(skips)


def test_skip_signatures_are_the_auf_states():
    expected = {
        signature(apply_moves(CubieState.solved(), AUF_TOKENS[j])) for j in range(4)
    }
    assert SKIP_SIGNATURES == expected and len(expected) == 4


def test_build_no_cross_case_collisions():
    seen: dict[tuple, str] = {}
    for sig, (case, _moves) in PLL_TABLE.items():
        assert seen.setdefault(sig, case.id) == case.id
    assert len(seen) == N_PLL_CASE_SIGNATURES


def test_every_table_entry_preserves_f2l_and_orientation():
    for sig, (case, moves) in PLL_TABLE.items():
        assert all(m in MOVE_TOKENS for m in moves), f"case {case.id}: bad tokens"
        # Reconstruct the runtime state directly from the signature (it fully
        # determines the state post-OLL) — an independent derivation.
        state = CubieState.solved()
        state.cp[0:4] = list(sig[0])
        state.ep[0:4] = list(sig[1])
        assert ll_is_oriented(state)
        after = apply_moves(state, moves)
        assert f2l_is_solved(after), f"case {case.id}: setup breaks F2L"
        assert ll_is_oriented(after), f"case {case.id}: setup breaks orientation"
        assert signature(after) in SKIP_SIGNATURES, (
            f"case {case.id}: moves do not solve the LL permutation up to AUF"
        )


def test_all_21_cases_appear_in_table():
    assert {case.id for case, _ in PLL_TABLE.values()} == set(PLL_IDS)


# --------------------------------------------------------------------------- #
# Runtime: full OLL -> PLL -> AUF pipeline on 200 seeded random states
# --------------------------------------------------------------------------- #


def test_pipeline_solves_200_random_ll_states():
    rng = random.Random(1010)
    pll_skips = 0
    for i in range(200):
        state = random_ll_state(rng)
        oll_step = solve_oll(state)
        if oll_step is not None:
            state = apply_moves(state, oll_step.moves)
        assert ll_is_oriented(state), f"iteration {i}: OLL stage failed"

        pll_step = solve_pll(state)
        if pll_step is None:
            pll_skips += 1
        else:
            assert isinstance(pll_step, PllStep)
            assert pll_step.case_id in PLL_IDS
            assert pll_step.label == f"PLL {pll_step.case_id} — {pll_step.name}"
            assert all(m in MOVE_TOKENS for m in pll_step.moves)
            state = apply_moves(state, pll_step.moves)

        auf = compute_auf(state)
        if auf is not None:
            assert auf in ("U", "U'", "U2")
            state = apply_moves(state, [auf])
        assert is_solved(state), f"iteration {i}: cube not solved after PLL+AUF"
    assert pll_skips < 200  # the generator must exercise real PLL cases


# --------------------------------------------------------------------------- #
# Skip and AUF paths
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_pll_skip_on_auf_only_states(k):
    state = apply_moves(CubieState.solved(), AUF_TOKENS[k])
    assert solve_pll(state) is None
    auf = compute_auf(state)
    expected = {0: None, 1: "U'", 2: "U2", 3: "U"}[k]
    assert auf == expected
    if auf is not None:
        state = apply_moves(state, [auf])
    assert is_solved(state)


def test_solve_pll_recognizes_every_pure_pll_state():
    with open(DATA_DIR / "pll.json", encoding="utf-8") as fh:
        pll_cases = json.load(fh)
    for case in pll_cases:
        state = apply_moves(CubieState.solved(), invert(parse_algorithm(case["alg"])))
        step = solve_pll(state)
        assert step is not None and step.case_id == case["id"]
        state = apply_moves(state, step.moves)
        auf = compute_auf(state)
        if auf is not None:
            state = apply_moves(state, [auf])
        assert is_solved(state), f"PLL {case['id']} pipeline failed"


def test_solve_pll_rejects_unoriented_last_layer():
    # Sune leaves F2L intact but the LL unoriented.
    state = apply_moves(CubieState.solved(), parse_algorithm("R U R' U R U2 R'"))
    assert f2l_is_solved(state) and not ll_is_oriented(state)
    with pytest.raises(ValueError):
        solve_pll(state)


def test_compute_auf_rejects_non_auf_state():
    state = apply_moves(CubieState.solved(), ["R"])
    with pytest.raises(ValueError):
        compute_auf(state)
