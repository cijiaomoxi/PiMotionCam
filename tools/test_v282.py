#!/usr/bin/env python3
"""v2.8.2 behavior and integration tests; all hardware-independent."""

from __future__ import annotations
import io
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from PIL import Image
from core import audio
from core.app import AppService
from core.audio_recording import AudioRecorder
from core.camera import V4L2Backend, Camera, _v4l2_devices
from core.config import Config
from core.control import ControlServer, packet, sign_message, allowed_command
from core.detect import Detector
from core.detection_journal import DetectionJournal
from core.extended_web import validate_patch
from core.media_tools import (
    next_name,
    safe_path,
    verified_copy,
    archive_event,
    archive_calendar,
)
from core.motion_analysis import motion_vectors
from core.presets import Presets
from core.recorder import Recorder, _mp4_has_moov
from core.scheduler import Scheduler
from core.servo import Servo
from core.solar import solar_times, scheduled_time
from core.state import RuntimeState
from core.video_processing import VideoProcessor, EFFECTS, image_effect
from core.web import create_app


class LocalConfig(Config):
    def internal_media_dir(self):
        return self.path.parent / "media"

    def ensure_dirs(self):
        for name in ("videos", "stills", "timelapse", "audio"):
            self.media_sub(name).mkdir(parents=True, exist_ok=True)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = LocalConfig(self.root / "config.json")
        self.cfg.ensure_dirs()
        self.state = RuntimeState()

    def tearDown(self):
        self.tmp.cleanup()


