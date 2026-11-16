#!/usr/bin/env python3
"""Real-array parity, concurrency, buffer safety and API compatibility tests."""
from __future__ import annotations

import concurrent.futures
import contextlib
import copy
import io
import math
import os
import queue
import struct
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image

from core import audio, config as config_mod, native
from core.camera import _enqueue_latest
from core.detect import Detector, _box_sum
from core.media_stats import MediaStatsCache, list_media, scan_media
from core.recorder import Recorder
from core.util import dir_size


def reference(cur, prev, spec):
    h, w = cur.shape
    mask = np.abs(cur.astype(np.int16) - prev.astype(np.int16)) > spec["mag_limit"]
    radius = spec["noise_k"]
    if radius > 0:
        k = radius * 2 + 1
        mask = _box_sum(mask, k) >= max(1., k * k * .25)
    x0, y0 = max(0, spec["x0"]), max(0, spec["y0"])
    x1, y1 = min(w, spec["x1"]), min(h, spec["y1"])
    sub = mask[y0:y1, x0:x1]
    ratio = float(np.float32(sub.sum() / sub.size))
    hits = spec["hit_count"] + 1 if ratio >= float(np.float32(spec["count_limit"])) else 0
    ys, xs = np.nonzero(sub)
    bbox = (x0 + int(xs.min()), y0 + int(ys.min()),
            x0 + int(xs.max()), y0 + int(ys.max())) if ys.size else (0, 0, 0, 0)
    return ratio, hits, hits >= spec["consecutive"], bool(ys.size), bbox


