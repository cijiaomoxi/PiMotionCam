#!/usr/bin/env python3
"""Reproducible, read-only microbenchmarks; optionally sample a live API.

Run the same file with --repo pointing at each checkout. No camera, microphone,
configuration or media files are changed. Results are machine-specific.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import urllib.request
from pathlib import Path


def measure(fn, iterations):
    for _ in range(5):
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 4),
            "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * .95))], 4),
            "samples": len(samples)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--iterations", type=int, default=100)
    ap.add_argument("--url", help="Optional live server, e.g. http://127.0.0.1:8080")
    ap.add_argument("--config", type=Path, help="Optional existing config for its actual motion regions")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.iterations < 1:
        ap.error("--iterations must be positive")
    sys.path.insert(0, str(args.repo.resolve()))
    import numpy as np
    from core import __version__, native
    from core.audio import AudioCapture

    if not native.available():
        raise SystemExit("Native backend required: " + native.build_log())
    rng = np.random.default_rng(280)
    prev = rng.integers(0, 256, (180, 320), dtype=np.uint8)
    cur = prev.copy()
    cur[40:115, 70:200] = rng.integers(0, 256, (75, 130), dtype=np.uint8)
    result = {"version": __version__, "platform": platform.platform(),
              "python": platform.python_version(), "numpy": np.__version__,
              "backend": native.backend(), "repo": str(args.repo), "benchmarks": {}}
    for count in (1, 8, 32):
        regions = []
        for mag, radius in ((12, 2), (28, 3)):
            for i in range(count):
                x, y = (i * 17) % 100, (i * 13) % 55
                regions.append(dict(x0=x, y0=y, x1=320 - x, y1=180 - y,
                                    mag_limit=mag, noise_k=radius, count_limit=.006,
                                    consecutive=2, hit_count=1))
        def detect():
            if native.detect(cur, prev, 320, 180, regions) is None:
                raise RuntimeError("Native detection failed")
        result["benchmarks"][f"detect_{count}_regions_per_algorithm"] = measure(
            detect, args.iterations)
    if args.config:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        motion = cfg["motion"]
        regions = []
        for algo in motion["algorithms"].values():
            if not algo.get("enabled", True):
                continue
            for region in motion["regions"]:
                if not region.get("enabled", True):
                    continue
                x0, y0 = max(0, int(region["x"] * 320)), max(0, int(region["y"] * 180))
                regions.append(dict(x0=x0, y0=y0,
                    x1=min(320, max(x0 + 1, int((region["x"] + region["w"]) * 320))),
                    y1=min(180, max(y0 + 1, int((region["y"] + region["h"]) * 180))),
                    mag_limit=int(algo["magnitude_limit"]), noise_k=int(algo["noise_filter"]),
                    count_limit=float(algo["count_limit"]), consecutive=max(1, int(algo["consecutive_frames"])),
                    hit_count=1))
        def configured_detect():
            if native.detect(cur, prev, 320, 180, regions) is None:
                raise RuntimeError("Configured detection failed")
        result["configured_region_specs"] = len(regions)
        result["benchmarks"]["detect_configured_regions"] = measure(configured_detect, args.iterations)
    cap = AudioCapture(state=None)
    for count in (2048, 24000):
        pcm = rng.integers(-32768, 32768, count, dtype=np.int16).astype("<i2").tobytes()
        result["benchmarks"][f"audio_rms_{count}_samples"] = measure(
            lambda: cap._rms_level(pcm), args.iterations)
    if args.url:
        def request_state():
            with urllib.request.urlopen(args.url.rstrip("/") + "/api/state", timeout=20) as r:
                data = json.load(r)
                if "media" not in data or not data.get("camera_ready"):
                    raise RuntimeError("Live camera/state unavailable")
        result["benchmarks"]["api_state"] = measure(request_state, args.iterations)
    report = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
