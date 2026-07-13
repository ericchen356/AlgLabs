"""T11: cfop.solve on 300 seeded random scrambles (§10) + response structure."""

import random
import statistics

import pytest

from cube.facelet import CubieState, cubies_to_facelets, facelets_to_cubies, is_solved
from cube.moves import MOVE_TOKENS, apply_moves, random_scramble
from solver import cfop

N_SCRAMBLES = 300

STAGE_IDS = ["cross", "f2l", "oll", "pll"]
STAGE_LABELS = {"cross": "Cross", "f2l": "F2L", "oll": "OLL", "pll": "PLL"}

STEP_KEYS = {"label", "case", "moves", "notation", "move_offset", "skipped", "highlight"}

D_EDGES = ["DR", "DF", "DL", "DB"]
LL_PIECES = {
    ("edge", "UR"), ("edge", "UF"), ("edge", "UL"), ("edge", "UB"),
    ("corner", "URF"), ("corner", "UFL"), ("corner", "ULB"), ("corner", "UBR"),
}
F2L_PAIR_OF_SLOT = {"FR": "DFR", "FL": "DLF", "BL": "DBL", "BR": "DRB"}


def _scrambled_facelets(rng: random.Random) -> str:
    return cubies_to_facelets(apply_moves(CubieState.solved(), random_scramble(rng)))


def _flat_moves(result: dict) -> list[str]:
    return [m for stage in result["stages"] for step in stage["steps"] for m in step["moves"]]


def _check_result(facelets: str, result: dict) -> list[str]:
    """Full §8 structural check; returns the flat move list."""
    assert result["valid"] is True
    assert result["facelets"] == facelets

    # Stage ids / labels / order.
    assert [s["id"] for s in result["stages"]] == STAGE_IDS
    for stage in result["stages"]:
        assert stage["label"] == STAGE_LABELS[stage["id"]]

    flat: list[str] = []
    for stage in result["stages"]:
        for step in stage["steps"]:
            assert set(step) == STEP_KEYS
            # move_offset = index of the step's first move in the flat list
            # (cumulative lengths), also for empty/skipped steps.
            assert step["move_offset"] == len(flat)
            assert all(m in MOVE_TOKENS for m in step["moves"])
            assert step["notation"] == " ".join(step["moves"])
            if step["skipped"]:
                assert step["moves"] == []
            flat.extend(step["moves"])
    assert result["total_moves"] == len(flat)

    # Cross: one step, <= 8 moves, highlights the 4 D-edges.
    (cross_step,) = result["stages"][0]["steps"]
    assert cross_step["label"] == "Cross"
    assert cross_step["case"] is None
    assert len(cross_step["moves"]) <= 8
    assert cross_step["highlight"] == [{"type": "edge", "piece": p} for p in D_EDGES]

    # F2L: 4 steps numbered in solved order, each highlighting its own pair.
    f2l_steps = result["stages"][1]["steps"]
    assert len(f2l_steps) == 4
    slots_seen = []
    for i, step in enumerate(f2l_steps, start=1):
        assert step["case"] is None
        slot = step["label"].split("(")[1].split(" ")[0]
        assert step["label"] == f"F2L pair {i} ({slot} slot)"
        slots_seen.append(slot)
        assert step["highlight"] == [
            {"type": "edge", "piece": slot},
            {"type": "corner", "piece": F2L_PAIR_OF_SLOT[slot]},
        ]
        assert "D" not in {m[0] for m in step["moves"]}  # 15-move set
    assert sorted(slots_seen) == sorted(F2L_PAIR_OF_SLOT)

    # OLL: one step — either a recognized case or an explicit skip.
    (oll_step,) = result["stages"][2]["steps"]
    if oll_step["skipped"]:
        assert oll_step["label"] == "OLL skip" and oll_step["case"] is None
    else:
        assert oll_step["label"].startswith("OLL ")
        assert oll_step["case"] == oll_step["label"]

    # PLL: case-or-skip step, then optionally the AUF step.
    pll_steps = result["stages"][3]["steps"]
    assert len(pll_steps) in (1, 2)
    if pll_steps[0]["skipped"]:
        assert pll_steps[0]["label"] == "PLL skip" and pll_steps[0]["case"] is None
    else:
        assert pll_steps[0]["label"].startswith("PLL ")
        assert pll_steps[0]["case"] == "PLL " + pll_steps[0]["label"].split(" ")[1]
    if len(pll_steps) == 2:
        auf = pll_steps[1]
        assert auf["label"] == "AUF" and auf["case"] is None and not auf["skipped"]
        assert auf["moves"] in (["U"], ["U'"], ["U2"])

    # OLL/PLL/AUF highlight all 8 U-layer pieces.
    for step in [oll_step, *pll_steps]:
        assert {(h["type"], h["piece"]) for h in step["highlight"]} == LL_PIECES
        assert len(step["highlight"]) == 8

    return flat


