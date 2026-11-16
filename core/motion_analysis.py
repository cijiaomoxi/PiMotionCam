"""Optional bounded software block matching; independent of legacy MMAL."""

from __future__ import annotations

import math
import numpy as np


def motion_vectors(previous, current, max_vectors=12):
    """Match textured moving 8x8 blocks on a <=96px-wide image.

    Vectors are normalized to the displayed frame. Search and output are
    bounded so a textured full frame cannot create unbounded per-frame work.
    """
    stride = max(1, math.ceil(max(current.shape) / 96))
    a = previous[::stride, ::stride].astype(np.int16)
    b = current[::stride, ::stride].astype(np.int16)
    h, w = b.shape
    radius, block = 4, 8
    candidates = []
    for y in range(radius, h - block - radius + 1, block):
        for x in range(radius, w - block - radius + 1, block):
            tile = a[y : y + block, x : x + block]
            change = float(np.abs(tile - b[y : y + block, x : x + block]).mean())
            if change >= 5 and float(tile.std()) >= 8:
                candidates.append((change, x, y))
    vectors = []
    for zero, x, y in sorted(candidates, reverse=True)[:max_vectors]:
        tile = a[y : y + block, x : x + block]
        best = (zero, 0, 0)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                score = float(
                    np.abs(
                        tile - b[y + dy : y + dy + block, x + dx : x + dx + block]
                    ).mean()
                )
                if score < best[0]:
                    best = (score, dx, dy)
        confidence = 1 - best[0] / max(1, zero)
        if confidence >= 0.3 and (best[1] or best[2]):
            vectors.append(
                {
                    "x": (x + block / 2) / w,
                    "y": (y + block / 2) / h,
                    "dx": best[1] / w,
                    "dy": best[2] / h,
                    "confidence": round(confidence, 3),
                }
            )
    dx = float(np.median([v["dx"] for v in vectors])) if vectors else 0.0
    dy = float(np.median([v["dy"] for v in vectors])) if vectors else 0.0
    direction = "still"
    if dx or dy:
        direction = (
            ("right" if dx > 0 else "left")
            if abs(dx) > abs(dy)
            else ("down" if dy > 0 else "up")
        )
    return {
        "source": "software",
        "direction": direction,
        "dx": round(dx, 5),
        "dy": round(dy, 5),
        "vectors": vectors,
    }
