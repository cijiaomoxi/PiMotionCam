"""多区域双算法帧差检测，可选软件方向分析；不使用 MMAL 硬件矢量。

官方依赖 BCM2835 的 MMAL 硬件运动矢量，Debian 13 的新 libcamera 栈不向用户态
暴露该能力，这里使用独立的帧差分实现：

  1. 帧与上一帧灰度图做绝对差
  2. 按 magnitude_limit 二值化
  3. 邻域密度滤波去掉孤立噪点
  4. 在每个运动区域内统计有效变化像素占比，超过 count_limit 即命中
  5. 连续命中 consecutive_frames 帧才判定为移动

两套算法并行运行：far 面向远处小/慢目标，near 面向近处大目标，
各自独立配置灵敏度——对应官方"双运动检测算法并行"的特性。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from collections import deque

import numpy as np

from . import native


@dataclass
class Detection:
    motion: bool = False
    algorithm: str | None = None
    region: str | None = None
    ratio: float = 0.0
    bbox: tuple[int, int, int, int] | None = None   # 触发区域的像素包围盒
    ratios: dict = field(default_factory=dict)        # {算法: {区域: 占比}}
    analysis: dict = field(default_factory=dict)


def _box_sum(mask: np.ndarray, k: int) -> np.ndarray:
    """用积分图计算 k×k 邻域内的置位像素数（O(N)）。"""
    if k <= 1:
        return mask.astype(np.int32)
    h, w = mask.shape
    m = mask.astype(np.int32)
    ii = np.zeros((h + 1, w + 1), dtype=np.int32)
    np.cumsum(np.cumsum(m, axis=0), axis=1, out=ii[1:, 1:])
    r = k // 2
    ys = np.arange(h)
    xs = np.arange(w)
    y0 = np.clip(ys - r, 0, h)
    y1 = np.clip(ys + r + 1, 0, h)
    x0 = np.clip(xs - r, 0, w)
    x1 = np.clip(xs + r + 1, 0, w)
    return (ii[y1[:, None], x1[None, :]]
            - ii[y0[:, None], x1[None, :]]
            - ii[y1[:, None], x0[None, :]]
            + ii[y0[:, None], x0[None, :]])


class Detector:
    """线程安全的帧差分检测器。"""

    def __init__(self, config_provider):
        self._cfg = config_provider
        self._lock = threading.Lock()
        self._prev: np.ndarray | None = None
        self._hits: dict[tuple[str, str], int] = {}
        self.last = Detection()
        self.frame_count = 0
        self.detect_fps = 0.0
        self._fps_mark = time.time()
        self._fps_count = 0
        self._recent = deque(maxlen=120)
        self._suppress_until = 0.0

    def reset(self):
        with self._lock:
            self._prev = None
            self._hits.clear()
            self._recent.clear()

    def suppress(self, seconds=1.0):
        with self._lock:
            self._suppress_until = time.monotonic() + max(0., min(60., float(seconds)))
            self._hits.clear()
            self._recent.clear()

    def _analyze(self, det, prev, gray):
        options = self._cfg.get("motion", "analysis", default={}) or {}
        if not options.get("enabled"):
            return det
        from .motion_analysis import motion_vectors
        diff = np.abs(gray.astype(np.int16) - prev.astype(np.int16))
        mask = diff > max(1, int(options.get("threshold", 15)))
        significant = mask & (_box_sum(mask, 3) >= 3)
        roi = np.zeros(gray.shape, dtype=bool)
        for region in self._regions():
            h, w = gray.shape
            x0 = max(0, min(w, int(float(region.get("x", 0))*w)))
            y0 = max(0, min(h, int(float(region.get("y", 0))*h)))
            x1 = max(x0, min(w, int((float(region.get("x", 0)) + float(region.get("w", 1))) * w)))
            y1 = max(y0, min(h, int((float(region.get("y", 0)) + float(region.get("h", 1))) * h)))
            roi[y0:y1, x0:x1] = True
        significant &= roi
        mask &= roi
        raw = int(mask.sum())
        kept = int(significant.sum())
        det.analysis = {"source": "software", "changed_pixels": raw,
                        "rejected_pixels": max(0, raw-kept),
                        "change_ratio": round(kept/max(1, mask.size), 5)}
        if options.get("vectors", True):
            flow = motion_vectors(prev, gray)
            flow["vectors"] = [v for v in flow["vectors"]
                               if roi[min(gray.shape[0]-1, int(v["y"]*gray.shape[0])),
                                      min(gray.shape[1]-1, int(v["x"]*gray.shape[1]))]]
            vectors = flow["vectors"]
            dx = float(np.median([v["dx"] for v in vectors])) if vectors else 0.
            dy = float(np.median([v["dy"] for v in vectors])) if vectors else 0.
            flow.update(dx=dx, dy=dy, direction=("right" if dx>0 else "left") if abs(dx)>abs(dy)
                        else (("down" if dy>0 else "up") if dy else "still"))
            det.analysis.update(flow)
        burst = float(options.get("burst_ratio", 0))
        ratio = kept/max(1, int(roi.sum()))
        self._recent.append(ratio >= burst if burst > 0 else False)
        frames = max(1, min(60, int(options.get("burst_frames", 3))))
        gap = max(0, min(60, int(options.get("confirm_gap_frames", 0))))
        recent = list(self._recent)[-(frames+gap):]
        if burst > 0 and recent[-1] and sum(recent) >= frames:
            det.motion, det.algorithm, det.region = True, "burst", "Full frame"
            det.ratio = ratio
        wanted = options.get("direction", "any")
        if wanted in ("left", "right", "up", "down") and det.analysis.get("direction") != wanted:
            det.motion = False
        return det

    # ------------------------------------------------------------------
    def _algorithms(self) -> dict:
        algos = self._cfg.get("motion", "algorithms", default={}) or {}
        return {k: v for k, v in algos.items() if isinstance(v, dict) and v.get("enabled", True)}

    def _regions(self) -> list[dict]:
        regions = self._cfg.get("motion", "regions", default=[]) or []
        return [r for r in regions if isinstance(r, dict) and r.get("enabled", True)]

    # ------------------------------------------------------------------
    def _native_detect(self, gray, prev, algos, regions):
        """走 C 内核的检测路径。返回 Detection；不可用时返回 None。"""
        h, w = gray.shape[:2]

        specs = []
        for algo_name, algo in algos.items():
            mag = int(algo.get("magnitude_limit", 15))
            count_limit = float(algo.get("count_limit", 0.01))
            consec = max(1, int(algo.get("consecutive_frames", 2)))
            noise = int(algo.get("noise_filter", 0))
            for region in regions:
                name = region.get("name") or "区域"
                x0 = int(float(region.get("x", 0.0)) * w)
                y0 = int(float(region.get("y", 0.0)) * h)
                x1 = int((float(region.get("x", 0.0)) + float(region.get("w", 1.0))) * w)
                y1 = int((float(region.get("y", 0.0)) + float(region.get("h", 1.0))) * h)
                x0, y0 = max(0, x0), max(0, y0)
                x1 = min(w, max(x1, x0 + 1))
                y1 = min(h, max(y1, y0 + 1))
                key = (algo_name, name)
                specs.append({
                    "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "mag_limit": mag, "noise_k": noise,
                    "count_limit": count_limit, "consecutive": consec,
                    "hit_count": self._hits.get(key, 0),
                    "_key": key, "_algo": algo_name, "_name": name,
                })

        if not specs:
            # 没有启用区域时，ratios 仍要保留各算法的空字典（与 Python 版一致）
            det = Detection()
            det.ratios = {algo_name: {} for algo_name in algos}
            return det

        results = native.detect(gray, prev, w, h, specs)
        if results is None:
            return None

        det = Detection()
        det.ratios = {}
        for spec, r in zip(specs, results):
            algo_name = spec["_algo"]
            name = spec["_name"]
            det.ratios.setdefault(algo_name, {})[name] = round(r.ratio, 5)
            self._hits[spec["_key"]] = r.hit_count

            # 与 Python 版一致：只记录第一个命中的区域的包围盒
            if r.hit and not det.motion:
                det.motion = True
                det.algorithm = algo_name
                det.region = name
                det.ratio = round(r.ratio, 5)
                if r.has_bbox:
                    det.bbox = tuple(r.bbox)
        return det

    # ------------------------------------------------------------------
    def process(self, gray: np.ndarray) -> Detection:
        """喂入一帧灰度图，返回检测结果。"""
        with self._lock:
            if (not self._cfg.get("motion", "enabled", default=True)
                    or time.monotonic() < self._suppress_until):
                # Keep the baseline current while disabled, and discard old
                # consecutive hits so re-enabling starts a fresh sequence.
                self._prev = gray.copy()
                self._hits.clear()
                self._recent.clear()
                self.last = Detection()
                self.frame_count += 1
                self._fps_count += 1
                self._maybe_update_fps()
                return self.last
            prev = self._prev
            if prev is None or prev.shape != gray.shape:
                self._prev = gray.copy()
                self._hits.clear()
                self.last = Detection()
                return self.last

            algos = self._algorithms()
            regions = self._regions()

            # 原生内核优先（结果与下面纯 Python 实现逐位一致）
            if native.available():
                det = self._native_detect(gray, prev, algos, regions)
                if det is not None:
                    det = self._analyze(det, prev, gray)
                    self._prev = gray.copy()
                    self.last = det
                    self.frame_count += 1
                    self._fps_count += 1
                    self._maybe_update_fps()
                    return det

            diff = np.abs(gray.astype(np.int16) - prev.astype(np.int16))
            self._prev = gray.copy()

            det = Detection()
            det.ratios = {}

            for algo_name, algo in algos.items():
                mag = int(algo.get("magnitude_limit", 15))
                count_limit = float(algo.get("count_limit", 0.01))
                consec = max(1, int(algo.get("consecutive_frames", 2)))
                noise = int(algo.get("noise_filter", 0))

                mask = diff > mag
                if noise > 0:
                    k = noise * 2 + 1
                    density = _box_sum(mask, k)
                    # 邻域内至少 1/4 的像素发生变化才算"有效变化"，滤除孤立噪点
                    significant = density >= max(1.0, (k * k) * 0.25)
                else:
                    significant = mask

                det.ratios[algo_name] = {}
                for region in regions:
                    name = region.get("name") or "区域"
                    x0 = int(float(region.get("x", 0.0)) * gray.shape[1])
                    y0 = int(float(region.get("y", 0.0)) * gray.shape[0])
                    x1 = int((float(region.get("x", 0.0)) + float(region.get("w", 1.0))) * gray.shape[1])
                    y1 = int((float(region.get("y", 0.0)) + float(region.get("h", 1.0))) * gray.shape[0])
                    x0, y0 = max(0, x0), max(0, y0)
                    x1 = min(gray.shape[1], max(x1, x0 + 1))
                    y1 = min(gray.shape[0], max(y1, y0 + 1))
                    sub = significant[y0:y1, x0:x1]
                    ratio = float(sub.sum()) / max(1, sub.size)
                    det.ratios[algo_name][name] = round(ratio, 5)

                    key = (algo_name, name)
                    if ratio >= count_limit:
                        self._hits[key] = self._hits.get(key, 0) + 1
                    else:
                        self._hits[key] = 0

                    if self._hits[key] >= consec and not det.motion:
                        det.motion = True
                        det.algorithm = algo_name
                        det.region = name
                        det.ratio = round(ratio, 5)
                        ys, xs = np.nonzero(sub)
                        if ys.size:
                            det.bbox = (x0 + int(xs.min()), y0 + int(ys.min()),
                                        x0 + int(xs.max()), y0 + int(ys.max()))

            # 没有任何命中则清零所有计数
            for key in list(self._hits):
                if det.ratios.get(key[0], {}).get(key[1], 0) < 0:
                    self._hits.pop(key, None)

            det = self._analyze(det, prev, gray)
            self.last = det
            self.frame_count += 1
            self._fps_count += 1
            self._maybe_update_fps()
            return det

    def _maybe_update_fps(self):
        if self._fps_count >= 10:
            el = time.time() - self._fps_mark
            self.detect_fps = round(self._fps_count / el, 1) if el > 0 else 0.0
            self._fps_count = 0
            self._fps_mark = time.time()
