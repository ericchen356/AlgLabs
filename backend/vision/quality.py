"""Per-face scan quality assessment (CONTRACTS.md §6 / §8 /scan-face).

Works purely from the per-patch statistics produced by
:mod:`vision.sampling`: a cell is suspect when its pixel stddev is high
(motion blur, grid misalignment, partial glare — the patch straddles two
colours) or when it is a blown highlight (all channels essentially clipped
at the sensor maximum, which no real sticker colour produces under a sane
exposure — including white, which lands a few counts below full clip).
"""

from __future__ import annotations

from typing import Sequence, TypedDict

from .sampling import FaceSamples

#: Per-patch RGB stddev above which a cell is considered noisy/glared.
NOISE_STD_THRESHOLD = 25.0

#: Minimum per-channel mean (all three of r, g, b) for a patch to count as
#: a blown highlight. Deliberately extreme so a plain white sticker under
#: normal exposure never trips it.
BLOWN_CHANNEL_MIN = 254.0


class QualityReport(TypedDict):
    """Shape of the ``quality`` object in the /scan-face response."""

    ok: bool
    noisy_cells: list[int]
    message: str


def assess_quality(
    samples_rgb: Sequence[Sequence[float]], stddevs: Sequence[float]
) -> QualityReport:
    """Assess one face's scan quality from its 9 patch statistics.

    Args:
        samples_rgb: 9 x ``[r, g, b]`` patch means, row-major.
        stddevs: 9 per-patch stddevs (as produced by ``sample_face``).

    Returns:
        ``QualityReport`` with an overall ``ok`` flag, the row-major indices
        of suspect cells, and a user-facing message.
    """
    if len(samples_rgb) != 9 or len(stddevs) != 9:
        raise ValueError("Expected exactly 9 RGB samples and 9 stddevs.")

    noisy_cells: list[int] = []
    for index, (rgb, stddev) in enumerate(zip(samples_rgb, stddevs)):
        blown = min(rgb) >= BLOWN_CHANNEL_MIN
        if stddev > NOISE_STD_THRESHOLD or blown:
            noisy_cells.append(index)

    if not noisy_cells:
        return QualityReport(ok=True, noisy_cells=[], message="Face captured cleanly.")
    cells = ", ".join(str(i + 1) for i in noisy_cells)
    return QualityReport(
        ok=False,
        noisy_cells=noisy_cells,
        message=(
            f"Cell(s) {cells} look noisy or glared. Hold the cube steady, "
            "avoid reflections, and re-scan this face."
        ),
    )


def assess_face(samples: FaceSamples) -> QualityReport:
    """Convenience wrapper: assess quality straight from ``FaceSamples``."""
    return assess_quality(samples.samples_rgb, samples.stddevs)
