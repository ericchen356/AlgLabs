"""Color sampling from a cropped cube-face image (CONTRACTS.md §6).

The frontend sends the square guide-box region of a single cube face as a
base64-encoded image (raw base64 or a ``data:`` URL).  This module decodes
it, normalises it to a canonical square, and averages the middle-40% patch
of each of the 9 cells in row-major order (top-left -> bottom-right), which
per the scan protocol corresponds exactly to facelet indices 1..9 of the
scanned face.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

import cv2
import numpy as np

#: Canonical side length the guide region is resampled to before patch
#: extraction (the frontend guarantees >= 270 px per CONTRACTS.md §6).
CANONICAL_SIZE = 270

#: Fraction of each cell's side covered by the sampled centre patch.
PATCH_FRACTION = 0.40


class SamplingError(ValueError):
    """Raised when an image payload cannot be decoded into a usable image."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class FaceSamples:
    """Per-cell colour statistics for one scanned face (row-major order).

    Attributes:
        samples_lab: 9 x ``[L, a, b]`` patch means in OpenCV 8-bit Lab
            (``L`` in ``[0, 255]``).
        samples_rgb: 9 x ``[r, g, b]`` patch means in ``[0, 255]``.
        stddevs: 9 per-patch pixel standard deviations (mean of the three
            RGB channel stddevs) — the raw signal for quality assessment.
    """

    samples_lab: list[list[float]]
    samples_rgb: list[list[float]]
    stddevs: list[float]


def decode_base64_image(data: str) -> np.ndarray:
    """Decode a raw-base64 or ``data:`` URL image payload to a BGR array.

    Raises:
        SamplingError: if the payload is not valid base64 or does not decode
            to an image OpenCV understands.
    """
    if not isinstance(data, str) or not data.strip():
        raise SamplingError("Empty image payload.")
    payload = data.strip()
    if payload.startswith("data:"):
        _, sep, payload = payload.partition(",")
        if not sep:
            raise SamplingError("Malformed data: URL (missing comma separator).")
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise SamplingError(f"Invalid base64 image payload: {exc}") from exc
    if not raw:
        raise SamplingError("Decoded image payload is empty.")
    buffer = np.frombuffer(raw, dtype=np.uint8)
    try:
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except cv2.error as exc:
        # e.g. a header declaring more pixels than CV_IO_MAX_IMAGE_PIXELS.
        raise SamplingError(f"Payload is not a decodable image: {exc}") from exc
    if image is None:
        raise SamplingError("Payload is not a decodable image.")
    return image


def _to_canonical_square(image: np.ndarray) -> np.ndarray:
    """Centre-crop to a square and resample to ``CANONICAL_SIZE``."""
    height, width = image.shape[:2]
    side = min(height, width)
    top = (height - side) // 2
    left = (width - side) // 2
    square = image[top : top + side, left : left + side]
    interpolation = cv2.INTER_AREA if side >= CANONICAL_SIZE else cv2.INTER_LINEAR
    return cv2.resize(
        square, (CANONICAL_SIZE, CANONICAL_SIZE), interpolation=interpolation
    )


def sample_face(image: str | np.ndarray) -> FaceSamples:
    """Sample the 9 sticker patches of a scanned face.

    Args:
        image: base64 string (raw or ``data:`` URL) or an already-decoded
            BGR ``uint8`` array of the cropped square guide region.

    Returns:
        ``FaceSamples`` with per-patch mean Lab, mean RGB and stddev, in
        row-major cell order.
    """
    if isinstance(image, str):
        bgr = decode_base64_image(image)
    else:
        bgr = np.asarray(image)
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise SamplingError("Expected a 3-channel BGR image array.")
        bgr = bgr.astype(np.uint8, copy=False)

    bgr = _to_canonical_square(bgr)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2Lab)

    cell = CANONICAL_SIZE // 3
    patch = int(round(cell * PATCH_FRACTION))
    inset = (cell - patch) // 2

    samples_lab: list[list[float]] = []
    samples_rgb: list[list[float]] = []
    stddevs: list[float] = []
    for row in range(3):
        for col in range(3):
            y0 = row * cell + inset
            x0 = col * cell + inset
            lab_patch = lab[y0 : y0 + patch, x0 : x0 + patch].astype(np.float64)
            bgr_patch = bgr[y0 : y0 + patch, x0 : x0 + patch].astype(np.float64)
            lab_mean = lab_patch.reshape(-1, 3).mean(axis=0)
            bgr_mean = bgr_patch.reshape(-1, 3).mean(axis=0)
            bgr_std = bgr_patch.reshape(-1, 3).std(axis=0)
            samples_lab.append([float(v) for v in lab_mean])
            samples_rgb.append([float(bgr_mean[2]), float(bgr_mean[1]), float(bgr_mean[0])])
            stddevs.append(float(bgr_std.mean()))
    return FaceSamples(samples_lab=samples_lab, samples_rgb=samples_rgb, stddevs=stddevs)
