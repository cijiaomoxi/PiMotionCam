"""延时摄影（timelapse）：按周期抓帧存图，结束后合成 MP4。

对应官方 PiKrellCam 的 tl_start / tl_hold / tl_end。
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

from .util import run_command


class Timelapse:
    def __init__(self, config, state, camera, hooks=None, log=None):
        self.config = config
        self.state = state
        self.camera = camera
        self.hooks = hooks
        self.log = log or (lambda *a, **k: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._index = 0
        self._hold = False
        self._running = False
        self._period = 30.0
        self._dir: Path | None = None
        self._session = ""

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict:
        return {
            "running": self._running,
            "hold": self._hold,
            "period": self._period,
            "index": self._index,
            "session": self._session,
        }

    # ------------------------------------------------------------------
    def start(self, period: int | None = None) -> dict:
        with self._lock:
            if self._running:
                return self.status()
            self._period = float(period or self.config.get("timelapse", "period", default=30))
            self._period = max(1.0, self._period)
            self._index = 0
            self._session = time.strftime("%Y%m%d_%H%M%S")
            self._dir = self.config.media_sub("timelapse") / self._session
            self._dir.mkdir(parents=True, exist_ok=True)
            self._hold = False
            self._running = True
            self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="timelapse", daemon=True)
        self._thread.start()
        self.state.update(timelapse_running=True)
        self.log(f"timelapse started: period={self._period}s dir={self._dir}")
        return self.status()

    def hold(self, on: bool = True) -> dict:
        with self._lock:
            self._hold = bool(on)
        self.log(f"timelapse hold={on}")
        return self.status()

    def end(self) -> dict:
        with self._lock:
            if not self._running:
                return self.status()
            self._running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=8)
        self.state.update(timelapse_running=False)
        out = self._convert()
        if self.hooks:
            try:
                self.hooks.fire("on_timelapse_end", {"id": self._session, "video": out})
            except Exception:
                pass
        self.log(f"timelapse ended: {out}")
        return {"ok": True, "video": out}

    # ------------------------------------------------------------------
    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                hold = self._hold
                idx = self._index
                session = self._session
            if not hold:
                frame = self.camera.latest
                if frame:
                    path = self.config.media_sub("timelapse") / session / f"frame_{idx:05d}.jpg"
                    try:
                        path.write_bytes(frame)
                        with self._lock:
                            self._index = idx + 1
                    except Exception:
                        pass
            self._stop.wait(self._period)

    def _convert(self) -> str:
        if not self._dir:
            return ""
        frames = sorted(self._dir.glob("frame_*.jpg"))
        if not frames:
            return ""
        out = self.config.media_sub("videos") / f"timelapse_{self._session}.mp4"
        fps = max(1, int(round(1.0 / max(1.0, self._period))))
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(fps), "-i", str(self._dir / "frame_%05d.jpg"),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ]
        rc, _, err = run_command(" ".join(cmd), timeout=1800)
        if rc != 0:
            self.log(f"timelapse convert failed: {err[:300]}")
            return ""
        shutil.rmtree(self._dir, ignore_errors=True)
        return out.name
