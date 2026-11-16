"""Audio-only MP3 recording using the same capture lease as live listening."""

from __future__ import annotations
import shutil
import os
import select
import subprocess
import threading
import time
from .media_tools import next_name


class AudioRecorder:
    def __init__(self, service):
        self.service = service
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._status = {"recording": False, "file": "", "error": ""}

    def status(self):
        with self._lock:
            return dict(self._status)

    def start(self, seconds=120):
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Audio recording is already running")
            if not shutil.which("ffmpeg"):
                raise RuntimeError("ffmpeg is unavailable")
            seconds = max(1.0, min(3600.0, float(seconds)))
            ok, reason, _ = self.service.config.media_write_target()
            if not ok:
                raise OSError(reason)
            path = self.service.config.media_sub("audio") / next_name(
                self.service.config, "audio", ".mp3"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            capture, release = self.service.acquire_audio("record")
            self._stop.clear()
            self._status = {
                "recording": True,
                "file": path.name,
                "error": "",
                "started_at": time.time(),
            }
            self._thread = threading.Thread(
                target=self._record,
                args=(capture, release, path, seconds),
                daemon=True,
                name="audio-mp3",
            )
            self._thread.start()
            return dict(self._status)

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=8)
        return self.status()

    def _record(self, capture, release, path, seconds):
        proc = None
        error = ""
        samples = 0
        try:
            st = capture.status()
            proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "s16le",
                    "-ar",
                    str(st["rate"]),
                    "-ac",
                    str(st["channels"]),
                    "-i",
                    "-",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "96k",
                    str(path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + seconds
            os.set_blocking(proc.stdin.fileno(), False)
            for chunk in capture.live_pcm(idle_timeout=4):
                if self._stop.is_set() or time.monotonic() >= deadline:
                    break
                available, _, target = self.service.config.media_write_target()
                if not available or target.resolve() != path.parent.parent.resolve():
                    raise OSError("Recording storage is unavailable")
                # Capture and output share the storage guard. Stop before a full disk.
                reserve = (
                    float(self.service.config.get("record", "min_free_gb", default=1))
                    * 1024**3
                )
                if shutil.disk_usage(path.parent).free < reserve:
                    raise OSError("Insufficient free recording space")
                remaining = memoryview(chunk)
                write_deadline = time.monotonic() + 2
                while remaining:
                    if self._stop.is_set():
                        break
                    if time.monotonic() > write_deadline or proc.poll() is not None:
                        raise OSError("Audio encoder stopped accepting samples")
                    if select.select([], [proc.stdin], [], 0.1)[1]:
                        try:
                            written = os.write(proc.stdin.fileno(), remaining)
                            remaining = remaining[written:]
                        except BlockingIOError:
                            continue
                samples += len(chunk)
            proc.stdin.close()
            if proc.wait(timeout=8) != 0 or not samples:
                raise OSError("No microphone samples could be recorded")
        except Exception as exc:
            error = str(exc)
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            path.unlink(missing_ok=True)
        finally:
            release()
            with self._lock:
                self._status.update(recording=False, error=error)
