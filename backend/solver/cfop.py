"""CFOP orchestrator: cross -> F2L -> OLL -> PLL (+AUF) -> §8 solve response.

:func:`solve` takes a 54-char facelet string, validates it (§5), runs the
four solver stages and assembles the exact ``POST /api/solve`` 200 response
body of CONTRACTS.md §8 (a plain JSON-serializable dict).

Guarantees:

* Input is validated with :mod:`cube.validate` first; an invalid cube raises
  :class:`CubeInvalidError` carrying the §5 error dicts (the API layer turns
  it into the 400 body).
* Defense in depth: after the response is built, the full flat move list is
  applied to the input state and the result MUST be solved — otherwise
  :class:`SolverVerificationError` is raised. A solver bug can never ship an
  unsolved walkthrough.
"""

from __future__ import annotations

from typing import Any

from cube.facelet import (
    CORNER_COLOR,
    EDGE_COLOR,
    CubieState,
    facelets_to_cubies,
    is_solved,
)
from cube.moves import apply_moves, to_notation
from cube.validate import validate

from solver.cross import solve_cross
from solver.f2l import solve_f2l
from solver.oll import solve_oll
from solver.pll import compute_auf, solve_pll

#: The §8 SolveResult is the plain /api/solve 200 response body.
SolveResult = dict[str, Any]


class CubeInvalidError(ValueError):
    """The input facelet string failed §5 validation.

    ``errors`` holds the ready-to-serialize §5 error dicts
    (``{code, message, facelets, suspect_faces}``).
    """

    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__(
            "Invalid cube: " + "; ".join(e["code"] for e in errors)
        )
        self.errors = errors


class SolverVerificationError(AssertionError):
    """The emitted move list did not solve the input state (solver bug)."""


# --------------------------------------------------------------------------- #
# Highlights (§8): pieces named by their SOLVED slot.
# --------------------------------------------------------------------------- #

#: The 4 cross edges (D-layer edge slots), highlighted by the Cross step.
CROSS_HIGHLIGHT: list[dict[str, str]] = [
    {"type": "edge", "piece": name} for name in ("DR", "DF", "DL", "DB")
]

#: All 8 U-layer pieces, highlighted by OLL / PLL / AUF steps.
LAST_LAYER_HIGHLIGHT: list[dict[str, str]] = [
    *({"type": "edge", "piece": name} for name in ("UR", "UF", "UL", "UB")),
    *({"type": "corner", "piece": name} for name in ("URF", "UFL", "ULB", "UBR")),
]


def _f2l_highlight(pair: tuple[int, int]) -> list[dict[str, str]]:
    """Highlight for one F2L pair: its edge slot + corner slot names."""
    corner_id, edge_id = pair
    return [
        {"type": "edge", "piece": EDGE_COLOR[edge_id]},
        {"type": "corner", "piece": CORNER_COLOR[corner_id]},
    ]


# --------------------------------------------------------------------------- #
# Response assembly
# --------------------------------------------------------------------------- #


def _step(
    label: str,
    moves: list[str],
    move_offset: int,
    highlight: list[dict[str, str]],
    case: str | None = None,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "case": case,
        "moves": list(moves),
        "notation": to_notation(moves),
        "move_offset": move_offset,
        "skipped": skipped,
        "highlight": highlight,
    }


def solve(facelets: str) -> SolveResult:
    """Solve a cube with CFOP and build the §8 ``/api/solve`` response body.

    Raises:
        CubeInvalidError: if ``facelets`` fails §5 validation.
        SolverVerificationError: if (impossibly, absent a bug) the emitted
            moves do not solve the input state.
    """
    result = validate(facelets)
    if not result.valid:
        raise CubeInvalidError([e.to_dict() for e in result.errors])

    initial = facelets_to_cubies(facelets)
    state = initial.copy()
    flat_moves: list[str] = []

    def commit(moves: list[str]) -> int:
        """Apply ``moves``, append them to the flat list, return their offset."""
        nonlocal state
        offset = len(flat_moves)
        state = apply_moves(state, moves)
        flat_moves.extend(moves)
        return offset

    # ---- Cross -------------------------------------------------------------
    cross_moves = solve_cross(state)
    cross_stage = {
        "id": "cross",
        "label": "Cross",
        "steps": [
            _step("Cross", cross_moves, commit(cross_moves), CROSS_HIGHLIGHT)
        ],
    }

    # ---- F2L (steps numbered in the order actually solved) ------------------
    f2l_steps = []
    for number, f2l in enumerate(solve_f2l(state), start=1):
        f2l_steps.append(
            _step(
                f"F2L pair {number} ({f2l.slot} slot)",
                f2l.moves,
                commit(f2l.moves),
                _f2l_highlight(f2l.pair),
            )
        )
    f2l_stage = {"id": "f2l", "label": "F2L", "steps": f2l_steps}

    # ---- OLL ----------------------------------------------------------------
    oll = solve_oll(state)
    if oll is None:
        oll_step = _step(
            "OLL skip", [], len(flat_moves), LAST_LAYER_HIGHLIGHT, skipped=True
        )
    else:
        oll_step = _step(
            oll.label,
            oll.moves,
            commit(oll.moves),
            LAST_LAYER_HIGHLIGHT,
            case=oll.label,
        )
    oll_stage = {"id": "oll", "label": "OLL", "steps": [oll_step]}

    # ---- PLL (+ AUF as its own step when non-empty) --------------------------
    pll = solve_pll(state)
    if pll is None:
        pll_steps = [
            _step(
                "PLL skip", [], len(flat_moves), LAST_LAYER_HIGHLIGHT, skipped=True
            )
        ]
    else:
        pll_steps = [
            _step(
                pll.label,
                pll.moves,
                commit(pll.moves),
                LAST_LAYER_HIGHLIGHT,
                case=f"PLL {pll.case_id}",
            )
        ]
    auf = compute_auf(state)
    if auf is not None:
        pll_steps.append(
            _step("AUF", [auf], commit([auf]), LAST_LAYER_HIGHLIGHT)
        )
    pll_stage = {"id": "pll", "label": "PLL", "steps": pll_steps}

    # ---- MANDATORY defense in depth ------------------------------------------
    _verify(initial, flat_moves)

    return {
        "valid": True,
        "facelets": facelets,
        "total_moves": len(flat_moves),
        "stages": [cross_stage, f2l_stage, oll_stage, pll_stage],
    }


def _verify(initial: CubieState, flat_moves: list[str]) -> None:
    """Hard-fail unless the flat move list solves the input state (§7)."""
    if not is_solved(apply_moves(initial.copy(), flat_moves)):
        raise SolverVerificationError(
            "CFOP verification failed: the emitted move list does not solve "
            "the input state. This is a solver bug; refusing to return the "
            "walkthrough."
        )


__all__ = [
    "CROSS_HIGHLIGHT",
    "LAST_LAYER_HIGHLIGHT",
    "CubeInvalidError",
    "SolveResult",
    "SolverVerificationError",
    "solve",
]