def test_t11_300_random_scrambles():
    """T11: 300 seeded scrambles — verified solutions, sane lengths, §8 shape."""
    rng = random.Random(2026)
    lengths: list[int] = []
    for _ in range(N_SCRAMBLES):
        facelets = _scrambled_facelets(rng)
        result = cfop.solve(facelets)  # internal defense-in-depth verify runs
        flat = _check_result(facelets, result)
        # External re-verification: the flat move list solves the input.
        assert is_solved(apply_moves(facelets_to_cubies(facelets), flat))
        lengths.append(len(flat))

    median = statistics.median(lengths)
    mean = statistics.fmean(lengths)
    print(
        f"\nT11 report: {N_SCRAMBLES} scrambles — median={median} "
        f"mean={mean:.1f} max={max(lengths)} min={min(lengths)} moves"
    )
    assert 40 <= median <= 80


def test_solved_cube_all_stages_trivial():
    result = cfop.solve(cubies_to_facelets(CubieState.solved()))
    _check_result(cubies_to_facelets(CubieState.solved()), result)
    assert result["total_moves"] == 0
    (cross_step,) = result["stages"][0]["steps"]
    assert cross_step["moves"] == []
    assert all(s["moves"] == [] for s in result["stages"][1]["steps"])
    assert result["stages"][2]["steps"][0]["skipped"] is True
    assert result["stages"][2]["steps"][0]["label"] == "OLL skip"
    assert result["stages"][3]["steps"][0]["skipped"] is True
    assert result["stages"][3]["steps"][0]["label"] == "PLL skip"
    assert len(result["stages"][3]["steps"]) == 1  # no AUF step


def test_auf_only_state_emits_auf_step():
    """U applied to solved: everything skips except a single AUF step."""
    facelets = cubies_to_facelets(apply_moves(CubieState.solved(), ["U"]))
    result = cfop.solve(facelets)
    _check_result(facelets, result)
    assert result["total_moves"] == 1
    pll_steps = result["stages"][3]["steps"]
    assert pll_steps[0]["label"] == "PLL skip" and pll_steps[0]["skipped"]
    assert pll_steps[1]["label"] == "AUF" and pll_steps[1]["moves"] == ["U'"]
    assert pll_steps[1]["move_offset"] == 0


def test_invalid_inputs_raise_structured_errors():
    with pytest.raises(cfop.CubeInvalidError) as exc_info:
        cfop.solve("U" * 53)
    assert [e["code"] for e in exc_info.value.errors] == ["bad_length"]

    with pytest.raises(cfop.CubeInvalidError) as exc_info:
        cfop.solve("U" * 54)
    assert [e["code"] for e in exc_info.value.errors] == ["bad_counts"]

    # Twist one corner of the solved cube: URF facelets (8, 9, 20) rotated.
    solved = cubies_to_facelets(CubieState.solved())
    twisted = list(solved)
    twisted[8], twisted[9], twisted[20] = "R", "F", "U"
    with pytest.raises(cfop.CubeInvalidError) as exc_info:
        cfop.solve("".join(twisted))
    codes = [e["code"] for e in exc_info.value.errors]
    assert "corner_twist" in codes
    error = exc_info.value.errors[codes.index("corner_twist")]
    assert set(error) == {"code", "message", "facelets", "suspect_faces"}
    assert set(error["facelets"]) == {8, 9, 20}


def test_verification_is_a_hard_failure(monkeypatch):
    """A (simulated) solver bug must raise, never ship an unsolved result."""
    # T-perm applied to solved: cross/F2L/OLL trivial, PLL genuinely needed.
    facelets = cubies_to_facelets(
        apply_moves(CubieState.solved(), "R U R' U' R' F R2 U' R' U' R U R' F'")
    )
    monkeypatch.setattr(cfop, "solve_pll", lambda state: None)
    monkeypatch.setattr(cfop, "compute_auf", lambda state: None)
    with pytest.raises(cfop.SolverVerificationError):
        cfop.solve(facelets)