@unittest.skipUnless(native.available(), "native backend disabled/unavailable")
class NativeTests(unittest.TestCase):
    def test_detection_matches_reference(self):
        rng = np.random.default_rng(281)
        for h, w in ((1, 1), (7, 11), (19, 31), (180, 320)):
            prev = rng.integers(0, 256, (h, w), dtype=np.uint8)
            for kind in ("still", "random", "sparse"):
                cur = prev.copy() if kind != "random" else rng.integers(0, 256, (h, w), dtype=np.uint8)
                if kind == "sparse":
                    cur[h // 2:, w // 3:] = 0
                specs = []
                for radius in (0, 1, 2, 3, 9):
                    for mag in (0, 12, 28, 255):
                        for i in range(3):
                            x0, y0 = int(rng.integers(0, w)), int(rng.integers(0, h))
                            specs.append(dict(x0=x0, y0=y0, x1=w, y1=h,
                                              mag_limit=mag, noise_k=radius,
                                              count_limit=(0., .006, .5)[i],
                                              consecutive=2, hit_count=i))
                result = native.detect(cur, prev, w, h, specs)
                self.assertIsNotNone(result)
                for spec, got in zip(specs, result):
                    with self.subTest(shape=(h, w), kind=kind, spec=spec):
                        want = reference(cur, prev, spec)
                        self.assertEqual((got.ratio, got.hit_count, got.hit,
                                          got.has_bbox, tuple(got.bbox)), want)

    def test_single_region_local_path(self):
        rng = np.random.default_rng(5)
        cur = rng.integers(0, 256, (40, 60), dtype=np.uint8)
        prev = np.zeros_like(cur)
        for radius in (0, 1, 4):
            spec = dict(x0=-2, y0=-3, x1=25, y1=17, mag_limit=12,
                        noise_k=radius, count_limit=.1, consecutive=2, hit_count=1)
            got = native.detect(cur, prev, 60, 40, [spec])[0]
            self.assertEqual((got.ratio, got.hit_count, got.hit,
                              got.has_bbox, tuple(got.bbox)), reference(cur, prev, spec))

    def test_concurrent_detectors(self):
        def run(seed):
            rng = np.random.default_rng(seed)
            h, w = 29 + seed, 47 + seed
            prev = rng.integers(0, 256, (h, w), dtype=np.uint8)
            cur = rng.integers(0, 256, (h, w), dtype=np.uint8)
            specs = [dict(x0=i, y0=i, x1=w, y1=h, mag_limit=80,
                          noise_k=2, count_limit=.01, consecutive=2, hit_count=1)
                     for i in range(3)]
            for _ in range(30):
                got = native.detect(cur, prev, w, h, specs)
                for spec, item in zip(specs, got):
                    self.assertEqual((item.ratio, item.hit_count, item.hit,
                                      item.has_bbox, tuple(item.bbox)), reference(cur, prev, spec))
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(run, range(6)))

    def test_strided_images_and_invalid_layouts(self):
        rng = np.random.default_rng(9)
        rgb = rng.integers(0, 256, (50, 80, 3), dtype=np.uint8)[::-1, ::2]
        self.assertFalse(rgb.flags.c_contiguous)
        self.assertTrue(np.array_equal(native.gray_ds(rgb, 40, 50, 20, 25),
                                      native.gray_ds(rgb.copy(), 40, 50, 20, 25)))
        self.assertEqual(native.jpeg(rgb, 40, 50, 72), native.jpeg(rgb.copy(), 40, 50, 72))
        self.assertIsNone(native.jpeg(rgb, 41, 50, 72))
        self.assertIsNone(native.gray_ds(rgb.astype(np.float32), 40, 50, 20, 25))
        self.assertIsNone(native.detect(rgb[:, :, 0], rgb[:, :, 0], 41, 50, []))
        spec = dict(x0=0, y0=0, x1=40, y1=50, mag_limit=1,
                    noise_k=1, count_limit=.1, consecutive=1, hit_count=0)
        gray = rgb[:, :, 0]
        got = native.detect(gray, np.zeros_like(gray), 40, 50, [spec])[0]
        self.assertEqual(got.ratio, reference(gray, np.zeros_like(gray), spec)[0])

    def test_jpeg_overflow_and_retry(self):
        rgb = np.random.default_rng(14).integers(0, 256, (256, 256, 3), dtype=np.uint8)
        guarded = np.full(48, 77, dtype=np.uint8)
        size = native._load().pkc_jpeg(native._ptr(rgb), 256, 256, 100,
                                      native._ptr(guarded), 16)
        self.assertLess(size, 0)
        self.assertTrue(np.all(guarded[16:] == 77), "C encoder wrote past capacity")
        data = native.jpeg(rgb, 256, 256, 100)
        self.assertIsNotNone(data)
        self.assertGreater(len(data), 256 * 256 * 3 // 2 + 4096)
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            self.assertEqual(im.size, (256, 256))

    def test_detector_matches_python_over_sequence(self):
        class Config:
            def get(self, *keys, default=None):
                return copy.deepcopy({"algorithms": {
                    "far": dict(enabled=True, magnitude_limit=12, noise_filter=2,
                                count_limit=.006, consecutive_frames=2),
                    "near": dict(enabled=True, magnitude_limit=28, noise_filter=3,
                                 count_limit=.02, consecutive_frames=3)},
                    "regions": [dict(name=str(i), enabled=True, x=i / 10, y=i / 10,
                                     w=.5, h=.5) for i in range(4)]}.get(keys[1], default))
        fast, slow = Detector(Config()), Detector(Config())
        rng = np.random.default_rng(28)
        base = np.zeros((40, 60), dtype=np.uint8)
        frames = [base, base, rng.integers(0, 256, base.shape, dtype=np.uint8), base, base, base]
        for frame in frames:
            got = fast.process(frame)
            with patch.object(native, "available", return_value=False):
                want = slow.process(frame)
            self.assertEqual(got, want)
        fast.reset()
        self.assertFalse(fast.process(base).motion)


class DetectorControlTests(unittest.TestCase):
    def test_motion_disable_clears_hits_and_resumes_with_fresh_frames(self):
        for force_python in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                config = config_mod.Config(Path(directory) / "config.json")
                config.set({"motion": {"enabled": True, "algorithms": {
                    "far": {"enabled": True, "count_limit": 0,
                            "consecutive_frames": 2}, "near": {"enabled": False}}}})
                detector = Detector(config)
                frame = np.zeros((24, 32), dtype=np.uint8)
                backend = (patch.object(native, "available", return_value=False)
                           if force_python else contextlib.nullcontext())
                with backend:
                    self.assertFalse(detector.process(frame).motion)
                    self.assertFalse(detector.process(frame).motion)
                    self.assertTrue(detector.process(frame).motion)
                    config.set({"motion": {"enabled": False}})
                    frame[:] = 255
                    self.assertFalse(detector.process(frame).motion)
                    self.assertEqual(detector._hits, {})
                    self.assertTrue(np.array_equal(detector._prev, frame))
                    config.set({"motion": {"enabled": True}})
                    self.assertFalse(detector.process(frame).motion)
                    self.assertTrue(detector.process(frame).motion)


class AudioAndQueueTests(unittest.TestCase):
    def test_frame_rate_counts_intervals_after_delayed_start(self):
        for fps in (2, 8, 10, 30):
            rec = Recorder.__new__(Recorder)
            rec.config = types.SimpleNamespace(get=lambda *keys, default=None: (
                True if keys == ("record", "paused") else fps))
            rec._rate_frames, rec._rate_mark, rec._rate_fps = 0, 0., 0.
            rec._in_event = rec._loop_active = False
            rec._proc = rec._loop_proc = None
            for i in range(fps * 7):
                rec.on_frame(b"", 1000. + i / fps)
            self.assertAlmostEqual(rec._rate_fps, fps, places=6)
            self.assertEqual(rec._video_fps(), fps)

    def test_rms_matches_scalar_and_fallback(self):
        cap = audio.AudioCapture(None)
        rng = np.random.default_rng(29)
        cases = [b"", b"x", b"\x00\x00" * 50, struct.pack("<h", -32768) * 50,
                 rng.integers(-32768, 32768, 24000, dtype=np.int16).astype("<i2").tobytes() + b"x"]
        for data in cases:
            samples = [v for (v,) in struct.iter_unpack("<h", data[:len(data) // 2 * 2])]
            rms = math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0
            want = round((max(-60., min(0., 20 * math.log10(rms / 32768))) + 60) / 60, 3) if rms else 0.
            self.assertEqual(cap._rms_level(data), want)
            with patch.object(audio, "np", None):
                self.assertEqual(cap._rms_level(data), want)

    def test_full_queue_keeps_newest_frame(self):
        q = queue.Queue(maxsize=2)
        for frame in (b"oldest", b"older", b"newest"):
            _enqueue_latest(q, frame)
        self.assertEqual([q.get_nowait(), q.get_nowait()], [b"older", b"newest"])


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("videos", "stills", "loop", "timelapse/frames"):
            (self.root / name).mkdir(parents=True)
        (self.root / "videos/a.mp4").write_bytes(b"v" * 11)
        (self.root / "stills/a.jpg").write_bytes(b"s" * 7)
        (self.root / "loop/a.mp4").write_bytes(b"l" * 19)
        (self.root / "timelapse/frames/a.jpg").write_bytes(b"t" * 5)

    def test_single_scan_matches_fresh_quota_and_counts(self):
        self.assertEqual(scan_media(self.root), dict(disk_bytes=42, videos=1, stills=1))
        self.assertEqual(dir_size(self.root), 42)
        (self.root / "loop/a.mp4").write_bytes(b"l" * 30)
        self.assertEqual(dir_size(self.root), 53, "Quota must never use cached sizes")

    def test_cache_expiry_invalidation_and_isolation(self):
        cache = MediaStatsCache(3)
        with patch("core.media_stats.time.monotonic", return_value=100):
            first = cache.snapshot(self.root)
            first["disk_bytes"] = -1
            (self.root / "videos/b.mp4").write_bytes(b"x" * 10)
            self.assertEqual(cache.snapshot(self.root)["disk_bytes"], 42)
        with patch("core.media_stats.time.monotonic", return_value=104):
            self.assertEqual(cache.snapshot(self.root)["disk_bytes"], 52)
        cache.invalidate()
        self.assertEqual(cache.snapshot(self.root)["videos"], 2)
        self.assertEqual(cache.snapshot(self.root / "missing"), dict(disk_bytes=0, videos=0, stills=0))

    def test_cache_coalesces_concurrent_readers(self):
        cache = MediaStatsCache(30)
        barrier = threading.Barrier(6)
        def read(_):
            barrier.wait()
            return cache.snapshot(self.root)
        with patch("core.media_stats.scan_media", wraps=scan_media) as scan:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(read, range(6)))
            self.assertEqual(scan.call_count, 1)
            self.assertTrue(all(r["disk_bytes"] == 42 for r in results))

    def test_replaced_mount_directory_invalidates_cache(self):
        cache = MediaStatsCache(30)
        self.assertEqual(cache.snapshot(self.root / "loop")["disk_bytes"], 19)
        (self.root / "loop").rename(self.root / "old-loop")
        (self.root / "loop").mkdir()
        self.assertEqual(cache.snapshot(self.root / "loop")["disk_bytes"], 0)

    def test_symlink_cycle_and_missing_files(self):
        (self.root / "loop/back").symlink_to(self.root, target_is_directory=True)
        (self.root / "stills/broken.jpg").symlink_to(self.root / "does-not-exist")
        self.assertEqual(scan_media(self.root)["disk_bytes"], 42)
        self.assertEqual(list_media(self.root / "stills", ".jpg")[0]["name"], "a.jpg")
        self.assertEqual(list_media(self.root / "missing", ".jpg"), [])

    def test_persisted_pause_overrides_initial_runtime_state(self):
        from tools.test_web_v270 import Service
        from core.web import create_app
        with patch.object(config_mod, "ROOT_DIR", self.root):
            service = Service(self.root)
            client = create_app(service).test_client()
            for paused in (True, False):
                service.config.set({"record": {"paused": paused}})
                service.state.update(record_paused=not paused)
                state = client.get("/api/state").get_json()
                self.assertEqual(state["record_paused"], paused)
                self.assertEqual(state["record"]["paused"], paused)

    def test_api_schema_cache_and_write_invalidation(self):
        from tools.test_web_v270 import Service
        from core.web import create_app
        with patch.object(config_mod, "ROOT_DIR", self.root):
            service = Service(self.root)
            service.config.ensure_dirs()
            (service.config.media_sub("videos") / "one.mp4").write_bytes(b"x")
            client = create_app(service).test_client()
            state = client.get("/api/state").get_json()
            for key in ("media", "loop", "record", "audio", "release", "version"):
                self.assertIn(key, state)
            self.assertEqual(state["media"]["videos"], 1)
            (service.config.media_sub("videos") / "two.mp4").write_bytes(b"xx")
            self.assertEqual(client.get("/api/state").get_json()["media"]["videos"], 1)
            client.post("/api/record", json={"action": "on"})
            self.assertEqual(client.get("/api/state").get_json()["media"]["videos"], 2)
            files = client.get("/api/videos").get_json()
            self.assertEqual(len(files), 2)
            self.assertEqual(set(files[0]), {"name", "size", "size_h", "mtime"})
            service.config.set({"web": {"password_hash": config_mod.hash_password("test-pass")}})
            self.assertEqual(client.get("/api/config").status_code, 401)
            self.assertEqual(client.get("/login").status_code, 200)
            for asset in ("/static/style.css", "/static/i18n.js"):
                with client.get(asset) as response:
                    self.assertEqual(response.status_code, 200)
            self.assertEqual(client.post("/api/auth/login", json={"password": "test-pass"}).status_code, 200)
            self.assertEqual(client.get("/api/config").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