class AudioTests(Case):
    def test_monitoring_does_not_enable_audio_in_video_recordings(self):
        rec = Recorder(self.cfg, self.state, audio=types.SimpleNamespace(running=True))
        self.assertFalse(rec._audio_enabled())
        self.cfg.set({"record": {"audio_enabled": True}})
        self.assertTrue(rec._audio_enabled())

    def test_audio_only_mp3_is_decodable_and_releases_capture(self):
        releases = []
        pcm = (
            (np.sin(np.arange(1600) * 2 * np.pi * 440 / 16000) * 1000)
            .astype("<i2")
            .tobytes()
        )
        capture = types.SimpleNamespace(
            status=lambda: {"rate": 16000, "channels": 1},
            live_pcm=lambda **kw: (pcm for _ in range(10)),
        )
        self.cfg.set({"record": {"min_free_gb": 0}})
        service = types.SimpleNamespace(
            config=self.cfg,
            acquire_audio=lambda kind: (capture, lambda: releases.append(True)),
        )
        recorder = AudioRecorder(service)
        recorder.start(10)
        recorder._thread.join(3)
        self.assertFalse(recorder.status()["recording"])
        self.assertFalse(recorder.status()["error"])
        self.assertEqual(releases, [True])
        path = self.cfg.media_sub("audio") / recorder.status()["file"]
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            check=True,
        )
        self.assertAlmostEqual(
            float(json.loads(result.stdout)["format"]["duration"]), 1, delta=0.1
        )

    def test_sound_trigger_holds_threshold_and_respects_pause(self):
        svc = AppService.__new__(AppService)
        svc.config = self.cfg
        svc._sound_started = None
        svc._sound_last = 0.0
        calls = []
        svc.recorder = types.SimpleNamespace(trigger=lambda *args: calls.append(args))
        self.cfg.set(
            {"record": {"audio_trigger_enabled": True, "audio_trigger_seconds": 0.3}}
        )
        with mock.patch(
            "core.app.time.monotonic", side_effect=[100, 100.2, 100.4, 101.5]
        ):
            for _ in range(4):
                svc._sound_level(0.8)
        self.assertEqual(calls, [(2, "audio"), (2, "audio")])
        self.cfg.set({"record": {"paused": True}})
        svc._sound_level(0.9)
        self.assertEqual(len(calls), 2)

    def test_gain_clips_and_fallback_matches(self):
        pcm = struct.pack("<5h", -32768, -1000, 0, 1000, 32767)
        self.assertIs(audio.apply_gain(pcm, 0), pcm)
        expected = struct.unpack("<5h", audio.apply_gain(pcm, 6))
        self.assertEqual(expected[0], -32768)
        self.assertEqual(expected[-1], 32767)
        with mock.patch.object(audio, "np", None):
            self.assertEqual(audio.apply_gain(pcm, 6), struct.pack("<5h", *expected))

    def test_capture_timestamps_are_in_seconds(self):
        cap = audio.AudioCapture(None)
        pcm = b"\x01\x00" * 1600
        reads = iter((pcm, b""))

        def read(n):
            value = next(reads)
            if not value:
                cap._stop.set()
            return value

        proc = types.SimpleNamespace(
            stdout=types.SimpleNamespace(read=read), poll=lambda: 0
        )
        with mock.patch.object(
            audio.subprocess, "Popen", return_value=proc
        ), mock.patch.object(audio.time, "time", return_value=10.0):
            cap._run(types.SimpleNamespace(plug_id="test"))
        self.assertAlmostEqual(cap._chunks[0][0], 9.9)
        self.assertEqual(len(cap.slice_wav(9.9, 10.0)) - 44, len(pcm))

    def test_live_stream_starts_fresh_and_stop_wakes_readers(self):
        cap = audio.AudioCapture(None)
        cap._stop.clear()
        cap._push(b"old", 1.0)
        output = []
        stream = cap.live_pcm(0.5)
        ready = threading.Event()

        def reader():
            ready.set()
            output.extend(stream)

        thread = threading.Thread(target=reader)
        thread.start()
        ready.wait(1)
        # Wait for the generator to enter its condition, not a guessed delay.
        deadline = time.monotonic() + 1
        while not cap._live_condition._waiters and time.monotonic() < deadline:
            time.sleep(0.001)
        cap._push(b"new", 2.0)
        deadline = time.monotonic() + 1
        while output != [b"new"] and time.monotonic() < deadline:
            time.sleep(0.001)
        cap.stop()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(output, [b"new"])

    def test_slow_listener_memory_is_bounded(self):
        cap = audio.AudioCapture(None)
        for index in range(100):
            cap._push(b"\0\0" * 10, index)
        self.assertEqual(len(cap._live), 8)

    def test_listeners_share_capture_and_last_release_stops_it(self):
        svc = AppService.__new__(AppService)
        svc.config = self.cfg
        svc.state = self.state
        svc._audio_control_lock = threading.RLock()
        svc._audio_consumers = {}
        svc._audio_accepting = True
        svc.log = lambda *a: None
        svc._audio_prefer_port = lambda: ""
        active = types.SimpleNamespace(running=False, _thread=None)
        calls = []

        def start(**kw):
            active.running = True
            calls.append("start")
            return {"state": "running"}

        def stop():
            active.running = False
            calls.append("stop")

        active.start = start
        active.stop = stop
        active.status = lambda: {"state": "running" if active.running else "idle"}
        svc.audio = active
        self.cfg.set({"record": {"audio_stream_enabled": True}})
        _, first = svc.acquire_audio()
        _, second = svc.acquire_audio()
        self.assertEqual(calls, ["start"])
        first()
        self.assertTrue(active.running)
        second()
        second()
        self.assertEqual(calls, ["start", "stop"])
        self.cfg.set({"record": {"audio_stream_enabled": False}})
        with self.assertRaises(PermissionError):
            svc.acquire_audio()


