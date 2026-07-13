"""PLL recognition (21 cases) — lookup table built programmatically at import.

Per CONTRACTS.md section 7 ("Stage pll"):

* Precondition: the last layer is ORIENTED (post-OLL), so the state is fully
  determined by the permutation of the U-layer slots.
* Recognition key = ``(tuple(cp[0:4]), tuple(ep[0:4]))``.
* Construction: for each case's algorithm ``A``, pre-AUF ``k in 0..3`` and
  post-AUF ``j in 0..3``, the state ``s = apply(invert(U^k + A + U^j), SOLVED)``
  is solved by playing ``U^k A U^j``. The table maps
  ``signature(s) -> (case, moves = U^k token + parsed A)``; the trailing
  post-AUF is recovered at runtime by :func:`compute_auf` (and emitted as a
  separate "AUF" step by the orchestrator).
* Build-time gates: every setup preserves F2L AND last-layer orientation, and
  coverage is ALL 288 valid signatures — 284 mapping to (case, pre-AUF) plus
  the 4 identity-up-to-AUF signatures (PLL skip).

Why 288: cp[0:4] and ep[0:4] each range over the 24 permutations of the four
last-layer cubies, and total corner/edge permutation parity must match
(24 * 24 / 2 = 288).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

from cube.facelet import CubieState, is_solved
from cube.moves import apply_moves, invert, parse_algorithm

from .oll import AUF_TOKENS, ll_is_oriented

_DATA_PATH = Path(__file__).parent / "data" / "pll.json"

PLL_IDS = (
    "Aa", "Ab", "E", "F", "Ga", "Gb", "Gc", "Gd", "H", "Ja", "Jb",
    "Na", "Nb", "Ra", "Rb", "T", "Ua", "Ub", "V", "Y", "Z",
)

#: All valid post-OLL permutation signatures: 24 corner perms x 24 edge perms
#: with matching parity.
N_PLL_SIGNATURES = 288
N_PLL_CASE_SIGNATURES = 284  # 288 minus the 4 identity-up-to-AUF (skip) states

Signature = tuple[tuple[int, ...], tuple[int, ...]]


@dataclass(frozen=True)
class PllCase:
    """One PLL case as loaded from ``data/pll.json``."""

    id: str
    name: str
    alg: str
    #: Verified alternate algorithms (any pre/post-AUF angle) — ignored by the
    #: recognition table; consumed by the trainer for scramble diversity.
    alt: list[str] | None = None


@dataclass(frozen=True)
class PllStep:
    """Result of :func:`solve_pll` — one recognized PLL application."""

    case_id: str
    name: str
    label: str  # e.g. "PLL T — T Perm"
    moves: list[str]  # pre-AUF U token (if any) + parsed case algorithm


def signature(state: CubieState) -> Signature:
    """Permutation signature of the U-layer slots: ``(cp[0:4], ep[0:4])``."""
    return (tuple(state.cp[0:4]), tuple(state.ep[0:4]))


def _load_cases() -> list[PllCase]:
    with open(_DATA_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)
    cases = [PllCase(**entry) for entry in raw]
    assert len(cases) == 21, f"pll.json must have 21 cases, got {len(cases)}"
    assert sorted(c.id for c in cases) == sorted(PLL_IDS), "pll.json ids wrong"
    return cases


def _build_table() -> tuple[dict[Signature, tuple[PllCase, list[str]]], frozenset[Signature]]:
    """Build (signature -> (case, moves), skip signatures) with section-7 gates."""
    # The 4 identity-up-to-AUF states: U^j applied to solved, j in 0..3.
    skip_signatures: set[Signature] = set()
    for j in range(4):
        s = apply_moves(CubieState.solved(), AUF_TOKENS[j])
        skip_signatures.add(signature(s))
    assert len(skip_signatures) == 4

    table: dict[Signature, tuple[PllCase, list[str]]] = {}
    for case in _load_cases():
        alg_tokens = parse_algorithm(case.alg)
        for k in range(4):
            moves = AUF_TOKENS[k] + alg_tokens
            for j in range(4):
                # From s, playing `U^k A U^j` solves the cube exactly; the
                # stored moves omit the trailing U^j (found by compute_auf).
                s = apply_moves(CubieState.solved(), invert(moves + AUF_TOKENS[j]))
                assert ll_is_oriented(s), (
                    f"PLL case {case.id} ({case.name}): algorithm does not "
                    f"preserve F2L + last-layer orientation (k={k}, j={j}) "
                    f"— bad data?"
                )
                sig = signature(s)
                assert sig not in skip_signatures, (
                    f"PLL case {case.id} ({case.name}): algorithm is an "
                    f"identity up to AUF (k={k}, j={j}) — bad data?"
                )
                existing = table.get(sig)
                if existing is not None:
                    assert existing[0].id == case.id, (
                        f"PLL signature collision: cases {existing[0].id} and "
                        f"{case.id} share signature {sig}"
                    )
                    continue  # same case, symmetric under AUF — keep first
                table[sig] = (case, moves)
    assert len(table) == N_PLL_CASE_SIGNATURES, (
        f"PLL table must cover exactly {N_PLL_CASE_SIGNATURES} signatures, "
        f"got {len(table)}"
    )

    # Full coverage: table + skips == every parity-consistent signature.
    all_valid = valid_signatures()
    covered = set(table) | skip_signatures
    assert covered == all_valid, (
        f"PLL coverage mismatch: {len(covered)} covered vs "
        f"{len(all_valid)} valid signatures"
    )
    return table, frozenset(skip_signatures)


def _perm_parity(perm: tuple[int, ...]) -> int:
    parity = 0
    for i in range(len(perm)):
        for k in range(i + 1, len(perm)):
            if perm[i] > perm[k]:
                parity ^= 1
    return parity


def valid_signatures() -> set[Signature]:
    """All 288 parity-consistent post-OLL permutation signatures."""
    corner_perms = list(permutations(range(4)))
    edge_perms = corner_perms
    return {
        (cp, ep)
        for cp in corner_perms
        for ep in edge_perms
        if _perm_parity(cp) == _perm_parity(ep)
    }


#: signature -> (case, moves solving the LL permutation up to AUF), and the 4
#: skip (identity-up-to-AUF) signatures. Built at import.
PLL_TABLE: dict[Signature, tuple[PllCase, list[str]]]
SKIP_SIGNATURES: frozenset[Signature]
PLL_TABLE, SKIP_SIGNATURES = _build_table()


def solve_pll(state: CubieState) -> PllStep | None:
    """Recognize and solve the PLL stage.

    Precondition: F2L solved and last layer oriented (post-OLL). Returns
    ``None`` on a PLL skip (the state is solved up to a final AUF), otherwise
    a :class:`PllStep` whose ``moves`` (pre-AUF U turn, if any, followed by
    the case algorithm) bring the cube to solved-up-to-AUF; follow with
    :func:`compute_auf`.
    """
    if not ll_is_oriented(state):
        raise ValueError(
            "solve_pll precondition failed: F2L solved + last layer oriented required"
        )
    sig = signature(state)
    if sig in SKIP_SIGNATURES:
        return None  # PLL skip (possibly still needs an AUF)
    case, moves = PLL_TABLE[sig]
    # Defense in depth: after the moves the cube must be solved up to AUF.
    after = apply_moves(state.copy(), moves)
    assert signature(after) in SKIP_SIGNATURES and ll_is_oriented(after), (
        f"PLL case {case.id} ({case.name}) failed to solve the last-layer "
        f"permutation up to AUF"
    )
    return PllStep(
        case_id=case.id,
        name=case.name,
        label=f"PLL {case.id} — {case.name}",
        moves=list(moves),
    )


def compute_auf(state: CubieState) -> str | None:
    """Final U-turn adjustment: the token in {U, U', U2} (or ``None``) that
    solves ``state``, which must be solved up to AUF (post-PLL)."""
    if is_solved(state):
        return None
    for token in ("U", "U'", "U2"):
        if is_solved(apply_moves(state.copy(), [token])):
            return token
    raise ValueError("compute_auf precondition failed: state is not solved up to AUF")


__all__ = [
    "N_PLL_CASE_SIGNATURES",
    "N_PLL_SIGNATURES",
    "PLL_IDS",
    "PLL_TABLE",
    "PllCase",
    "PllStep",
    "SKIP_SIGNATURES",
    "compute_auf",
    "signature",
    "solve_pll",
    "valid_signatures",
]
