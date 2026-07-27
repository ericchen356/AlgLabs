"""OLL recognition (57 cases) — lookup table built programmatically at import.

Per CONTRACTS.md section 7 ("Stage oll"):

* Recognition key = orientation signature ``(tuple(co[0:4]), tuple(eo[0:4]))``
  of the U-layer slots (F2L is solved, so all last-layer pieces live there).
* For each case's algorithm ``A`` (run through ``parse_algorithm``) and each
  pre-AUF ``k in 0..3``, the state ``s = apply(invert(U^k + A), SOLVED)`` is
  solved by playing ``U^k A``; the table maps ``signature(s) -> (case, moves)``
  with ``moves = U^k token + parsed A``.
* Build-time gates: every constructed setup state has its first two layers
  solved (data-typo detector), the table covers EXACTLY the 215 non-solved
  orientation signatures, and no signature is claimed by two different cases.

Why the signature is sufficient: the orientation effect of applying a move
sequence ``M`` to a state ``t`` is ``(t.co[M.cp[i]] + M.co[i]) % 3`` (and the
edge analogue) — it depends only on ``t``'s orientation arrays, never on its
permutation. So any F2L-solved state sharing a setup state's signature is
oriented by that setup's moves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cube.facelet import CubieState
from cube.moves import apply_moves, invert, parse_algorithm

_DATA_PATH = Path(__file__).parent / "data" / "oll.json"

#: Pre-AUF token for k quarter turns of U (k=0 -> no token).
AUF_TOKENS: dict[int, list[str]] = {0: [], 1: ["U"], 2: ["U2"], 3: ["U'"]}

#: Number of distinct non-solved last-layer orientation signatures:
#: 3^3 corner twists x 2^3 edge flips (sum constraints) minus the solved one.
N_OLL_SIGNATURES = 27 * 8 - 1  # 215

Signature = tuple[tuple[int, ...], tuple[int, ...]]


@dataclass(frozen=True)
class OllCase:
    """One OLL case as loaded from ``data/oll.json``."""

    id: int
    name: str
    alg: str
    group: str | None = None
    #: Verified alternate algorithms (any pre-AUF angle) — ignored by the
    #: recognition table; consumed by the trainer for scramble diversity.
    alt: list[str] | None = None


@dataclass(frozen=True)
class OllStep:
    """Result of :func:`solve_oll` — one recognized OLL application."""

    case_id: int
    name: str
    label: str  # e.g. "OLL 27 — Sune"
    moves: list[str]  # pre-AUF U token (if any) + parsed case algorithm


def signature(state: CubieState) -> Signature:
    """Orientation signature of the U-layer slots: ``(co[0:4], eo[0:4])``."""
    return (tuple(state.co[0:4]), tuple(state.eo[0:4]))


SOLVED_SIGNATURE: Signature = ((0, 0, 0, 0), (0, 0, 0, 0))


def f2l_is_solved(state: CubieState) -> bool:
    """True iff the first two layers (all non-U-layer slots) are solved."""
    return (
        state.cp[4:8] == [4, 5, 6, 7]
        and state.co[4:8] == [0, 0, 0, 0]
        and state.ep[4:12] == [4, 5, 6, 7, 8, 9, 10, 11]
        and state.eo[4:12] == [0] * 8
    )


def ll_is_oriented(state: CubieState) -> bool:
    """True iff every last-layer piece is oriented (and F2L is solved)."""
    return f2l_is_solved(state) and state.co[0:4] == [0] * 4 and state.eo[0:4] == [0] * 4


def _load_cases() -> list[OllCase]:
    with open(_DATA_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    cases = [OllCase(**entry) for entry in raw]
    assert len(cases) == 57, f"oll.json must have 57 cases, got {len(cases)}"
    assert sorted(c.id for c in cases) == list(range(1, 58)), "oll.json ids must be 1..57"
    return cases


def _build_table() -> dict[Signature, tuple[OllCase, list[str]]]:
    """Build signature -> (case, solving moves), enforcing the section-7 gates."""
    table: dict[Signature, tuple[OllCase, list[str]]] = {}
    for case in _load_cases():
        alg_tokens = parse_algorithm(case.alg)
        for k in range(4):
            moves = AUF_TOKENS[k] + alg_tokens
            # From s, playing `U^k A` orients (in fact solves) the last layer.
            s = apply_moves(CubieState.solved(), invert(moves))
            assert f2l_is_solved(s), (
                f"OLL case {case.id} ({case.name}): algorithm does not preserve "
                f"the first two layers (pre-AUF k={k}) — bad data?"
            )
            sig = signature(s)
            assert sig != SOLVED_SIGNATURE, (
                f"OLL case {case.id} ({case.name}): algorithm is an identity on "
                f"last-layer orientation (pre-AUF k={k}) — bad data?"
            )
            existing = table.get(sig)
            if existing is not None:
                assert existing[0].id == case.id, (
                    f"OLL signature collision: cases {existing[0].id} and "
                    f"{case.id} share signature {sig}"
                )
                continue  # same case, symmetric under AUF — keep first entry
            table[sig] = (case, moves)
    assert len(table) == N_OLL_SIGNATURES, (
        f"OLL table must cover exactly {N_OLL_SIGNATURES} non-solved "
        f"signatures, got {len(table)}"
    )
    return table


#: signature -> (case, moves that orient the last layer). Built at import.
OLL_TABLE: dict[Signature, tuple[OllCase, list[str]]] = _build_table()


def solve_oll(state: CubieState) -> OllStep | None:
    """Recognize and solve the OLL stage.

    Precondition: the first two layers are solved. Returns ``None`` on an
    OLL skip (last layer already oriented), otherwise an :class:`OllStep`
    whose ``moves`` (pre-AUF U turn, if any, followed by the case algorithm)
    orient every last-layer piece.
    """
    if not f2l_is_solved(state):
        raise ValueError("solve_oll precondition failed: first two layers not solved")
    sig = signature(state)
    if sig == SOLVED_SIGNATURE:
        return None  # OLL skip
    case, moves = OLL_TABLE[sig]
    # Defense in depth: the returned moves must actually orient the last layer.
    after = apply_moves(state.copy(), moves)
    assert ll_is_oriented(after), (
        f"OLL case {case.id} ({case.name}) failed to orient the last layer"
    )
    return OllStep(
        case_id=case.id,
        name=case.name,
        label=f"OLL {case.id} · {case.name}",
        moves=list(moves),
    )


__all__ = [
    "AUF_TOKENS",
    "N_OLL_SIGNATURES",
    "OLL_TABLE",
    "OllCase",
    "OllStep",
    "SOLVED_SIGNATURE",
    "f2l_is_solved",
    "ll_is_oriented",
    "signature",
    "solve_oll",
]