class TransformTests(Case):
    def test_metadata_nodes_are_not_offered_as_cameras(self):
        def run(cmd, **kwargs):
            if cmd == ["v4l2-ctl", "--list-devices"]:
                return types.SimpleNamespace(
                    stdout=b"USB Camera:\n\t/dev/video1\n\t/dev/video2\n", returncode=0
                )
            return types.SimpleNamespace(returncode=0 if "/dev/video1" in cmd else 1)

        with mock.patch(
            "core.camera.shutil.which", return_value="/usr/bin/v4l2-ctl"
        ), mock.patch("core.camera.subprocess.run", side_effect=run):
            self.assertEqual([d["id"] for d in _v4l2_devices()], ["/dev/video1"])

    def test_usb_libcamera_alias_prefers_matching_v4l2_port(self):
        self.cfg.set({"camera": {"device": "1"}})
        camera = Camera.__new__(Camera)
        camera.config = self.cfg
        cameras = [
            {
                "index": 1,
                "id": "/base/usb@0,0-1.1:1.0-0bda",
                "type": "usb",
                "backend": "libcamera",
            },
            {
                "index": 2,
                "id": "/dev/video1",
                "device": "/dev/video1",
                "type": "usb",
                "backend": "v4l2",
            },
        ]
        with mock.patch("core.camera.list_cameras", return_value=cameras), mock.patch(
            "core.audio.video_usb_port", return_value="1.1"
        ):
            backend, chosen = camera._resolve_device()
            self.assertEqual(backend, "v4l2")
            self.assertEqual(chosen["device"], "/dev/video1")

    def test_independent_still_restores_capture_after_failure(self):
        camera = Camera.__new__(Camera)
        camera.config = self.cfg
        camera.state = self.state
        calls = []
        camera.stop = lambda: calls.append("stop")
        camera.start = lambda: calls.append("start")
        camera.recorder = types.SimpleNamespace(
            stop=lambda: calls.append("close recording")
        )
        camera.detector = types.SimpleNamespace(reset=lambda: calls.append("reset"))
        camera._resolve_device = lambda: ("libcamera", {"index": 0})
        with mock.patch(
            "core.camera.shutil.which", return_value="/usr/bin/rpicam-still"
        ), mock.patch(
            "core.camera.subprocess.run",
            return_value=types.SimpleNamespace(
                returncode=1, stdout=b"", stderr=b"unsupported size"
            ),
        ):
            with self.assertRaises(RuntimeError):
                camera.high_resolution_still([2592, 1944])
        self.assertEqual(calls, ["stop", "close recording", "reset", "start"])

    def test_usb_all_transforms_match_raw_csi_pixels(self):
        # Real ffmpeg decode/filter/encode, with unequal colored quadrants.
        im = np.zeros((48, 64, 3), dtype=np.uint8)
        im[:24, :32] = [240, 20, 20]
        im[:24, 32:] = [20, 240, 20]
        im[24:, :32] = [20, 20, 240]
        im[24:, 32:] = [230, 230, 20]
        buf = io.BytesIO()
        Image.fromarray(im).save(buf, "JPEG", quality=98)
        for rotation in (0, 90, 180, 270):
            for flip in ("none", "horizontal", "vertical", "both"):
                backend = V4L2Backend("/dev/fake", 64, 48, 10, rotation, flip, 90)
                args = backend.output_args()
                if rotation == 0 and flip == "none":
                    self.assertEqual(args, ["-c:v", "copy"])
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "image2pipe",
                        "-c:v",
                        "mjpeg",
                        "-i",
                        "-",
                        "-frames:v",
                        "1",
                        *args,
                        "-f",
                        "image2pipe",
                        "-",
                    ],
                    input=buf.getvalue(),
                    capture_output=True,
                    check=True,
                )
                image = np.asarray(Image.open(io.BytesIO(result.stdout)))
                expected = np.rot90(im, rotation // 90)
                if flip in ("horizontal", "both"):
                    expected = np.flip(expected, 1)
                if flip in ("vertical", "both"):
                    expected = np.flip(expected, 0)
                self.assertEqual((image.shape[1], image.shape[0]), backend.output_size)
                for y, x in ((0.25, 0.25), (0.25, 0.75), (0.75, 0.25), (0.75, 0.75)):
                    yy, xx = int(y * image.shape[0]), int(x * image.shape[1])
                    self.assertLess(
                        np.abs(image[yy, xx].astype("i2") - expected[yy, xx]).max(),
                        25,
                        (rotation, flip),
                    )

    def test_effects_are_real_and_dimensions_are_preserved(self):
        rng = np.random.default_rng(44)
        im = Image.fromarray(rng.integers(0, 256, (48, 64, 3), dtype="u1"))
        for effect in EFFECTS:
            changed = image_effect(im, effect)
            self.assertEqual(changed.size, im.size, effect)
            if effect != "none":
                self.assertFalse(
                    np.array_equal(np.asarray(changed), np.asarray(im)), effect
                )

    def test_processing_off_is_zero_copy_and_annotation_is_optional(self):
        buf = io.BytesIO()
        Image.new("RGB", (320, 180), "green").save(buf, "JPEG")
        jpeg = buf.getvalue()
        processor = VideoProcessor(self.cfg)
        self.assertIs(processor.transform(jpeg), jpeg)
        self.assertIs(processor.annotate(jpeg, {}), jpeg)
        self.cfg.set(
            {"web": {"burn_in": {"enabled": True, "text": "Test", "vu_meter": True}}}
        )
        result = processor.annotate(jpeg, {"audio_level": 0.8})
        self.assertNotEqual(result, jpeg)
        self.assertEqual(Image.open(io.BytesIO(result)).size, (320, 180))


class MotionTests(Case):
    def test_burst_obeys_enabled_regions(self):
        self.cfg.set(
            {
                "motion": {
                    "regions": [
                        {
                            "name": "small",
                            "x": 0.25,
                            "y": 0.25,
                            "w": 0.25,
                            "h": 0.25,
                            "enabled": True,
                        }
                    ],
                    "algorithms": {
                        "far": {"enabled": False},
                        "near": {"enabled": False},
                    },
                    "analysis": {
                        "enabled": True,
                        "vectors": False,
                        "burst_ratio": 0.1,
                        "burst_frames": 1,
                    },
                }
            }
        )
        detector = Detector(self.cfg)
        a = np.zeros((40, 40), dtype="u1")
        b = a.copy()
        b[:5, :5] = 255
        detector.process(a)
        self.assertFalse(detector.process(b).motion)
        c = b.copy()
        c[12:18, 12:18] = 255
        self.assertTrue(detector.process(c).motion)
        self.cfg.set({"motion": {"regions": []}}, replace=False)
        self.assertFalse(detector.process(a).motion)

    def test_vectors_follow_object_translation(self):
        rng = np.random.default_rng(42)
        a = np.zeros((72, 96), dtype="u1")
        a[20:52, 24:64] = rng.integers(40, 255, (32, 40), dtype="u1")
        for dx, dy, expected in (
            (3, 0, "right"),
            (-3, 0, "left"),
            (0, 3, "down"),
            (0, -3, "up"),
        ):
            b = np.roll(a, (dy, dx), (0, 1))
            result = motion_vectors(a, b)
            self.assertEqual(result["direction"], expected)
            self.assertTrue(result["vectors"])
        self.assertEqual(motion_vectors(a, a)["direction"], "still")

    def test_burst_and_suppression_respect_master_switch(self):
        self.cfg.set(
            {
                "motion": {
                    "algorithms": {
                        "far": {"enabled": False},
                        "near": {"enabled": False},
                    },
                    "analysis": {
                        "enabled": True,
                        "vectors": False,
                        "burst_ratio": 0.1,
                        "burst_frames": 2,
                        "confirm_gap_frames": 1,
                    },
                }
            }
        )
        detector = Detector(self.cfg)
        frames = [np.zeros((24, 32), dtype="u1"), np.full((24, 32), 255, dtype="u1")]
        detector.process(frames[0])
        self.assertFalse(detector.process(frames[1]).motion)
        self.assertTrue(detector.process(frames[0]).motion)
        detector.suppress(10)
        self.assertFalse(detector.process(frames[1]).motion)
        self.cfg.set({"motion": {"enabled": False}})
        detector._suppress_until = 0
        self.assertFalse(detector.process(frames[0]).motion)

    def test_statistics_are_bounded_and_fifo_without_reader_never_blocks(self):
        self.cfg.set(
            {"motion": {"output": {"csv": True, "events": True, "fifo": True}}}
        )
        detector = Detector(self.cfg)
        journal = DetectionJournal(self.cfg)
        journal.publish(detector.last)
        journal._queue.join()
        self.assertTrue((self.root / "logs/motion.csv").is_file())
        self.assertTrue((self.root / "logs/motion.fifo").exists())


class MediaTests(Case):
    def test_names_persist_and_reject_paths(self):
        a = next_name(self.cfg, "still", ".jpg")
        b = next_name(LocalConfig(self.cfg.path), "still", ".jpg")
        self.assertNotEqual(a, b)
        self.assertTrue(b.endswith("_000002.jpg"))
        self.cfg.set({"record": {"name_template": "../{seq}"}})
        with self.assertRaises(ValueError):
            next_name(self.cfg, "still", ".jpg")
        with self.assertRaises(ValueError):
            safe_path(self.root, "../private")

    def test_verified_copy_keeps_existing_different_file(self):
        src = self.root / "source"
        out = self.root / "archive/out"
        src.write_bytes(b"new")
        verified_copy(src, out)
        self.assertEqual(out.read_bytes(), b"new")
        src.write_bytes(b"other")
        with self.assertRaises(FileExistsError):
            verified_copy(src, out)
        self.assertEqual(out.read_bytes(), b"new")
        self.assertFalse(list(out.parent.glob(".copy-*")))

    def test_calendar_publishes_after_verified_copy_and_checks_space_and_mount(self):
        video = self.cfg.media_sub("videos") / "event.mp4"
        video.write_bytes(b"video")
        entry = {
            "id": "event",
            "video": video.name,
            "start": datetime(2026, 11, 16, 10).timestamp(),
        }
        self.cfg.set({"media": {"archive_target": str(self.root / "archive")}})
        result = archive_event(self.cfg, entry)
        self.assertTrue(result["verified"])
        self.assertEqual(archive_calendar(self.cfg, "2026-11-16")[0]["id"], "event")
        self.cfg.set({"media": {"archive_require_mount": True}})
        with self.assertRaises(OSError):
            archive_event(self.cfg, entry)
        self.cfg.set(
            {"media": {"archive_require_mount": False, "archive_min_free_percent": 100}}
        )
        with self.assertRaises(OSError):
            archive_event(self.cfg, entry)

    def test_manual_recording_runs_while_automatic_recording_is_paused(self):
        self.cfg.set(
            {
                "record": {
                    "paused": True,
                    "min_free_gb": 0,
                    "encoder": "libx264",
                    "pre_seconds": 0,
                },
                "camera": {"fps": 5},
            }
        )
        rec = Recorder(self.cfg, self.state)
        data = io.BytesIO()
        Image.new("RGB", (64, 48), "green").save(data, "JPEG")
        rec.manual(True, 10)
        start = time.time()
        for index in range(6):
            rec.on_frame(data.getvalue(), start + index / 5)
        rec.manual(False)
        self.assertTrue(self.cfg.get("record", "paused"))
        self.assertEqual(len(rec.events), 1)
        event = rec.events[0]
        self.assertEqual(event["algorithm"], "manual")
        self.assertTrue(_mp4_has_moov(self.cfg.media_sub("videos") / event["video"]))
        self.assertFalse(self.state.get("manual_recording"))


class SchedulingTests(Case):
    def test_solar_table_and_polar_day(self):
        times = solar_times(date(2026, 6, 21), 31.23, 121.47, "Asia/Shanghai")
        sunrise = times["sunrise"]
        self.assertTrue(4 * 60 + 45 < sunrise.hour * 60 + sunrise.minute < 5 * 60 + 10)
        self.assertLess(times["dawn"], times["sunrise"])
        self.assertLess(times["sunset"], times["dusk"])
        self.assertIsNone(solar_times(date(2026, 6, 21), 80, 0, "UTC")["sunrise"])
        self.assertEqual(
            scheduled_time(
                "sunset-30",
                date(2026, 6, 21),
                {"latitude": 31.23, "longitude": 121.47, "timezone": "Asia/Shanghai"},
            ),
            times["sunset"] - timedelta(minutes=30),
        )

    def test_interval_crosses_midnight_and_weekdays_are_applied(self):
        calls = []
        scheduler = Scheduler(
            self.cfg, calls.append, fifo_path=self.root / "commands.fifo"
        )
        self.cfg.set(
            {"schedules": [{"interval_minutes": 30, "days": "Mon", "command": "still"}]}
        )
        scheduler.reload()
        scheduler._tick(
            datetime(2026, 11, 16, 23, 50, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        scheduler._tick(datetime(2026, 11, 17, 0, 25, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(calls, ["still"])
        self.cfg.set({"schedules": [{"interval_minutes": 30, "command": "still"}]})
        scheduler.reload()
        scheduler._tick(datetime(2026, 11, 17, 0, 25, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(calls, ["still", "still"])

    def test_web_cannot_forge_local_shell_source(self):
        scheduler = Scheduler(
            self.cfg, lambda c: "unknown command: " + c, fifo_path=self.root / "fifo"
        )
        scheduler.save_entry(
            {
                "command": "echo injected",
                "source": "fake",
                "_trusted_local": True,
                "interval_minutes": 1,
            }
        )
        self.assertNotIn("source", self.cfg.get("schedules")[0])
        self.assertNotIn("_trusted_local", self.cfg.get("schedules")[0])
        with mock.patch(
            "core.scheduler.run_command",
            side_effect=AssertionError("shell must not run"),
        ):
            scheduler._tick()

    def test_fifo_can_stop_without_a_writer(self):
        scheduler = Scheduler(self.cfg, lambda c: c, fifo_path=self.root / "fifo")
        scheduler.start()
        scheduler.stop()
        self.assertFalse(scheduler._fifo_thread.is_alive())

    def test_preset_copy_move_and_activation_settle(self):
        calls = []
        presets = Presets(
            self.cfg, self.state, on_activate=lambda: calls.append("settle")
        )
        presets.save("A", {"camera": {"rotation": 90}, "motion": {"enabled": False}})
        presets.transfer("A", "B")
        presets.transfer("B", "C", True)
        self.assertNotIn("B", presets.list())
        self.assertEqual(presets.get("C"), presets.get("A"))
        presets.activate("C")
        self.assertEqual(calls, ["settle"])
        self.assertEqual(self.cfg.get("camera", "rotation"), 90)

    def test_servo_inversion_steps_and_bound_preset(self):
        servo = Servo(
            self.cfg, self.state, on_preset=lambda n: self.state.set("chosen", n)
        )
        self.cfg.set(
            {
                "servo": {
                    "pan_invert": True,
                    "positions": [
                        {"name": "here", "pan": 179, "tilt": 90, "preset": "night"}
                    ],
                }
            }
        )
        self.state.set("servo_enabled", True)
        servo._backend = "rpi"
        outputs = []
        servo._pwms = {"pan": types.SimpleNamespace(ChangeDutyCycle=outputs.append)}
        servo.goto("here")
        servo.step("pan", 1, True)
        self.assertEqual(self.state.get("chosen"), "night")
        self.assertEqual(servo._current["pan"], 180)
        self.assertAlmostEqual(outputs[-1], 2.5)


class ControlTests(Case):
    def setUp(self):
        super().setUp()
        self.secret = "a-test-secret-that-is-long"
        self.cfg.set(
            {"network": {"secret": self.secret, "tcp_enabled": True, "tcp_port": 0}}
        )
        self.calls = []
        self.control = ControlServer(self.cfg, self.calls.append)

    def tearDown(self):
        self.control.stop()
        super().tearDown()

    def test_signed_command_ack_and_replay_rejection(self):
        msg = packet(self.secret, "motion trigger 2")
        raw = json.dumps(msg).encode()
        ack = self.control.dispatch(raw, "127.0.0.1")
        self.assertEqual(self.calls, ["motion trigger 2"])
        self.assertEqual(ack["reply_to"], msg["id"])
        self.assertEqual(ack["signature"], sign_message(ack, self.secret))
        with self.assertRaises(PermissionError):
            self.control.dispatch(raw, "127.0.0.1")
        with self.assertRaises(PermissionError):
            self.control.dispatch(
                json.dumps(packet(self.secret, "restart")).encode(), "127.0.0.1"
            )
        with self.assertRaises(PermissionError):
            self.control.dispatch(
                json.dumps(packet(self.secret, "still")).encode(), "192.0.2.1"
            )
        self.assertFalse(allowed_command("still; echo bad"))

    @unittest.skipIf(
        os.environ.get("PMC_TEST_NO_NETWORK") == "1",
        "network transport disabled for this test run",
    )
    def test_real_tcp_roundtrip(self):
        self.control.start()
        self.assertFalse(self.control.error)
        with socket.create_connection(self.control.tcp_address, timeout=2) as conn:
            conn.sendall(json.dumps(packet(self.secret, "still")).encode() + b"\n")
            result = json.loads(conn.makefile("rb").readline())
        self.assertEqual(result["type"], "ack")
        self.assertEqual(self.calls, ["still"])

    def test_invalid_types_and_times_are_rejected(self):
        for value in ([], {"time": float("nan")}):
            value = (
                value
                if isinstance(value, list)
                else packet(self.secret, "still", **value)
            )
            with self.assertRaises((ValueError, PermissionError)):
                self.control.dispatch(json.dumps(value).encode(), "127.0.0.1")


class WebTests(Case):
    def setUp(self):
        super().setUp()
        self.service = types.SimpleNamespace(config=self.cfg, state=self.state)
        self.client = create_app(self.service).test_client()

    def test_new_routes_respect_password_guard(self):
        from core.config import hash_password

        self.cfg.set({"web": {"password_hash": hash_password("test")}})
        for url in (
            "/api/audio/stream",
            "/api/audio/record",
            "/api/archive/calendar",
            "/api/solar",
            "/api/camera/profile",
        ):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_live_audio_gate_and_headers_release(self):
        releases = []
        self.cfg.set({"record": {"audio_stream_enabled": True}})
        capture = types.SimpleNamespace(
            status=lambda: {"rate": 16000, "channels": 1},
            live_pcm=lambda **kw: (data for data in (b"\0\0", b"\1\0")),
        )
        self.service.acquire_audio = lambda kind: (capture, lambda: releases.append(1))
        response = self.client.get("/api/audio/stream")
        self.assertEqual(response.headers["X-Audio-Format"], "s16le")
        self.assertEqual(response.data, b"\0\0\1\0")
        response.close()
        self.assertTrue(releases)
        self.assertEqual(
            self.client.get(
                "/api/audio/stream", headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code,
            403,
        )

    def test_stream_can_be_disabled_during_recording(self):
        releases = []
        self.cfg.set({"record": {"audio_stream_enabled": True}})

        def chunks(**kw):
            yield b"\0\0"
            self.cfg.set({"record": {"audio_stream_enabled": False}})
            yield b"\1\0"

        capture = types.SimpleNamespace(
            status=lambda: {"rate": 16000, "channels": 1}, live_pcm=chunks
        )
        self.service.acquire_audio = lambda kind: (capture, lambda: releases.append(1))
        response = self.client.get("/api/audio/stream")
        self.assertEqual(response.data, b"\0\0")
        response.close()
        self.assertTrue(releases)

    def test_validation_and_path_traversal(self):
        for patch in (
            {"camera": {"rotation": 45}},
            {"camera": {"processing": {"crop": [-1, 0, 1, 1]}}},
            {"network": {"tcp_enabled": True}},
            {"record": {"audio_gain_db": float("nan")}},
            {"web": {"custom_links": [{"url": "javascript:alert(1)"}]}},
        ):
            with self.assertRaises((ValueError, KeyError)):
                validate_patch(patch, self.cfg)
        self.assertEqual(
            self.client.get("/media/stills/../../config.json").status_code, 404
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
